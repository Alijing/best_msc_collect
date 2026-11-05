import logging
import sys

from uvicorn.logging import DefaultFormatter

from app.core.config import settings


def setup_logging() -> None:
    level = logging.DEBUG if settings.DEBUG else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(DefaultFormatter("%(levelprefix)s %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)