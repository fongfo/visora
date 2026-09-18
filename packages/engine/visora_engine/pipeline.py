import asyncio
from pathlib import Path

from .audio import assemble_voice, duck, make_bgm, mix
from .composer import compose
from .jobs import LocalJobRunner
from .media import probe
from .providers import BaseImageProvider, BaseVideoProvider
from .scheduler import build_timeline
from .schemas import BackgroundMusic, JobState, ProjectState, SceneState, StoryboardSchema
from .state import SceneAssets, StateMachine


class LocalPipeline:
    """Offline harness; explicit confirmation calls stand in for future UI actions."""

    def __init__(self, storyboard: StoryboardSchema, image_provider: BaseImageProvider,
                 video_provider: BaseVideoProvider, directory: Path):
        self.storyboard = storyboard
        self.images = image_provider
        self.runner = LocalJobRunner(video_provider, initial_poll=0.05)
        self.directory = directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.project = StateMachine(ProjectState.DRAFT)
        self.scenes = [StateMachine(SceneState.PENDING) for _ in range(4)]
        self.assets = [SceneAssets() for _ in range(4)]
        self.keyframes_confirmed = False
        self.version = 1
        self.render_count = 0

    def confirm_storyboard(self):
        self.project.move(ProjectState.CONCEPT_READY)
        self.project.move(ProjectState.STORYBOARD_CONFIRMED)

    async def prepare_keyframes(self):
        if self.project.state != ProjectState.STORYBOARD_CONFIRMED:
            raise ValueError("Storyboard must be confirmed before generating keyframes")
        for i, scene in enumerate(self.storyboard.scenes):
            self.scenes[i].move(SceneState.KEYFRAME_GENERATING)
            try:
                self.assets[i].keyframe = await self.images.generate_keyframe(
                    scene.keyframe_prompt, self.storyboard.product_metadata.isolated_image_url)
                self.scenes[i].move(SceneState.KEYFRAME_READY)
            except Exception:
                self.scenes[i].move(SceneState.FAILED)
                raise

    def confirm_keyframes(self):
        if not all(s.state == SceneState.KEYFRAME_READY for s in self.scenes):
            raise ValueError("All keyframes must be ready")
        self.keyframes_confirmed = True

    async def generate(self, indices=(0, 1, 2, 3)):
        if not self.keyframes_confirmed:
            raise ValueError("Keyframes must be confirmed before video generation")
        self.project.move(ProjectState.PROCESSING)
        async def one(i):
            self.scenes[i].move(SceneState.VIDEO_GENERATING)
            try:
                asset = self.assets[i]
                job = await self.runner.submit(str(i + 1), asset.keyframe,
                    self.storyboard.scenes[i].motion_prompt,
                    {"duration": 5.0, "aspect_ratio": "9:16", "revision": asset.revision,
                     "project_version": self.version})
                await self.runner.wait(job)
                if job.machine.state != JobState.SUCCESS:
                    raise RuntimeError(f"Video job {job.id}: {job.error or job.machine.state}")
                asset.video = job.video_url
                asset.video_outdated = False
                self.scenes[i].move(SceneState.VIDEO_READY)
            except Exception:
                self.scenes[i].move(SceneState.FAILED)
                raise
        results = await asyncio.gather(*(one(i) for i in indices), return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                self.project.move(ProjectState.FAILED)
                raise result

    def render(self, name="final.mp4"):
        if self.project.state != ProjectState.PROCESSING or not all(s.state == SceneState.VIDEO_READY for s in self.scenes):
            raise ValueError("All scenes must be ready before composition")
        try:
            source_durations = [float(probe(a.video)["format"]["duration"]) for a in self.assets]
            timeline = build_timeline(self.storyboard, [a.video for a in self.assets],
                                      [a.audio for a in self.assets], source_durations)
            voice, envelope = self.directory / "voice.wav", self.directory / "envelope.wav"
            bgm, ducked, mixed = [self.directory / f"{n}.wav" for n in ("bgm", "ducked", "mixed")]
            timeline.tracks.background_music = BackgroundMusic(audio_url=str(bgm))
            assemble_voice(timeline, voice, envelope)
            make_bgm(bgm, timeline.duration)
            duck(bgm, envelope, ducked, calibrated=True)
            mix(voice, ducked, mixed)
            compose(timeline, mixed, self.directory / name)
            (self.directory / "timeline.json").write_text(timeline.model_dump_json(indent=2), encoding="utf-8")
            self.render_count += 1
            self.project.move(ProjectState.COMPLETED)
            return timeline
        except Exception:
            self.project.move(ProjectState.FAILED)
            raise

    async def reroll(self, scene_index: int):
        if self.project.state != ProjectState.COMPLETED or scene_index not in range(1, 5):
            raise ValueError("Reroll requires a completed project and a valid scene")
        self.assets[scene_index - 1].invalidate("reroll")
        await self.generate((scene_index - 1,))
        return self.render("rerolled.mp4")
