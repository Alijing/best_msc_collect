import logging
import os

from flask import Flask, jsonify
from flask_pydantic import ValidationError

from .config.default import Config
from logging.handlers import RotatingFileHandler

from .routes.api import api_bp

# v2 蓝图（基于 Scrapling 引擎）
from .routes.v2_api import v2_api_bp


def _setup_scrapling_env(app):
    """启动时将 Scrapling / Playwright 运行时所需的环境变量同步到 os.environ

    设计原则
    --------
    环境变量优先级（从高到低）：

    1. 进程启动时已有的 ``os.environ``（包括 ``setx`` 或 ``conda env config vars set`` 写入的）——
       推荐方式：让环境变量跟着系统/conda env 走，激活环境即生效。
    2. ``app.config['PLAYWRIGHT_BROWSERS_PATH']``（来自 ``Config``，已设为绝对路径作为兜底）——
       仅当 1 中未设置时使用。

    原因：Playwright / Patchright 启动浏览器时只会读 ``os.environ``，而 Flask 的
    ``app.config`` 不会自动注入到子进程。这里把 ``app.config`` 同步到 ``os.environ``，
    保证 Scrapling 内部能正确找到浏览器二进制。

    推荐做法
    --------
    浏览器已装到 ``D:\\ProgramData\\miniconda3\\envs\\best_msc_collect\\pw-browsers``，
    可任选一种方式持久化环境变量：

    ````powershell
    # 方式 1：用户级（推荐，简单）
    setx PLAYWRIGHT_BROWSERS_PATH "D:\\ProgramData\\miniconda3\\envs\\best_msc_collect\\pw-browsers"

    # 方式 2：conda env 级（跟着环境走，conda env remove 时一并清理）
    conda env config vars set PLAYWRIGHT_BROWSERS_PATH=D:\\ProgramData\\miniconda3\\envs\\best_msc_collect\\pw-browsers -n best_msc_collect
    ````

    注意：``setx`` 不会更新当前 shell，必须关闭 PowerShell 重开后才生效。
    """
    # 优先保留进程已有的环境变量（conda env config vars set 设置的）
    if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
        # 退化：使用 app.config 中的值
        pw_path = app.config.get("PLAYWRIGHT_BROWSERS_PATH")
        if pw_path:
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = pw_path
            app.logger.info(f"已从 app.config 设置 PLAYWRIGHT_BROWSERS_PATH={pw_path}")
    else:
        # 已存在（来自 conda env 或系统），仅记录不覆盖
        app.logger.info(
            f"PLAYWRIGHT_BROWSERS_PATH 已存在（来自 conda env 或系统）：{os.environ['PLAYWRIGHT_BROWSERS_PATH']}"
        )


def setup_logging(log_level, log_file):
    """设置全局日志配置"""
    # 创建日志格式化器
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # 获取根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # 创建文件处理器，使用循环日志文件
    file_handler = RotatingFileHandler(
        log_file, maxBytes=1024 * 1024 * 10, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # 创建控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # 将处理器添加到日志记录器中
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    return root_logger


def create_app():
    """创建 Flask 应用"""
    app = Flask(__name__)

    # 加载配置
    app.config.from_object(Config)

    # 同步 Scrapling / Playwright 运行时所需的环境变量
    _setup_scrapling_env(app)

    # 设置全局日志配置
    setup_logging(app.config["LOG_LEVEL"], app.config["LOG_FILE"])

    # 注册蓝图
    # v1：Selenium 引擎（保留兼容）
    app.register_blueprint(api_bp, url_prefix="/api")
    # v2：Scrapling 引擎（默认反爬绕过 + 自适应选择器）
    app.register_blueprint(v2_api_bp, url_prefix="/api/v2")

    # 启用 Pydantic 验证错误处理
    app.config["FLASK_PYDANTIC_VALIDATION_ERROR_RAISE"] = True

    @app.route("/")
    def index():
        return {
            "message": "Welcome to Best MSC Collect Service!",
            "version": "1.0.0",
            "docs": "/api/health - Health check endpoint",
        }

    app.logger.info("Starting Best MSC Collect Service...")
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host=app.config["HOST"], port=app.config["PORT"], debug=app.config["DEBUG"])
