"""从容器里抽出标题和 href。分析、目录、提取共用。"""
from app.utils.text import clean_text


def collect_links(container, item_selector: str = "a") -> list[tuple[str, str]]:
    selector = item_selector or "a"
    raw: list[tuple[str, str]] = []
    for anchor in container.css(selector):
        title = clean_text(anchor.xpath("string(.)").get() or "")
        href = anchor.attrib.get("href", "")
        if not title or not href:
            continue
        raw.append((title, href))
    return raw
