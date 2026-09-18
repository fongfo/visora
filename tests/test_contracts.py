import math

import pytest
from pydantic import ValidationError

from visora_engine.director import local_storyboard
from visora_engine.scheduler import BASE_DURATIONS, RewriteRequired, build_timeline
from visora_engine.schemas import StoryboardSchema, TimelineSchema


def board(durations=(2.55, 3.55, 4.05, 3.05)):
    value = local_storyboard()
    for scene, duration in zip(value.scenes, durations):
        scene.actual_audio_duration = duration
    return value


def schedule(value=None, **kwargs):
    return build_timeline(value or board(), [f"scene-{i}.mp4" for i in range(4)],
                          [f"voice-{i}.wav" for i in range(4)], [5.0]*4, **kwargs)


def test_frame_budget_and_overlap():
    timeline = schedule()
    assert timeline.duration == 15
    assert [v.timeline_start for v in timeline.tracks.video_clips] == [0, 3, 7, 11.5]
    assert [v.duration for v in timeline.tracks.video_clips] == [3.3, 4.3, 4.8, 3.5]
    assert sum(v.duration for v in timeline.tracks.video_clips) - .9 == pytest.approx(15)
    assert TimelineSchema.model_validate_json(timeline.model_dump_json()) == timeline


@pytest.mark.parametrize("mutation", ["three_scenes", "duplicates", "landscape", "nan", "extra"])
def test_invalid_storyboard(mutation):
    value = board().model_dump()
    if mutation == "three_scenes": value["scenes"].pop()
    if mutation == "duplicates": value["scenes"][1]["scene_index"] = 1
    if mutation == "landscape": value["target_aspect_ratio"] = "16:9"
    if mutation == "nan": value["scenes"][0]["actual_audio_duration"] = math.nan
    if mutation == "extra": value["unknown"] = True
    with pytest.raises(ValidationError): StoryboardSchema.model_validate(value)


@pytest.mark.parametrize("mutation", ["gap", "overlap", "source", "subtitle", "narration", "fps", "tail_transition", "long"])
def test_invalid_timeline(mutation):
    value = schedule().model_dump()
    clips = value["tracks"]["video_clips"]
    if mutation == "gap": clips[1]["timeline_start"] += .2
    if mutation == "overlap": clips[0]["transition_duration"] = .2
    if mutation == "source": clips[2]["trim_start"] = .5
    if mutation == "subtitle": value["tracks"]["subtitles"][0]["end_time"] = 3.1
    if mutation == "narration": value["tracks"]["voiceover_tracks"][0]["duration"] = 3
    if mutation == "fps": value["canvas"]["fps"] = 24
    if mutation == "tail_transition": clips[3].update(transition_out="dissolve", transition_duration=.3)
    if mutation == "long": clips[3].update(duration=5, source_duration=5)
    with pytest.raises(ValidationError): TimelineSchema.model_validate(value)


def test_small_extension_is_frame_aligned():
    timeline = schedule(board((2.75, 3.55, 4.05, 3.05)))
    assert timeline.duration == pytest.approx(15.2)


def test_large_extension_requires_rewrite():
    with pytest.raises(RewriteRequired): schedule(board((3, 3.4, 3.9, 2.9)))


def test_total_budget_cannot_grow_indefinitely():
    with pytest.raises(RewriteRequired):
        schedule(board(tuple(base - .1 for base in BASE_DURATIONS)))


def test_silent_scenes_keep_baseline():
    value = board()
    for scene in value.scenes:
        scene.voiceover_script = scene.subtitle_text = ""
        scene.actual_audio_duration = 0
    timeline = build_timeline(value, ["v"]*4, [None]*4, [5]*4)
    assert timeline.duration == 15
    assert not timeline.tracks.voiceover_tracks
    assert not timeline.tracks.subtitles


def test_missing_measured_audio_rejected():
    with pytest.raises(ValueError): schedule(local_storyboard())


def test_start_artifact_offset_requires_enough_source():
    with pytest.raises(ValidationError): schedule(trim_start=.5)


def test_all_budget_samples_have_safe_subtitle_boundaries():
    for extra in (0, .05, .1, .2, .3):
        timeline = schedule(board((2.55 + extra, 3.4, 3.9, 2.9)))
        for sub in timeline.tracks.subtitles:
            boundary = timeline.tracks.video_clips[sub.scene_index].timeline_start if sub.scene_index < 4 else timeline.duration
            assert sub.end_time <= boundary - .2


def test_real_short_speech_preserves_breath_bounds():
    timeline = schedule(board((2.424083, 3.083813, 4.198417, 2.724042)))
    assert 14 <= timeline.duration <= 16
    for voice in timeline.tracks.voiceover_tracks:
        boundary = timeline.tracks.video_clips[voice.scene_index].timeline_start if voice.scene_index < 4 else timeline.duration
        assert .2 <= boundary - voice.timeline_start - voice.duration <= .4


def test_very_short_narration_requires_expansion():
    with pytest.raises(RewriteRequired, match="expand"):
        schedule(board((1, 1, 1, 1)))
