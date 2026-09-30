import logging
from typing import List, Dict

from ..models.unified_model import UnifiedCollectConfig
from ..utils.web_collector import WebDataCollector

logger = logging.getLogger(__name__)


class NovelCrawlService:
    """小说爬虫服务"""

    @staticmethod
    def collect_chapter_and_details(collect_config: List[UnifiedCollectConfig],
                                    default_config: Dict = None) -> Dict:
        """
        使用WebCollectData收集小说章节和详情页数据

        Args:
            collect_config: 列表-详情页配置
            default_config: 默认配置

        Returns:
            Dict: 包含成功状态和数据或错误信息的字典
        """

        try:
            if not collect_config:
                return {
                    "success": False,
                    "error": "缺少列表-详情页配置"
                }

            # 创建WebCollectData实例用于列表页数据收集
            list_collector = WebDataCollector(
                collect_config,
                default_config.get('chromedriver_path') if default_config else None,
                default_config.get('headless', True) if default_config else True
            )

            # 收集列表和详情页数据
            result = list_collector.collect_data()

            return {
                "success": True,
                "data": result
            }

        except Exception as e:
            logger.error(f"收集小说列表和详情页数据时发生错误: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
