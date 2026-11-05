from fastapi import APIRouter, HTTPException

from app.api.guards import prepare_background
from app.core.background import TooManyTasksError, fire_and_forget
from app.core.task_store import task_store
from app.fetcher.http_fetcher import PlaywrightUnsupported
from app.schemas.crawl import CrawlRequest
from app.schemas.response import ApiResponse, error_responses
from app.schemas.tasks import TaskCreatedResponse
from app.services.crawl_service import crawl
from app.utils.url import UnsafeURLError

router = APIRouter(tags=["crawl"])


async def _run_crawl(task_id: str, req: CrawlRequest) -> None:
    await crawl(
        task_id=task_id,
        url=req.url,
        container_selector=req.container_selector,
        item_selector=req.item_selector,
        next_url=req.next_url,
        max_pages=req.max_pages,
        delay=req.delay,
        use_playwright=req.use_playwright,
        set_status_on_done=True,
    )


@router.post(
    "/crawl",
    response_model=ApiResponse[TaskCreatedResponse],
    responses=error_responses(400, 429),
)
async def crawl_endpoint(req: CrawlRequest):
    try:
        await prepare_background(req.url, req.use_playwright)
    except PlaywrightUnsupported as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except UnsafeURLError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    task_id = task_store.new_id()
    await task_store.create(task_id, {
        "task_id": task_id,
        "status": "pending",
        "stage": "pending",
        "url": req.url,
        "current_page": 0,
        "chapter_count": 0,
        "error": None,
    })
    try:
        fire_and_forget(_run_crawl(task_id, req), name=f"crawl:{task_id}", task_id=task_id)
    except TooManyTasksError as exc:
        await task_store.delete(task_id)
        raise HTTPException(status_code=429, detail=str(exc))
    return ApiResponse[TaskCreatedResponse].ok(
        TaskCreatedResponse(task_id=task_id, status="pending"),
    )
