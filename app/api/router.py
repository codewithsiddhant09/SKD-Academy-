from fastapi import APIRouter

from app.api.routes.booking import router as booking_router
from app.api.routes.categories import router as categories_router
from app.api.routes.chat import router as chat_router
from app.api.routes.debug import router as debug_router
from app.api.routes.health import router as health_router
from app.api.routes.session import router as session_router
from app.api.routes.upload import router as upload_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router, tags=["health"])
api_router.include_router(categories_router, tags=["categories"])
api_router.include_router(session_router, tags=["session"])
api_router.include_router(chat_router, tags=["chat"])
api_router.include_router(booking_router, tags=["booking"])
api_router.include_router(upload_router, tags=["upload"])
api_router.include_router(debug_router, tags=["debug"])
