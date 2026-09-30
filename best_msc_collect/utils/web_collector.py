import logging
import time
import traceback
from typing import List, Dict, Any

from selenium import webdriver
from selenium.common.exceptions import WebDriverException, TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from ..models.unified_model import UnifiedCollectConfig, UnifiedAction

# 获取日志记录器
logger = logging.getLogger(__name__)


def _check_element_exists(driver, selector: str) -> bool:
    """
    检查元素是否存在

    Args:
        driver: WebDriver实例
        selector: CSS选择器

    Returns:
        bool: 元素是否存在
    """
    try:
        elements = driver.find_elements(By.CSS_SELECTOR, selector)
        return len(elements) > 0
    except Exception as e:
        logger.error(f"检查元素存在时出错: {str(e)}, 选择器: {selector}")
        return False


def execute_actions(driver, actions: List[UnifiedAction]) -> bool:
    """
    在给定的WebDriver实例上执行操作的通用逻辑

    Args:
        driver: WebDriver实例
        actions: 操作配置

    Returns:
        bool: 操作是否成功执行
    """
    try:
        # 执行预定义的操作
        logger.info("开始执行操作配置...")
        for i, action in enumerate(actions):
            action_type = action.type
            selector = action.selector
            try:
                value = action.value or ""

                logger.info(f"执行第 {i + 1} 个操作: {action_type} on {selector}")

                if action_type == "fill":
                    # 填充输入框
                    element = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    element.clear()
                    element.send_keys(value)
                    logger.info(f"已填充 '{value}' 到元素: {selector}")

                elif action_type == "click":
                    # 点击按钮或其他元素
                    element = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    element.click()
                    # 等待页面加载
                    time.sleep(2)
                    logger.info(f"已点击元素: {selector}")

            except TimeoutException as e:
                logger.error(f"操作超时: {str(e)}, 操作详情: 类型={action_type}, 选择器={selector}")
                # 操作超时时直接返回失败
                raise Exception(f"操作超时: 类型={action_type}, 选择器={selector}")
            except Exception as e:
                logger.error(f"执行操作时出错: {str(e)}, 操作详情: 类型={action_type}, 选择器={selector}")
                # 操作出错时直接返回失败
                raise Exception(f"执行操作时出错: 类型={action_type}, 选择器={selector}, 错误={str(e)}")

        logger.info("所有操作执行完成")
        return True

    except Exception as e:
        logger.error(
            f"执行操作过程中发生错误: {str(e)}, 错误类型: {type(e).__name__}, 详细堆栈信息:\n{traceback.format_exc()}")
        # 发生异常时返回 False，表示执行失败
        return False


def extract_data(driver, config: UnifiedCollectConfig) -> List[Dict[str, Any]]:
    """
    在给定的WebDriver实例上提取数据

    Args:
        driver: WebDriver实例
        config: 数据提取配置

    Returns:
        List[Dict[str, Any]]: 收集到的数据
    """
    try:
        # 提取数据
        data = []
        extractions = config.data_extraction
        logger.info(f"共有 {len(extractions)} 个数据提取项")

        # 存储所有字段的提取结果
        field_results = {}

        unique_field = None

        # 提取每个字段
        for extraction in extractions:
            try:
                if extraction.unique:
                    unique_field = extraction.field

                field_name = extraction.field
                logger.info(f"提取字段 '{field_name}'")

                if extraction.method == "text":
                    elements = driver.find_elements(By.CSS_SELECTOR, extraction.selector)
                    # 提取所有元素的文本
                    values = [element.text for element in elements] if elements else [""]
                    field_results[field_name] = values
                    logger.info(f"成功提取 {len(values)} 个文本元素")

                elif extraction.method == "attribute":
                    elements = driver.find_elements(By.CSS_SELECTOR, extraction.selector)
                    attr_name = extraction.attribute
                    # 提取所有元素的属性
                    values = [element.get_attribute(attr_name) for element in elements] if elements else [""]
                    field_results[field_name] = values
                    logger.info(f"成功提取 {len(values)} 个属性 '{attr_name}'")

            except Exception as e:
                logger.warning(f"提取数据 '{extraction.field}' 失败: {str(e)}")
                field_results[extraction.field] = []

        # 将提取的数据组合成字典列表
        if field_results:
            # 获取最长的值列表长度
            max_length = max(len(values) for values in field_results.values()) if field_results else 0

            # 为每个索引创建一个字典
            for idx in range(max_length):
                item = {}
                for field_name, values in field_results.items():
                    if idx < len(values):
                        item[field_name] = values[idx]
                    else:
                        item[field_name] = ""
                data.append(item)

            logger.info(f"成功提取 {len(data)} 条数据记录")

        # TODO 去重逻辑有待完善，如果下一页的数据有上一页的数据，则不能完成去重
        if unique_field:
            # 对 data 进行去重
            seen_values = set()
            unique_data = []
            for item in data:
                if item[unique_field] not in seen_values:
                    seen_values.add(item[unique_field])
                    unique_data.append(item)
            data = unique_data

        return data

    except Exception as e:
        logger.error(
            f"提取数据过程中发生错误: {str(e)}, 错误类型: {type(e).__name__}, 详细堆栈信息:\n{traceback.format_exc()}")
        return []


