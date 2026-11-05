from fastapi import APIRouter, HTTPException

from app.api.guards import prepare_background
from app.core.background import TooManyTasksError, fire_and_forget
from app.core.task_store import task_store
from app.schemas.misc import NovelRequest
from app.schemas.response import ApiResponse, error_responses
from app.schemas.tasks import TaskCreatedResponse
from app.utils.url import UnsafeURLError

router = APIRouter(tags=["novel"])


async def _run_novel(task_id: str, req: NovelRequest) -> None:
    from app.services.novel_service import fetch_novel
    await fetch_novel(
        task_id=task_id,
        list_url=req.url,
        container_selector=req.container_selector,
        item_selector=req.item_selector,
        next_url=req.next_url,
        max_pages=req.max_pages,
        delay=req.delay,
        concurrency=req.concurrency,
        with_content=req.with_content,
        follow_pagination=req.follow_pagination,
        content_selector=req.content_selector,
        clean=req.clean,
    )


@router.post(
    "/novel",
    response_model=ApiResponse[TaskCreatedResponse],
    responses=error_responses(400, 429),
)
async def novel_endpoint(req: NovelRequest):
    try:
        await prepare_background(req.url)
    except UnsafeURLError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    task_id = task_store.new_id()
    await task_store.create(task_id, {
        "task_id": task_id,
        "status": "pending",
        "stage": "pending",
        "current_chapter": 0,
        "total_chapters": 0,
        "chapter_count": 0,
    })
    try:
        fire_and_forget(_run_novel(task_id, req), name=f"novel:{task_id}", task_id=task_id)
    except TooManyTasksError as exc:
        await task_store.delete(task_id)
        raise HTTPException(status_code=429, detail=str(exc))
    return ApiResponse[TaskCreatedResponse].ok(
        TaskCreatedResponse(task_id=task_id, status="pending"),
    )
