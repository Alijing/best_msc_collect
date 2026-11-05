import asyncio

import pytest

from app.core import rate_limit as rate_limit_mod
from app.core.rate_limit import DomainRateLimiter


@pytest.mark.asyncio
async def test_wait_does_not_block_other_domains(monkeypatch):
    release = asyncio.Event()
    started = asyncio.Event()
    real_sleep = rate_limit_mod.asyncio.sleep

    async def fake_sleep(delay: float) -> None:
        # 只拦住限速等待。wait_for 的超时仍走原来的 sleep。
        if delay >= 0.9:
            started.set()
            await release.wait()
            return
        await real_sleep(delay)

    monkeypatch.setattr(rate_limit_mod.asyncio, "sleep", fake_sleep)
    limiter = DomainRateLimiter(1.0)
    await limiter.acquire("https://a.example/1")

    waiting = asyncio.create_task(limiter.acquire("https://a.example/2"))
    await asyncio.wait_for(started.wait(), timeout=1)
    await asyncio.wait_for(limiter.acquire("https://b.example/1"), timeout=0.5)

    release.set()
    await waiting


@pytest.mark.asyncio
async def test_same_domain_reserves_separate_slots(monkeypatch):
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(rate_limit_mod.asyncio, "sleep", fake_sleep)
    limiter = DomainRateLimiter(1.0)
    await limiter.acquire("https://a.example/1")
    await asyncio.gather(
        limiter.acquire("https://a.example/2"),
        limiter.acquire("https://a.example/3"),
    )

    assert len(delays) == 2
    assert max(delays) - min(delays) == pytest.approx(1.0, abs=0.05)
