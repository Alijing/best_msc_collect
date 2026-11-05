import asyncio
from typing import Any, Optional

from app.analyzer.content_cleaner import clean_content
from app.analyzer.content_extractor import extract_text, pick_content_container
from app.analyzer.content_pagination import (
    detect_incomplete_hint,
    find_content_next_page,
)
from app.analyzer.selector_builder import build_css_selector
from app.core.rate_limit import rate_limiter
from app.fetcher import fetch
from app.parser.html_parser import parse_html


def _first_title(sel) -> Optional[str]:
    for raw in sel.css("h1::text, title::text").getall():
        title = raw.strip()
        if title:
            return title
    return None


def _extract_page(
        html: str,
        content_selector: Optional[str],
        lock_selector: bool,
        clean: bool,
        current_url: str,
        follow_pagination: bool,
) -> dict[str, Any]:
    """同步解析一页。选择器未锁定且匹配失败时重新打分。"""
    sel = parse_html(html)
    title = _first_title(sel)
    container = None
    learned = content_selector

    if content_selector:
        nodes = sel.css(content_selector)
        if nodes:
            container = nodes[0]
        elif lock_selector:
            return {
                "title": title,
                "selector": content_selector,
                "error": f"contentSelector 未匹配: {content_selector}",
            }

    if container is None:
        best = pick_content_container(sel)
        if not best:
            return {
                "title": title,
                "selector": learned,
                "error": "未识别到正文容器",
            }
        container = best["element"]
        built = build_css_selector(container.root)
        if built:
            learned = built

    raw_text = extract_text(container)
    if clean:
        raw_text = clean_content(raw_text)

    next_url = None
    if follow_pagination:
        hint = detect_incomplete_hint(sel)
        next_url = find_content_next_page(sel, current_url, has_incomplete_hint=hint)

    return {
        "title": title,
        "text": raw_text,
        "selector": learned,
        "next_url": next_url,
    }


def _ok_response(
        url: str,
        final_url: str,
        title: Optional[str],
        page_texts: list[str],
        page_urls: list[str],
        selector: Optional[str],
) -> dict[str, Any]:
    full_content = "\n".join(t for t in page_texts if t)
    return {
        "url": url,
        "final_url": final_url,
        "title": title,
        "content": full_content,
        "length": len(full_content),
        "pages_crawled": len(page_urls),
        "page_urls": page_urls,
        "content_selector": selector,
    }


def _err_response(
        url: str,
        final_url: str,
        title: Optional[str],
        page_texts: list[str],
        page_urls: list[str],
        selector: Optional[str],
        error: str,
) -> dict[str, Any]:
    return {
        "url": url,
        "final_url": final_url,
        "title": title,
        "content": "\n".join(page_texts),
        "length": sum(len(t) for t in page_texts),
        "pages_crawled": len(page_urls),
        "page_urls": page_urls,
        "content_selector": selector,
        "error": error,
    }


async def fetch_content(
        url: str,
        content_selector: Optional[str] = None,
        follow_pagination: bool = True,
        max_pages: int = 20,
        use_playwright: bool = False,
        clean: bool = True,
        lock_selector: bool = False,
) -> dict[str, Any]:
    page_texts: list[str] = []
    page_urls: list[str] = []
    visited: set[str] = set()
    current: Optional[str] = url
    title: Optional[str] = None
    final_url = url
    learned = content_selector

    while current and current not in visited and len(page_urls) < max_pages:
        visited.add(current)
        await rate_limiter.acquire(current)

        result = await fetch(current, use_playwright=use_playwright)
        final_url = result.final_url
        page = await asyncio.to_thread(
            _extract_page,
            result.html,
            learned,
            lock_selector,
            clean,
            current,
            follow_pagination,
        )
        if title is None and page.get("title"):
            title = page["title"]
        if page.get("selector"):
            learned = page["selector"]
        if page.get("error"):
            return _err_response(
                url, final_url, title, page_texts, page_urls, learned, page["error"],
            )

        page_texts.append(page.get("text") or "")
        page_urls.append(current)

        if not follow_pagination or not page.get("next_url"):
            break
        current = page["next_url"]

    return _ok_response(url, final_url, title, page_texts, page_urls, learned)
