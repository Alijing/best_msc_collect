"""正文容器识别：文本密度高、链接少、段落多。"""
from typing import Any, Optional

from parsel import Selector

_SKIP_TAGS = {"script", "style"}
_BREAK_TAGS = {"p", "br"}


def _text_len(el) -> int:
    return len("".join(el.xpath(".//text()").getall()).strip())


def _link_text_len(el) -> int:
    total = 0
    for a in el.xpath(".//a"):
        total += len("".join(a.xpath(".//text()").getall()))
    return total


def score_content(el) -> Optional[dict[str, Any]]:
    text_len = _text_len(el)
    if text_len < 200:
        return None

    link_len = _link_text_len(el)
    link_ratio = link_len / text_len if text_len else 1.0
    p_count = len(el.xpath(".//p")) + len(el.xpath(".//br"))
    para_score = min(p_count / 5, 1.0)
    node_count = len(el.xpath(".//*")) + 1
    density = text_len / node_count

    score = (
            min(text_len / 2000, 1.0) * 0.4
            + (1 - link_ratio) * 0.3
            + para_score * 0.2
            + min(density / 50, 1.0) * 0.1
    )

    return {
        "element": el,
        "score": score,
        "text_len": text_len,
        "link_ratio": link_ratio,
        "p_count": p_count,
    }


def pick_content_container(sel: Selector) -> Optional[dict[str, Any]]:
    candidates = sel.css(
        "div, article, section, main, "
        "#content, #chaptercontent, #chapter-content, #booktext, "
        ".content, .chapter-content, .read-content, .article-content"
    )
    best = None
    best_score = 0.0
    for c in candidates:
        r = score_content(c)
        if r and r["score"] > best_score:
            best_score = r["score"]
            best = r
    return best


def extract_text(container) -> str:
    """从已解析节点取文本。br / p 保留换行，跳过 script 与 style。"""
    root = getattr(container, "root", container)
    parts: list[str] = []

    def rec(node) -> None:
        tag = node.tag if isinstance(getattr(node, "tag", None), str) else ""
        if not tag or tag.lower() in _SKIP_TAGS:
            return
        if node.text:
            parts.append(node.text)
        for child in node:
            child_tag = child.tag if isinstance(getattr(child, "tag", None), str) else ""
            if child_tag and child_tag.lower() not in _SKIP_TAGS:
                rec(child)
                if child_tag.lower() in _BREAK_TAGS:
                    parts.append("\n")
            if child.tail:
                parts.append(child.tail)

    rec(root)
    lines = [ln.strip() for ln in "".join(parts).splitlines()]
    return "\n".join(ln for ln in lines if ln)
