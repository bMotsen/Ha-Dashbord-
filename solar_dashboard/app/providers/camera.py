"""Live kamerabilleder: henter videostrømmen (Tuya-skyen eller egen RTSP-adresse) og omsætter den
med ffmpeg til en MJPEG-strøm, som browseren kan vise i et almindeligt <img>-element.
ffmpeg kører kun så længe nogen ser på billedet."""
from __future__ import annotations

import asyncio
import logging
import shutil

LOG = logging.getLogger(__name__)


def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        exe = shutil.which("ffmpeg")
        if not exe:
            raise RuntimeError("ffmpeg mangler")
        return exe


async def mjpeg_stream(source: str, width: int = 480, fps: int = 4, demo: bool = False):
    """Async generator med bytes til en multipart/x-mixed-replace-respons."""
    vf = f"fps={fps},scale={width}:-2"
    if demo:
        cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-re", "-f", "lavfi", "-i",
               f"testsrc2=size=640x360:rate={fps}", "-vf", f"scale={width}:-2", "-q:v", "7", "-f", "mpjpeg", "-boundary_tag", "frame", "-"]
    else:
        pre = ["-rtsp_transport", "tcp"] if source.startswith("rtsp") else []
        cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "warning", "-fflags", "nobuffer", *pre, "-i", source,
               "-an", "-vf", vf, "-q:v", "7", "-f", "mpjpeg", "-boundary_tag", "frame", "-"]
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        got = False
        while True:
            chunk = await asyncio.wait_for(proc.stdout.read(65536), timeout=25)
            if not chunk:
                break
            got = True
            yield chunk
        if not got:
            err = (await proc.stderr.read(600)).decode(errors="ignore").strip().replace("\n", " | ")
            LOG.warning("Kamera: ffmpeg gav intet billede (%s): %s", source.split("?")[0][:60], err)
    except asyncio.TimeoutError:
        LOG.warning("Kamera: ingen billeder i 25 sek – afbryder (%s)", source.split("?")[0][:60])
        try:
            proc.kill()
            err = await asyncio.wait_for(proc.stderr.read(600), 2)
            LOG.warning("Kamera: ffmpeg sagde: %s", err.decode(errors="ignore").strip().replace("\n", " | ")[:500])
        except Exception:  # noqa: BLE001
            pass
    finally:
        if proc.returncode is None:
            proc.kill()
        try:
            await proc.wait()
        except Exception:  # noqa: BLE001
            pass
