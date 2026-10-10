import json
import os
from pathlib import Path
import shutil
import subprocess
import wave

import imageio_ffmpeg


def ffmpeg() -> str:
    return os.environ.get("FFMPEG_BINARY") or shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()


def run_ffmpeg(args: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run([ffmpeg(), "-hide_banner", "-y", "-nostdin", *map(str, args)],
                            capture_output=True, text=True, cwd=cwd, timeout=360)
    if result.returncode:
        raise RuntimeError(result.stderr[-6000:])
    return result.stderr


def wav_duration(path: str | Path) -> float:
    with wave.open(str(path), "rb") as audio:
        return audio.getnframes() / audio.getframerate()


def probe(path: str | Path) -> dict:
    binary = os.environ.get("FFPROBE_BINARY") or shutil.which("ffprobe")
    if not binary:
        sibling = Path(ffmpeg()).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
        if sibling.exists():
            binary = str(sibling)
    if not binary:
        raise RuntimeError("Install ffprobe or set FFPROBE_BINARY for acceptance verification")
    result = subprocess.run([binary, "-v", "error", "-count_frames", "-show_streams",
                             "-show_format", "-of", "json", str(path)],
                            check=True, capture_output=True, text=True, timeout=120)
    return json.loads(result.stdout)


def font_file() -> Path:
    candidates = [os.environ.get("VISORA_FONT", ""), "C:/Windows/Fonts/arial.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise RuntimeError("Set VISORA_FONT to a TrueType font")


def prepare_font(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(font_file(), directory / "font.ttf")
