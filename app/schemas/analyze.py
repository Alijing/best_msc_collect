from pydantic import BaseModel

from app.schemas.common import documented, with_example


class AnalyzeRequest(BaseModel):
    """分析目录页的请求。"""

    model_config = with_example({
        "url": "https://example.com/book/1/",
        "use_playwright": False,
    })

    url: str = documented(description="目录页 URL，仅允许 http 或 https", example="https://example.com/book/1/")
    use_playwright: bool = documented(
        False,
        description="是否使用浏览器渲染。当前不支持，传 true 时返回 400",
        example=False,
    )


class ChapterSample(BaseModel):
    """目录识别结果中的一条样本章节。"""

    model_config = with_example({
        "title": "第一章",
        "url": "https://example.com/1.html",
    })

    title: str = documented(description="章节标题", example="第一章")
    url: str = documented(description="章节绝对 URL", example="https://example.com/1.html")


class AnalyzeResponse(BaseModel):
    """目录页识别结果。未识别到容器时选择器为 null，confidence 为 0，接口仍返回 200。"""

    model_config = with_example({
        "url": "https://example.com/book/1/",
        "container_selector": "#list",
        "item_selector": "a",
        "next_url": "https://example.com/book/1/2.html",
        "next_text": "下一页",
        "confidence": 0.86,
        "sample_chapters": [
            {"title": "第一章", "url": "https://example.com/1.html"},
        ],
    })

    url: str = documented(
        description="抓取并跟随跳转后的最终 URL",
        example="https://example.com/book/1/",
    )
    container_selector: str | None = documented(
        description="章节列表容器的 CSS 选择器。未识别到时为 null",
        example="#list",
    )
    item_selector: str | None = documented(
        description="容器内章节链接的 CSS 选择器。识别成功时为 a，未识别到时为 null",
        example="a",
    )
    next_url: str | None = documented(
        description="下一页目录的绝对 URL。没有下一页时为 null",
        example="https://example.com/book/1/2.html",
    )
    next_text: str | None = documented(
        description="下一页链接上的文字。没有下一页时为 null",
        example="下一页",
    )
    confidence: float = documented(
        description="目录容器识别的置信度，范围 0 到 1。未识别到时为 0",
        example=0.86,
    )
    sample_chapters: list[ChapterSample] = documented(
        description="样本章节，最多 8 条",
        example=[{"title": "第一章", "url": "https://example.com/1.html"}],
    )
