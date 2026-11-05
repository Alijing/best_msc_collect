from fastapi import HTTPException

from app.core.background import active_count
from app.core.config import settings
from app.fetcher.http_fetcher import reject_playwright
from app.utils.url import assert_safe_url


async def prepare_background(url: str, use_playwright: bool = False) -> None:
    reject_playwright(use_playwright)
    if active_count() >= settings.MAX_BACKGROUND_TASKS:
        raise HTTPException(status_code=429, detail="后台任务过多，请稍后重试")
    await assert_safe_url(url)
