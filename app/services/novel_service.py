import asyncio
import time
from typing import Any, Optional

from app.core.config import settings
from app.core.task_store import task_store
from app.services.content_service import fetch_content
from app.services.crawl_service import crawl

PROGRESS_EVERY = 20
PROGRESS_INTERVAL = 0.5


def should_report_progress(
        done: int,
        total: int,
        last_done: int,
        last_at: float,
        now: float,
) -> bool:
    if total > 0 and done >= total:
        return True
    if done - last_done >= PROGRESS_EVERY:
        return True
    return now - last_at >= PROGRESS_INTERVAL


async def fetch_novel(
        task_id: str,
        list_url: str,
        container_selector: Optional[str] = None,
        item_selector: Optional[str] = None,
        next_url: Optional[str] = None,
        max_pages: int = settings.MAX_PAGES_DEFAULT,
        delay: float = settings.DELAY_DEFAULT,
        concurrency: int = 2,
        with_content: bool = True,
        follow_pagination: bool = True,
        content_selector: Optional[str] = None,
        clean: bool = True,
) -> dict[str, Any]:
    try:
        # 阶段 1：目录
        await task_store.update(task_id, status="running", stage="catalog")
        catalog = await crawl(
            task_id=task_id,
            url=list_url,
            container_selector=container_selector,
            item_selector=item_selector,
            next_url=next_url,
            max_pages=max_pages,
            delay=delay,
            set_status_on_done=False,
        )
        chapters = catalog["chapters"]

        if not with_content:
            result = {
                "pages_crawled": catalog["pages_crawled"],
                "chapter_count": len(chapters),
                "chapters": chapters,
            }
            await task_store.update(
                task_id,
                result=result,
                status="completed",
                stage="done",
            )
            return result

        # 阶段 2：正文
        total = len(chapters)
        await task_store.update(
            task_id,
            status="running",
            stage="content",
            total_chapters=total,
            current_chapter=0,
        )

        sem = asyncio.Semaphore(concurrency)
        results: list[Optional[dict[str, Any]]] = [None] * total
        counter = asyncio.Lock()
        progress_lock = asyncio.Lock()
        started = time.monotonic()
        done = {"n": 0, "reported": 0, "reported_at": started, "sent": 0}
        holder = {"selector": content_selector}
        lock_selector = content_selector is not None

        async def _report(n: int) -> None:
            async with progress_lock:
                if n < done["sent"]:
                    return
                await task_store.update(task_id, current_chapter=n)
                done["sent"] = n

        async def _one(idx: int, ch: dict) -> None:
            async with sem:
                learned: Optional[str] = None
                try:
                    r = await fetch_content(
                        ch["url"],
                        content_selector=holder["selector"],
                        follow_pagination=follow_pagination,
                        clean=clean,
                        lock_selector=lock_selector,
                    )
                    results[idx] = {
                        **ch,
                        "content": r.get("content", ""),
                        "content_pages": r.get("pages_crawled", 0),
                        "content_error": r.get("error"),
                    }
                    learned = r.get("content_selector")
                except Exception as e:
                    results[idx] = {
                        **ch,
                        "content": "",
                        "content_pages": 0,
                        "content_error": str(e),
                    }
                if learned and not lock_selector:
                    holder["selector"] = learned
            report_n = 0
            async with counter:
                done["n"] += 1
                n = done["n"]
                now = time.monotonic()
                if should_report_progress(
                        n, total, done["reported"], done["reported_at"], now,
                ):
                    done["reported"] = n
                    done["reported_at"] = now
                    report_n = n
            if report_n:
                await _report(report_n)

        if total and not content_selector:
            await _one(0, chapters[0])
        start = 1 if total and not content_selector else 0
        if start < total:
            await asyncio.gather(*(_one(i, chapters[i]) for i in range(start, total)))

        full_chapters: list[dict[str, Any]] = [
            results[i] or {**ch, "content": ""}
            for i, ch in enumerate(chapters)
        ]

        result_payload = {
            "pages_crawled": catalog["pages_crawled"],
            "chapter_count": total,
            "chapters": full_chapters,
        }

        await task_store.update(
            task_id,
            result=result_payload,
            status="completed",
            stage="done",
            current_chapter=total,
        )
        return result_payload

    except Exception as e:
        await task_store.update(task_id, status="failed", error=str(e))
        raise
