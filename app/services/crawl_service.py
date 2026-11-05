import asyncio
from typing import Any, Optional

from app.analyzer.chapter_filter import filter_chapters
from app.analyzer.container_scorer import pick_best_container
from app.analyzer.link_extract import collect_links
from app.analyzer.next_page import find_next_page
from app.analyzer.selector_builder import build_css_selector
from app.core.config import settings
from app.core.rate_limit import catalog_extra_wait, rate_limiter
from app.core.task_store import task_store
from app.fetcher import fetch
from app.parser.html_parser import parse_html
from app.utils.url import normalize_url


def _read_catalog_page(
        html: str,
        final_url: str,
        container_selector: Optional[str],
        item_selector: Optional[str],
        forced_next: Optional[str],
        page_no: int,
) -> dict[str, Any]:
    sel = parse_html(html)
    learned = False
    if not container_selector:
        best = pick_best_container(sel)
        if not best:
            return {"error": "未识别到章节容器"}
        container_selector = build_css_selector(best["element"].root)
        item_selector = "a"
        learned = True

    containers = sel.css(container_selector)
    if not containers:
        if page_no == 1:
            return {
                "error": f"containerSelector 未匹配到元素: {container_selector}",
                "container_selector": container_selector,
                "item_selector": item_selector,
            }
        return {
            "stop": True,
            "container_selector": container_selector,
            "item_selector": item_selector,
            "learned": learned,
        }

    filtered = filter_chapters(collect_links(containers[0], item_selector or "a"))
    links = [(title, normalize_url(href, final_url)) for title, href in filtered]
    if forced_next:
        nxt = forced_next
    else:
        found = find_next_page(sel, final_url)
        nxt = found["url"] if found else None
    return {
        "container_selector": container_selector,
        "item_selector": item_selector or "a",
        "learned": learned,
        "links": links,
        "next_url": nxt,
    }


async def crawl(
        task_id: str,
        url: str,
        container_selector: Optional[str] = None,
        item_selector: Optional[str] = None,
        next_url: Optional[str] = None,
        max_pages: int = settings.MAX_PAGES_DEFAULT,
        delay: float = settings.DELAY_DEFAULT,
        use_playwright: bool = False,
        set_status_on_done: bool = True,
) -> dict[str, Any]:
    """抓目录。失败时把任务标成 failed。"""
    try:
        return await _crawl(
            task_id=task_id,
            url=url,
            container_selector=container_selector,
            item_selector=item_selector,
            next_url=next_url,
            max_pages=max_pages,
            delay=delay,
            use_playwright=use_playwright,
            set_status_on_done=set_status_on_done,
        )
    except Exception as exc:
        await task_store.update(task_id, status="failed", error=str(exc))
        raise


async def _crawl(
        task_id: str,
        url: str,
        container_selector: Optional[str],
        item_selector: Optional[str],
        next_url: Optional[str],
        max_pages: int,
        delay: float,
        use_playwright: bool,
        set_status_on_done: bool,
) -> dict[str, Any]:
    chapters: list[dict[str, Any]] = []
    seen_pages: set[str] = set()
    seen_urls: set[str] = set()
    current: Optional[str] = url
    pages = 0
    auto_analyzed = False
    forced_next = next_url

    await task_store.update(task_id, stage="catalog")

    while current and current not in seen_pages and pages < max_pages:
        seen_pages.add(current)
        pages += 1

        await rate_limiter.acquire(current)
        await task_store.update(task_id, current_page=pages)

        result = await fetch(current, use_playwright=use_playwright)
        page = await asyncio.to_thread(
            _read_catalog_page,
            result.html,
            result.final_url,
            container_selector,
            item_selector,
            forced_next if pages == 1 else None,
            pages,
        )
        forced_next = None
        if page.get("container_selector"):
            container_selector = page["container_selector"]
        if page.get("item_selector"):
            item_selector = page["item_selector"]
        if page.get("learned"):
            auto_analyzed = True
        if page.get("error"):
            raise RuntimeError(page["error"])
        if page.get("stop"):
            break

        for title, link in page.get("links") or []:
            if link in seen_urls:
                continue
            seen_urls.add(link)
            chapters.append({
                "order": len(chapters) + 1,
                "title": title,
                "url": link,
            })

        await task_store.update(
            task_id,
            chapter_count=len(chapters),
            chapters=chapters,
        )
        current = page.get("next_url")

        extra = catalog_extra_wait(delay, rate_limiter.rate)
        if extra > 0:
            await asyncio.sleep(extra)

    update_payload: dict[str, Any] = {
        "pages_crawled": pages,
        "chapter_count": len(chapters),
        "chapters": chapters,
    }
    if set_status_on_done:
        update_payload["status"] = "completed"
        update_payload["stage"] = "done"
    await task_store.update(task_id, **update_payload)

    return {
        "pages_crawled": pages,
        "chapter_count": len(chapters),
        "auto_analyzed": auto_analyzed,
        "chapters": chapters,
    }
