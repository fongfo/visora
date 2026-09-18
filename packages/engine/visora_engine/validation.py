import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import numpy as np

from .audio import (RATE, duck, make_bgm, measure_ducking, mix, read_wav, write_wav,
                    SPEC_COMPRESSOR, CALIBRATED_COMPRESSOR)
from .director import local_storyboard
from .media import ffmpeg, probe, run_ffmpeg, wav_duration
from .pipeline import LocalPipeline
from .providers import MockImageProvider, MockVideoProvider
from .schemas import StoryboardSchema, TimelineSchema


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def configure_probe(root):
    if not os.environ.get("FFPROBE_BINARY") and not shutil.which("ffprobe"):
        candidates = list((root / ".tools").glob("**/ffprobe.exe"))
        if candidates:
            os.environ["FFPROBE_BINARY"] = str(candidates[0])


def verify_video(path: Path, expected_duration: float) -> dict:
    metadata = probe(path)
    video = next(s for s in metadata["streams"] if s["codec_type"] == "video")
    audio = next((s for s in metadata["streams"] if s["codec_type"] == "audio"), None)
    frames = int(video["nb_read_frames"])
    duration = float(metadata["format"]["duration"])
    passed = (video["width"] == 1080 and video["height"] == 1920
              and video["pix_fmt"] == "yuv420p" and video["r_frame_rate"] == "30/1"
              and frames == round(expected_duration * 30)
              and abs(duration - expected_duration) < .08 and audio is not None)
    # Fully decode as a separate corruption check.
    run_ffmpeg(["-v", "error", "-xerror", "-i", path, "-f", "null", "-"])
    return {"passed": passed, "duration": duration, "frames": frames,
            "width": video["width"], "height": video["height"], "fps": video["r_frame_rate"],
            "pixel_format": video["pix_fmt"], "audio_codec": audio["codec_name"] if audio else None}


async def validate(root: Path, output: Path, speech_dir: Path | None):
    configure_probe(root)
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text('{"passed": false, "status": "running_or_interrupted"}', encoding="utf-8")
    if speech_dir is None:
        if os.name != "nt":
            raise RuntimeError("Use --speech-dir with speech-raw-1.wav through speech-raw-4.wav")
        speech_dir = output
        subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                        str(root / "scripts/local_speech.ps1"), "-OutputDirectory", str(output)],
                       check=True, capture_output=True, text=True, timeout=60)
    storyboard = local_storyboard()
    provider = MockVideoProvider(output / "clips")
    pipeline = LocalPipeline(storyboard, MockImageProvider(output / "keyframes"), provider, output)
    for i, scene in enumerate(storyboard.scenes):
        target = output / f"speech-{i+1}.wav"
        run_ffmpeg(["-i", speech_dir / f"speech-raw-{i+1}.wav", "-ar", str(RATE), "-ac", "1",
                    "-c:a", "pcm_s16le", target])
        measured = float(probe(target)["format"]["duration"])
        if abs(measured - wav_duration(target)) > .001:
            raise RuntimeError("ffprobe and PCM duration disagree")
        scene.actual_audio_duration = wav_duration(target)
        pipeline.assets[i].audio = str(target)
    (output / "storyboard.json").write_text(storyboard.model_dump_json(indent=2), encoding="utf-8")
    for name, model in (("storyboard", StoryboardSchema), ("timeline", TimelineSchema)):
        (output / f"{name}.schema.json").write_text(json.dumps(model.model_json_schema(), indent=2), encoding="utf-8")
    pipeline.confirm_storyboard()
    await pipeline.prepare_keyframes()
    pipeline.confirm_keyframes()
    await pipeline.generate()
    timeline = pipeline.render()
    original = [a.video for a in pipeline.assets]
    original_hashes = [digest(a.video) for a in pipeline.assets]
    await pipeline.reroll(2)
    preserved = all(pipeline.assets[i].video == original[i] and digest(original[i]) == original_hashes[i]
                    for i in (0, 2, 3))
    reroll_passed = preserved and pipeline.assets[1].video != original[1] and provider.submissions == 5 and pipeline.render_count == 2
    # Measurable gate test: known 1.0-amplitude key, active during [1s, 3s].
    signal = np.zeros(5 * RATE)
    signal[RATE:3*RATE] = 1
    write_wav(output / "test-key.wav", signal)
    make_bgm(output / "test-bgm.wav", 5)
    metrics = {}
    for name, calibrated in (("spec", False), ("calibrated", True)):
        duck(output / "test-bgm.wav", output / "test-key.wav", output / f"test-{name}.wav", calibrated)
        metrics[name] = measure_ducking(output / "test-bgm.wav", output / f"test-{name}.wav")
    # Direct application of section 8 to real offline speech, retained for A/B listening.
    duck(output / "bgm.wav", output / "voice.wav", output / "speech-spec-ducked.wav", False)
    mix(output / "voice.wav", output / "speech-spec-ducked.wav", output / "speech-spec-mix.wav")
    peak = float(np.max(np.abs(read_wav(output / "mixed.wav"))))
    report = {"paid_api_calls": 0, "speech_source": "Windows offline speech or supplied local WAV",
              "ffmpeg": subprocess.check_output([ffmpeg(), "-version"], text=True).splitlines()[0],
              "final": verify_video(output / "final.mp4", timeline.duration),
              "rerolled": verify_video(output / "rerolled.mp4", timeline.duration),
              "reroll_preserves_other_scenes": reroll_passed, "provider_submissions": provider.submissions,
              "project_history": pipeline.project.history,
              "scene_histories": [s.history for s in pipeline.scenes],
              "jobs": [{"id": j.id, "history": j.machine.history} for j in pipeline.runner.jobs.values()],
              "audio_durations": [s.actual_audio_duration for s in storyboard.scenes],
              "breath_tails": [(timeline.tracks.video_clips[v.scene_index].timeline_start if v.scene_index < 4 else timeline.duration)
                               - v.timeline_start - v.duration for v in timeline.tracks.voiceover_tracks],
              "ducking": metrics, "spec_filter": SPEC_COMPRESSOR,
              "calibrated_filter": CALIBRATED_COMPRESSOR, "mixed_peak": peak,
              "listening_review": "Manual listening still required; metrics do not establish subjective naturalness"}
    report["passed"] = all([report["final"]["passed"], report["rerolled"]["passed"], reroll_passed,
                            metrics["calibrated"]["passes"], peak < .99])
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in {"ducking", "jobs", "scene_histories"}}, indent=2))
    if not report["passed"]:
        raise RuntimeError(f"Local acceptance failed; inspect {output / 'report.json'}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("artifacts/local-validation"))
    parser.add_argument("--speech-dir", type=Path)
    args = parser.parse_args()
    asyncio.run(validate(Path.cwd(), args.output.resolve(), args.speech_dir.resolve() if args.speech_dir else None))


if __name__ == "__main__":
    main()
