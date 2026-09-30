# -*- coding: utf-8 -*-
"""
Best MSC Collect Service - v2 业务服务层
========================================

本包是 v2 版本的服务层实现，基于 Scrapling 引擎（参见 :mod:`best_msc_collect.utils.scrapling_collector`）。
对外暴露的入口与 v1 完全一致（同一份 Pydantic 模型），但实现细节与返回结构略有增强：

- 不再依赖 Selenium + ChromeDriver
- 默认使用 StealthyFetcher（反爬绕过）
- 支持 adaptive 自适应选择器
- 返回结构新增 ``version`` / ``elapsed_ms`` / ``total_items`` 等元信息
- 修复了 v1 中 ``video_preview_service`` 直接修改入参 url 的副作用 bug

v1 服务包（:mod:`best_msc_collect.services`）继续保留，旧 API 仍然可用。
"""

# 显式导出两个 service 类，便于上层 `from best_msc_collect.services.v2 import XxxServiceV2`
from .video_preview_service import VideoPreviewServiceV2
from .novel_crawl_service import NovelCrawlServiceV2

# 公开 API
__all__ = ["VideoPreviewServiceV2", "NovelCrawlServiceV2"]
