from pydantic import BaseModel

from app.schemas.common import documented, with_example

_TASK_ID = "8f3c1a0e4b2d4c6a9e1f0a2b3c4d5e6f"


class TaskCreatedResponse(BaseModel):
    """异步任务创建结果。目录抓取和全本抓取共用。"""

    model_config = with_example({
        "task_id": _TASK_ID,
        "status": "pending",
    })

    task_id: str = documented(
        description="任务 ID，用于查询进度、分页取章节和删除任务",
        example=_TASK_ID,
    )
    status: str = documented(
        description="创建后的任务状态，固定为 pending",
        example="pending",
    )


class TaskStatusResponse(BaseModel):
    """任务进度。不含章节正文。"""

    model_config = with_example({
        "task_id": _TASK_ID,
        "status": "running",
        "stage": "content",
        "current_page": 3,
        "current_chapter": 20,
        "total_chapters": 86,
        "chapter_count": 86,
        "pages_crawled": 3,
        "error": None,
        "result_available": False,
    })

    task_id: str = documented(description="任务 ID", example=_TASK_ID)
    status: str = documented(
        description="任务状态：pending 已创建，running 进行中，completed 已完成，failed 失败",
        example="running",
    )
    stage: str | None = documented(
        None,
        description="当前阶段：pending 尚未开始，catalog 抓目录，content 抓正文，done 已结束。失败时保持失败前的阶段",
        example="content",
    )
    current_page: int = documented(0, description="目录阶段已处理的页码，从 0 开始累计", example=3)
    current_chapter: int = documented(0, description="正文阶段已处理的章节数", example=20)
    total_chapters: int = documented(
        0,
        description="正文阶段的章节总数。目录尚未完成时可能为 0",
        example=86,
    )
    chapter_count: int = documented(0, description="已保存的章节数", example=86)
    pages_crawled: int | None = documented(
        None,
        description="目录实际翻过的页数。尚未写入时为 null",
        example=3,
    )
    error: str | None = documented(
        None,
        description="任务失败原因。未失败时为 null",
        example="连接超时",
    )
    result_available: bool = documented(
        False,
        description="最终结果是否已经写入。只抓目录时可能仍为 false，但章节接口已经能读到当前目录",
        example=False,
    )


class ChapterItem(BaseModel):
    """分页接口返回的一章。"""

    model_config = with_example({
        "order": 1,
        "title": "第一章",
        "url": "https://example.com/1.html",
        "content": "正文",
        "content_pages": 1,
        "content_error": None,
    })

    order: int = documented(description="章节序号，从 1 开始", example=1)
    title: str = documented(description="章节标题", example="第一章")
    url: str = documented(description="章节绝对 URL", example="https://example.com/1.html")
    content: str | None = documented(
        None,
        description="章节正文。未抓取，或请求 withContent=false 时为 null",
        example="正文",
    )
    content_pages: int | None = documented(
        None,
        description="这一章跟随分页抓取的页数。正文尚未抓取时为 null",
        example=1,
    )
    content_error: str | None = documented(
        None,
        description="这一章抓取失败的原因。成功或尚未抓取时为 null。单章失败不会让整个任务失败",
        example="未识别到正文容器",
    )


class TaskDeleted(BaseModel):
    """删除任务的结果。"""

    model_config = with_example({"ok": True})

    ok: bool = documented(True, description="是否已取消后台任务并删除已存数据", example=True)


class TaskChaptersResponse(BaseModel):
    """一页章节。chapters 为空表示这一页已经到头。"""

    model_config = with_example({
        "task_id": _TASK_ID,
        "status": "completed",
        "stage": "done",
        "total": 86,
        "offset": 0,
        "limit": 50,
        "with_content": True,
        "chapters": [{
            "order": 1,
            "title": "第一章",
            "url": "https://example.com/1.html",
            "content": "正文",
            "content_pages": 1,
            "content_error": None,
        }],
    })

    task_id: str = documented(description="任务 ID", example=_TASK_ID)
    status: str = documented(
        description="任务状态：pending、running、completed、failed",
        example="completed",
    )
    stage: str | None = documented(
        None,
        description="当前阶段：pending、catalog、content、done",
        example="done",
    )
    total: int = documented(description="已保存的章节总数，不是本页条数", example=86)
    offset: int = documented(description="本页起始偏移，从 0 开始", example=0)
    limit: int = documented(description="本页最多返回的章节数", example=50)
    with_content: bool = documented(description="本页是否带上正文", example=True)
    chapters: list[ChapterItem] = documented(
        description="本页章节。空数组表示已经到头",
        example=[{
            "order": 1,
            "title": "第一章",
            "url": "https://example.com/1.html",
            "content": "正文",
            "content_pages": 1,
            "content_error": None,
        }],
    )
