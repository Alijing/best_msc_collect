from pydantic import BaseModel

from app.core.config import settings
from app.schemas.common import Chapter, documented, with_example

_CHAPTER = {
    "order": 1,
    "title": "第一章",
    "url": "https://example.com/1.html",
    "content": "正文",
}


class ContentRequest(BaseModel):
    """同步抓取一章正文的请求。"""

    model_config = with_example({
        "url": "https://example.com/1.html",
        "content_selector": "#content",
        "follow_pagination": True,
        "max_pages": 20,
        "use_playwright": False,
        "clean": True,
    })

    url: str = documented(description="章节页 URL，仅允许 http 或 https", example="https://example.com/1.html")
    content_selector: str | None = documented(
        None,
        description="正文容器的 CSS 选择器。传入后必须能匹配，匹配不到时 data.error 会说明原因。为空则自动识别",
        example="#content",
    )
    follow_pagination: bool = documented(
        True,
        description="是否跟随正文里的「下一页」继续抓取",
        example=True,
    )
    max_pages: int = documented(
        20,
        description="这一章最多跟随的分页数，范围 1–100",
        example=20,
        ge=1,
        le=100,
    )
    use_playwright: bool = documented(
        False,
        description="是否使用浏览器渲染。当前不支持，传 true 时返回 400",
        example=False,
    )
    clean: bool = documented(True, description="是否去掉常见广告、水印和站点提示", example=True)


class ContentResponse(BaseModel):
    """一章正文。选择器未命中时 code 仍为 200，原因在 error。"""

    model_config = with_example({
        "url": "https://example.com/1.html",
        "final_url": "https://example.com/1.html",
        "title": "第一章",
        "content": "正文",
        "length": 2,
        "pages_crawled": 1,
        "page_urls": ["https://example.com/1.html"],
        "error": None,
    })

    url: str = documented(description="请求里的章节 URL", example="https://example.com/1.html")
    final_url: str = documented(
        description="跟随跳转后的最终 URL",
        example="https://example.com/1.html",
    )
    title: str | None = documented(None, description="章节标题。页面没有标题时为 null", example="第一章")
    content: str = documented("", description="合并后的正文。未抓到时为空字符串", example="正文")
    length: int = documented(0, description="正文字符数", example=2)
    pages_crawled: int = documented(0, description="这一章实际抓取的分页数", example=1)
    page_urls: list[str] = documented(
        description="各分页的最终 URL，按抓取顺序",
        example=["https://example.com/1.html"],
        default_factory=list,
    )
    error: str | None = documented(
        None,
        description="选择器未命中或未识别到正文时的说明。成功时为 null。此时接口 code 仍为 200，已抓到的前文仍在 content",
        example="contentSelector 未匹配: #content",
    )


class NovelRequest(BaseModel):
    """异步抓取目录并可选抓取正文的请求。"""

    model_config = with_example({
        "url": "https://example.com/book/1/",
        "container_selector": "#list",
        "item_selector": "a",
        "next_url": "https://example.com/book/1/2.html",
        "max_pages": 20,
        "delay": 0,
        "concurrency": 2,
        "with_content": True,
        "follow_pagination": True,
        "content_selector": "#content",
        "clean": True,
    })

    url: str = documented(description="目录页 URL，仅允许 http 或 https", example="https://example.com/book/1/")
    container_selector: str | None = documented(
        None,
        description="章节列表容器的 CSS 选择器。为空则自动识别，并在后续目录页复用",
        example="#list",
    )
    item_selector: str | None = documented(
        None,
        description="容器内章节链接的 CSS 选择器。为空则使用 a",
        example="a",
    )
    next_url: str | None = documented(
        None,
        description="第一页的下一页绝对 URL。只用于第一页，后续页面自行识别",
        example="https://example.com/book/1/2.html",
    )
    max_pages: int = documented(
        settings.MAX_PAGES_DEFAULT,
        description="目录最多翻页数，范围 1–5000。默认值为配置项 MAX_PAGES_DEFAULT",
        example=20,
        ge=1,
        le=5000,
    )
    delay: float = documented(
        settings.DELAY_DEFAULT,
        description="目录页之间的最小间隔（秒），范围 0–10。比域名限速更严时才补足差额。默认值为配置项 DELAY_DEFAULT。正文抓取不使用该间隔",
        example=0,
        ge=0,
        le=10,
    )
    concurrency: int = documented(
        2,
        description="正文阶段的并发数，范围 1–10",
        example=2,
        ge=1,
        le=10,
    )
    with_content: bool = documented(
        True,
        description="是否在目录抓完后继续抓正文。false 时只保存目录",
        example=True,
    )
    follow_pagination: bool = documented(True, description="抓正文时是否跟随「下一页」", example=True)
    content_selector: str | None = documented(
        None,
        description="正文容器的 CSS 选择器。为空则由第一章识别后复用",
        example="#content",
    )
    clean: bool = documented(True, description="是否去掉常见广告、水印和站点提示", example=True)


class ExtractRequest(BaseModel):
    """用调用方给出的选择器，从一页里抽出链接。"""

    model_config = with_example({
        "url": "https://example.com/book/1/",
        "container_selector": "#list",
        "item_selector": "a",
        "use_playwright": False,
    })

    url: str = documented(description="要提取链接的页面 URL，仅允许 http 或 https", example="https://example.com/book/1/")
    container_selector: str = documented(description="链接所在容器的 CSS 选择器", example="#list")
    item_selector: str = documented("a", description="容器内链接元素的 CSS 选择器", example="a")
    use_playwright: bool = documented(
        False,
        description="是否使用浏览器渲染。当前不支持，传 true 时返回 400",
        example=False,
    )


class ExtractResponse(BaseModel):
    """按选择器抽出的章节链接。未命中时 count 为 0，原因在 error，接口仍返回 200。"""

    model_config = with_example({
        "url": "https://example.com/book/1/",
        "count": 1,
        "chapters": [{
            "order": 1,
            "title": "第一章",
            "url": "https://example.com/1.html",
        }],
        "error": None,
    })

    url: str = documented(description="抓取并跟随跳转后的最终 URL", example="https://example.com/book/1/")
    count: int = documented(description="抽出的章节数。选择器未命中时为 0", example=1)
    chapters: list[Chapter] = documented(
        description="抽出的章节，已按顺序编号",
        example=[{"order": 1, "title": "第一章", "url": "https://example.com/1.html"}],
    )
    error: str | None = documented(
        None,
        description="容器选择器未匹配时的说明。命中时为 null。此时接口 code 仍为 200",
        example="containerSelector 未匹配到元素: #list",
    )


class ExportChapter(BaseModel):
    """导出文件中的一章。"""

    model_config = with_example(_CHAPTER)

    order: int = documented(0, description="章节序号，从 1 开始", example=1)
    title: str = documented(description="章节标题", example="第一章")
    url: str = documented("", description="章节 URL", example="https://example.com/1.html")
    content: str = documented("", description="章节正文。没有正文时为空字符串", example="正文")


class ExportRequest(BaseModel):
    """把调用方提交的章节导出为文件。不会按任务 ID 读取存储。"""

    model_config = with_example({
        "title": "书名",
        "format": "txt",
        "chapters": [_CHAPTER],
    })

    title: str = documented("novel", description="书名，同时用作下载文件名", example="书名")
    format: str = documented("txt", description="导出格式：txt、json 或 csv", example="txt")
    chapters: list[ExportChapter] = documented(
        description="要导出的章节",
        example=[_CHAPTER],
    )
