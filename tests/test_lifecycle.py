import asyncio

import httpx
import pytest

from app.core.background import TooManyTasksError, active_count, cancel_task, drain_background, fire_and_forget
from app.core.config import settings
from app.core.task_store import TaskStore
from app.fetcher.http_fetcher import HttpFetcher
from app.services.crawl_service import crawl
from app.utils.url import UnsafeURLError


def _client_for(fetcher: HttpFetcher, handler) -> None:
    fetcher._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
        event_hooks={"response": [fetcher._on_response]},
    )


@pytest.mark.asyncio
async def test_redirect_to_private_ip_is_blocked():
    fetcher = HttpFetcher()
    await fetcher.close()
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.path == "/a":
            return httpx.Response(302, headers={"Location": "http://127.0.0.1/secret"})
        return httpx.Response(200, content=b"nope")

    _client_for(fetcher, handler)
    try:
        with pytest.raises(UnsafeURLError):
            await fetcher.fetch("http://1.1.1.1/a")
    finally:
        await fetcher.close()
    assert seen == ["http://1.1.1.1/a"]


@pytest.mark.asyncio
async def test_oversized_response_stops(monkeypatch):
    monkeypatch.setattr(settings, "MAX_RESPONSE_SIZE", 8)
    monkeypatch.setattr(settings, "HTTP_RETRY_ATTEMPTS", 1)
    fetcher = HttpFetcher()
    await fetcher.close()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"0123456789abcdef")

    _client_for(fetcher, handler)
    try:
        with pytest.raises(ValueError, match="响应过大"):
            await fetcher.fetch("http://1.1.1.1/big")
    finally:
        await fetcher.close()


@pytest.mark.asyncio
async def test_blocked_status_does_not_retry_forever(monkeypatch):
    monkeypatch.setattr(settings, "HTTP_RETRY_ATTEMPTS", 1)
    fetcher = HttpFetcher()
    await fetcher.close()
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, content=b"slow down" * 100)

    _client_for(fetcher, handler)
    try:
        with pytest.raises(Exception):
            await fetcher.fetch("http://1.1.1.1/limited")
    finally:
        await fetcher.close()
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_crawl_failure_marks_task(monkeypatch):
    store = TaskStore()
    monkeypatch.setattr("app.services.crawl_service.task_store", store)

    async def boom(_url: str, use_playwright: bool = False):
        raise RuntimeError("网络断开")

    monkeypatch.setattr("app.services.crawl_service.fetch", boom)
    await store.create("t", {"status": "pending", "stage": "pending"})
    with pytest.raises(RuntimeError, match="网络断开"):
        await crawl("t", "http://1.1.1.1/list", max_pages=1, delay=0)
    data = await store.get("t")
    assert data is not None
    assert data["status"] == "failed"
    assert "网络断开" in data["error"]


@pytest.mark.asyncio
async def test_background_limit_and_cancel(monkeypatch):
    monkeypatch.setattr(settings, "MAX_BACKGROUND_TASKS", 1)

    async def hang() -> None:
        await asyncio.sleep(30)

    started = asyncio.Event()

    async def wait_for_cancel() -> None:
        started.set()
        await asyncio.sleep(30)

    first = fire_and_forget(hang(), name="hang", task_id="keep")
    try:
        with pytest.raises(TooManyTasksError):
            fire_and_forget(hang(), name="overflow")
        assert active_count() == 1
    finally:
        first.cancel()
        await asyncio.gather(first, return_exceptions=True)

    second = fire_and_forget(wait_for_cancel(), name="cancel-me", task_id="gone")
    await asyncio.wait_for(started.wait(), timeout=1)
    assert cancel_task("gone") is True
    with pytest.raises(asyncio.CancelledError):
        await second
    assert active_count() == 0


@pytest.mark.asyncio
async def test_drain_background_cancels_stuck_tasks(monkeypatch):
    monkeypatch.setattr(settings, "MAX_BACKGROUND_TASKS", 2)

    async def hang() -> None:
        await asyncio.sleep(30)

    task = fire_and_forget(hang(), name="drain")
    await drain_background(timeout=0.01)
    assert task.cancelled() or task.done()
    assert active_count() == 0
