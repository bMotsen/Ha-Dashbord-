"""Netværkstest af et kamera: hvilke porte er åbne, og svarer de på RTSP?"""
from __future__ import annotations

import asyncio

PORTS = [554, 10554, 8554, 5543, 7447, 80, 8080, 8000, 8899, 5000, 6668, 34567, 9000, 443]
PATHS = ["/tcp/av0_0", "/udp/av0_0", "/live/ch0", "/live/ch00_0", "/stream1", "/h264", "/11", "/ch0_0.h264", "/onvif1", "/"]


async def _open(ip: str, port: int) -> bool:
    try:
        r, w = await asyncio.wait_for(asyncio.open_connection(ip, port), 1.5)
        w.close()
        return True
    except Exception:  # noqa: BLE001
        return False


async def _describe(ip: str, port: int, path: str) -> str | None:
    try:
        r, w = await asyncio.wait_for(asyncio.open_connection(ip, port), 2)
        w.write(f"DESCRIBE rtsp://{ip}:{port}{path} RTSP/1.0\r\nCSeq: 1\r\nAccept: application/sdp\r\n\r\n".encode())
        await w.drain()
        data = await asyncio.wait_for(r.read(200), 2.5)
        w.close()
        line = data.decode(errors="ignore").split("\r\n")[0]
        return line if line.startswith("RTSP/") else None
    except Exception:  # noqa: BLE001
        return None


async def scan(ip: str) -> dict:
    opened = [p for p, ok in zip(PORTS, await asyncio.gather(*[_open(ip, p) for p in PORTS])) if ok]
    rtsp = []
    for port in opened:
        for path in PATHS:
            line = await _describe(ip, port, path)
            if line:
                rtsp.append({"port": port, "path": path, "svar": line})
                if "200" in line or "401" in line:
                    break
    good = [r for r in rtsp if " 200 " in r["svar"] or " 401 " in r["svar"]]
    if good:
        g = good[0]
        verdict = (f"Kameraet taler RTSP. Prøv: rtsp://{ip}:{g['port']}{g['path']}" +
                   (" (kræver brugernavn og kode)" if " 401 " in g["svar"] else " (ingen kode nødvendig)"))
    elif rtsp:
        verdict = "Der er en RTSP-server, men ingen af de kendte stier passede."
    elif opened:
        verdict = "Kameraet svarer på nogle porte, men ikke på RTSP. RTSP er sandsynligvis slået fra."
    else:
        verdict = "Ingen åbne porte fundet. Er IP-adressen rigtig, og er kameraet tændt og på samme netværk?"
    return {"ip": ip, "aabne_porte": opened, "rtsp_svar": rtsp, "konklusion": verdict}


LOGIN_PATHS = ["/Streaming/Channels/101", "/Streaming/Channels/102", "/stream1", "/stream0", "/live/ch0", "/live", "/h264/ch1/main/av_stream",
               "/cam/realmonitor?channel=1&subtype=0", "/onvif1", "/ch0_0.h264", "/11", "/tcp/av0_0", "/av0_0", "/"]
LOGIN_PORTS = [8554, 554, 10554, 5543]


async def _try_url(url: str) -> bool:
    from .providers.camera import ffmpeg_exe

    try:
        proc = await asyncio.create_subprocess_exec(
            ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-rtsp_transport", "tcp", "-t", "2", "-i", url,
            "-frames:v", "1", "-f", "null", "-", stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        try:
            await asyncio.wait_for(proc.wait(), 9)
        except asyncio.TimeoutError:
            proc.kill()
            return False
        return proc.returncode == 0
    except Exception:  # noqa: BLE001
        return False


async def find_stream(ip: str, user: str, password: str) -> dict:
    """Prøv de almindeligste RTSP-adresser med brugernavn og kode - ffmpeg afgør hvad der virker."""
    from urllib.parse import quote

    open_ports = [p for p, ok in zip(LOGIN_PORTS, await asyncio.gather(*[_open(ip, p) for p in LOGIN_PORTS])) if ok]
    if not open_ports:
        return {"ok": False, "fejl": f"Ingen RTSP-port åben på {ip} (prøvet {LOGIN_PORTS}). Er ONVIF slået til, og er IP'en rigtig?"}
    cred = f"{quote(user, safe='')}:{quote(password, safe='')}@"
    sem = asyncio.Semaphore(4)

    async def one(port, path):
        async with sem:
            url = f"rtsp://{cred}{ip}:{port}{path}"
            return url if await _try_url(url) else None

    results = await asyncio.gather(*[one(p, path) for p in open_ports for path in LOGIN_PATHS])
    good = [u for u in results if u]
    if good:
        return {"ok": True, "url": good[0], "porte": open_ports}
    return {"ok": False, "fejl": "RTSP-porten svarer, men ingen af de kendte adresser virkede med dette brugernavn/kode", "porte": open_ports}


async def probe_url(url: str, seconds: int = 14) -> dict:
    """Prøv at åbne en videoadresse med ffmpeg og fortæl hvad der skete (uden at afsløre adressens nøgler)."""
    from urllib.parse import urlsplit

    from .providers.camera import ffmpeg_exe

    parts = urlsplit(url)
    info = {"type": parts.scheme, "vaert": parts.hostname, "sti": parts.path[-40:]}
    try:
        pre = ["-rtsp_transport", "tcp"] if url.startswith("rtsp") else []
        proc = await asyncio.create_subprocess_exec(
            ffmpeg_exe(), "-hide_banner", "-loglevel", "warning", *pre, "-i", url, "-t", "3", "-frames:v", "2", "-f", "null", "-",
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        try:
            _, err = await asyncio.wait_for(proc.communicate(), seconds)
            info["ok"] = proc.returncode == 0
            info["ffmpeg"] = err.decode(errors="ignore").strip().replace(url, "<adresse>")[-500:]
        except asyncio.TimeoutError:
            proc.kill()
            info["ok"] = False
            info["ffmpeg"] = f"ingen billeder efter {seconds} sek (tidsgrænse)"
    except Exception as err:  # noqa: BLE001
        info["ok"] = False
        info["ffmpeg"] = f"kunne ikke starte ffmpeg: {err}"
    return info


async def probe_dashboard_stream(url: str, seconds: int = 20) -> dict:
    """Kør præcis den samme omsætning som dashboardet bruger, og tæl billeder."""
    from .providers.camera import mjpeg_stream

    got, first = 0, None
    t0 = asyncio.get_event_loop().time()
    gen = mjpeg_stream(url, 480, 4)
    try:
        async def run():
            nonlocal got, first
            async for chunk in gen:
                if first is None:
                    first = round(asyncio.get_event_loop().time() - t0, 1)
                got += chunk.count(b"\xff\xd8")
                if got >= 3:
                    return
        await asyncio.wait_for(run(), seconds)
    except asyncio.TimeoutError:
        pass
    finally:
        await gen.aclose()
    return {"billeder_modtaget": got, "foerste_billede_efter_sek": first, "virker": got > 0}
