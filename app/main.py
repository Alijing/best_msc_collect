from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import analyze, content, crawl, export, extract, novel, tasks
from app.core.background import drain_background
from app.core.config import settings
from app.core.exception_handlers import register_exception_handlers, use_unified_openapi
from app.core.logging import setup_logging
from app.core.task_store import task_store
from app.fetcher import close_fetchers
from app.schemas.response import ApiResponse, HealthData


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    await task_store.init()
    yield
    await drain_background()
    await close_fetchers()
    await task_store.close()


app = FastAPI(
    title=settings.APP_NAME,
    description="小说目录结构分析与批量抓取服务（无状态、无数据库）",
    version="1.0.0",
    lifespan=lifespan,
)
register_exception_handlers(app)
use_unified_openapi(app)

app.include_router(analyze.router, prefix="/api")
app.include_router(crawl.router, prefix="/api")
app.include_router(content.router, prefix="/api")
app.include_router(extract.router, prefix="/api")
app.include_router(novel.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(export.router, prefix="/api")


@app.get("/health", tags=["system"], response_model=ApiResponse[HealthData])
async def health():
    return ApiResponse[HealthData].ok(HealthData(status="ok", app=settings.APP_NAME))
