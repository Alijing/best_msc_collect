from __future__ import annotations  # 添加这一行以支持延迟类型注解
from typing import List, Optional, Dict
from pydantic import BaseModel, Field


class UnifiedAction(BaseModel):
    """统一的操作配置模型"""
    type: str
    selector: str
    value: Optional[str] = None

    def __init__(self, type: str, selector: str, value: Optional[str] = None, **kwargs):
        super().__init__(type=type, selector=selector, value=value, **kwargs)


class UnifiedDataExtraction(BaseModel):
    """统一的数据提取项模型"""
    field: str
    unique: Optional[bool] = False
    method: str
    selector: str
    attribute: Optional[str] = None

    def __init__(self, field: str, method: str, selector: str,
                 unique: Optional[bool] = False,
                 attribute: Optional[str] = None, **kwargs):
        super().__init__(field=field, unique=unique, method=method, selector=selector, attribute=attribute, **kwargs)


class UnifiedCollectConfig(BaseModel):
    """统一的配置模型"""
    # 目标链接
    url: Optional[str] = None
    # 返回数据字段
    data_field: Optional[str] = None
    # 下一页链接选择器
    next_page_selector: Optional[str] = None
    # 操作
    actions: List[UnifiedAction] = Field(default_factory=list)
    # 数据提取
    data_extraction: List[UnifiedDataExtraction] = Field(default_factory=list)
    # 下级页面配置
    lower_level_page_config: List[UnifiedCollectConfig] = Field(default_factory=list)

    def __init__(self, url: str = "",
                 data_field: Optional[str] = None,
                 actions: List[UnifiedAction] = None,
                 data_extraction: List[UnifiedDataExtraction] = None,
                 lower_level_page_config: List[UnifiedCollectConfig] = None,
                 **kwargs):
        if actions is None:
            actions = []
        if data_extraction is None:
            data_extraction = []
        if lower_level_page_config is None:
            lower_level_page_config = []
        super().__init__(url=url, data_field=data_field, actions=actions, data_extraction=data_extraction,
                         lower_level_page_config=lower_level_page_config, **kwargs)
