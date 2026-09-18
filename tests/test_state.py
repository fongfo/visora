import pytest

from visora_engine.schemas import JobState, ProjectState, SceneState
from visora_engine.state import SceneAssets, StateMachine, fingerprint


@pytest.mark.parametrize("kind,sequence", [
    (JobState, ["QUEUED", "RUNNING", "SUCCESS"]),
    (ProjectState, ["DRAFT", "CONCEPT_READY", "STORYBOARD_CONFIRMED", "PROCESSING", "COMPLETED", "PROCESSING", "COMPLETED"]),
    (SceneState, ["PENDING", "KEYFRAME_GENERATING", "KEYFRAME_READY", "VIDEO_GENERATING", "VIDEO_READY", "VIDEO_GENERATING", "VIDEO_READY"]),
])
def test_complete_generation_and_reroll_paths(kind, sequence):
    machine = StateMachine(kind(sequence[0]))
    for state in sequence[1:]: machine.move(kind(state))
    assert machine.history == sequence


@pytest.mark.parametrize("source,target", [
    (ProjectState.DRAFT, ProjectState.PROCESSING),
    (ProjectState.STORYBOARD_CONFIRMED, ProjectState.COMPLETED),
    (SceneState.PENDING, SceneState.VIDEO_GENERATING),
    (SceneState.KEYFRAME_READY, SceneState.VIDEO_READY),
    (JobState.QUEUED, JobState.SUCCESS),
])
def test_cannot_skip_confirmation_or_generation(source, target):
    with pytest.raises(ValueError): StateMachine(source).move(target)


@pytest.mark.parametrize("terminal", [JobState.SUCCESS, JobState.FAILED, JobState.CANCELLED])
def test_terminal_job_cannot_accept_late_completion(terminal):
    with pytest.raises(ValueError): StateMachine(terminal).move(JobState.SUCCESS)


def test_fingerprint_canonical_and_parameter_sensitive():
    args = ("scene-1", "mock-v1", "keyframe", "motion")
    assert fingerprint(*args, {"a": 1, "b": 2}) == fingerprint(*args, {"b": 2, "a": 1})
    for field in ("seed", "revision", "duration", "model_version"):
        assert fingerprint(*args, {}) != fingerprint(*args, {field: 1})


@pytest.mark.parametrize("change", ["script", "keyframe", "global", "reroll"])
def test_cascading_invalidation(change):
    asset = SceneAssets(keyframe="k", video="v", audio="a", subtitles="s")
    asset.invalidate(change)
    assert asset.revision == 2
    if change == "script":
        assert asset.keyframe == "k" and asset.video == "v" and asset.audio is None and asset.subtitles is None
    elif change == "keyframe":
        assert asset.keyframe is None and asset.video == "v" and asset.video_outdated and asset.audio == "a"
    elif change == "global":
        assert asset.keyframe is asset.video is asset.audio is asset.subtitles is None
    else:
        assert asset.keyframe == "k" and asset.audio == "a" and asset.video == "v" and asset.video_outdated
