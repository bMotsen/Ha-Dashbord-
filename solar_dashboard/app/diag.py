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
