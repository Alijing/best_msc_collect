"""识别正文分页（区别于章节跳转）。"""
import re
from typing import Optional
from urllib.parse import urljoin, urlparse

from parsel import Selector

_NEXT_PAGE_RE = re.compile(
    r"^\s*(下一?[页頁]|下页|next(\s*page)?|»|>>|›|→)\s*$",
    re.IGNORECASE,
)

_NEXT_CHAPTER_RE = re.compile(
    r"^\s*(下一?[章节節回卷篇话集]|next\s*chapter)\s*$",
    re.IGNORECASE,
)

_INCOMPLETE_RE = re.compile(
    r"本章未完|未完待续|章节未完|请点击下一[页頁]|点击下一[页頁]继续",
)


def _same_chapter_pagination(current_url: str, candidate_url: str) -> bool:
    c = urlparse(current_url)
    n = urlparse(candidate_url)

    if c.netloc != n.netloc:
        return False

    if c.path == n.path:
        return bool(re.search(r"(?:^|&)page=\d+", n.query))

    c_no_ext = re.sub(r"\.html?$", "", c.path)
    n_no_ext = re.sub(r"\.html?$", "", n.path)

    if re.match(re.escape(c_no_ext) + r"[_-]\d+$", n_no_ext):
        return True

    m1 = re.match(r"^(.*?)[_-](\d+)$", c_no_ext)
    m2 = re.match(r"^(.*?)[_-](\d+)$", n_no_ext)
    if m1 and m2 and m1.group(1) == m2.group(1):
        return True

    return False


def detect_incomplete_hint(sel: Selector) -> bool:
    text = "".join(sel.xpath("//text()").getall())
    return bool(_INCOMPLETE_RE.search(text))


def find_content_next_page(
        sel: Selector,
        current_url: str,
        has_incomplete_hint: bool = False,
) -> Optional[str]:
    candidates: list[tuple[int, str]] = []

    for a in sel.css("a[href]"):
        href = a.attrib.get("href", "")
        if not href or href.startswith(("javascript:", "#", "mailto:")):
            continue

        text = (a.xpath("string(.)").get() or "").strip()
        if not text:
            continue

        if _NEXT_CHAPTER_RE.match(text):
            continue

        try:
            full = urljoin(current_url, href)
        except Exception:
            continue
        if full.rstrip("/") == current_url.rstrip("/"):
            continue

        score = 0
        if _NEXT_PAGE_RE.match(text):
            score += 5
        elif "下一页" in text and len(text) <= 12:
            score += 4
        elif "下页" in text and len(text) <= 8:
            score += 4
        else:
            score -= 2

        if _same_chapter_pagination(current_url, full):
            score += 4
        else:
            if score < 5:
                continue

        if has_incomplete_hint:
            score += 1

        candidates.append((score, full))

    if not candidates:
        return None

    candidates.sort(key=lambda x: -x[0])
    top_score, top_url = candidates[0]
    return top_url if top_score >= 5 else None
