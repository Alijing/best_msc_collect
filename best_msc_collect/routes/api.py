import logging

from flask import Blueprint, jsonify, current_app, request
from flask_pydantic import validate, ValidationError

from ..models.unified_model import UnifiedCollectConfig
from ..services import NovelCrawlService
from ..services import VideoPreviewService

# 获取日志记录器
logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__)


@api_bp.route('/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    return jsonify({
        "status": "healthy",
        "message": "Web Preview Service is running"
    }), 200


@api_bp.route('/video/preview', methods=['POST'])
@validate()
def video_preview(body: UnifiedCollectConfig):
    """使用预设配置进行预览"""
    try:
        # 从应用配置中加载预设基础配置
        default_config = current_app.config.get('PREVIEW_CONFIG', {})

        # 调用服务层处理业务逻辑
        result = VideoPreviewService.video_preview(body, default_config=default_config)

        return jsonify(result), 200 if result["success"] else 500

    except Exception as e:
        logger.error(f"预览接口发生错误: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_bp.route('/novel/crawl', methods=['POST'])
@validate()
def novel_crawl():
    """列表-详情页小说数据采集"""
    try:
        data = request.get_json()
        # 将原始 JSON 数据转换为 UnifiedCollectConfig 对象列表
        if data is not None and isinstance(data, list):
            body = [UnifiedCollectConfig(**item) for item in data]
        else:
            # 如果不是列表格式，可以按需处理或抛出错误
            raise ValueError("Expected a list of configurations")

        # 从应用配置中加载预设基础配置
        default_config = current_app.config.get('WEB_DATA_COLLECT_CONFIG', {})

        # 调用服务层处理业务逻辑
        result = NovelCrawlService.collect_chapter_and_details(
            body,
            default_config=default_config
        )
        return jsonify(result), 200 if result["success"] else 500

    except Exception as e:
        logger.error(f"列表-详情页小说数据采集接口发生错误: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# 添加验证错误处理
@api_bp.errorhandler(ValidationError)
def handle_validation_error(error):
    """处理参数验证错误"""
    logger.error(f"参数验证失败: {error}")
    # 捕捉flask_pydantic 的 validate（）返回的错误,并且重写返回值（方便前端msg）
    body_params = error.body_params
    form_params = error.form_params
    path_params = error.path_params
    query_params = error.query_params
    msg = {}
    if body_params is not None:
        msg["body_params"] = [{k: v for k, v in params.items() if k != 'url'} for params in body_params]
    if form_params is not None:
        msg["form_params"] = [{k: v for k, v in params.items() if k != 'url'} for params in form_params]
    if path_params is not None:
        msg["path_params"] = [{k: v for k, v in params.items() if k != 'url'} for params in path_params]
    if query_params is not None:
        msg["query_params"] = [{k: v for k, v in params.items() if k != 'url'} for params in query_params]

    return jsonify({
        "success": False,
        "error": "参数验证失败",
        "details": msg
    }), 400
