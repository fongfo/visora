from abc import ABC, abstractmethod
import asyncio
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import Field

from .media import prepare_font, run_ffmpeg
from .schemas import Contract


class ProviderErrorCode(str, Enum):
    AUTH_INVALID = "AUTH_INVALID"
    RATE_LIMITED = "RATE_LIMITED"
    CONTENT_FLAGGED = "CONTENT_FLAGGED"
    TIMEOUT = "TIMEOUT"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    MALFORMED_OUTPUT = "MALFORMED_OUTPUT"


class ProviderError(RuntimeError):
    def __init__(self, code: ProviderErrorCode):
        self.code = code
        super().__init__(code.value)


class ProviderCapabilities(Contract):
    supported_durations: list[float]
    supported_aspect_ratios: list[str]
    supports_webhook: bool
    max_concurrent_jobs: int = Field(gt=0)


class BaseImageProvider(ABC):
    @abstractmethod
    async def generate_keyframe(self, prompt: str, product_image_url: str,
                                aspect_ratio: str = "9:16") -> str: ...


class BaseVideoProvider(ABC):
    capabilities: ProviderCapabilities

    @abstractmethod
    async def submit_i2v(self, keyframe_url: str, motion_prompt: str, duration: float,
                         aspect_ratio: str = "9:16", webhook_url: str | None = None) -> str: ...

    @abstractmethod
    async def get_job_status(self, job_id: str) -> dict[str, Any]: ...


COLORS = ("0x183b56", "0x7c3e66", "0x127475", "0xa65d03")


class MockImageProvider(BaseImageProvider):
    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        prepare_font(self.directory)

    async def generate_keyframe(self, prompt, product_image_url, aspect_ratio="9:16"):
        if aspect_ratio != "9:16":
            raise ValueError("Mock supports 9:16 only")
        # Explicit local fixture prompt, not a parser for real model prompts.
        scene = int(prompt.removeprefix("Scene "))
        if scene not in range(1, 5):
            raise ValueError("Mock prompt must be Scene 1/2/3/4")
        output = self.directory / f"scene-{scene}-keyframe.png"
        await asyncio.to_thread(run_ffmpeg, ["-f", "lavfi", "-i",
            f"color=c={COLORS[scene-1]}:s=1080x1920:r=30", "-vf",
            f"drawtext=fontfile=font.ttf:text='Scene {scene}':fontcolor=white:fontsize=100:x=(w-tw)/2:y=(h-th)/2",
            "-frames:v", "1", str(output)], self.directory)
        return str(output)


class MockVideoProvider(BaseVideoProvider):
    capabilities = ProviderCapabilities(supported_durations=[5.0],
        supported_aspect_ratios=["9:16"], supports_webhook=False, max_concurrent_jobs=2)

    def __init__(self, directory: Path, failure: ProviderErrorCode | None = None):
        self.directory = directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.failure = failure
        self.jobs: dict[str, dict] = {}
        self.tasks: set[asyncio.Task] = set()
        self.slots = asyncio.Semaphore(self.capabilities.max_concurrent_jobs)
        self.submissions = 0

    async def submit_i2v(self, keyframe_url, motion_prompt, duration,
                         aspect_ratio="9:16", webhook_url=None):
        if duration not in self.capabilities.supported_durations or aspect_ratio != "9:16" or webhook_url:
            raise ValueError("Unsupported mock capability")
        if not Path(keyframe_url).is_file():
            raise ProviderError(ProviderErrorCode.MALFORMED_OUTPUT)
        job_id = uuid4().hex
        self.submissions += 1
        self.jobs[job_id] = {"status": "RUNNING"}
        task = asyncio.create_task(self._render(job_id, keyframe_url))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return job_id

    async def _render(self, job_id, keyframe):
        try:
            async with self.slots:
                if self.failure:
                    raise ProviderError(self.failure)
                output = self.directory / f"{job_id}.mp4"
                await asyncio.to_thread(run_ffmpeg, ["-loop", "1", "-framerate", "30", "-i", keyframe,
                    "-t", "5", "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                    "-threads", "2", "-pix_fmt", "yuv420p", str(output)])
                self.jobs[job_id] = {"status": "COMPLETED", "video_url": str(output), "duration": 5.0}
        except Exception as error:
            self.jobs[job_id] = {"status": "FAILED", "error": getattr(error, "code", ProviderErrorCode.UPSTREAM_UNAVAILABLE).value}

    async def get_job_status(self, job_id):
        return dict(self.jobs[job_id])
