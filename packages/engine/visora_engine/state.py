from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json

from .schemas import JobState as J, ProjectState as P, SceneState as S

EDGES = {
    P: {P.DRAFT: {P.CONCEPT_READY}, P.CONCEPT_READY: {P.STORYBOARD_CONFIRMED},
        P.STORYBOARD_CONFIRMED: {P.PROCESSING}, P.PROCESSING: {P.COMPLETED, P.FAILED},
        P.COMPLETED: {P.PROCESSING}, P.FAILED: {P.PROCESSING}},
    S: {S.PENDING: {S.KEYFRAME_GENERATING}, S.KEYFRAME_GENERATING: {S.KEYFRAME_READY, S.FAILED},
        S.KEYFRAME_READY: {S.VIDEO_GENERATING}, S.VIDEO_GENERATING: {S.VIDEO_READY, S.FAILED},
        S.VIDEO_READY: {S.VIDEO_GENERATING}, S.FAILED: {S.KEYFRAME_GENERATING, S.VIDEO_GENERATING}},
    J: {J.QUEUED: {J.RUNNING, J.CANCELLED, J.FAILED},
        J.RUNNING: {J.SUCCESS, J.FAILED, J.CANCELLED}},
}


@dataclass
class StateMachine:
    state: Enum
    history: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.history.append(self.state.value)

    def move(self, target: Enum):
        if type(target) is not type(self.state) or target not in EDGES[type(self.state)].get(self.state, set()):
            raise ValueError(f"Illegal transition: {self.state} -> {target}")
        self.state = target
        self.history.append(target.value)


def fingerprint(scene_id: str, model: str, keyframe_url: str, motion_prompt: str,
                params: dict) -> str:
    payload = [scene_id, model, keyframe_url, motion_prompt, params]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


@dataclass
class SceneAssets:
    revision: int = 1
    keyframe: str | None = None
    video: str | None = None
    audio: str | None = None
    subtitles: str | None = None
    video_outdated: bool = False

    def invalidate(self, change: str):
        if change not in {"script", "keyframe", "global", "reroll"}:
            raise ValueError("Unknown change")
        self.revision += 1
        if change in {"script", "global"}:
            self.audio = self.subtitles = None
        if change in {"keyframe", "global"}:
            self.keyframe = None
            self.video_outdated = self.video is not None
        if change == "global":
            self.video = None
            self.video_outdated = False
        if change == "reroll":
            self.video_outdated = self.video is not None
