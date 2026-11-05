from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

from app.schemas.common import documented, with_example

T = TypeVar("T")


class HealthData(BaseModel):
    """健康检查结果。"""

    model_config = with_example({"status": "ok", "app": "BEST MSC COLLECT"})

    status: str = documented(description="进程是否可用。正常为 ok", example="ok")
    app: str = documented(description="服务名称", example="BEST MSC COLLECT")


class ApiResponse(BaseModel, Generic[T]):
    """所有 JSON 接口共用的响应外壳。"""

    code: int = documented(
        description="业务状态码：200 成功，500 失败，其他值见业务定义",
        example=200,
    )
    msg: str = documented(
        description="提示信息：成功时为 ok，失败时为错误描述",
        example="ok",
    )
    data: T | None = Field(
        ...,
        description="业务数据：可为任意类型（分页对象、实体、列表等）",
    )

    @classmethod
    def ok(cls, data: T | None = None, msg: str = "ok") -> "ApiResponse[T]":
        return cls(code=200, msg=msg, data=data)

    @classmethod
    def fail(cls, code: int, msg: str) -> "ApiResponse[T]":
        return cls(code=code, msg=msg, data=None)


def error_responses(*codes: int) -> dict[int, dict[str, Any]]:
    """OpenAPI 里列出的错误响应，结构和成功响应一致。"""
    descriptions = {
        400: "请求错误",
        404: "资源不存在",
        429: "请求过多",
        500: "服务器错误",
        502: "上游抓取失败",
    }
    return {
        code: {
            "model": ApiResponse[None],
            "description": descriptions.get(code, "请求失败"),
        }
        for code in codes
    }
