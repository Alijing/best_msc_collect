from typing import Optional
from urllib.parse import urljoin, urlparse

from parsel import Selector

from app.utils.text import NEXT_TEXT_RE


def find_next_page(sel: Selector, current_url: str) -> Optional[dict[str, str]]:
    cur_path = urlparse(current_url).path
    cur_host = urlparse(current_url).netloc
    candidates: list[tuple[int, dict[str, str]]] = []

    for a in sel.css("a[href]"):
        href = a.attrib.get("href", "")
        if not href or href.startswith(("javascript:", "#", "mailto:")):
            continue
        try:
            full = urljoin(current_url, href)
        except Exception:
            continue
        if full.rstrip("/") == current_url.rstrip("/"):
            continue

        text = (a.xpath("string(.)").get() or "").strip()
        rel = (a.attrib.get("rel") or "").lower()
        score = 0

        if "next" in rel:
            score += 4
        if NEXT_TEXT_RE.match(text):
            score += 3
        elif "下一" in text and len(text) <= 6:
            score += 2

        p = urlparse(full)
        if p.path == cur_path:
            score += 2
        if p.netloc == cur_host:
            score += 1

        if score >= 3:
            candidates.append((score, {"url": full, "text": text}))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]