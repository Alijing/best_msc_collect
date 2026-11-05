import asyncio

from fastapi import APIRouter, HTTPException

from app.analyzer.chapter_filter import filter_chapters
from app.analyzer.link_extract import collect_links
from app.fetcher import fetch
from app.fetcher.http_fetcher import PlaywrightUnsupported
from app.parser.html_parser import parse_html
from app.schemas.common import Chapter
from app.schemas.misc import ExtractRequest, ExtractResponse
from app.schemas.response import ApiResponse, error_responses
from app.utils.url import UnsafeURLError, normalize_url

router = APIRouter(tags=["extract"])


def _extract_html(
        html: str,
        final_url: str,
        container_selector: str,
        item_selector: str,
) -> dict:
    sel = parse_html(html)
    containers = sel.css(container_selector)
    if not containers:
        return {
            "url": final_url,
            "chapters": [],
            "error": f"containerSelector 未匹配到元素: {container_selector}",
        }
    filtered = filter_chapters(collect_links(containers[0], item_selector or "a"))
    chapters = [
        {"order": index + 1, "title": title, "url": normalize_url(href, final_url)}
        for index, (title, href) in enumerate(filtered)
    ]
    return {"url": final_url, "chapters": chapters, "error": None}


@router.post(
    "/extract",
    response_model=ApiResponse[ExtractResponse],
    responses=error_responses(400, 502),
)
async def extract_endpoint(req: ExtractRequest):
    try:
        result = await fetch(req.url, use_playwright=req.use_playwright)
        extracted = await asyncio.to_thread(
            _extract_html,
            result.html,
            result.final_url,
            req.container_selector,
            req.item_selector,
        )
        chapters = [Chapter(**item) for item in extracted["chapters"]]
        return ApiResponse[ExtractResponse].ok(ExtractResponse(
            url=extracted["url"],
            count=len(chapters),
            chapters=chapters,
            error=extracted["error"],
        ))
    except PlaywrightUnsupported as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except UnsafeURLError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"提取失败: {exc}")
