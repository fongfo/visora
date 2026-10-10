import asyncio
from pathlib import Path

import pytest

from visora_engine.director import local_storyboard
from visora_engine.pipeline import LocalPipeline
from visora_engine.providers import BaseImageProvider, BaseVideoProvider
from visora_engine.schemas import ProjectState, SceneState


class ImageStub(BaseImageProvider):
    async def generate_keyframe(self, prompt, product_image_url, aspect_ratio="9:16"):
        return prompt + ".png"


class VideoStub(BaseVideoProvider):
    def __init__(self):
        self.calls = 0
        self.failed = False

    async def submit_i2v(self, *args, **kwargs):
        self.calls += 1
        return str(self.calls)

    async def get_job_status(self, job_id):
        return {"status": "FAILED", "error": "TIMEOUT"} if self.failed else {"status": "COMPLETED", "video_url": job_id + ".mp4"}


def test_confirmation_gates_prevent_early_generation(tmp_path):
    async def scenario():
        video = VideoStub()
        pipeline = LocalPipeline(local_storyboard(), ImageStub(), video, tmp_path)
        with pytest.raises(ValueError): await pipeline.prepare_keyframes()
        with pytest.raises(ValueError): await pipeline.generate()
        with pytest.raises(ValueError): pipeline.confirm_keyframes()
        pipeline.confirm_storyboard()
        await pipeline.prepare_keyframes()
        with pytest.raises(ValueError): await pipeline.generate()
        assert video.calls == 0
    asyncio.run(scenario())


def test_provider_failure_marks_project_and_scenes_then_allows_retry(tmp_path):
    async def scenario():
        video = VideoStub()
        pipeline = LocalPipeline(local_storyboard(), ImageStub(), video, tmp_path)
        pipeline.confirm_storyboard()
        await pipeline.prepare_keyframes()
        pipeline.confirm_keyframes()
        video.failed = True
        with pytest.raises(RuntimeError): await pipeline.generate()
        assert pipeline.project.state == ProjectState.FAILED
        assert all(s.state == SceneState.FAILED for s in pipeline.scenes)
        video.failed = False
        await pipeline.generate()
        assert all(s.state == SceneState.VIDEO_READY for s in pipeline.scenes)
        # Generation alone must not claim a completed project before rendering.
        assert pipeline.project.state == ProjectState.PROCESSING
    asyncio.run(scenario())


def test_render_failure_cannot_publish_completed_project(tmp_path, monkeypatch):
    async def scenario():
        pipeline = LocalPipeline(local_storyboard(), ImageStub(), VideoStub(), tmp_path)
        pipeline.confirm_storyboard()
        await pipeline.prepare_keyframes()
        pipeline.confirm_keyframes()
        await pipeline.generate()
        def broken_probe(path): raise RuntimeError("Unreadable media")
        monkeypatch.setattr("visora_engine.pipeline.probe", broken_probe)
        with pytest.raises(RuntimeError): pipeline.render()
        assert pipeline.project.state == ProjectState.FAILED
        assert pipeline.render_count == 0
    asyncio.run(scenario())
