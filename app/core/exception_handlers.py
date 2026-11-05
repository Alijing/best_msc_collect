import json
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.response import ApiResponse

logger = logging.getLogger(__name__)


def _detail_message(detail: Any) -> str:
    if detail is None or detail == "":
        return "请求失败"
    if isinstance(detail, str):
        return detail
    return str(detail)


def _validation_message(exc: RequestValidationError) -> str:
    parts: list[str] = []
    for err in exc.errors():
        loc = [
            str(item)
            for item in err.get("loc", ())
            if str(item) not in {"body", "query", "path", "header"}
        ]
        field = ".".join(loc)
        msg = err.get("msg") or "参数错误"
        parts.append(f"{field}: {msg}" if field else msg)
    return "；".join(parts) or "请求参数错误"


def _json_error(status_code: int, msg: str) -> JSONResponse:
    body = ApiResponse[None].fail(status_code, msg).model_dump()
    return JSONResponse(status_code=status_code, content=body)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _json_error(exc.status_code, _detail_message(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return _json_error(422, _validation_message(exc))

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("未处理异常 %s %s", request.method, request.url.path)
        return _json_error(500, "服务器内部错误")


def use_unified_openapi(app: FastAPI) -> None:
    """参数校验失败在文档里也展示为 code / msg / data，而不是 detail。"""
    original = app.openapi
    error_schema = ApiResponse[None].model_json_schema()
    error_schema.pop("title", None)

    def custom_openapi():
        schema = original()
        for path_item in schema.get("paths", {}).values():
            for operation in path_item.values():
                if not isinstance(operation, dict):
                    continue
                responses = operation.get("responses")
                if not isinstance(responses, dict) or "422" not in responses:
                    continue
                responses["422"] = {
                    "description": "请求参数校验失败",
                    "content": {"application/json": {"schema": error_schema}},
                }
        _drop_unused_validation_schemas(schema)
        return schema

    app.openapi = custom_openapi


def _drop_unused_validation_schemas(schema: dict) -> None:
    """422 已改为统一结构后，去掉 FastAPI 默认的 detail 模型。"""
    components = schema.get("components", {}).get("schemas", {})
    stale = [name for name in ("HTTPValidationError", "ValidationError") if name in components]
    if not stale:
        return
    rest = {name: body for name, body in components.items() if name not in stale}
    referenced = json.dumps({"paths": schema.get("paths", {}), "schemas": rest})
    for name in stale:
        if f"#/components/schemas/{name}" not in referenced:
            components.pop(name, None)
