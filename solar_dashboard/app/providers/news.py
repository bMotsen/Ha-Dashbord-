"""Seneste nyheder (DR + Nordjyske) til rulleteksten.

For hver kilde prøves flere adresser: kendte RSS-feeds, RSS-link fundet på siden (autodiscovery),
og til sidst overskrifter læst direkte fra sidens HTML. Det der virker, bruges.
Egne feeds kan sættes i config under news.sources.
"""
from __future__ import annotations

import html
import logging
import re
import threading
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse

import httpx

from ..store import Store, iso, utcnow

LOG = logging.getLogger(__name__)

DEFAULT_SOURCES = [
    {"name": "DR", "feeds": ["https://www.dr.dk/nyheder/service/feeds/allenyheder",
                             "https://www.dr.dk/nyheder/service/feeds/regionale/nordjylland"],
     "pages": ["https://www.dr.dk/nyheder"], "limit": 8},
    {"name": "Nordjyske", "feeds": ["https://nordjyske.dk/rss", "https://nordjyske.dk/rss/nyheder",
                                    "https://nordjyske.dk/rss/aalborg"],
     "pages": ["https://nordjyske.dk/nyheder/aalborg", "https://nordjyske.dk/nyheder"], "limit": 12,
     "html_path": "/nyheder/"},
]
UA = "Mozilla/5.0 (compatible; solar-dashboard/1.0)"


def _clean(t: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", t or ""))).strip()


def parse_feed(xml_text: str, limit: int) -> list[dict]:
    root = ET.fromstring(xml_text.encode("utf-8", errors="ignore") if isinstance(xml_text, str) else xml_text)
    items = []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for it in list(root.iter("item")) + list(root.iter("{http://www.w3.org/2005/Atom}entry")):
        title = _clean((it.findtext("title") or it.findtext("a:title", namespaces=ns)))
        link = (it.findtext("link") or "").strip()
        if not link:
            el = it.find("a:link", ns)
            link = (el.get("href") if el is not None else "") or ""
        date = it.findtext("pubDate") or it.findtext("a:updated", namespaces=ns) or it.findtext("a:published", namespaces=ns)
        ts = None
        if date:
            try:
                ts = parsedate_to_datetime(date)
            except Exception:  # noqa: BLE001
                try:
                    ts = datetime.fromisoformat(date.replace("Z", "+00:00"))
                except Exception:  # noqa: BLE001
                    ts = None
        if title and link:
            items.append({"title": title, "url": link.strip(), "ts": ts.timestamp() if ts else 0})
    items.sort(key=lambda x: x["ts"], reverse=True)
    return items[:limit]


def parse_html(page: str, base: str, path_hint: str, limit: int) -> list[dict]:
    """Reserve: overskrifter fra <a>-links til artikler."""
    out, seen = [], set()
    host = urlparse(base).netloc
    for m in re.finditer(r'<a\b[^>]*href="([^"#]+)"[^>]*>(.*?)</a>', page, re.S | re.I):
        href, inner = m.group(1), m.group(2)
        url = urljoin(base, href)
        if urlparse(url).netloc != host or path_hint not in url:
            continue
        title = _clean(inner)
        if len(title) < 28 or len(title) > 200 or url in seen or title in seen:
            continue
        seen.add(url); seen.add(title)
        out.append({"title": title, "url": url, "ts": 0})
        if len(out) >= limit:
            break
    return out


class NewsProvider(threading.Thread):
    def __init__(self, cfg: dict, store: Store) -> None:
        super().__init__(name="news", daemon=True)
        self.cfg = cfg
        self.store = store
        self.http = httpx.Client(timeout=15.0, follow_redirects=True, headers={"User-Agent": UA})
        self._stop = threading.Event()
        self.working: dict[str, str] = {}

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        every = max(int(self.cfg.get("refresh_minutes") or 10), 3) * 60
        while not self._stop.is_set():
            try:
                self.store.set("news", self.fetch_all())
            except Exception as err:  # noqa: BLE001
                LOG.warning("Nyheder: %s", err)
            self._stop.wait(every)

    def _fetch_source(self, src: dict) -> list[dict]:
        name, limit = src["name"], int(src.get("limit") or 10)
        tried = []
        if name in self.working:  # brug det der virkede sidst først
            tried.append(self.working[name])
        tried += [u for u in src.get("feeds", []) if u not in tried]
        for url in tried:
            try:
                r = self.http.get(url)
                if r.status_code == 200 and ("<rss" in r.text[:2000] or "<feed" in r.text[:2000] or "<item" in r.text[:4000]):
                    items = parse_feed(r.text, limit)
                    if items:
                        self.working[name] = url
                        return items
            except Exception as err:  # noqa: BLE001
                LOG.debug("Nyheder: %s fejlede: %s", url, err)
        for page in src.get("pages", []):
            try:
                r = self.http.get(page)
                if r.status_code != 200:
                    continue
                for m in re.finditer(r'<link[^>]+type="application/(?:rss|atom)\+xml"[^>]*>', r.text, re.I):
                    h = re.search(r'href="([^"]+)"', m.group(0))
                    if h:
                        feed = urljoin(page, h.group(1))
                        rr = self.http.get(feed)
                        if rr.status_code == 200:
                            items = parse_feed(rr.text, limit)
                            if items:
                                self.working[name] = feed
                                LOG.info("Nyheder: fandt feed for %s: %s", name, feed)
                                return items
                items = parse_html(r.text, page, src.get("html_path", "/"), limit)
                if items:
                    LOG.info("Nyheder: %s læses fra siden %s (ingen RSS fundet)", name, page)
                    return items
            except Exception as err:  # noqa: BLE001
                LOG.debug("Nyheder: %s fejlede: %s", page, err)
        raise RuntimeError(f"ingen nyheder fundet for {name}")

    def fetch_all(self) -> dict:
        sources = self.cfg.get("sources") or DEFAULT_SOURCES
        merged, errors = [], []
        for src in sources:
            try:
                for it in self._fetch_source(src):
                    it["src"] = src["name"]
                    merged.append(it)
            except Exception as err:  # noqa: BLE001
                errors.append(str(err))
                LOG.warning("Nyheder: %s", err)
        # skift mellem kilderne så begge vises, nyeste først i hver
        by_src: dict[str, list] = {}
        for it in merged:
            by_src.setdefault(it["src"], []).append(it)
        mixed = []
        while any(by_src.values()):
            for k in list(by_src):
                if by_src[k]:
                    mixed.append(by_src[k].pop(0))
        return {"ok": bool(mixed), "demo": False, "items": mixed, "error": "; ".join(errors) or None, "updated": iso(utcnow())}


def demo_news() -> dict:
    items = [
        {"src": "DR", "title": "Demo: Her vises de seneste nyheder fra DR", "url": "https://www.dr.dk/nyheder"},
        {"src": "Nordjyske", "title": "Demo: Og de seneste lokale nyheder fra Aalborg og omegn", "url": "https://nordjyske.dk"},
        {"src": "DR", "title": "Demo: Tryk på en overskrift for at læse hele artiklen", "url": "https://www.dr.dk/nyheder"},
        {"src": "Nordjyske", "title": "Demo: Nyhederne opdateres automatisk hvert 10. minut", "url": "https://nordjyske.dk"},
    ]
    return {"ok": True, "demo": True, "items": items}
