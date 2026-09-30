# -*- coding: utf-8 -*-
"""
v2 API 路由蓝图
===============

本模块定义 v2 版本对外暴露的 HTTP 接口，挂在 ``/api/v2`` 前缀下。
与 v1（``routes/api.py``）并行运行，调用方可按需选择 v1 或 v2。

API 列表
--------
- ``GET  /api/v2/health``            健康检查
- ``POST /api/v2/video/preview``     视频预览（Scrapling 引擎）
- ``POST /api/v2/novel/crawl``       小说列表 + 详情页采集（Scrapling 引擎）

设计要点
--------
1. **不修改入参对象**：所有入参校验后立即转 Pydantic 模型，service 层再 ``model_copy(deep=True)``。
2. **统一返回结构**：所有接口均返回 ``{success, version, ...}``，便于客户端判断。
3. **参数校验显式化**：用 Pydantic 显式校验并返回 400 + 错误明细，比 v1 的 ``@validate()`` 装饰器
   错误处理更可控（v1 的 ``handle_validation_error`` 会过滤掉 ``url`` 字段，体验较差）。
4. **绝不抛出未捕获异常**：每个路由均包 try/except，保证 HTTP 200/500/400 三态。
"""

import logging
from typing import List

from flask import Blueprint, jsonify, current_app, request
from pydantic import ValidationError as PydanticValidationError

# v2 业务服务（基于 Scrapling）
from ..services.v2 import VideoPreviewServiceV2, NovelCrawlServiceV2

# 统一的 Pydantic 配置模型（与 v1 共用）
from ..models.unified_model import UnifiedCollectConfig

# 当前模块的日志记录器
logger = logging.getLogger(__name__)

# 固定 API 版本号，与 service 中的 VERSION 对齐
API_VERSION = "v2"

# v2 蓝图对象（在 app.py 中注册并设置 url_prefix='/api/v2'）
v2_api_bp = Blueprint("v2_api", __name__)


# ----------------------------------------------------------------------
# 通用工具方法
# ----------------------------------------------------------------------


def _error_response(error_msg: str, http_status: int = 500, details=None):
    """构造统一结构的错误响应

    Args:
        error_msg: 错误描述（中文/英文均可），将放入 ``error`` 字段。
        http_status: HTTP 状态码，默认 500；参数校验失败时传 400。
        details: 可选，附加错误明细（如 Pydantic 的字段错误列表）。

    Returns:
        Flask ``Response`` 对象，已 ``jsonify`` 并设置好 status_code。
    """
    payload = {
        "success": False,
        "version": API_VERSION,
        "error": error_msg,
    }
    if details is not None:
        payload["details"] = details
    return jsonify(payload), http_status


def _success_response(data: dict, http_status: int = 200):
    """构造统一结构的成功响应

    Args:
        data: 业务数据字典（service 层返回的完整结构）。
        http_status: HTTP 状态码，默认 200。

    Returns:
        Flask ``Response`` 对象。
    """
    # 在 data 顶层补 version 字段（如果 service 还没带）
    if isinstance(data, dict) and "version" not in data:
        data = {**data, "version": API_VERSION}
    return jsonify(data), http_status


# ----------------------------------------------------------------------
# 优化 #4：异常分类 → HTTP 状态码
# ----------------------------------------------------------------------


def _classify_exception(e: Exception) -> int:
    """根据异常类型推断合适的 HTTP 状态码

    分类规则
    --------
    - Pydantic / 自定义 ValueError → 400（参数错误）
    - 连接 / 网络错误 → 502（上游错误）
    - 超时 → 504（网关超时）
    - 反爬拦截（403/429）→ 503（服务不可用，重试可能恢复）
    - 其他未预期异常 → 500

    Args:
        e: 捕获的异常实例。

    Returns:
        推荐的 HTTP 状态码。
    """
    # 优先按类型匹配（不依赖异常 message，更可靠）
    # 延迟导入 scrapling/patchright 异常类，避免启动期就强依赖
    try:
        from patchright._impl._errors import TimeoutError as PlaywrightTimeoutError

        if isinstance(e, PlaywrightTimeoutError):
            return 504
    except ImportError:
        pass

    # 连接 / 网络错误（scrapling Fetcher 抛的）
    if isinstance(e, ConnectionError):
        return 502
    if isinstance(e, TimeoutError):
        return 504

    # 反爬拦截：尝试从 message 中识别 403/429
    msg = str(e).lower()
    if "403" in msg or "forbidden" in msg:
        return 503
    if "429" in msg or "too many" in msg:
        return 503
    if "captcha" in msg or "cloudflare" in msg:
        return 503

    # 参数错误
    if isinstance(e, ValueError):
        return 400

    # 默认：未预期错误
    return 500


