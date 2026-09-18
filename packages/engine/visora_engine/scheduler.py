import math

from .schemas import StoryboardSchema, TimelineSchema

BASE_DURATIONS = (3.0, 4.0, 4.5, 3.5)


class RewriteRequired(ValueError):
    """Ask the director to rewrite and regenerate TTS; never stretch narration."""

    def __init__(self, message: str, action: str = "condense"):
        self.action = action
        super().__init__(message)


def build_timeline(storyboard: StoryboardSchema, videos: list[str],
                   audio: list[str | None], source_durations: list[float],
                   trim_start: float = 0) -> TimelineSchema:
    storyboard = StoryboardSchema.model_validate(storyboard.model_dump())
    if not all(len(items) == 4 for items in (videos, audio, source_durations)):
        raise ValueError("Four source entries are required")
    budgets = []
    for scene, baseline, path in zip(storyboard.scenes, BASE_DURATIONS, audio):
        duration = scene.actual_audio_duration
        if scene.voiceover_script and (duration is None or duration <= 0 or not path):
            raise ValueError("Voiced scenes require measured audio and source")
        if not scene.voiceover_script and (duration or path):
            raise ValueError("Silent scenes cannot contain narration")
        required = (duration or 0) + 0.15 + 0.3
        if required - baseline > 0.4 + 1e-6:
            raise RewriteRequired(f"Scene {scene.scene_index}: condense narration by 25%")
        if not scene.voiceover_script:
            budgets.append(baseline)
        else:
            # A short voice must not create an overlong breath tail. Reserve .15s
            # onset, then keep the last .2-.4s silent on an integer-frame boundary.
            lower = math.ceil((duration + .15 + .2) * 30 - 1e-8)
            upper = math.floor((duration + .15 + .4) * 30 + 1e-8)
            desired = math.ceil(max(baseline, required) * 30 - 1e-8)
            budgets.append(max(lower, min(upper, desired)) / 30)
    if sum(budgets) > 16 + 1e-6:
        raise RewriteRequired("Total narration budget exceeds 16s")
    if sum(budgets) < 14 - 1e-6:
        raise RewriteRequired("Narration too short for 14s with <=0.4s breath tails; expand the script", action="expand")
    clips, voices, subtitles = [], [], []
    start = 0.0
    for i, (scene, budget) in enumerate(zip(storyboard.scenes, budgets)):
        transition = 0.3 if i < 3 else 0
        clips.append(dict(scene_index=i + 1, source_url=videos[i], timeline_start=start,
                          duration=budget + transition, source_duration=source_durations[i],
                          trim_start=trim_start, transition_out="dissolve" if transition else None,
                          transition_duration=transition))
        if audio[i]:
            voices.append(dict(scene_index=i + 1, audio_url=audio[i],
                               timeline_start=start + 0.15, duration=scene.actual_audio_duration))
            if scene.subtitle_text:
                subtitles.append(dict(scene_index=i + 1, text=scene.subtitle_text,
                                      start_time=start + 0.15,
                                      end_time=min(start + 0.15 + scene.actual_audio_duration,
                                                   start + budget - 0.2)))
        start += budget
    return TimelineSchema.model_validate(dict(tracks=dict(video_clips=clips,
                                                         voiceover_tracks=voices,
                                                         subtitles=subtitles)))
