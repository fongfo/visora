import asyncio
from dataclasses import dataclass, field
from uuid import uuid4

from .providers import BaseVideoProvider, ProviderError, ProviderErrorCode
from .schemas import JobState
from .state import StateMachine, fingerprint


@dataclass
class Job:
    id: str
    fingerprint: str
    machine: StateMachine = field(default_factory=lambda: StateMachine(JobState.QUEUED))
    external_id: str | None = None
    video_url: str | None = None
    error: ProviderErrorCode | None = None


class LocalJobRunner:
    """Single-process test adapter. Redis transactions are required for distributed workers."""

    def __init__(self, provider: BaseVideoProvider, timeout=360.0, initial_poll=3.0):
        self.provider = provider
        self.timeout = timeout
        self.initial_poll = initial_poll
        self.jobs: dict[str, Job] = {}
        self.active: dict[str, str] = {}
        self.lock = asyncio.Lock()
        self.tasks: dict[str, asyncio.Task] = {}

    async def submit(self, scene_id, keyframe, prompt, params):
        fp = fingerprint(scene_id, type(self.provider).__name__, keyframe, prompt, params)
        async with self.lock:
            existing = self.active.get(fp)
            if existing and self.jobs[existing].machine.state in {JobState.QUEUED, JobState.RUNNING}:
                return self.jobs[existing]
            job = Job(uuid4().hex, fp)
            self.jobs[job.id] = job
            self.active[fp] = job.id
            self.tasks[job.id] = asyncio.create_task(self._execute(job, keyframe, prompt, params))
            return job

    async def _execute(self, job, keyframe, prompt, params):
        try:
            job.machine.move(JobState.RUNNING)
            async with asyncio.timeout(self.timeout):
                job.external_id = await self.provider.submit_i2v(keyframe, prompt,
                    params.get("duration", 5.0), params.get("aspect_ratio", "9:16"))
                delay = self.initial_poll
                while True:
                    result = await self.provider.get_job_status(job.external_id)
                    status = result.get("status")
                    if status == "COMPLETED":
                        if not result.get("video_url"):
                            raise ProviderError(ProviderErrorCode.MALFORMED_OUTPUT)
                        job.video_url = result["video_url"]
                        job.machine.move(JobState.SUCCESS)
                        return
                    if status == "FAILED":
                        raise ProviderError(ProviderErrorCode(result.get("error", "UPSTREAM_UNAVAILABLE")))
                    if status not in {"QUEUED", "RUNNING"}:
                        raise ProviderError(ProviderErrorCode.MALFORMED_OUTPUT)
                    await asyncio.sleep(delay)
                    delay = min(delay * 1.5, 12.0)
        except asyncio.CancelledError:
            if job.machine.state in {JobState.QUEUED, JobState.RUNNING}:
                job.machine.move(JobState.CANCELLED)
        except Exception as error:
            job.error = ProviderErrorCode.TIMEOUT if isinstance(error, TimeoutError) else getattr(
                error, "code", ProviderErrorCode.UPSTREAM_UNAVAILABLE)
            job.machine.move(JobState.FAILED)
        finally:
            if self.active.get(job.fingerprint) == job.id:
                self.active.pop(job.fingerprint, None)

    async def wait(self, job):
        await self.tasks[job.id]
        return job

    async def cancel(self, job):
        if job.machine.state in {JobState.QUEUED, JobState.RUNNING}:
            self.tasks[job.id].cancel()
            try:
                await self.tasks[job.id]
            except asyncio.CancelledError:
                job.machine.move(JobState.CANCELLED)
                if self.active.get(job.fingerprint) == job.id:
                    self.active.pop(job.fingerprint, None)
