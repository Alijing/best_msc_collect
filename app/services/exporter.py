import csv
import io
import json
from typing import Any


def to_txt(novel_title: str, chapters: list[dict[str, Any]]) -> str:
    lines = [novel_title, "=" * len(novel_title), ""]
    for ch in chapters:
        lines.append(ch["title"])
        lines.append("-" * len(ch["title"]))
        lines.append(ch.get("content", ""))
        lines.append("")
    return "\n".join(lines)


def to_json(novel_title: str, chapters: list[dict[str, Any]]) -> str:
    return json.dumps(
        {"title": novel_title, "chapters": chapters},
        ensure_ascii=False,
        indent=2,
    )


def to_csv(chapters: list[dict[str, Any]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["order", "title", "url", "content"])
    for ch in chapters:
        w.writerow([
            ch.get("order", ""),
            ch.get("title", ""),
            ch.get("url", ""),
            ch.get("content", ""),
        ])
    return buf.getvalue()