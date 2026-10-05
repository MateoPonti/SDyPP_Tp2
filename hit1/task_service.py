"""HTTP task service used by HIT 1 Docker containers."""

from hit1.task_service.main import app, ejecutarTarea

__all__ = ["app", "ejecutarTarea"]
