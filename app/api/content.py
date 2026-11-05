from fastapi import APIRouter, HTTPException

from app.fetcher.http_fetcher import PlaywrightUnsupported
from app.schemas.misc import ContentRequest, ContentResponse
from app.schemas.response import ApiResponse, error_responses
from app.services.content_service import fetch_content
from app.utils.url import UnsafeURLError

router = APIRouter(tags=["content"])


@router.post(
    "/content",
    response_model=ApiResponse[ContentResponse],
    responses=error_responses(400, 502),
)
async def content_endpoint(req: ContentRequest):
    try:
        result = await fetch_content(
            req.url,
            content_selector=req.content_selector,
            follow_pagination=req.follow_pagination,
            max_pages=req.max_pages,
            use_playwright=req.use_playwright,
            clean=req.clean,
            lock_selector=bool(req.content_selector),
        )
    except PlaywrightUnsupported as e:
        raise HTTPException(status_code=400, detail=str(e))
    except UnsafeURLError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"正文抓取失败: {e}")
    return ApiResponse[ContentResponse].ok(result)
