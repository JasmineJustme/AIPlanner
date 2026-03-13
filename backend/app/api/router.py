from fastapi import APIRouter

from app.api.config_agents import router as config_agents_router
from app.api.config_workflows import router as config_workflows_router
from app.api.config_wagents import router as config_wagents_router
from app.api.config_datasources import router as config_datasources_router
from app.api.config_llm import router as config_llm_router
from app.api.config_notifications import router as config_notifications_router
from app.api.config_import_export import router as config_import_export_router
from app.api.config_responsibilities import router as config_responsibilities_router
from app.api.system import router as system_router
from app.api.todos import router as todos_router
from app.api.messages import router as messages_router
from app.api.settings import router as settings_router
from app.api.dashboard import router as dashboard_router
from app.api.history import router as history_router
from app.api.analytics import router as analytics_router
from app.api.search import router as search_router
from app.api.audit_logs import router as audit_logs_router
from app.api.orchestration import router as orchestration_router
from app.api.scheduling import router as scheduling_router
from app.api.sse import router as sse_router

api_router = APIRouter(prefix="/api")

api_router.include_router(config_agents_router)
api_router.include_router(config_workflows_router)
api_router.include_router(config_wagents_router)
api_router.include_router(config_datasources_router)
api_router.include_router(config_llm_router)
api_router.include_router(config_notifications_router)
api_router.include_router(config_import_export_router)
api_router.include_router(config_responsibilities_router)
api_router.include_router(system_router)
api_router.include_router(todos_router)
api_router.include_router(messages_router)
api_router.include_router(settings_router)
api_router.include_router(dashboard_router)
api_router.include_router(history_router)
api_router.include_router(analytics_router)
api_router.include_router(search_router)
api_router.include_router(audit_logs_router)
api_router.include_router(orchestration_router)
api_router.include_router(scheduling_router)
api_router.include_router(sse_router)
