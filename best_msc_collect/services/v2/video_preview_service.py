# -*- coding: utf-8 -*-
"""
v2 视频预览服务
===============

职责
----
对应 v1 的 :class:`best_msc_collect.services.video_preview_service.VideoPreviewService`，
但底层使用 Scrapling 引擎实现（StealthyFetcher / DynamicFetcher）。

典型场景
--------
磁链 / 网盘链接预览：访问 magnet.pics 等聚合站，把磁链填入搜索框、点击预览按钮，
抓取页面中的图片列表（缩略图），返回给调用方。

v1 vs v2 关键差异
----------------
+----------------------------+----------------------------+----------------------------+
| 维度                       | v1 (Selenium)              | v2 (Scrapling)             |
+============================+============================+============================+
| 引擎                       | ChromeDriver               | StealthyFetcher            |
| 反爬能力                   | 无（容易被识别为机器人）   | 内置 Cloudflare Turnstile  |
| 入参 url 副作用            | 直接修改入参（bug）        | 拷贝后再修改（已修复）     |
| 抓取页数限制               | 硬编码 2 页                | SCRAPLING_MAX_PAGES=50     |
| 返回结构                   | {data, success}            | + elapsed_ms / version     |
+----------------------------+----------------------------+----------------------------+
"""

import logging
import time
from typing import Dict, Optional

# v1 共用同一份 Pydantic 模型，保证入参兼容
from ...models.unified_model import UnifiedCollectConfig
# v2 核心采集器
from ...utils.scrapling_collector import ScraplingCollector

# 模块日志（由 app.py 统一接管配置）
logger = logging.getLogger(__name__)


class VideoPreviewServiceV2:
    """v2 视频预览服务

    业务定位
    --------
    - 接收一个 :class:`UnifiedCollectConfig` 配置（含 actions 与 data_extraction）
    - 强制使用 ``default_config`` 中的 ``preview_url`` 作为目标页面
    - 调用 :class:`ScraplingCollector` 完成 actions 与数据提取
    - 返回统一结构 ``{success, data, version, elapsed_ms}``

    使用示例
    --------
    >>> from best_msc_collect.models.unified_model import UnifiedCollectConfig, UnifiedAction, UnifiedDataExtraction
    >>> config = UnifiedCollectConfig(
    ...     data_field="videoPreview",
    ...     actions=[UnifiedAction(type="fill", selector=".magnet-input", value="magnet:..."),
    ...              UnifiedAction(type="click", selector=".preview-button")],
    ...     data_extraction=[UnifiedDataExtraction(field="imageUrls", method="attribute",
    ...                                             selector=".thumb-item img", attribute="src")],
    ... )
    >>> result = VideoPreviewServiceV2.video_preview(config, default_config={"preview_url": "..."})
    """

    # 固定版本号字段，便于调用方识别返回来源
    VERSION = "v2"

    @staticmethod
    def video_preview(
        collect_config: UnifiedCollectConfig,
        default_config: Optional[Dict] = None,
    ) -> Dict:
        """使用 Scrapling 引擎执行视频预览

        Args:
            collect_config: 采集配置，必需含 ``actions`` 与 ``data_extraction``；
                ``url`` 字段会被 ``default_config["preview_url"]`` 覆盖。
            default_config: 默认配置字典，建议至少包含 ``preview_url``、``fetcher``、
                ``headless``、``network_idle``、``adaptive``、``proxy``、``max_pages``、
                ``timeout`` 等键。来源通常是 Flask app.config["SCRAPLING_CONFIG"]。

        Returns:
            Dict，统一返回结构::

                {
                    "success": True/False,
                    "data": {<data_field>: [...]} 或 {}，
                    "version": "v2",
                    "elapsed_ms": <int>，采集耗时（毫秒）
                }

            失败时：``success=False``，``data`` 为空 dict，``elapsed_ms`` 仍会返回便于排查。
        """
        # 记录开始时间，用于计算 elapsed_ms
        start_ts = time.time()
        try:
            # ----- 参数校验 -----
            if not collect_config:
                return {
                    "success": False,
                    "data": {},
                    "version": VideoPreviewServiceV2.VERSION,
                    "elapsed_ms": int((time.time() - start_ts) * 1000),
                    "error": "缺少采集配置",
                }

            # ----- 修复 v1 bug：使用深拷贝避免污染调用方入参 -----
            # v1 的实现直接执行 `collect_config.url = default_config.get('preview_url')`，
            # 会永久修改 Pydantic 对象，进而污染同一请求后续的日志/重试逻辑。
            # v2 通过 model_copy() 创建深拷贝，仅修改副本。
            config_copy = collect_config.model_copy(deep=True)
            default_config = default_config or {}
            # 优化 #3：区分"preview_url 未配置"和"preview_url 配置为空串"
            # 用 `in` 判定：未配置时回退到 config_copy.url（v1 行为），配置为空串时强制使用空串
            if "preview_url" in default_config:
                config_copy.url = default_config["preview_url"] or config_copy.url
            # 否则保留 config_copy.url（用户请求里传的 url）

            logger.info(
                f"v2 video_preview 启动: preview_url={config_copy.url}, "
                f"fetcher={default_config.get('fetcher', 'stealthy')}"
            )

            # ----- 实例化采集器并执行 -----
            # 注意：ScraplingCollector 内部已处理 max_pages / max_children 等配置项
            collector = ScraplingCollector(
                [config_copy],                # 包成列表，与 collect_data_recursive 签名一致
                default_settings=default_config,
            )
            result = collector.collect_data()

            # ----- 包装成功结果 -----
            return {
                "success": True,
                "data": result,
                "version": VideoPreviewServiceV2.VERSION,
                "elapsed_ms": int((time.time() - start_ts) * 1000),
            }
        except Exception as e:
            # 任何异常都包装为统一结构（route 层不再需要 try/except）
            logger.error(f"v2 video_preview 失败: {e}", exc_info=True)
            return {
                "success": False,
                "data": {},
                "version": VideoPreviewServiceV2.VERSION,
                "elapsed_ms": int((time.time() - start_ts) * 1000),
                "error": str(e),
            }
