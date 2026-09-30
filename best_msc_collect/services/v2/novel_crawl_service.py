# -*- coding: utf-8 -*-
"""
v2 小说爬虫服务
==============

职责
----
对应 v1 的 :class:`best_msc_collect.services.novel_crawl_service.NovelCrawlService`，
但底层使用 Scrapling 引擎实现。

典型场景
--------
抓取小说站（如笔趣阁）的章节列表 + 每章正文：
1. 访问章节列表页，提取所有章节链接
2. 逐个访问章节详情页，抓取正文
3. 合并为 ``{chapters: [{title, link, contents: [{content: "..."}]}]}`` 结构返回

v1 vs v2 关键差异
----------------
+----------------------------+----------------------------+----------------------------+
| 维度                       | v1 (Selenium)              | v2 (Scrapling)             |
+============================+============================+============================+
| 引擎                       | ChromeDriver               | StealthyFetcher            |
| 反爬能力                   | 无                         | 内置反爬绕过               |
| 下级页面处理数             | 硬编码 2 条                | SCRAPLING_MAX_CHILDREN=100 |
| 自适应选择器               | 无                         | adaptive=True              |
| 返回结构                   | {data, success}            | + elapsed_ms / version     |
|                            |                            | + total_items              |
+----------------------------+----------------------------+----------------------------+
"""

import logging
import time
from typing import Dict, List, Optional

# v1 共用同一份 Pydantic 模型
from ...models.unified_model import UnifiedCollectConfig
# v2 核心采集器
from ...utils.scrapling_collector import ScraplingCollector

# 模块日志
logger = logging.getLogger(__name__)


class NovelCrawlServiceV2:
    """v2 小说爬虫服务

    业务定位
    --------
    - 接收 :class:`UnifiedCollectConfig` 列表（每个元素可含 ``lower_level_page_config``）
    - 调用 :class:`ScraplingCollector` 完成列表抓取与下级页面递归
    - 返回统一结构，含 ``success`` / ``data`` / ``version`` / ``elapsed_ms`` / ``total_items``

    与 v1 行为差异
    ------------
    - 不会像 v1 那样硬编码 2 条下级；走 ``SCRAPLING_MAX_CHILDREN`` 配置
    - 不会像 v1 那样硬编码 2 页分页；走 ``SCRAPLING_MAX_PAGES`` 配置
    - 返回新增 ``total_items`` 字段，便于前端统计展示
    """

    # 固定版本号
    VERSION = "v2"

    @staticmethod
    def collect_chapter_and_details(
        collect_config: List[UnifiedCollectConfig],
        default_config: Optional[Dict] = None,
    ) -> Dict:
        """使用 Scrapling 引擎执行小说列表与详情页采集

        Args:
            collect_config: 列表 + 详情页配置列表。典型场景只有一个根配置，
                其 ``lower_level_page_config`` 中描述详情页抓取规则。
            default_config: 默认配置字典，建议至少包含 ``fetcher`` / ``headless`` /
                ``network_idle`` / ``adaptive`` / ``proxy`` / ``max_pages`` /
                ``max_children`` / ``timeout`` 等键。来源通常是 Flask
                app.config["SCRAPLING_CONFIG"]。

        Returns:
            Dict，统一返回结构::

                {
                    "success": True/False,
                    "data": {...}，与 v1 结构兼容，由 config.data_field 决定 key 名
                    "version": "v2",
                    "elapsed_ms": <int>，采集耗时（毫秒）
                    "total_items": <int>，采集到的总记录数
                }

            失败时：``success=False``，``data`` 为空 dict，``elapsed_ms`` 仍会返回，
            ``total_items=0``，并附 ``error`` 字段。
        """
        # 记录开始时间
        start_ts = time.time()
        try:
            # ----- 参数校验 -----
            if not collect_config:
                return {
                    "success": False,
                    "data": {},
                    "version": NovelCrawlServiceV2.VERSION,
                    "elapsed_ms": int((time.time() - start_ts) * 1000),
                    "total_items": 0,
                    "error": "缺少采集配置",
                }

            default_config = default_config or {}
            logger.info(
                f"v2 novel_crawl 启动: 任务数={len(collect_config)}, "
                f"fetcher={default_config.get('fetcher', 'stealthy')}"
            )

            # ----- 实例化采集器并执行 -----
            collector = ScraplingCollector(
                collect_config,
                default_settings=default_config,
            )
            result = collector.collect_data()

            # ----- 统计 total_items -----
            # 统计原则：递归遍历 result 中所有 list 元素并累加长度
            total_items = NovelCrawlServiceV2._count_items(result)

            # ----- 包装成功结果 -----
            return {
                "success": True,
                "data": result,
                "version": NovelCrawlServiceV2.VERSION,
                "elapsed_ms": int((time.time() - start_ts) * 1000),
                "total_items": total_items,
            }
        except Exception as e:
            # 任何异常都包装为统一结构
            logger.error(f"v2 novel_crawl 失败: {e}", exc_info=True)
            return {
                "success": False,
                "data": {},
                "version": NovelCrawlServiceV2.VERSION,
                "elapsed_ms": int((time.time() - start_ts) * 1000),
                "total_items": 0,
                "error": str(e),
            }

    @staticmethod
    def _count_items(data) -> int:
        """递归统计结果中的总记录数

        统计规则
        --------
        - dict：递归累加其 value
        - list：返回长度（每个元素视为一条记录）
        - 其他：返回 0

        Args:
            data: :func:`collect_data_recursive` 的返回值（dict / list / 标量）。

        Returns:
            int，总记录数。
        """
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict):
            return sum(NovelCrawlServiceV2._count_items(v) for v in data.values())
        # 标量 / None：按 0 条记录处理
        return 0
