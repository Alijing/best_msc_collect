"""后台任务管理：保存强引用、限制数量、支持取消和退出排空。"""
import asyncio
import logging
from typing import Any, Coroutine, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_background_tasks: set[asyncio.Task] = set()
_by_id: dict[str, asyncio.Task] = {}


class TooManyTasksError(RuntimeError):
    pass


def active_count() -> int:
    return sum(1 for task in _background_tasks if not task.done())


def fire_and_forget(
        coro: Coroutine[Any, Any, Any],
        name: str = "background-task",
        task_id: Optional[str] = None,
) -> asyncio.Task:
    if active_count() >= settings.MAX_BACKGROUND_TASKS:
        coro.close()
        raise TooManyTasksError("后台任务过多，请稍后重试")

    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)
    if task_id:
        _by_id[task_id] = task

    def _on_done(done: asyncio.Task) -> None:
        _background_tasks.discard(done)
        if task_id and _by_id.get(task_id) is done:
            _by_id.pop(task_id, None)
        if done.cancelled():
            logger.warning("[%s] cancelled", name)
            return
        exc = done.exception()
        if exc is not None:
            logger.error("[%s] failed: %s", name, exc, exc_info=exc)

    task.add_done_callback(_on_done)
    return task


def cancel_task(task_id: str) -> bool:
    task = _by_id.get(task_id)
    if task is None or task.done():
        return False
    task.cancel()
    return True


async def drain_background(timeout: float | None = None) -> None:
    """先等正在跑的任务结束，超时后再取消，避免先拆掉 HTTP 客户端。"""
    wait = settings.SHUTDOWN_DRAIN_SECONDS if timeout is None else timeout
    pending = [task for task in list(_background_tasks) if not task.done()]
    if not pending:
        return
    _, still = await asyncio.wait(pending, timeout=wait)
    for task in still:
        task.cancel()
    if still:
        await asyncio.wait(still, timeout=2)
