import re
from typing import Any, Optional

from parsel import Selector

from app.utils.text import is_chapter_like

_SECTION_TITLE_RE = re.compile(
    r"章节|目录|正文|全部章节|章节列表|章节目录|最新章节"
)


def _url_template(href: str) -> str:
    return re.sub(r"\d+", "#", href.split("?")[0])


def _depth(el) -> int:
    d = 0
    while el is not None:
        el = el.getparent()
        d += 1
    return d


def _node_text(node) -> str:
    return "".join(node.itertext()).strip()


def _context_bonus(container_root) -> float:
    cur = container_root
    for _ in range(3):
        if cur is None:
            break
        for h in cur.xpath(".//h1|.//h2|.//h3|.//h4"):
            text = _node_text(h)
            if _SECTION_TITLE_RE.search(text):
                return 1.0
        cur = cur.getparent()
    return 0.0


def score_container(container: Selector) -> Optional[dict[str, Any]]:
    links = container.css("a[href]")
    n = len(links)
    if n < 3:
        return None

    nodes = len(container.xpath(".//*")) + 1
    density = n / nodes

    chap_cnt = 0
    tmpl_map: dict[str, int] = {}
    total_len = 0

    for a in links:
        text = (a.xpath("string(.)").get() or "").strip()
        href = a.attrib.get("href", "")
        if is_chapter_like(text):
            chap_cnt += 1
        total_len += len(text)
        key = _url_template(href)
        tmpl_map[key] = tmpl_map.get(key, 0) + 1

    chap_ratio = chap_cnt / n
    tmpl_ratio = max(tmpl_map.values()) / n if tmpl_map else 0.0
    avg_len = total_len / n
    len_ok = 1.0 if 2 <= avg_len <= 30 else 0.3

    try:
        ctx_bonus = _context_bonus(container.root)
    except Exception:
        ctx_bonus = 0.0

    base = (
            0.35 * chap_ratio
            + 0.20 * tmpl_ratio
            + 0.10 * min(density * 3, 1.0)
            + 0.10 * len_ok
            + 0.25 * ctx_bonus
    )
    size_bonus = min(1.0, 0.5 + n / 40)

    return {
        "element": container,
        "score": base * size_bonus,
        "link_count": n,
        "chapter_ratio": chap_ratio,
        "template_ratio": tmpl_ratio,
        "density": density,
        "context_bonus": ctx_bonus,
    }


def pick_best_container(sel: Selector) -> Optional[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    for c in sel.css("div, ul, ol, dl, table, section, article, nav"):
        r = score_container(c)
        if r:
            scored.append(r)
    if not scored:
        return None

    best = scored[0]
    for r in scored[1:]:
        if r["score"] > best["score"]:
            best = r

    best_depth = _depth(best["element"].root)
    threshold = best["score"] * 0.9
    for r in scored:
        if r["score"] < threshold:
            continue
        depth = _depth(r["element"].root)
        if depth > best_depth:
            best = r
            best_depth = depth
    return best