# ----------------------------------------------------------------------
# 路由：API 文档（优化 #6）
# ----------------------------------------------------------------------


@v2_api_bp.route("/docs", methods=["GET"])
def api_docs():
    """v2 API 自描述文档端点

    返回 v2 的可用 fetcher / data_extraction method / 路由清单等元数据，
    便于前端集成时动态发现能力，无需查 README。

    Returns:
        JSON: 包含 fetcher、method、路由列表的字典。
    """
    return (
        jsonify(
            {
                "version": API_VERSION,
                "engine": "scrapling",
                "fetchers": {
                    "fetcher": {
                        "type": "http",
                        "speed": "fastest",
                        "support_js": False,
                        "support_actions": False,
                        "description": "纯 HTTP 抓取，TLS 指纹伪装，适合 API/静态站",
                    },
                    "dynamic": {
                        "type": "browser",
                        "speed": "medium",
                        "support_js": True,
                        "support_actions": True,
                        "description": "Playwright 浏览器，支持 JS 与 actions",
                    },
                    "stealthy": {
                        "type": "browser",
                        "speed": "slow",
                        "support_js": True,
                        "support_actions": True,
                        "description": "隐身浏览器（patchright），可绕过 Cloudflare/反爬",
                    },
                },
                "extraction_methods": [
            "text: 元素直接文本（lxml .text），子元素内文本取不到",
            "all_text: 递归取所有子元素文本（推荐，适用含子元素的混排场景）",
            "attribute: 元素属性（需指定 attribute 字段）",
            "xpath: XPath 表达式",
            "regex: 对页面原始文本按正则提取（selector 复用为 pattern）",
        ],
                "action_types": ["fill", "click"],
                "endpoints": [
                    {
                        "method": "GET",
                        "path": "/api/v2/health",
                        "description": "健康检查",
                    },
                    {
                        "method": "GET",
                        "path": "/api/v2/docs",
                        "description": "本自描述端点",
                    },
                    {
                        "method": "POST",
                        "path": "/api/v2/video/preview",
                        "description": "视频预览",
                    },
                    {
                        "method": "POST",
                        "path": "/api/v2/novel/crawl",
                        "description": "小说列表+详情采集",
                    },
                ],
                "config_keys": [
                    "fetcher",
                    "headless",
                    "network_idle",
                    "adaptive",
                    "proxy",
                    "max_pages",
                    "max_children",
                    "timeout",
                ],
            }
        ),
        200,
    )


# ----------------------------------------------------------------------
# 路由：健康检查
# ----------------------------------------------------------------------


@v2_api_bp.route("/health", methods=["GET"])
def health_check():
    """v2 健康检查接口

    Returns:
        JSON: ``{"status": "healthy", "version": "v2", "message": "..."}``
    """
    return (
        jsonify(
            {
                "status": "healthy",
                "version": API_VERSION,
                "message": f"Best MSC Collect Service {API_VERSION} is running (Scrapling engine)",
            }
        ),
        200,
    )


# ----------------------------------------------------------------------
# 路由：视频预览
# ----------------------------------------------------------------------


