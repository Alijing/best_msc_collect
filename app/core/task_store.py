"""任务进度存储：默认内存，配置 REDIS_URL 时使用 Redis。

进度、目录和正文分开存放。拉取正文时按页读取，不解析整本。
已删除的任务拒绝后续写入。内存中正在运行的任务不会为了腾出名额被丢掉。
"""
import asyncio
import json
import logging
import time
import uuid
from typing import Any, Optional
from urllib.parse import urlparse

from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as aioredis
except ImportError:
    aioredis = None

_MISSING = object()
_BODY_CHUNK = 80
_ACTIVE = {"pending", "running"}

_GUARD_HSET = """
if redis.call('exists', KEYS[1]) == 1 then
  return 0
end
if redis.call('exists', KEYS[2]) == 0 then
  return 0
end
local i = 2
while i + 1 <= #ARGV do
  redis.call('hset', KEYS[2], ARGV[i], ARGV[i + 1])
  i = i + 2
end
redis.call('expire', KEYS[2], ARGV[1])
local n = 3
while n <= #KEYS do
  redis.call('expire', KEYS[n], ARGV[1])
  n = n + 1
end
return 1
"""

_GUARD_SET = """
if redis.call('exists', KEYS[1]) == 1 then
  return 0
end
if redis.call('exists', KEYS[2]) == 0 then
  return 0
end
redis.call('set', KEYS[3], ARGV[2], 'EX', ARGV[1])
return 1
"""

_GUARD_BODIES = """
if redis.call('exists', KEYS[1]) == 1 then
  return 0
end
if redis.call('exists', KEYS[2]) == 0 then
  return 0
end
if ARGV[2] == '1' then
  redis.call('del', KEYS[3])
end
local i = 3
while i + 1 <= #ARGV do
  redis.call('hset', KEYS[3], ARGV[i], ARGV[i + 1])
  i = i + 2
end
if redis.call('exists', KEYS[3]) == 1 then
  redis.call('expire', KEYS[3], ARGV[1])
end
return 1
"""

_GUARD_DELETE = """
redis.call('set', KEYS[1], '1', 'EX', ARGV[1])
redis.call('del', KEYS[2], KEYS[3], KEYS[4], KEYS[5])
return 1
"""


def _flatten(d: dict[str, Any]) -> dict[str, str]:
    return {k: json.dumps(v, ensure_ascii=False) for k, v in d.items()}


