import re
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.schemas.misc import ExportRequest
from app.schemas.response import error_responses
from app.services.exporter import to_csv, to_json, to_txt

router = APIRouter(tags=["export"])


def _safe_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]', "_", name).strip() or "novel"
    return name[:80]


def _content_disposition(filename: str) -> str:
    # HTTP 头只能编码 latin-1。ASCII 名给旧客户端，filename* 保留中文。
    if "." in filename:
        stem, ext = filename.rsplit(".", 1)
    else:
        stem, ext = filename, ""
    ascii_stem = stem.encode("ascii", "ignore").decode().strip(" .") or "novel"
    ascii_ext = ext.encode("ascii", "ignore").decode()
    ascii_name = f"{ascii_stem}.{ascii_ext}" if ascii_ext else ascii_stem
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"


@router.post("/export", responses=error_responses(400))
async def export_endpoint(req: ExportRequest):
    title = _safe_filename(req.title)
    fmt = req.format.lower()
    chapters = [chapter.model_dump() for chapter in req.chapters]

    if fmt == "txt":
        body = to_txt(req.title, chapters)
        return Response(
            content=body.encode("utf-8"),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": _content_disposition(f"{title}.txt")},
        )

    if fmt == "json":
        body = to_json(req.title, chapters)
        return Response(
            content=body.encode("utf-8"),
            media_type="application/json",
            headers={"Content-Disposition": _content_disposition(f"{title}.json")},
        )

    if fmt == "csv":
        body = to_csv(chapters)
        return Response(
            content=body.encode("utf-8-sig"),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": _content_disposition(f"{title}.csv")},
        )

    raise HTTPException(status_code=400, detail="format 必须是 txt / json / csv")
