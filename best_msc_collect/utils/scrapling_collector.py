# -*- coding: utf-8 -*-
"""
基于 Scrapling 的网页数据采集器（v2 核心模块）
============================================

模块定位
--------
本模块是 Best MSC Collect Service 的 v2 版本核心采集器，取代 v1 中基于 Selenium + ChromeDriver
的实现（见 ``web_collector.py``）。它封装了 Scrapling 库提供的能力，向上层 service 提供统一、可配置、
可递归的网页数据采集 API。

与 v1 的差异
-----------
1. 引擎切换：Selenium（慢、需 ChromeDriver）→ Scrapling（Playwright + curl_cffi）
2. 反爬能力：无 → 内置 StealthyFetcher 可绕过 Cloudflare Turnstile
3. 选择器：仅 CSS → CSS + XPath + 文本/正则
4. 自适应：网站改版即崩 → ``adaptive=True`` 自动重定位元素
5. 限制去除：v1 硬编码最多 2 页 / 2 条下级 → 本版本通过 ``max_pages`` / ``max_children`` 配置
6. 副作用：v1 的 video_preview 直接修改入参 url → 本版本统一使用深拷贝传递

Fetcher 选择指南
---------------
+---------------+----------------+------------------+----------------+
| Fetcher       | 速度           | 是否支持 actions | 典型场景       |
+===============+================+==================+================+
| fetcher       | 极快（纯 HTTP）| 否               | 静态页、API    |
| dynamic       | 中             | 是               | 需 JS 渲染     |
| stealthy      | 中             | 是               | 有反爬/验证码  |
+---------------+----------------+------------------+----------------+
默认使用 ``stealthy``，兼顾功能与反爬能力。
"""

import logging
import re
import traceback
from typing import List, Dict, Any, Optional
from urllib.parse import (
    urljoin,
)  # 用于相对/绝对 url 智能拼接，替代 v1 字符串拼接（修复 base_url="" 时的翻页 bug）

# 引入统一配置模型（与 v1 共用，保持 API 兼容）
from ..models.unified_model import UnifiedCollectConfig, UnifiedAction

# 获取当前模块的日志记录器，会被 app.py 中 setup_logging 配置统一接管
logger = logging.getLogger(__name__)


