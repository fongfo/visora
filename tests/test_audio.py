from pathlib import Path

import numpy as np
import pytest

from visora_engine.audio import RATE, duck, make_bgm, measure_ducking, mix, read_wav, write_wav


def test_actual_ffmpeg_ducking_and_recovery(tmp_path: Path):
    key = np.zeros(5 * RATE)
    key[RATE:3*RATE] = 1
    write_wav(tmp_path / "key.wav", key)
    make_bgm(tmp_path / "bgm.wav", 5)
    duck(tmp_path / "bgm.wav", tmp_path / "key.wav", tmp_path / "duck.wav", True)
    metrics = measure_ducking(tmp_path / "bgm.wav", tmp_path / "duck.wav")
    assert len(read_wav(tmp_path / "duck.wav")) == 5 * RATE
    assert np.sqrt(np.mean(read_wav(tmp_path / "duck.wav")[-RATE:] ** 2)) > .01
    assert metrics["passes"], metrics
    assert -16 <= metrics["steady_gain_db"] <= -14


@pytest.mark.parametrize("duration", [1, 5, 15 + 5/30])
def test_silent_scene_keeps_music_level(tmp_path, duration):
    write_wav(tmp_path / "key.wav", np.zeros(round(duration * RATE)))
    make_bgm(tmp_path / "bgm.wav", duration)
    duck(tmp_path / "bgm.wav", tmp_path / "key.wav", tmp_path / "duck.wav", True)
    assert np.max(np.abs(read_wav(tmp_path / "duck.wav") - read_wav(tmp_path / "bgm.wav") * .4)) < 2 / 32767


def test_mix_does_not_clip_or_cut_silent_tail(tmp_path):
    write_wav(tmp_path / "voice.wav", np.zeros(2 * RATE))
    make_bgm(tmp_path / "bgm.wav", 2)
    mix(tmp_path / "voice.wav", tmp_path / "bgm.wav", tmp_path / "mix.wav")
    audio = read_wav(tmp_path / "mix.wav")
    assert len(audio) == 2 * RATE
    assert np.max(np.abs(audio)) < .99
    assert np.sqrt(np.mean(audio[-RATE:] ** 2)) > .01
