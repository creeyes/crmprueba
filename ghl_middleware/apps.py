import os
from django.apps import AppConfig


class GhlMiddlewareConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ghl_middleware'

    def ready(self):
        import ghl_middleware.signals  # noqa: F401

        # Arrancar el worker automatico de sync DB → GHL.
        # Solo arranca si NO estamos en el autoreloader de Django (evita doble ejecucion en dev).
        # En produccion (gunicorn) siempre arranca.
        if os.environ.get('RUN_MAIN') != 'true':
            from .sync_worker import start_sync_loop
            start_sync_loop()
