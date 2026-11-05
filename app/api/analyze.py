from fastapi import APIRouter, HTTPException

from app.fetcher.http_fetcher import PlaywrightUnsupported
from app.schemas.analyze import AnalyzeRequest, AnalyzeResponse
from app.schemas.response import ApiResponse, error_responses
from app.services.analyze_service import analyze
from app.utils.url import UnsafeURLError

router = APIRouter(tags=["analyze"])


@router.post(
    "/analyze",
    response_model=ApiResponse[AnalyzeResponse],
    responses=error_responses(400, 502),
)
async def analyze_endpoint(req: AnalyzeRequest):
    try:
        result = await analyze(req.url, use_playwright=req.use_playwright)
    except PlaywrightUnsupported as e:
        raise HTTPException(status_code=400, detail=str(e))
    except UnsafeURLError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"分析失败: {e}")
    return ApiResponse[AnalyzeResponse].ok(result)