class ScraplingCollector:
    """基于 Scrapling 的网页数据采集器（v2 核心类）

    职责
    ----
    1. 接收 ``UnifiedCollectConfig`` 配置列表（可能嵌套 ``lower_level_page_config``）
    2. 按需选择 Fetcher（``fetcher`` / ``dynamic`` / ``stealthy``）抓取页面
    3. 在动态页面上执行 actions（fill / click）
    4. 按多种 method（text / attribute / xpath / regex）提取数据
    5. 递归处理多级页面与分页

    典型用法
    --------
    >>> from best_msc_collect.models.unified_model import UnifiedCollectConfig
    >>> from best_msc_collect.utils.scrapling_collector import ScraplingCollector
    >>> configs = [UnifiedCollectConfig(url="https://example.com", ...)]
    >>> collector = ScraplingCollector(configs, default_settings={"fetcher": "stealthy"})
    >>> data = collector.collect_data()
    """

    # 类级别默认配置，作为兜底；实例化时可被 default_settings 覆盖
    DEFAULT_SETTINGS = {
        "fetcher": "stealthy",  # 默认抓取器：反爬隐身模式
        "headless": True,  # 浏览器无头模式（生产环境推荐）
        "network_idle": True,  # 抓取时等待网络空闲（动态页必备）
        "adaptive": True,  # 自适应选择器：网站改版后自动重新定位
        "proxy": None,  # 代理地址，例如 "http://127.0.0.1:7890"
        "max_pages": 50,  # 分页抓取最大页数（去除 v1 的 2 页硬编码）
        "max_children": 100,  # 下级页面最大处理数（去除 v1 的 2 条硬编码）
        "timeout": 30000,  # 单次请求超时（单位：毫秒；30000 = 30 秒）
        "concurrent_children": False,  # 优化 #2：下级页面并发抓取（默认关闭，避免 scrapling 浏览器实例竞争）
        "max_workers": 4,  # 优化 #2：并发抓取时的最大 worker 数
    }

    def __init__(
        self,
        config: List[UnifiedCollectConfig],
        default_settings: Optional[Dict] = None,
    ):
        """初始化采集器

        Args:
            config: 统一采集配置列表；通常只有一个根配置，其内部 ``lower_level_page_config``
                    用于嵌套下级页面。注意：本参数会被实例保留（不修改），递归时通过深拷贝传递
                    以避免污染调用方入参（修复 v1 的副作用 bug）。
            default_settings: 覆盖默认设置的字典，键必须存在于 ``DEFAULT_SETTINGS`` 中；
                    值为 ``None`` 的项不会覆盖默认设置。

        Attributes:
            self.config: 入参配置列表（只读语义，实际由调用方负责不修改）
            self.settings: 合并后的运行时配置
        """
        self.config = config
        # 先拷贝一份默认值，避免修改类级别 dict
        self.settings = dict(self.DEFAULT_SETTINGS)
        # 合并调用方传入的设置：仅在值非 None 且键已知时覆盖
        if default_settings:
            for k, v in default_settings.items():
                if v is not None and k in self.settings:
                    self.settings[k] = v

        # adaptive 是 scrapling 的**类级别**属性（不是实例），改一次全局生效。
        # 在 __init__ 中调用一次即可，避免每次 fetch 重复触发 try/except 导入链。
        self._apply_adaptive()

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------

    def _get_fetcher(self, fetcher_name: Optional[str] = None):
        """根据名称返回对应的 fetcher 类（延迟导入，避免启动期强依赖）

        Args:
            fetcher_name: fetcher 名称，可选值 ``fetcher`` / ``dynamic`` / ``stealthy``；
                          传 None 时使用 ``self.settings["fetcher"]``。
                          未知名称默认回落 ``stealthy``。

        Returns:
            fetcher 类（不是实例）：调用方应使用 ``Fetcher.get(...)`` 或 ``Fetcher.fetch(...)``
            获取 Response。
        """
        name = (fetcher_name or self.settings["fetcher"]).lower()
        if name == "fetcher":
            # 纯 HTTP 抓取器，速度最快，但不支持 JS 与 actions
            from scrapling.fetchers import Fetcher

            return Fetcher
        if name == "dynamic":
            # Playwright 浏览器，支持 JS 与 actions
            from scrapling.fetchers import DynamicFetcher

            return DynamicFetcher
        # 默认 / 显式指定 stealthy：隐身 + 反爬绕过
        from scrapling.fetchers import StealthyFetcher

        return StealthyFetcher

    def _apply_adaptive(self):
        """为所有 fetcher 启用 adaptive 模式

        adaptive 模式的工作原理：Scrapling 在抓取时记录元素的多维指纹（位置、属性、文本相似度），
        当 CSS 选择器失效时，自动在 DOM 中寻找最相似的元素。

        注意：Scrapling 的 adaptive 是类级别开关，因此本方法会同步设置三个 fetcher 类。
        每个 fetcher 的 import 都用 try/except 容错：某个 fetcher 因依赖缺失
        （如 Fetcher 需要 curl_cffi）无法导入时，不影响其他 fetcher 工作。
        """
        # adaptive 是类属性，不是实例属性
        adaptive = self.settings["adaptive"]
        # 三个 fetcher 独立 try/except，任一不可用不影响其他
        try:
            from scrapling.fetchers import Fetcher

            Fetcher.adaptive = adaptive
        except ImportError as e:
            # Fetcher 依赖 curl_cffi，未安装时跳过即可（v2 视频预览不依赖它）
            logger.debug(f"Fetcher 不可用（adaptive 跳过）: {e}")
        try:
            from scrapling.fetchers import DynamicFetcher

            DynamicFetcher.adaptive = adaptive
        except ImportError as e:
            logger.debug(f"DynamicFetcher 不可用（adaptive 跳过）: {e}")
        try:
            from scrapling.fetchers import StealthyFetcher

            StealthyFetcher.adaptive = adaptive
        except ImportError as e:
            logger.debug(f"StealthyFetcher 不可用（adaptive 跳过）: {e}")

    # ------------------------------------------------------------------
    # 抓取 / 操作 / 提取 三大主流程
    # ------------------------------------------------------------------

    def fetch_page(
        self,
        url: str,
        fetcher_name: Optional[str] = None,
        page_action: Optional[callable] = None,
        wait_selector: Optional[str] = None,
        wait_selector_state: str = "attached",
    ):
        """抓取单个页面并返回 Scrapling Response 对象

        Args:
            url: 目标 URL，必须是完整的 http(s) 地址。
            fetcher_name: 临时指定 fetcher；传 None 则用全局设置。
            page_action: 可选回调，签名为 ``fn(page) -> None``。在浏览器型 fetcher 中，
                         scrapling 会在页面加载完成后调用本回调，并传入 Playwright ``Page``。
                         常用于：填表 + 点击 + 等待异步结果。
                         纯 ``Fetcher``（HTTP）不支持本参数，传了也忽略。
            wait_selector: 可选 CSS 选择器，scrapling 会等待该元素进入指定状态后再返回。
                           适合等待异步内容出现（例如点击按钮后的预览图片）。
            wait_selector_state: 等待状态，``attached``（默认）/ ``visible`` / ``hidden`` 等。

        Returns:
            Scrapling ``Response`` 对象，同时具备 ``Selector`` 能力（.css / .xpath / .text）。
            注意：``StealthyFetcher.fetch`` 不会把 ``page`` 暴露在 Response 上，
            必须在 ``page_action`` 回调中执行交互操作。

        Raises:
            Exception: 抓取失败时抛出原始异常（Scrapling 内部异常或网络异常）。
        """
        # adaptive 已在 __init__ 中应用过；这里不再重复调用（类级别共享）
        F = self._get_fetcher(fetcher_name)
        # 分支：纯 HTTP fetcher（不支持 proxy / network_idle / headless / page_action 等参数）
        if F.__name__ == "Fetcher":
            if page_action or wait_selector:
                logger.debug("纯 HTTP fetcher 忽略 page_action / wait_selector 参数")
            # stealthy_headers=True 模拟浏览器指纹，降低被反爬拦截概率
            return F.get(url, stealthy_headers=True)
        # 浏览器型 fetcher：统一传入 headless / network_idle / proxy / timeout
        common = {
            "headless": self.settings["headless"],
            "network_idle": self.settings["network_idle"],
            "proxy": self.settings["proxy"],
            "timeout": self.settings["timeout"],
        }
        # page_action / wait_selector 仅在浏览器型 fetcher 中生效
        if page_action is not None:
            common["page_action"] = page_action
        if wait_selector is not None:
            common["wait_selector"] = wait_selector
            common["wait_selector_state"] = wait_selector_state
        return F.fetch(url, **common)

    def _make_page_action(self, actions: Optional[List[UnifiedAction]]):
        """将 ``UnifiedAction`` 列表包装为 scrapling 的 ``page_action`` 回调

        Args:
            actions: 用户配置的 actions 列表（可能为空 / None）。

        Returns:
            ``None`` 当 actions 为空；否则返回一个 ``fn(page) -> None`` 闭包。
            scrapling 会在页面加载完成后调用此闭包，传入 Playwright ``Page``。
        """
        if not actions:
            return None

        def _action(page):
            """scrapling 内部调用的 page_action 回调

            这里直接复用 ``execute_actions`` 的执行逻辑，保证 fill / click / 等待行为与
            v1 一致。失败由 ``execute_actions`` 内部捕获（返回 bool），不抛出到 scrapling。
            """
            self.execute_actions(page, actions)

        return _action

    def execute_actions(self, page, actions: List[UnifiedAction]) -> bool:
        """在 Playwright Page 对象上依次执行 actions

        Args:
            page: Playwright 的 ``Page`` 实例，由 scrapling 在 page_action 回调中传入。
            actions: 操作列表，每个元素为 ``UnifiedAction``，含 type / selector / value。

        Returns:
            bool: 所有 actions 全部成功返回 True；任一失败返回 False（不抛出异常）。

        Notes:
            - ``fill``：清空并填入文本，超时 10 秒。
            - ``click``：点击元素后等待 ``networkidle``（10 秒超时容错），确保 JS 渲染完成。
            - 当前仅支持 ``fill`` / ``click`` 两种 type；其他 type 记录 warning 后跳过。
            - 本方法在 v2 中不再被 ``collect_data_recursive`` 直接调用，
              而是作为 scrapling ``page_action`` 回调执行（见 ``_make_page_action``）。
        """
        # 空 actions 时视为成功（与 v1 行为一致）
        if not actions:
            return True
        if page is None:
            logger.warning("page_action 回调收到空 page 对象，跳过 actions")
            return False
        try:
            # 顺序执行每个 action（actions 之间通常有依赖关系，不可并行）
            for i, action in enumerate(actions):
                # 统一小写，避免 "Click" / "CLICK" 之类的大小写差异
                action_type = (action.type or "").lower()
                selector = action.selector
                value = action.value or ""
                logger.info(f"执行第 {i + 1} 个操作: {action_type} on {selector}")
                if action_type == "fill":
                    # Playwright 的 fill 会自动清空已有内容
                    page.fill(selector, value, timeout=10000)
                elif action_type == "click":
                    page.click(selector, timeout=10000)
                    # 点击后等待网络空闲，确保动态内容已加载
                    try:
                        page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        # 部分页面可能无 networkidle 事件，不视为致命错误
                        pass
                else:
                    # 显式列出支持类型，便于排查：未来可扩展 hover / scroll / wait 等
                    logger.warning(
                        f"暂不支持的操作类型: {action_type}（已支持: fill / click）"
                    )
            return True
        except Exception as e:
            # 任何 Playwright 异常都记录完整堆栈，便于排查
            logger.error(f"执行 actions 失败: {e}\n{traceback.format_exc()}")
            return False

    def extract_data(
        self, response, config: UnifiedCollectConfig
    ) -> List[Dict[str, Any]]:
        """根据配置从 Response 中提取数据，并组装为字典列表

        支持的 method
        ------------
        - ``text``：元素**直接文本**（lxml .text），子元素内的文本取不到；
                   仅当元素本身含直接文本时才有值（如 <a>纯文本</a>）。
                   对 <a><i></i>章 龙城苏<i></i></a> 会返回 ""。
        - ``all_text``：**递归**取所有子元素文本（推荐），用空串连接并 strip；
                       适用 <a><i></i>章 龙城苏<i></i></a> → "章 龙城苏"。
        - ``attribute``：元素属性值（需指定 ``attribute`` 字段，与 v1 一致）
        - ``xpath``：通过 XPath 表达式选取元素并取文本（v1 不支持）
        - ``regex``：对页面原始 HTML/文本按正则提取全部匹配（v1 不支持，
                     此时 ``selector`` 字段复用为正则 pattern）

        Args:
            response: Scrapling Response 对象。
            config: 当前层级的采集配置，含 ``data_extraction`` 列表。

        Returns:
            List[Dict]: 每条字典的 key 为 ``field``，value 为提取出的标量。
            列表长度 = 各字段提取结果的最大长度；不足的字段填 ""。
            如果指定了 ``unique=True`` 的字段，会按该字段值去重（v1 行为）。

        Notes:
            - 多个字段按"最大长度对齐"原则组装，确保字段数对齐。
            - 去重在组装之后进行，避免破坏字段对齐。
        """
        # 各字段提取出的原始值列表（按 field 索引）
        field_results: Dict[str, List[Any]] = {}
        # 标记哪个字段需要参与去重（v1 行为：unique 字段）
        unique_field = None

        # 逐个字段提取
        for extraction in config.data_extraction or []:
            field_name = extraction.field
            # 记录唯一的 unique 字段名（v1 语义：整个数据集按此字段去重）
            if extraction.unique:
                unique_field = field_name
            # method 默认 text，统一小写
            method = (extraction.method or "text").lower()
            selector = extraction.selector
            try:
                if method == "text":
                    # CSS 选择器 → 取每个元素的 .text
                    # 注意：scrapling 的 .text 走 lxml 的 .text 属性，**只取直接文本节点**。
                    # 若元素内含子元素混排（如 <a><i></i>章 龙城苏<i></i></a>），
                    # 直接文本为 None，会返回 ""，此时应改用 "all_text" method。
                    elements = (
                        response.css(selector) if hasattr(response, "css") else []
                    )
                    # 优化 #5：未找到元素用 [None] 标记，与"找到但内容为空"区分
                    values = [el.text for el in elements] if elements else [None]
                elif method == "all_text":
                    # ----- 优化 #10：递归取所有子元素文本 -----
                    # 适用于元素内含子元素（如 <a><i></i>标题文字<i></i></a>）。
                    # separator="" 把所有文本片段连成一个字符串；strip=True 去掉首尾空白。
                    # valid_values=True 跳过空文本（避免"  "变成 ["", "", "标题"] 这种情况）。
                    elements = (
                        response.css(selector) if hasattr(response, "css") else []
                    )
                    if elements:
                        values = [
                            el.get_all_text(separator="", strip=True) for el in elements
                        ]
                    else:
                        values = [None]
                elif method == "attribute":
                    # CSS 选择器 → 取每个元素的指定 attribute
                    elements = (
                        response.css(selector) if hasattr(response, "css") else []
                    )
                    attr_name = extraction.attribute
                    values = (
                        [el.attrib.get(attr_name) for el in elements]
                        if elements
                        else [None]
                    )
                elif method == "xpath":
                    # XPath 选择器（v1 不支持，v2 新增）
                    elements = (
                        response.xpath(selector) if hasattr(response, "xpath") else []
                    )
                    values = [el.text for el in elements] if elements else [None]
                elif method == "regex":
                    # regex 模式：selector 字段复用为正则 pattern
                    raw = response.text or "" if hasattr(response, "text") else ""
                    values = re.findall(selector, raw) or [None]
                else:
                    # 未知 method：跳过该字段，不影响其他字段
                    logger.warning(f"未知 method: {method}, 跳过字段 {field_name}")
                    continue
                field_results[field_name] = values
                logger.info(f"成功提取 {len(values)} 个 {method} 值: {field_name}")
            except Exception as e:
                # 单个字段失败不影响整体，记录 warning 后置空
                logger.warning(f"提取字段 {field_name} 失败: {e}")
                field_results[field_name] = [None]

        # ----- 组装为字典列表 -----
        # 按"最大长度对齐"原则：每个索引位置生成一条记录
        data: List[Dict[str, Any]] = []
        if field_results:
            # 取所有字段中提取出最多的那个的长度作为总条数
            max_length = max((len(v) for v in field_results.values()), default=0)
            for idx in range(max_length):
                item = {}
                for field_name, values in field_results.items():
                    # 优化 #5：长度不足时填 None（与"未找到"语义统一）
                    item[field_name] = values[idx] if idx < len(values) else None
                data.append(item)

        # ----- 去重 -----
        # v1 行为：按 unique 字段全量去重，保留首次出现的记录
        if unique_field:
            seen = set()
            unique_data = []
            for item in data:
                key = item.get(unique_field)
                if key not in seen:
                    seen.add(key)
                    unique_data.append(item)
            data = unique_data

        return data

    # ------------------------------------------------------------------
    # 递归主流程
    # ------------------------------------------------------------------

    def collect_data_recursive(
        self,
        response,
        config: UnifiedCollectConfig,
        base_url: str = "",
    ) -> Dict[str, Any]:
        """递归采集数据，支持多级嵌套与分页

        处理流程
        --------
        1. 解析 ``config.url``，与 ``base_url`` 拼接为完整 URL
        2. 抓取当前页（首含 actions），提取数据
        3. 若配置了 ``next_page_selector``，点击下一页后重复步骤 2
           （最多 ``max_pages`` 页，避免无限翻页）
        4. 处理 ``lower_level_page_config``：逐条进入下级页面抓取
           （最多 ``max_children`` 条，避免单次请求过重）
        5. 返回组装好的结果字典

        Args:
            response: 父级调用时为 None（仅作占位参数，便于扩展）；
                      递归时为 None（每次重新 fetch）。
            config: 当前层级的配置（含 url / actions / data_extraction / lower_level_page_config）。
            base_url: 父级 URL，用于拼接相对路径。空字符串表示无父级。

        Returns:
            Dict[str, Any]: 若 ``data_field`` 已配置，返回 ``{data_field: [...]}``；
                            否则直接返回列表（保持与 v1 一致）。
                            下级数据会合并到对应父记录的字典中。
        """
        # 防御：未配置 url 时直接返回空
        if not config.url:
            return {}

        # ----- URL 解析：相对路径 → 绝对路径 -----
        # 用 urljoin 处理各种相对/绝对 url 形式：
        #   - "https://..."  → 原样
        #   - "/read/1651/2/" → 基于 base_url 拼接（但 base_url="" 时只能 fallback 到 config.url 自身）
        #   - "read/1651/2/" → 基于 base_url 拼接
        if config.url.startswith("http"):
            full_url = config.url
        else:
            # 修复 #9：base_url 为空时无法用 urljoin 拼接，回退到 config.url 自身
            # 这样如果 config.url 本身就是完整 url 也能正确处理
            full_url = urljoin(base_url or config.url, config.url)

        # ===== 第一步：抓取列表页（含分页） =====
        all_list_data: List[Dict[str, Any]] = []
        page_num = 1
        max_pages = self.settings["max_pages"]

        # =====================================================================
        # TODO: 测试代码 - 写死最多抓 5 页（生产测试用，测完务必删除本段）
        # =====================================================================
        # 目的：本地测试时快速验证翻页逻辑，最多抓 5 页就 break，便于人工核对。
        # 移除方法：删除下面这 3 行即可恢复按 max_pages 抓取所有页。
        # 注意：本段必须紧跟 max_pages 赋值之后、while 循环之前。
        # =====================================================================
        _TEST_HARDCODED_MAX_PAGES = 5  # 写死上限；测试完后请删除上方 TODO 块
        max_pages = min(max_pages, _TEST_HARDCODED_MAX_PAGES)
        logger.warning(
            f"[TEST ONLY] 翻页上限被写死为 {_TEST_HARDCODED_MAX_PAGES} 页（生产测试临时）"
        )

        # 分页循环：每次抓一页，直到翻完或达到 max_pages
        while page_num <= max_pages:
            logger.info(f"采集第 {page_num}/{max_pages} 页: {full_url}")
            # actions 仅在第一页执行（v1 行为，避免重复触发副作用）
            # 关键：actions 必须作为 page_action 回调传给 scrapling，
            # 因为 StealthyFetcher/DynamicFetcher 抓完不暴露 page 对象。
            # 后续翻页（page_num > 1）不传 page_action，避免重复触发填表/点击。
            has_actions = page_num == 1 and config.actions
            page_action = (
                self._make_page_action(config.actions) if has_actions else None
            )
            # ----- 优化 #8：wait_selector 自动推断 -----
            # 当有 actions 时，scrapling 可能在 actions 触发异步请求后才返回。
            # 用 data_extraction 第一个字段的 selector 作为"等待结果出现"的标记，
            # 状态用 visible（最常见的"等异步内容渲染"）。
            # 仅在有 actions 的第一页推断；后续翻页和纯抓取页不等待。
            wait_selector = None
            wait_selector_state = "attached"
            if has_actions and config.data_extraction:
                first_ext = config.data_extraction[0]
                if first_ext.selector:
                    wait_selector = first_ext.selector
                    wait_selector_state = "visible"
                    logger.debug(
                        f"自动推断 wait_selector={wait_selector} (state={wait_selector_state})"
                    )
            # 每次都重新 fetch（response 是一次性的，不能跨页复用）
            current_response = self.fetch_page(
                full_url,
                fetcher_name=None,
                page_action=page_action,
                wait_selector=wait_selector,
                wait_selector_state=wait_selector_state,
            )

            # 提取当前页数据并累积
            current_data = self.extract_data(current_response, config)
            all_list_data.extend(current_data)
            logger.info(
                f"第 {page_num} 页提取 {len(current_data)} 条，累计 {len(all_list_data)} 条"
            )

            # ----- 翻页判断 -----
            # 未配置 next_page_selector 视为单页，直接结束
            if not config.next_page_selector:
                break
            try:
                # 通过 next_page_selector 找到下一页链接元素
                next_els = current_response.css(config.next_page_selector)
                if not next_els:
                    # 找不到下一页元素：列表已抓完
                    break
                # ----- 优化 #1：智能选择下一页元素 -----
                # v1 直接用 next_els[0]，但 selector 可能匹配到一组链接（如页码 1 2 3 4 5），
                # 这会反复抓到第 1 页。优先选 href/text 含 "next" / "下一页" / ">" 的元素，
                # 都找不到再 fallback 到第一个有 href 的元素。
                next_href = None
                next_keywords = ("next", "下一页", "›", "»", ">")
                for el in next_els:
                    href = el.attrib.get("href")
                    if not href:
                        continue
                    text = (el.text or "").strip().lower()
                    href_lower = href.lower()
                    if any(kw in href_lower or kw in text for kw in next_keywords):
                        next_href = href
                        break
                if not next_href:
                    # fallback：用第一个有 href 的元素（v1 行为兜底）
                    for el in next_els:
                        href = el.attrib.get("href")
                        if href:
                            next_href = href
                            break
                if not next_href:
                    break
                # ----- 修复 #9：相对路径用 urljoin 拼接 -----
                # v1 用字符串拼接，base_url="" 时相对路径（如 "/read/1651/2/"）无法正确解析。
                # urljoin 能基于**当前已抓取的页面 url** 智能拼接：
                #   - 绝对 URL（"https://..."）→ 原样使用
                #   - 协议相对 URL（"//foo.com/a"）→ 继承协议
                #   - 站点绝对路径（"/a/b"）→ 保留域名
                #   - 相对路径（"a/b"）→ 相对当前页面拼接
                full_url = urljoin(full_url, next_href)
            except Exception as e:
                # 翻页过程任何异常都视为结束（保守策略，避免循环卡死）
                logger.warning(f"获取下一页失败: {e}")
                break
            page_num += 1

        # ----- 组装当前层结果 -----
        result: Dict[str, Any] = {}
        if config.data_field:
            # 命名输出：{"chapters": [...]}
            result[config.data_field] = all_list_data
        else:
            # 未指定 data_field：保持 v1 的列表返回（向后兼容）
            result = all_list_data

        # ===== 第二步：处理下级页面配置 =====
        for lower_config in config.lower_level_page_config or []:
            # 关键判断：lower_config.url 是字段名（如 "link"）还是固定 URL？
            # 如果它出现在当前 data_extraction 的 field 列表中，就视为字段名
            if lower_config.url in [
                item.field for item in (config.data_extraction or [])
            ]:
                # ----- 模式 A：下级 url 来自当前数据（典型场景：列表 → 详情） -----
                count = 0
                max_children = self.settings["max_children"]
                # 优化 #2：根据配置决定是否并发抓取下级页面
                # 注意：仅对纯 HTTP fetcher 安全；浏览器型 fetcher 下并发可能产生竞争
                if (
                    self.settings.get("concurrent_children")
                    and self.settings["fetcher"] == "fetcher"
                ):
                    # ----- 优化 #2 路径 A：并发抓取 -----
                    from concurrent.futures import ThreadPoolExecutor, as_completed

                    max_workers = min(self.settings.get("max_workers", 4), max_children)
                    # 预先准备所有任务（不修改 all_list_data，仅收集）
                    tasks = []
                    for data_item in all_list_data:
                        if count >= max_children:
                            logger.info(f"已达下级页面最大处理数 {max_children}，停止")
                            break
                        if (
                            lower_config.url in data_item
                            and data_item[lower_config.url]
                        ):
                            # 修复 #9：下级 url 也用 urljoin 拼接，避免相对路径丢失域名
                            lower_url = urljoin(full_url, data_item[lower_config.url])
                            # 深拷贝下级配置（修复 v1 修改入参的副作用 bug）
                            lower_copy = UnifiedCollectConfig(**lower_config.dict())
                            lower_copy.url = lower_url
                            tasks.append((data_item, lower_copy))
                            count += 1
                    # 并发执行所有任务
                    logger.info(
                        f"并发抓取 {len(tasks)} 个下级页面（max_workers={max_workers}）"
                    )
                    with ThreadPoolExecutor(max_workers=max_workers) as executor:
                        future_to_task = {
                            executor.submit(
                                self.collect_data_recursive,
                                current_response,
                                cfg,
                                base_url,
                            ): item
                            for item, cfg in tasks
                        }
                        for future in as_completed(future_to_task):
                            data_item = future_to_task[future]
                            try:
                                lower_data = future.result()
                                if isinstance(lower_data, dict):
                                    data_item.update(lower_data)
                                else:
                                    data_item["nested_data"] = lower_data
                            except Exception as e:
                                logger.warning(f"并发抓取下级页面失败: {e}")
                                data_item["nested_data"] = None
                else:
                    # ----- 模式 A 串行路径（默认，安全） -----
                    for data_item in all_list_data:
                        # 限制最大处理数（去除 v1 的 2 条硬编码）
                        if count >= max_children:
                            logger.info(f"已达下级页面最大处理数 {max_children}，停止")
                            break
                        # 取出下级 url 并做相对路径处理
                        if (
                            lower_config.url in data_item
                            and data_item[lower_config.url]
                        ):
                            # 修复 #9：下级 url 也用 urljoin 拼接
                            lower_url = urljoin(full_url, data_item[lower_config.url])
                            # 关键：深拷贝下级配置并设置新 url（修复 v1 修改入参的副作用 bug）
                            lower_copy = UnifiedCollectConfig(**lower_config.dict())
                            lower_copy.url = lower_url
                            # 递归调用
                            lower_data = self.collect_data_recursive(
                                current_response, lower_copy, base_url
                            )
                            # 合并到父记录：字典直接 update，否则用 nested_data 包裹
                            if isinstance(lower_data, dict):
                                data_item.update(lower_data)
                            else:
                                data_item["nested_data"] = lower_data
                            count += 1
            else:
                # ----- 模式 B：下级 url 是固定 URL（独立抓取） -----
                lower_data = self.collect_data_recursive(
                    current_response, lower_config, full_url
                )
                if lower_config.data_field:
                    result[lower_config.data_field] = lower_data
                elif isinstance(lower_data, dict):
                    # 合并到当前 result
                    result.update(lower_data)
                else:
                    # 非字典类型：用 data_field 或默认名 "nested_data" 包裹
                    field_name = lower_config.data_field or "nested_data"
                    result[field_name] = lower_data

        return result

    def collect_data(self) -> Dict[str, Any]:
        """采集入口方法

        Returns:
            Dict[str, Any]: 完整采集结果，结构由 config 的 data_field / lower_level_page_config 决定。

        Raises:
            Exception: 采集过程任何异常都会被包装后抛出（保留原始堆栈到日志）。
        """
        try:
            logger.info("开始 Scrapling 数据采集...")
            # 防御：空配置直接返回
            if not self.config:
                logger.warning("采集配置为空")
                return {}
            # 仅取第一个配置作为根（与 v1 行为一致，列表通常只有一个根配置）
            result = self.collect_data_recursive(None, self.config[0])
            logger.info("Scrapling 数据采集完成")
            return result
        except Exception as e:
            # 记录完整堆栈便于排查
            logger.error(
                f"采集数据失败: {e}, 错误类型: {type(e).__name__}, 堆栈:\n{traceback.format_exc()}"
            )
            # 重新抛出，service 层会捕获并包装为统一返回结构
            raise Exception("数据采集过程中发生错误")