class WebDataCollector:
    """
    网页数据收集工具类
    根据UnifiedCollectConfig配置收集网页数据，支持多级页面嵌套抓取
    """

    def __init__(self, config: List[UnifiedCollectConfig], chromedriver_path: str = None, headless: bool = True):
        self.config = config
        self.chromedriver_path = chromedriver_path
        self.headless = headless

    def setup_driver(self):
        """
        设置Chrome WebDriver

        Returns:
            webdriver.Chrome: 配置好的WebDriver实例
        """
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-plugins")
        chrome_options.add_argument("--disable-images")
        chrome_options.add_argument("--disable-javascript")  # 可选：禁用JavaScript提高速度

        # 配置ChromeDriver路径
        service = None
        chromedriver_path = self.chromedriver_path
        if chromedriver_path:
            # 检查路径是否存在
            import os
            if not os.path.exists(chromedriver_path):
                logger.error(f"ChromeDriver路径不存在: {chromedriver_path}")
                raise FileNotFoundError(f"ChromeDriver not found at: {chromedriver_path}")

            # 检查是否是文件
            if not os.path.isfile(chromedriver_path):
                # 如果是目录，尝试在目录中查找chromedriver.exe
                possible_paths = [
                    os.path.join(chromedriver_path, "chromedriver.exe"),
                    os.path.join(chromedriver_path, "chromedriver")
                ]
                found = False
                for path in possible_paths:
                    if os.path.exists(path) and os.path.isfile(path):
                        chromedriver_path = path
                        found = True
                        break

                if not found:
                    logger.error(f"在目录中未找到ChromeDriver可执行文件: {chromedriver_path}")
                    raise FileNotFoundError(f"ChromeDriver executable not found in: {chromedriver_path}")

            service = Service(chromedriver_path)
            logger.info(f"使用指定的ChromeDriver路径: {chromedriver_path}")
        else:
            # 不指定路径，让selenium自动寻找系统PATH中的chromedriver
            service = Service()
            logger.info("使用系统PATH中的ChromeDriver")

        try:
            logger.info("正在初始化Chrome WebDriver...")
            driver = webdriver.Chrome(service=service, options=chrome_options)
            logger.info("Chrome WebDriver 初始化成功")
            return driver
        except WebDriverException as e:
            logger.error(f"无法初始化Chrome WebDriver: {str(e)}, 错误类型: {type(e).__name__}")
            raise
        except Exception as e:
            logger.error(
                f"初始化Chrome WebDriver时发生未知错误: {str(e)}, 错误类型: {type(e).__name__}, 详细堆栈信息: {traceback.format_exc()}")
            raise

    def collect_data_recursive(self, driver, config: UnifiedCollectConfig, base_url: str = "") -> Dict[str, Any]:
        """
        递归收集数据，处理嵌套的页面配置

        Args:
            driver: WebDriver实例
            config: 收集配置
            base_url: 基础URL，用于相对链接的处理

        Returns:
            Dict[str, Any]: 收集到的数据，包括嵌套页面的数据
        """
        logger.info(f"开始收集页面数据: {config.url}")

        # 构造完整URL
        if config.url.startswith("http"):
            full_url = config.url
        else:
            # 处理相对URL
            full_url = base_url.rstrip("/") + "/" + config.url.lstrip("/")

        all_list_data = []

        # 收集列表页数据
        page_num = 1
        while True:
            if page_num == 3:
                break

            logger.info(f"正在收集第 {page_num} 页数据")
            # 访问页面
            driver.get(full_url)
            # 等待页面加载
            time.sleep(2)
            # 执行操作
            if config.actions:
                execute_actions(driver, config.actions)

            # 提取当前页面数据
            current_data = extract_data(driver, config)
            all_list_data.extend(current_data)

            # 提取当前页列表数据
            logger.info(f"第 {page_num} 页列表数据收集完成，收集到 {len(current_data)} 条数据")

            # 如果没有下一页选择器，或者找不到下一页元素，则退出循环
            if not config.next_page_selector or not _check_element_exists(driver, config.next_page_selector):
                logger.info("列表页数据收集完成，没有找到下一页元素")
                break

            element = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, config.next_page_selector))
            )
            next_page_url = element.get_attribute("href")
            element.click()
            logger.info(f"已点击下一页元素: {config.next_page_selector}")
            if next_page_url:
                full_url = next_page_url
            else:
                logger.warning("无法获取下一页URL，请检查是否正确配置了选择器")

            # 等待页面加载
            time.sleep(3)
            page_num += 1

        result = {}
        if config.data_field:
            result[config.data_field] = all_list_data
        else:
            result = all_list_data

        # 处理下级页面配置
        for lower_config in config.lower_level_page_config:
            # 如果下级配置的URL是一个字段名，则从当前数据中获取实际URL
            if lower_config.url in [item.field for item in config.data_extraction]:

                i = 0
                for data_item in all_list_data:
                    if i == 1:
                        break
                    i += 1

                    if lower_config.url in data_item and data_item[lower_config.url]:
                        # 构造下级页面URL
                        lower_url = data_item[lower_config.url]
                        if not lower_url.startswith("http"):
                            # 处理相对URL
                            lower_url = base_url.rstrip("/") + "/" + lower_url.lstrip("/")

                        # 更新下级配置的URL
                        lower_config_copy = UnifiedCollectConfig(**lower_config.dict())
                        lower_config_copy.url = lower_url

                        # 递归收集下级页面数据
                        lower_data = self.collect_data_recursive(driver, lower_config_copy, base_url)

                        # 把 lower_data 添加到 data_item
                        if isinstance(lower_data, dict):
                            data_item.update(lower_data)
                        else:
                            data_item['nested_data'] = lower_data

            else:
                # 下级配置有固定的URL，直接递归收集数据
                lower_data = self.collect_data_recursive(driver, lower_config, full_url)
                if lower_config.data_field:
                    result[lower_config.data_field] = lower_data
                else:
                    if isinstance(lower_data, dict):
                        result.update(lower_data)
                    else:
                        # 对于非字典类型的数据，使用字段名存储或使用默认名称
                        field_name = lower_config.data_field if lower_config.data_field else 'nested_data'
                        result[field_name] = lower_data

        return result

    def collect_data(self) -> Dict[str, Any]:
        """
        收集数据入口方法

        Returns:
            Dict[str, Any]: 收集到的所有数据
        """
        driver = None
        try:
            logger.info("开始收集数据...")

            # 初始化WebDriver
            driver = self.setup_driver()
            if driver is None:
                logger.error("WebDriver初始化失败")
                return {}

            # 收集数据
            result = self.collect_data_recursive(driver, self.config[0])

            logger.info("数据收集完成")
            return result

        except Exception as e:
            logger.error(
                f"收集数据过程中发生错误: {str(e)}, 错误类型: {type(e).__name__}, 详细堆栈信息:\n{traceback.format_exc()}"
            )
            raise Exception("数据收集过程中发生错误")

        finally:
            if driver:
                try:
                    driver.quit()
                    logger.info("浏览器已关闭")
                except Exception as e:
                    logger.error(f"关闭浏览器时出错: {str(e)}")
