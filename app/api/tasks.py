from fastapi import APIRouter, HTTPException, Query

from app.core.background import cancel_task
from app.core.task_store import task_store
from app.schemas.response import ApiResponse, error_responses
from app.schemas.tasks import (
    ChapterItem,
    TaskChaptersResponse,
    TaskDeleted,
    TaskStatusResponse,
)

router = APIRouter(tags=["tasks"])


def _result_available(data: dict) -> bool:
    if data.get("result_ready"):
        return True
    result = data.get("result")
    return isinstance(result, dict) and bool(result.get("chapters"))


def _to_item(ch: dict, with_content: bool) -> ChapterItem:
    return ChapterItem(
        order=int(ch.get("order", 0)),
        title=ch.get("title", ""),
        url=ch.get("url", ""),
        content=ch.get("content") if with_content else None,
        content_pages=ch.get("content_pages"),
        content_error=ch.get("content_error"),
    )


@router.get(
    "/tasks/{task_id}",
    response_model=ApiResponse[TaskStatusResponse],
    responses=error_responses(404),
)
async def get_task(task_id: str):
    data = await task_store.get(task_id)
    if not data:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")

    return ApiResponse[TaskStatusResponse].ok(TaskStatusResponse(
        task_id=task_id,
        status=data.get("status", "unknown"),
        stage=data.get("stage"),
        current_page=int(data.get("current_page", 0)),
        current_chapter=int(data.get("current_chapter", 0)),
        total_chapters=int(data.get("total_chapters", 0)),
        chapter_count=int(data.get("chapter_count") or 0),
        pages_crawled=data.get("pages_crawled"),
        error=data.get("error"),
        result_available=_result_available(data),
    ))


@router.get(
    "/tasks/{task_id}/chapters",
    response_model=ApiResponse[TaskChaptersResponse],
    responses=error_responses(404),
)
async def get_task_chapters(
        task_id: str,
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=500),
        with_content: bool = Query(
            True,
            alias="withContent",
            description="是否返回正文。false 时不读正文",
        ),
):
    data = await task_store.get(task_id)
    if not data:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")

    total, page = await task_store.get_chapter_page(
        task_id, offset, limit, with_content,
    )

    return ApiResponse[TaskChaptersResponse].ok(TaskChaptersResponse(
        task_id=task_id,
        status=data.get("status", "unknown"),
        stage=data.get("stage"),
        total=total,
        offset=offset,
        limit=limit,
        with_content=with_content,
        chapters=[_to_item(ch, with_content) for ch in page],
    ))


@router.delete(
    "/tasks/{task_id}",
    response_model=ApiResponse[TaskDeleted],
)
async def delete_task(task_id: str):
    cancel_task(task_id)
    await task_store.delete(task_id)
    return ApiResponse[TaskDeleted].ok(TaskDeleted(ok=True))