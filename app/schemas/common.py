from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


def _camelize(value: Any) -> Any:
    """文档示例里的字段名改成驼峰，和接口 JSON 一致。"""
    if isinstance(value, dict):
        return {to_camel(str(key)): _camelize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_camelize(item) for item in value]
    return value


def documented(
        default: Any = ...,
        *,
        description: str,
        example: Any,
        **constraints: Any,
) -> Any:
    """给字段同时写上说明，以及文档里的示例值。"""
    shown = _camelize(example)
    params: dict[str, Any] = {
        "description": description,
        "examples": [shown],
        "json_schema_extra": {"example": shown},
        **constraints,
    }
    if "default_factory" not in constraints:
        params["default"] = default
    return Field(**params)


def with_example(example: dict[str, Any]) -> ConfigDict:
    """整个对象的示例。对外 JSON 使用驼峰，Python 字段名仍是蛇形。"""
    shown = _camelize(example)
    return ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        json_schema_extra={"example": shown, "examples": [shown]},
    )


class Chapter(BaseModel):
    """从目录页抽出的一条章节链接。"""

    model_config = with_example({
        "order": 1,
        "title": "第一章",
        "url": "https://example.com/1.html",
    })

    order: int = documented(description="章节序号，从 1 开始", example=1)
    title: str = documented(description="章节标题", example="第一章")
    url: str = documented(description="章节绝对 URL", example="https://example.com/1.html")
