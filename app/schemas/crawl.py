from pydantic import BaseModel

from app.core.config import settings
from app.schemas.common import documented, with_example


class CrawlRequest(BaseModel):
    """异步抓取目录的请求。"""

    model_config = with_example({
        "url": "https://example.com/book/1/",
        "container_selector": "#list",
        "item_selector": "a",
        "next_url": "https://example.com/book/1/2.html",
        "max_pages": 20,
        "delay": 0,
        "use_playwright": False,
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
        description="目录页之间的最小间隔（秒），范围 0–10。比域名限速更严时才补足差额。默认值为配置项 DELAY_DEFAULT",
        example=0,
        ge=0,
        le=10,
    )
    use_playwright: bool = documented(
        False,
        description="是否使用浏览器渲染。当前不支持，传 true 时返回 400",
        example=False,
    )
