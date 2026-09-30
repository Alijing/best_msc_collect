import os


class Config:
    # ChromeDriver配置
    CHROMEDRIVER_PATH = os.environ.get(
        "CHROMEDRIVER_PATH", "D:\\alijing\\tools\\chromedriver-win64\\chromedriver.exe"
    )

    # 日志配置
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    LOG_FILE = os.environ.get("LOG_FILE", "web_data_collection.log")

    # 服务配置
    HOST = os.environ.get("HOST", "192.168.0.191")
    PORT = int(os.environ.get("PORT", 5000))
    DEBUG = os.environ.get("DEBUG", "False").lower() == "true"

    # 默认预览配置（仅包含基础配置）
    PREVIEW_CONFIG = {
        "preview_url": os.environ.get("PREVIEW_URL", "https://magnet.pics/"),
        "chromedriver_path": CHROMEDRIVER_PATH,
        "headless": os.environ.get("PREVIEW_HEADLESS", "True").lower() == "true",
    }

    WEB_DATA_COLLECT_CONFIG = {
        "chromedriver_path": CHROMEDRIVER_PATH,
        "headless": os.environ.get("WEB_DATA_COLLECTION_HEADLESS", "True").lower()
        == "true",
    }

    # Scrapling v2 配置
    # 默认抓取器：fetcher（纯HTTP，最快） / dynamic（Playwright浏览器） / stealthy（隐身+反爬绕过）
    SCRAPLING_FETCHER = os.environ.get("SCRAPLING_FETCHER", "stealthy")
    # 浏览器是否无头模式
    SCRAPLING_HEADLESS = os.environ.get("SCRAPLING_HEADLESS", "True").lower() == "true"
    # 是否等待网络空闲后再返回（动态页面需要）
    SCRAPLING_NETWORK_IDLE = (
        os.environ.get("SCRAPLING_NETWORK_IDLE", "True").lower() == "true"
    )
    # 是否启用自适应选择器（网站改版后自动重新定位元素）
    SCRAPLING_ADAPTIVE = os.environ.get("SCRAPLING_ADAPTIVE", "True").lower() == "true"
    # 代理地址，例如 http://127.0.0.1:7890，留空表示不使用
    SCRAPLING_PROXY = os.environ.get("SCRAPLING_PROXY", "") or None
    # 分页抓取最大页数（v1 硬编码为 2）
    SCRAPLING_MAX_PAGES = int(os.environ.get("SCRAPLING_MAX_PAGES", 50))
    # 下级页面最大处理数（v1 硬编码为 2）
    SCRAPLING_MAX_CHILDREN = int(os.environ.get("SCRAPLING_MAX_CHILDREN", 100))
    # 单次请求超时（单位：毫秒；30000 = 30 秒）
    # 注意：scrapling 浏览器型 fetcher（StealthyFetcher / DynamicFetcher）将 timeout 直接当作毫秒传给 patchright，
    # 所以这里必须用毫秒单位，不要写成秒。Fetcher（纯 HTTP）的 timeout 单位也是毫秒。
    SCRAPLING_TIMEOUT = int(os.environ.get("SCRAPLING_TIMEOUT", 30000))
    # 优化 #2：下级页面并发抓取（默认 False）
    # 注意：scrapling 浏览器实例在同一进程内并发会竞争；仅对纯 HTTP fetcher（fetcher）安全。
    # 浏览器型 fetcher 下并发可能产生不明行为，请仅在已评估风险时打开。
    SCRAPLING_CONCURRENT_CHILDREN = (
        os.environ.get("SCRAPLING_CONCURRENT_CHILDREN", "False").lower() == "true"
    )
    # 优化 #2：并发抓取时的最大 worker 数
    SCRAPLING_MAX_WORKERS = int(os.environ.get("SCRAPLING_MAX_WORKERS", 4))

    # Playwright / Patchright 浏览器二进制目录
    # ----------------------------------------
    # 实际安装位置：D:\ProgramData\miniconda3\envs\best_msc_collect\pw-browsers
    # 装到 conda env 内跟着环境走，`conda env remove` 时一并清理。
    #
    # 优先级（由 app._setup_scrapling_env 决定）：
    #   1. 进程启动时已有的 os.environ（推荐用 setx 或 conda env config vars set 写入）
    #   2. 本配置项默认值（绝对路径，作为兜底）
    #   3. 系统默认 C:\Users\*\AppData\Local\ms-playwright（不推荐，沙箱会拦截）
    #
    # 推荐做法（永久生效）：setx PLAYWRIGHT_BROWSERS_PATH "D:\ProgramData\miniconda3\envs\best_msc_collect\pw-browsers"
    PLAYWRIGHT_BROWSERS_PATH = os.environ.get(
        "PLAYWRIGHT_BROWSERS_PATH",
        r"D:\ProgramData\miniconda3\envs\best_msc_collect\pw-browsers",
    )

    # Scrapling 聚合配置（service 直接读取此 dict）
    SCRAPLING_CONFIG = {
        "fetcher": SCRAPLING_FETCHER,
        "headless": SCRAPLING_HEADLESS,
        "network_idle": SCRAPLING_NETWORK_IDLE,
        "adaptive": SCRAPLING_ADAPTIVE,
        "proxy": SCRAPLING_PROXY,
        "max_pages": SCRAPLING_MAX_PAGES,
        "max_children": SCRAPLING_MAX_CHILDREN,
        "timeout": SCRAPLING_TIMEOUT,
        "concurrent_children": SCRAPLING_CONCURRENT_CHILDREN,
        "max_workers": SCRAPLING_MAX_WORKERS,
    }
