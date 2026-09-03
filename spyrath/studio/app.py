"""Production-facing ASGI entrypoint for ``uvicorn spyrath.studio.app:app``."""

from .api import create_app
from .runtime import create_real_service, StudioRuntimeConfig
from .auth_api import create_access_controller
from .commercial import UsageStore

config = StudioRuntimeConfig.from_env()
service = create_real_service(config)
access = create_access_controller(config.metadata_db, config.auth_enabled)
usage = UsageStore(config.usage_db)
app = create_app(service, access=access, usage=usage)
