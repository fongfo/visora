import asyncio

import pytest

from visora_engine.jobs import LocalJobRunner
from visora_engine.providers import BaseVideoProvider, ProviderErrorCode
from visora_engine.schemas import JobState


class FakeProvider(BaseVideoProvider):
    def __init__(self, result=None):
        self.submissions = 0
        self.result = result or {"status": "COMPLETED", "video_url": "local.mp4"}

    async def submit_i2v(self, *args, **kwargs):
        self.submissions += 1
        await asyncio.sleep(.001)
        return str(self.submissions)

    async def get_job_status(self, job_id):
        return self.result


def test_concurrent_duplicate_submissions_and_explicit_reroll():
    async def scenario():
        provider = FakeProvider()
        runner = LocalJobRunner(provider, initial_poll=.001)
        jobs = await asyncio.gather(*(runner.submit("s", "k", "p", {}) for _ in range(20)))
        assert len({j.id for j in jobs}) == 1
        await runner.wait(jobs[0])
        assert provider.submissions == 1
        assert jobs[0].machine.history == ["QUEUED", "RUNNING", "SUCCESS"]
        reroll = await runner.submit("s", "k", "p", {"revision": 2})
        await runner.wait(reroll)
        assert reroll.id != jobs[0].id and provider.submissions == 2
    asyncio.run(scenario())


@pytest.mark.parametrize("result,expected", [
    ({"status": "FAILED", "error": "RATE_LIMITED"}, ProviderErrorCode.RATE_LIMITED),
    ({"status": "COMPLETED"}, ProviderErrorCode.MALFORMED_OUTPUT),
    ({"status": "nonsense"}, ProviderErrorCode.MALFORMED_OUTPUT),
    ({"status": "RUNNING"}, ProviderErrorCode.TIMEOUT),
])
def test_failures_and_retry(result, expected):
    async def scenario():
        provider = FakeProvider(result)
        runner = LocalJobRunner(provider, timeout=.02, initial_poll=.001)
        job = await runner.submit("s", "k", "p", {})
        await runner.wait(job)
        assert job.machine.state == JobState.FAILED and job.error == expected
        provider.result = {"status": "COMPLETED", "video_url": "retry.mp4"}
        retry = await runner.submit("s", "k", "p", {})
        await runner.wait(retry)
        assert retry.id != job.id and retry.machine.state == JobState.SUCCESS
    asyncio.run(scenario())


@pytest.mark.parametrize("started", [False, True])
def test_cancel_is_terminal_and_does_not_publish_late_output(started):
    async def scenario():
        provider = FakeProvider({"status": "RUNNING"})
        runner = LocalJobRunner(provider, initial_poll=.001)
        job = await runner.submit("s", "k", "p", {})
        if started: await asyncio.sleep(.003)
        await runner.cancel(job)
        provider.result = {"status": "COMPLETED", "video_url": "late.mp4"}
        await asyncio.sleep(.002)
        assert job.machine.state == JobState.CANCELLED and job.video_url is None
        assert not runner.active
    asyncio.run(scenario())