def _unflatten(d: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in d.items():
        try:
            out[k] = json.loads(v)
        except (TypeError, ValueError):
            out[k] = v
    return out


def _redis_target(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.hostname or "?"
    port = parsed.port or 6379
    db = (parsed.path or "/0").lstrip("/") or "0"
    return f"{host}:{port}/{db}"


def _order_of(chapter: dict[str, Any]) -> Optional[int]:
    try:
        return int(chapter.get("order"))
    except (TypeError, ValueError):
        return None


def _split_chapters(
        chapters: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[int, str]]:
    light: list[dict[str, Any]] = []
    bodies: dict[int, str] = {}
    for chapter in chapters:
        item = dict(chapter)
        order = _order_of(item)
        if "content" in item and order is not None:
            bodies[order] = item.pop("content") or ""
        elif "content" in item:
            item.pop("content", None)
        light.append(item)
    return light, bodies


class TaskStore:
    def __init__(self, max_tasks: int = 200) -> None:
        self._memory: dict[str, dict[str, Any]] = {}
        self._catalog: dict[str, list[dict[str, Any]]] = {}
        self._results: dict[str, dict[str, Any]] = {}
        self._bodies: dict[str, dict[int, str]] = {}
        self._max = max_tasks
        self._lock = asyncio.Lock()
        self._redis: Optional["aioredis.Redis"] = None

    async def init(self) -> None:
        if not settings.REDIS_URL:
            return
        if aioredis is None:
            logger.error("已配置 REDIS_URL，但未安装 redis 包，任务进度将使用内存")
            return
        target = _redis_target(settings.REDIS_URL)
        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            await client.ping()
        except Exception as exc:
            logger.error("Redis 连接失败（%s），任务进度将使用内存：%s", target, exc)
            try:
                await client.aclose()
            except Exception:
                pass
            self._redis = None
            return
        self._redis = client
        logger.info("Redis 已连接：%s", target)

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()

    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex

    @staticmethod
    def _key(task_id: str) -> str:
        return f"task:{task_id}"

    @staticmethod
    def _catalog_key(task_id: str) -> str:
        return f"task:{task_id}:catalog"

    @staticmethod
    def _result_key(task_id: str) -> str:
        return f"task:{task_id}:result"

    @staticmethod
    def _bodies_key(task_id: str) -> str:
        return f"task:{task_id}:bodies"

    @staticmethod
    def _deleted_key(task_id: str) -> str:
        return f"task:{task_id}:deleted"

    async def create(self, task_id: str, data: dict[str, Any]) -> None:
        now = time.time()
        progress = {k: v for k, v in data.items() if k not in ("chapters", "result")}
        progress.setdefault("created_at", now)
        progress.setdefault("updated_at", progress["created_at"])
        progress.setdefault("result_ready", False)
        if self._redis is not None:
            # 4.0 之前的 Redis 只接受 HSET key field value，多字段会报 wrong number of arguments。
            pipe = self._redis.pipeline()
            key = self._key(task_id)
            for field, value in _flatten(progress).items():
                pipe.hset(key, field, value)
            pipe.expire(key, settings.TASK_TTL_SECONDS)
            await pipe.execute()
            return
        async with self._lock:
            self._memory[task_id] = progress
            self._evict_locked()

    async def update(self, task_id: str, **kwargs: Any) -> None:
        chapters = kwargs.pop("chapters", _MISSING)
        result = kwargs.pop("result", _MISSING)
        if self._redis is not None:
            await self._update_redis(task_id, chapters, result, kwargs)
            return
        async with self._lock:
            if task_id not in self._memory:
                return
            if chapters is not _MISSING:
                self._store_chapters_locked(task_id, list(chapters or []), replace_bodies=False)
            if isinstance(result, dict):
                self._store_result_locked(task_id, result)
                kwargs["result_ready"] = True
            kwargs["updated_at"] = time.time()
            self._memory[task_id].update(kwargs)
            self._evict_locked()

    async def set_catalog(self, task_id: str, chapters: list[dict[str, Any]]) -> None:
        await self.update(task_id, chapters=chapters)

    async def get(self, task_id: str) -> Optional[dict[str, Any]]:
        if self._redis is not None:
            data = await self._redis.hgetall(self._key(task_id))
            return _unflatten(data) if data else None
        async with self._lock:
            item = self._memory.get(task_id)
            return dict(item) if item else None

    async def get_chapter_page(
            self,
            task_id: str,
            offset: int,
            limit: int,
            with_content: bool,
    ) -> tuple[int, list[dict[str, Any]]]:
        if self._redis is not None:
            return await self._page_redis(task_id, offset, limit, with_content)
        async with self._lock:
            catalog = self._catalog.get(task_id)
            legacy_bodies: dict[int, str] = {}
            if catalog is None:
                catalog, legacy_bodies = self._legacy_locked(task_id)
            total = len(catalog)
            page = [dict(ch) for ch in catalog[offset:offset + limit]]
            if not with_content or not page:
                return total, page
            bodies = self._bodies.get(task_id) or {}
            for chapter in page:
                order = _order_of(chapter)
                if order is None:
                    continue
                if order in bodies:
                    chapter["content"] = bodies[order]
                elif order in legacy_bodies:
                    chapter["content"] = legacy_bodies[order]
            return total, page

    async def get_chapter_list(self, task_id: str, with_content: bool) -> list[dict[str, Any]]:
        _total, page = await self.get_chapter_page(task_id, 0, 10**9, with_content)
        return page

    async def delete(self, task_id: str) -> None:
        if self._redis is not None:
            ttl = str(settings.TASK_TTL_SECONDS)
            await self._redis.eval(
                _GUARD_DELETE,
                5,
                self._deleted_key(task_id),
                self._key(task_id),
                self._catalog_key(task_id),
                self._result_key(task_id),
                self._bodies_key(task_id),
                ttl,
            )
            return
        async with self._lock:
            self._drop_locked(task_id)

    async def _update_redis(
            self,
            task_id: str,
            chapters: Any,
            result: Any,
            fields: dict[str, Any],
    ) -> None:
        if chapters is not _MISSING:
            await self._redis_put_chapters(task_id, list(chapters or []), replace_bodies=False)
        if isinstance(result, dict):
            meta = {k: v for k, v in result.items() if k != "chapters"}
            await self._redis_set(
                task_id,
                self._result_key(task_id),
                json.dumps(meta, ensure_ascii=False),
            )
            await self._redis_put_chapters(
                task_id,
                list(result.get("chapters") or []),
                replace_bodies=True,
            )
            fields["result_ready"] = True
        fields["updated_at"] = time.time()
        await self._redis_hset(task_id, _flatten(fields))

    async def _redis_hset(self, task_id: str, fields: dict[str, str]) -> None:
        if not fields or self._redis is None:
            return
        args: list[str] = [str(settings.TASK_TTL_SECONDS)]
        for key, value in fields.items():
            args.extend((key, value))
        await self._redis.eval(
            _GUARD_HSET,
            5,
            self._deleted_key(task_id),
            self._key(task_id),
            self._catalog_key(task_id),
            self._result_key(task_id),
            self._bodies_key(task_id),
            *args,
        )

    async def _redis_set(self, task_id: str, key: str, payload: str) -> None:
        if self._redis is None:
            return
        await self._redis.eval(
            _GUARD_SET,
            3,
            self._deleted_key(task_id),
            self._key(task_id),
            key,
            str(settings.TASK_TTL_SECONDS),
            payload,
        )

    async def _redis_put_chapters(
            self,
            task_id: str,
            chapters: list[dict[str, Any]],
            replace_bodies: bool,
    ) -> None:
        light, bodies = _split_chapters(chapters)
        await self._redis_set(
            task_id,
            self._catalog_key(task_id),
            json.dumps(light, ensure_ascii=False),
        )
        items = list(bodies.items())
        if not items and not replace_bodies:
            return
        if not items:
            await self._redis_bodies(task_id, [], replace=True)
            return
        for index in range(0, len(items), _BODY_CHUNK):
            chunk = items[index:index + _BODY_CHUNK]
            await self._redis_bodies(task_id, chunk, replace=replace_bodies and index == 0)

    async def _redis_bodies(
            self,
            task_id: str,
            items: list[tuple[int, str]],
            replace: bool,
    ) -> None:
        if self._redis is None:
            return
        args: list[str] = [str(settings.TASK_TTL_SECONDS), "1" if replace else "0"]
        for order, content in items:
            args.extend((str(order), content))
        await self._redis.eval(
            _GUARD_BODIES,
            3,
            self._deleted_key(task_id),
            self._key(task_id),
            self._bodies_key(task_id),
            *args,
        )

    async def _page_redis(
            self,
            task_id: str,
            offset: int,
            limit: int,
            with_content: bool,
    ) -> tuple[int, list[dict[str, Any]]]:
        assert self._redis is not None
        raw = await self._redis.get(self._catalog_key(task_id))
        legacy_bodies: dict[int, str] = {}
        if raw is None:
            result = await self._read_result(task_id)
            chapters = result.get("chapters") if isinstance(result, dict) else None
            if isinstance(chapters, list):
                catalog, legacy_bodies = _split_chapters(chapters)
            else:
                catalog = []
        else:
            data = json.loads(raw)
            catalog = data if isinstance(data, list) else []
        total = len(catalog)
        page = [dict(ch) for ch in catalog[offset:offset + limit]]
        if not with_content or not page:
            return total, page
        orders = [order for order in (_order_of(ch) for ch in page) if order is not None]
        bodies = await self._read_bodies(task_id, orders)
        for chapter in page:
            order = _order_of(chapter)
            if order is None:
                continue
            if order in bodies:
                chapter["content"] = bodies[order]
            elif order in legacy_bodies:
                chapter["content"] = legacy_bodies[order]
        return total, page

    async def _read_result(self, task_id: str) -> Optional[dict[str, Any]]:
        if self._redis is not None:
            raw = await self._redis.get(self._result_key(task_id))
            if not raw:
                return None
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        async with self._lock:
            return self._results.get(task_id)

    async def _read_bodies(self, task_id: str, orders: list[int]) -> dict[int, str]:
        if not orders:
            return {}
        if self._redis is not None:
            raw = await self._redis.hmget(self._bodies_key(task_id), [str(order) for order in orders])
            found: dict[int, str] = {}
            for order, value in zip(orders, raw):
                if value is not None:
                    found[order] = value
            return found
        async with self._lock:
            saved = self._bodies.get(task_id) or {}
            return {order: saved[order] for order in orders if order in saved}

    def _store_chapters_locked(
            self,
            task_id: str,
            chapters: list[dict[str, Any]],
            replace_bodies: bool,
    ) -> None:
        light, bodies = _split_chapters(chapters)
        self._catalog[task_id] = light
        if replace_bodies:
            self._bodies[task_id] = bodies
        elif bodies:
            self._bodies.setdefault(task_id, {}).update(bodies)

    def _store_result_locked(self, task_id: str, result: dict[str, Any]) -> None:
        meta = {k: v for k, v in result.items() if k != "chapters"}
        self._results[task_id] = meta
        self._store_chapters_locked(task_id, list(result.get("chapters") or []), replace_bodies=True)

    def _legacy_locked(self, task_id: str) -> tuple[list[dict[str, Any]], dict[int, str]]:
        result = self._results.get(task_id) or {}
        chapters = result.get("chapters") if isinstance(result, dict) else None
        if not isinstance(chapters, list):
            progress = self._memory.get(task_id) or {}
            chapters = progress.get("chapters")
        if not isinstance(chapters, list):
            return [], {}
        return _split_chapters(chapters)

    def _drop_locked(self, task_id: str) -> None:
        self._memory.pop(task_id, None)
        self._catalog.pop(task_id, None)
        self._results.pop(task_id, None)
        self._bodies.pop(task_id, None)

    def _evict_locked(self) -> None:
        now = time.time()
        ttl = settings.TASK_TTL_SECONDS
        stale = [
            task_id
            for task_id, data in self._memory.items()
            if now - float(data.get("updated_at") or data.get("created_at") or now) > ttl
        ]
        for task_id in stale:
            self._drop_locked(task_id)
        if len(self._memory) <= self._max:
            return
        terminal = [
            task_id
            for task_id, data in self._memory.items()
            if data.get("status") not in _ACTIVE
        ]
        terminal.sort(key=lambda task_id: float(self._memory[task_id].get("created_at") or 0))
        for task_id in terminal:
            if len(self._memory) <= self._max:
                break
            self._drop_locked(task_id)


task_store = TaskStore()
