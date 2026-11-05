import asyncio
from typing import Any

from app.analyzer.chapter_filter import filter_chapters
from app.analyzer.container_scorer import pick_best_container
from app.analyzer.link_extract import collect_links
from app.analyzer.next_page import find_next_page
from app.analyzer.selector_builder import build_css_selector
from app.fetcher import fetch
from app.parser.html_parser import parse_html
from app.utils.url import normalize_url


def _analyze_html(html: str, final_url: str) -> dict[str, Any]:
    sel = parse_html(html)
    best = pick_best_container(sel)
    if not best:
        return {
            "url": final_url,
            "container_selector": None,
            "item_selector": None,
            "next_url": None,
            "next_text": None,
            "confidence": 0.0,
            "sample_chapters": [],
        }

    container = best["element"]
    next_page = find_next_page(sel, final_url)
    filtered = filter_chapters(collect_links(container, "a[href]"))
    samples = [
        {"title": title, "url": normalize_url(href, final_url)}
        for title, href in filtered[:8]
    ]
    return {
        "url": final_url,
        "container_selector": build_css_selector(container.root),
        "item_selector": "a",
        "next_url": next_page["url"] if next_page else None,
        "next_text": next_page["text"] if next_page else None,
        "confidence": round(best["score"], 3),
        "sample_chapters": samples,
    }


async def analyze(url: str, use_playwright: bool = False) -> dict[str, Any]:
    result = await fetch(url, use_playwright=use_playwright)
    return await asyncio.to_thread(_analyze_html, result.html, result.final_url)
