"""Production-facing ASGI entrypoint for ``uvicorn spyrath.studio.app:app``."""

from .api import create_app
from .runtime import create_real_service

app = create_app(create_real_service())