@v2_api_bp.route("/video/preview", methods=["POST"])
def video_preview():
    """v2 视频预览接口（基于 Scrapling 引擎）

    请求体格式
    ----------
    单个 JSON 对象，结构与 v1 的 ``/api/video/preview`` 一致::

        {
            "data_field": "videoPreview",
            "actions": [{"type": "fill", "selector": ".magnet-input", "value": "magnet:..."},
                        {"type": "click", "selector": ".preview-button"}],
            "data_extraction": [{"field": "imageUrls", "method": "attribute",
                                  "selector": ".thumb-item img", "attribute": "src"}]
        }

    说明
    ----
    - 不需要传 ``url`` 字段：service 层会从 ``SCRAPLING_CONFIG.preview_url`` 强制覆盖
    - 失败时返回 HTTP 500 + ``{success:false, error, version}``
    - 参数不合法时返回 HTTP 400 + ``{success:false, error, details, version}``
    """
    try:
        # ----- 1. 读取并校验请求体 -----
        # 显式读取 JSON 便于自定义错误返回（v1 用的 @validate() 错误结构对前端不够友好）
        raw = request.get_json()
        if not raw or not isinstance(raw, dict):
            return _error_response("请求体必须为 JSON 对象", http_status=400)

        # 用 Pydantic 模型校验入参（缺失必填字段或类型错误时抛 ValidationError）
        try:
            body: UnifiedCollectConfig = UnifiedCollectConfig(**raw)
        except PydanticValidationError as e:
            # 将 Pydantic 错误明细原样返回，便于前端定位
            logger.warning(f"v2 video_preview 参数校验失败: {e.errors()}")
            return _error_response("参数验证失败", http_status=400, details=e.errors())

        # ----- 2. 调用 service 层 -----
        # default_config 来自 app.config['SCRAPLING_CONFIG']，包含 fetcher/headless 等
        default_config = current_app.config.get("SCRAPLING_CONFIG", {})
        result = VideoPreviewServiceV2.video_preview(
            body, default_config=default_config
        )

        # ----- 3. 包装返回 -----
        # service 已返回 success 字段，按 success 决定 HTTP 状态码
        return _success_response(
            result, http_status=200 if result.get("success") else 500
        )

    except Exception as e:
        # 兜底：任何未预期异常都按分类器返回合适状态码（绝不让 Flask 默认 500 页面泄漏）
        http_status = _classify_exception(e)
        logger.error(f"v2 video_preview 接口异常: {e}", exc_info=True)
        return _error_response(str(e), http_status=http_status)


# ----------------------------------------------------------------------
# 路由：小说采集
# ----------------------------------------------------------------------


@v2_api_bp.route("/novel/crawl", methods=["POST"])
def novel_crawl():
    """v2 小说列表 + 详情页采集接口（基于 Scrapling 引擎）

    请求体格式
    ----------
    JSON 数组，元素结构与 v1 的 ``/api/novel/crawl`` 一致::

        [
            {
                "url": "https://example.com/novel/",
                "data_field": "chapters",
                "next_page_selector": ".listpage .right a",
                "actions": [],
                "data_extraction": [
                    {"field": "title", "method": "text", "selector": ".panel-chapterlist dd a"},
                    {"field": "link", "unique": true, "method": "attribute",
                     "selector": ".panel-chapterlist dd a", "attribute": "href"}
                ],
                "lower_level_page_config": [
                    {
                        "url": "link",
                        "data_field": "contents",
                        "data_extraction": [{"field": "content", "method": "text",
                                              "selector": "#content"}]
                    }
                ]
            }
        ]

    说明
    ----
    - 与 v1 不同：v2 真正用 ``flask-pydantic`` 风格的显式校验（修复 v1 绕过 ``@validate()`` 的问题）
    - 返回新增 ``total_items`` / ``elapsed_ms`` / ``version`` 字段
    """
    try:
        # ----- 1. 读取并校验请求体 -----
        raw = request.get_json()
        if not raw or not isinstance(raw, list):
            return _error_response("请求体必须为 JSON 数组", http_status=400)

        # 逐项 Pydantic 校验
        try:
            body: List[UnifiedCollectConfig] = [
                UnifiedCollectConfig(**item) for item in raw
            ]
        except PydanticValidationError as e:
            logger.warning(f"v2 novel_crawl 参数校验失败: {e.errors()}")
            return _error_response("参数验证失败", http_status=400, details=e.errors())

        # ----- 2. 调用 service 层 -----
        default_config = current_app.config.get("SCRAPLING_CONFIG", {})
        result = NovelCrawlServiceV2.collect_chapter_and_details(
            body,
            default_config=default_config,
        )

        # ----- 3. 包装返回 -----
        return _success_response(
            result, http_status=200 if result.get("success") else 500
        )

    except Exception as e:
        http_status = _classify_exception(e)
        logger.error(f"v2 novel_crawl 接口异常: {e}", exc_info=True)
        return _error_response(str(e), http_status=http_status)
