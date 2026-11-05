from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    APP_NAME: str = "BEST MSC COLLECT"
    DEBUG: bool = False

    # 抓取
    HTTP_TIMEOUT: float = 15.0
    MAX_RESPONSE_SIZE: int = 5 * 1024 * 1024
    USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    )
    MAX_REDIRECTS: int = 5

    # 重试
    HTTP_RETRY_ATTEMPTS: int = 3
    HTTP_RETRY_MIN_WAIT: float = 1.0
    HTTP_RETRY_MAX_WAIT: float = 10.0

    # 安全
    ALLOW_PRIVATE_IP: bool = False

    # 爬虫默认参数。翻页间隔由域名限速保证，delay 只在比限速更严时补差额。
    MAX_PAGES_DEFAULT: int = 500
    DELAY_DEFAULT: float = 0.0
    MAX_BACKGROUND_TASKS: int = 4

    # 进度存储
    REDIS_URL: str = ""
    TASK_TTL_SECONDS: int = 3600

    # 限速
    RATE_LIMIT_PER_DOMAIN: float = 2.0

    # SSRF：同一主机的解析结果缓存秒数
    DNS_CACHE_SECONDS: float = 30.0
    SHUTDOWN_DRAIN_SECONDS: float = 20.0


settings = Settings()