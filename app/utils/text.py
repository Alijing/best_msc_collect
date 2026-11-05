import re

CHAPTER_RE = re.compile(
    r"第\s*[0-9０-９一二三四五六七八九十百千万零两]+\s*[章节回卷篇话集]"
    r"|Chapter\s*\d+"
    r"|^\s*\d{1,4}\s*[\.、,，:：]",
    re.IGNORECASE,
)

NEXT_TEXT_RE = re.compile(
    r"^\s*(下一?[页頁]|下页|next(\s*page)?|»|>>|›|→|更多|查看更多|尾页|末页)\s*$",
    re.IGNORECASE,
)


def is_chapter_like(text: str) -> bool:
    text = (text or "").strip()
    if not (1 < len(text) <= 60):
        return False
    return bool(CHAPTER_RE.search(text))


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()