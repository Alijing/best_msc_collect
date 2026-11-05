import pytest

from app.analyzer.content_extractor import extract_text
from app.fetcher.base import FetchResult
from app.parser.html_parser import parse_html
from app.services.content_service import _extract_page, fetch_content
from app.services.novel_service import should_report_progress

PARAGRAPH = "山风" * 120
HTML = f"""<html><head><title>章标题</title></head><body>
<div class="nav">导航</div>
<div id="chaptercontent"><p>{PARAGRAPH}</p><p>甲<br/>乙</p><script>广告脚本</script></div>
</body></html>"""


def test_extract_text_keeps_breaks_and_skips_script():
    node = parse_html("<div><p>甲<br/>乙</p><script>广告脚本</script>丙</div>").css("div")[0]
    text = extract_text(node)
    assert text == "甲\n乙\n丙"
    assert "广告脚本" not in text


def test_extract_page_reuses_selector_without_rescore(monkeypatch):
    calls = {"n": 0}
    from app.services import content_service

    real = content_service.pick_content_container

    def wrapped(sel):
        calls["n"] += 1
        return real(sel)

    monkeypatch.setattr(content_service, "pick_content_container", wrapped)
    first = _extract_page(HTML, None, False, False, "https://example.com/1.html", False)
    assert first["selector"]
    assert calls["n"] == 1
    assert "广告脚本" not in first["text"]
    assert PARAGRAPH in first["text"]

    second = _extract_page(
        HTML, first["selector"], False, False, "https://example.com/2.html", False,
    )
    assert second.get("error") is None
    assert calls["n"] == 1
    assert PARAGRAPH in second["text"]


def test_locked_selector_does_not_rescore():
    page = _extract_page(
        HTML, "#missing", True, False, "https://example.com/1.html", False,
    )
    assert "未匹配" in page["error"]


def test_should_report_progress_batches_updates():
    assert should_report_progress(1, 100, 0, 0.0, 0.1) is False
    assert should_report_progress(1, 100, 0, 0.0, 0.5) is True
    assert should_report_progress(20, 100, 0, 0.0, 0.0) is True
    assert should_report_progress(5, 5, 4, 10.0, 10.1) is True


@pytest.mark.asyncio
async def test_fetch_content_returns_learned_selector(monkeypatch):
    async def fake_fetch(url: str, use_playwright: bool = False) -> FetchResult:
        return FetchResult(url=url, status=200, html=HTML, final_url=url)

    async def fake_acquire(_url: str) -> None:
        return None

    monkeypatch.setattr("app.services.content_service.fetch", fake_fetch)
    monkeypatch.setattr("app.services.content_service.rate_limiter.acquire", fake_acquire)

    result = await fetch_content(
        "https://example.com/1.html",
        follow_pagination=False,
        clean=False,
    )
    assert result["content_selector"]
    assert result["title"] == "章标题"
    assert PARAGRAPH in result["content"]
    assert "广告脚本" not in result["content"]
