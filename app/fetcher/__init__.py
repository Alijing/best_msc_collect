from app.fetcher.base import FetchResult
from app.fetcher.http_fetcher import HttpFetcher, PlaywrightUnsupported, reject_playwright

_http = HttpFetcher()


async def fetch(url: str, use_playwright: bool = False) -> FetchResult:
    reject_playwright(use_playwright)
    return await _http.fetch(url)


async def close_fetchers() -> None:
    await _http.close()
