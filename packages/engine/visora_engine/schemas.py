from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ProductMetadata(Contract):
    name: str = Field(min_length=1)
    brand: str | None = None
    selling_points: list[str]
    isolated_image_url: str = Field(min_length=1)


class StoryboardScene(Contract):
    scene_index: int = Field(ge=1, le=4)
    shot_type: str
    camera_motion: str
    lighting_style: str
    keyframe_prompt: str
    motion_prompt: str
    voiceover_script: str
    subtitle_text: str
    planned_duration: float = Field(gt=0, le=16)
    actual_audio_duration: float | None = Field(default=None, ge=0, le=360)


class StoryboardSchema(Contract):
    schema_version: Literal[1] = 1
    concept_title: str = Field(min_length=1)
    target_aspect_ratio: Literal["9:16"] = "9:16"
    total_target_duration: Literal[15.0] = 15.0
    language: Literal["en", "zh"] = "en"
    product_metadata: ProductMetadata
    scenes: list[StoryboardScene] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def ordered_scenes(self):
        if [s.scene_index for s in self.scenes] != [1, 2, 3, 4]:
            raise ValueError("Exactly four ordered, unique scenes are required")
        return self


class Canvas(Contract):
    width: Literal[1080] = 1080
    height: Literal[1920] = 1920
    fps: Literal[30] = 30
    pixel_format: Literal["yuv420p"] = "yuv420p"


class VideoClip(Contract):
    scene_index: int = Field(ge=1, le=4)
    source_url: str = Field(min_length=1)
    timeline_start: float = Field(ge=0)
    duration: float = Field(gt=0)
    source_duration: float = Field(gt=0)
    trim_start: float = Field(default=0, ge=0)
    transition_out: Literal["dissolve"] | None = None
    transition_duration: float = Field(default=0, ge=0, le=0.3)

    @model_validator(mode="after")
    def available_media(self):
        if self.trim_start + self.duration > self.source_duration + 1e-6:
            raise ValueError("Insufficient source media for trim")
        if (self.transition_out is None) != (self.transition_duration == 0):
            raise ValueError("Transition type and duration must agree")
        return self


class VoiceoverTrack(Contract):
    scene_index: int = Field(ge=1, le=4)
    audio_url: str
    timeline_start: float = Field(ge=0)
    duration: float = Field(gt=0)


class DuckingSettings(Contract):
    mode: Literal["narration_envelope"] = "narration_envelope"
    target_db: Literal[-15.0] = -15.0
    attack_ms: Literal[50] = 50
    release_ms: Literal[300] = 300


class BackgroundMusic(Contract):
    audio_url: str
    volume: float = Field(default=0.4, ge=0, le=1)
    ducking: DuckingSettings = Field(default_factory=DuckingSettings)


class Subtitle(Contract):
    scene_index: int = Field(ge=1, le=4)
    text: str = Field(min_length=1)
    start_time: float = Field(ge=0)
    end_time: float = Field(gt=0)
    style: Literal["minimal_modern", "bold_impact"] = "minimal_modern"


class Overlay(Contract):
    type: Literal["logo", "cta_button"]
    asset_url: str
    x: int = Field(ge=0, lt=1080)
    y: int = Field(ge=0, lt=1920)
    start_time: float = Field(ge=0)
    duration: float = Field(gt=0)


class Tracks(Contract):
    video_clips: list[VideoClip] = Field(min_length=4, max_length=4)
    voiceover_tracks: list[VoiceoverTrack] = Field(default_factory=list)
    background_music: BackgroundMusic | None = None
    subtitles: list[Subtitle] = Field(default_factory=list)
    overlays: list[Overlay] = Field(default_factory=list)


class TimelineSchema(Contract):
    schema_version: Literal[1] = 1
    canvas: Canvas = Field(default_factory=Canvas)
    tracks: Tracks

    @property
    def duration(self) -> float:
        last = self.tracks.video_clips[-1]
        return last.timeline_start + last.duration

    @model_validator(mode="after")
    def coherent_timeline(self):
        clips = self.tracks.video_clips
        if [c.scene_index for c in clips] != [1, 2, 3, 4]:
            raise ValueError("Timeline requires four ordered scenes")
        expected = 0.0
        for i, clip in enumerate(clips):
            if abs(clip.timeline_start - expected) > 1e-6:
                raise ValueError("Timeline has gap or incorrect transition overlap")
            if abs(clip.duration * 30 - round(clip.duration * 30)) > 1e-5:
                raise ValueError("Clip durations must align to 30 fps frames")
            if i < 3 and clip.transition_duration != 0.3:
                raise ValueError("MVP requires 0.3s dissolve transitions")
            if i == 3 and clip.transition_out is not None:
                raise ValueError("Final clip cannot transition to absent media")
            expected += clip.duration - clip.transition_duration
        if not 14 <= self.duration <= 16:
            raise ValueError("Final duration must be 14-16 seconds")
        voices = self.tracks.voiceover_tracks
        if len({v.scene_index for v in voices}) != len(voices):
            raise ValueError("Only one narration track per scene")
        for voice in voices:
            clip = clips[voice.scene_index - 1]
            boundary = clips[voice.scene_index].timeline_start if voice.scene_index < 4 else self.duration
            if abs(voice.timeline_start - clip.timeline_start - 0.15) > 1e-6:
                raise ValueError("Narration starts 0.15s after scene onset")
            if voice.timeline_start + voice.duration > boundary - 0.2 + 1e-6:
                raise ValueError("Narration crosses scene breath boundary")
            if boundary - voice.timeline_start - voice.duration > 0.4 + 1e-6:
                raise ValueError("Narration breath tail exceeds 0.4s")
        for sub in self.tracks.subtitles:
            clip = clips[sub.scene_index - 1]
            boundary = clips[sub.scene_index].timeline_start if sub.scene_index < 4 else self.duration
            if sub.start_time < clip.timeline_start or not sub.start_time < sub.end_time <= boundary - 0.2 + 1e-6:
                raise ValueError("Subtitle crosses scene boundary or has invalid interval")
        for overlay in self.tracks.overlays:
            if overlay.start_time + overlay.duration > self.duration + 1e-6:
                raise ValueError("Overlay exceeds timeline")
        return self


class ProjectState(str, Enum):
    DRAFT = "DRAFT"
    CONCEPT_READY = "CONCEPT_READY"
    STORYBOARD_CONFIRMED = "STORYBOARD_CONFIRMED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class SceneState(str, Enum):
    PENDING = "PENDING"
    KEYFRAME_GENERATING = "KEYFRAME_GENERATING"
    KEYFRAME_READY = "KEYFRAME_READY"
    VIDEO_GENERATING = "VIDEO_GENERATING"
    VIDEO_READY = "VIDEO_READY"
    FAILED = "FAILED"


class JobState(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
