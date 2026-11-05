import re

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.fetcher.base import FetchResult
from app.utils.url import UnsafeURLError, assert_safe_url

_CHARSET_RE = re.compile(r"charset\s*=\s*['\"]?\s*([\w.:-]+)", re.I)


class RetryableHTTPError(httpx.HTTPError):
    """可重试的 HTTP 错误（403/429/503）。"""


class PlaywrightUnsupported(ValueError):
    pass


def reject_playwright(use_playwright: bool) -> None:
    if use_playwright:
        raise PlaywrightUnsupported("当前不支持 usePlaywright")


def decode_html(content: bytes, content_type: str | None) -> str:
    charset = None
    if content_type:
        matched = _CHARSET_RE.search(content_type)
        if matched:
            charset = matched.group(1)
    if not charset:
        head = content[:4096].decode("latin-1", errors="ignore")
        matched = _CHARSET_RE.search(head)
        if matched:
            charset = matched.group(1)
    if not charset and content.startswith(b"\xef\xbb\xbf"):
        charset = "utf-8-sig"
    try:
        return content.decode(charset or "utf-8")
    except (LookupError, UnicodeDecodeError):
        return content.decode("utf-8", errors="replace")


async def read_capped(resp: httpx.Response, limit: int) -> bytes:
    buf = bytearray()
    async for chunk in resp.aiter_bytes():
        if len(buf) + len(chunk) > limit:
            raise ValueError(f"响应过大: 超过 {limit} bytes")
        buf.extend(chunk)
    return bytes(buf)


class HttpFetcher:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=settings.HTTP_TIMEOUT,
            follow_redirects=True,
            max_redirects=settings.MAX_REDIRECTS,
            event_hooks={"response": [self._on_response]},
            headers={
                "User-Agent": settings.USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )

    async def _on_response(self, response: httpx.Response) -> None:
        if not response.is_redirect:
            return
        location = response.headers.get("location")
        if not location:
            return
        await assert_safe_url(str(response.url.join(location)))

    async def _do_request(self, url: str) -> FetchResult:
        async with self._client.stream("GET", url) as resp:
            if resp.status_code in (403, 429, 503):
                raise RetryableHTTPError(
                    f"被限流或封禁: {resp.status_code}",
                    request=resp.request,
                )
            resp.raise_for_status()
            content = await read_capped(resp, settings.MAX_RESPONSE_SIZE)
            return FetchResult(
                url=url,
                status=resp.status_code,
                html=decode_html(content, resp.headers.get("content-type")),
                final_url=str(resp.url),
            )

    async def fetch(self, url: str) -> FetchResult:
        await assert_safe_url(url)

        async for attempt in AsyncRetrying(
                stop=stop_after_attempt(settings.HTTP_RETRY_ATTEMPTS),
                wait=wait_exponential(
                    multiplier=1.0,
                    min=settings.HTTP_RETRY_MIN_WAIT,
                    max=settings.HTTP_RETRY_MAX_WAIT,
                ),
                retry=retry_if_exception_type(
                    (
                            httpx.TimeoutException,
                            httpx.ConnectError,
                            httpx.ReadError,
                            httpx.RemoteProtocolError,
                            RetryableHTTPError,
                    )
                ),
                reraise=True,
        ):
            with attempt:
                return await self._do_request(url)

        raise RuntimeError("unreachable")

    async def close(self) -> None:
        await self._client.aclose()
