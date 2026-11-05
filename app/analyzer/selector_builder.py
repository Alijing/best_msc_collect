import re

_SAFE = re.compile(r"^[A-Za-z][\w-]*$")
_UTILITY_PREFIXES = (
    "p-", "px-", "py-", "m-", "mx-", "my-", "mt-", "mb-", "ml-", "mr-",
    "text-", "bg-", "border-", "rounded-", "shadow", "flex", "grid",
    "gap-", "w-", "h-", "max-", "min-", "font-",
)


def _is_utility_class(c: str) -> bool:
    return any(c.startswith(p) for p in _UTILITY_PREFIXES)


def _pick_class(cur) -> str | None:
    cls = cur.get("class")
    if not cls:
        return None
    for c in cls.split():
        if _SAFE.match(c) and not _is_utility_class(c):
            return c
    return None


def build_css_selector(element, max_depth: int = 5) -> str:
    parts: list[str] = []
    cur = element
    while cur is not None:
        tag = cur.tag
        if not isinstance(tag, str):
            break
        tag = tag.lower()
        if tag in ("html", "body"):
            break

        eid = cur.get("id")
        if eid and _SAFE.match(eid):
            parts.insert(0, f"#{eid}")
            break

        seg = tag
        cls = _pick_class(cur)
        if cls:
            seg += f".{cls}"

        parent = cur.getparent()
        if parent is not None:
            siblings = parent.xpath(f"./{tag}")
            if len(siblings) > 1:
                same = [
                    s for s in siblings
                    if (s.get("class") or "") == (cur.get("class") or "")
                ]
                if len(same) > 1:
                    idx = 1
                    for i, s in enumerate(siblings, start=1):
                        if s is cur:
                            idx = i
                            break
                    seg += f":nth-of-type({idx})"

        parts.insert(0, seg)

        if len(parts) >= max_depth:
            break
        cur = parent

    return " > ".join(parts) if parts else ""
