from pathlib import Path
import wave

import numpy as np

from .media import run_ffmpeg

RATE = 48000
SPEC_COMPRESSOR = "sidechaincompress=threshold=0.12:ratio=4:attack=50:release=300"
# A constant-amplitude narration envelope makes gain independent of speaker loudness.
CALIBRATED_COMPRESSOR = "sidechaincompress=threshold=0.1:ratio=4:knee=1:attack=50:release=300:detection=peak"


def write_wav(path: Path, data: np.ndarray):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes((np.clip(data, -1, 1) * 32767).astype("<i2").tobytes())


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as audio:
        if audio.getframerate() != RATE or audio.getnchannels() != 1 or audio.getsampwidth() != 2:
            raise ValueError("Expected 48kHz mono PCM16 WAV")
        return np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2").astype(float) / 32767


def make_bgm(path: Path, duration: float):
    t = np.arange(round(duration * RATE)) / RATE
    chord = sum(np.sin(2 * np.pi * f * t) for f in (220, 277.18, 329.63)) / 3
    pulse = 0.75 + 0.25 * np.sin(2 * np.pi * 1.5 * t) ** 2
    write_wav(path, 0.3 * chord * pulse)


def assemble_voice(timeline, path: Path, envelope_path: Path):
    result = np.zeros(round(timeline.duration * RATE))
    envelope = np.zeros_like(result)
    for track in timeline.tracks.voiceover_tracks:
        samples = read_wav(Path(track.audio_url))
        if abs(len(samples) / RATE - track.duration) > 1 / RATE:
            raise ValueError("Measured narration does not match timeline")
        start = round(track.timeline_start * RATE)
        end = start + len(samples)
        if end > len(result):
            raise ValueError("Narration exceeds output duration")
        result[start:end] += samples
        envelope[start:end] = 1
    write_wav(path, result)
    write_wav(envelope_path, envelope)


def duck(bgm: Path, key: Path, output: Path, calibrated: bool):
    compressor = CALIBRATED_COMPRESSOR if calibrated else SPEC_COMPRESSOR
    duration = len(read_wav(bgm)) / RATE
    # Equal audio blocks and explicit output duration avoid framesync EOF truncation.
    run_ffmpeg(["-i", bgm, "-i", key, "-filter_complex_threads", "1", "-filter_complex",
                f"[0:a]volume=0.4,apad,asetnsamples=n=1024:p=0[b];"
                f"[1:a]apad,asetnsamples=n=1024:p=0[key];[b][key]{compressor}[out]",
                "-map", "[out]", "-t", str(duration), "-c:a", "pcm_s16le", output])
    if len(read_wav(output)) != len(read_wav(bgm)):
        raise RuntimeError("Sidechain processing truncated the background music")


def mix(voice: Path, ducked: Path, output: Path):
    # normalize=0 avoids amix's default 6dB attenuation of two tracks.
    run_ffmpeg(["-i", voice, "-i", ducked, "-filter_complex",
                "[0:a][1:a]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.95:level=0:latency=1[out]",
                "-map", "[out]", "-c:a", "pcm_s16le", output])


def measure_ducking(reference: Path, result: Path, onset=1.0, offset=3.0) -> dict:
    source, rendered = read_wav(reference) * 0.4, read_wav(result)
    if len(source) != len(rendered):
        raise ValueError("Cannot accept ducking metrics from a truncated track")
    def gain(start, end):
        a, b = round(start * RATE), round(end * RATE)
        return float(20 * np.log10(max(np.sqrt(np.mean(rendered[a:b] ** 2)), 1e-9)
                                  / max(np.sqrt(np.mean(source[a:b] ** 2)), 1e-9)))
    windows = [{"after_offset_ms": ms, "gain_db": round(gain(offset + ms / 1000, offset + ms / 1000 + .02), 3)}
               for ms in range(0, 501, 10)]
    recovery = next((x["after_offset_ms"] for x in windows if x["gain_db"] >= -1), None)
    attenuation = gain(onset + .5, offset - .2)
    return {"steady_gain_db": round(attenuation, 3), "recovery_to_minus_1db_ms": recovery,
            "passes": abs(attenuation + 15) <= 1 and recovery is not None and recovery <= 300,
            "recovery_curve": windows}
