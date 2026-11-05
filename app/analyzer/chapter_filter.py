"""章节链接过滤：URL 模板投票 + 标题正则。"""
import re
from collections import Counter

from app.utils.text import is_chapter_like


def url_template(href: str) -> str:
    return re.sub(r"\d+", "#", href.split("?")[0].rstrip("/"))


def filter_chapters(links: list[tuple[str, str]]) -> list[tuple[str, str]]:
    if not links:
        return []

    tmpl_counter = Counter(url_template(h) for _, h in links)
    top_tmpl, top_count = tmpl_counter.most_common(1)[0]

    if len(links) >= 3 and top_count / len(links) >= 0.5:
        candidates = [(t, h) for t, h in links if url_template(h) == top_tmpl]
    else:
        candidates = links

    chapters = [(t, h) for t, h in candidates if is_chapter_like(t)]

    if len(chapters) >= max(3, int(len(links) * 0.3)):
        return chapters
    return candidates
