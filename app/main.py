import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Ensure project root is on sys.path regardless of PM2 cwd or entrypoint.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("bookly")

from app.api import deps
from app.api.router import api_router
from app.sockets.socketio_server import create_socket_app


async def _init_dependencies() -> None:
    try:
        await asyncio.to_thread(deps.initialize_dependencies)
    except Exception:
        logger.exception("Dependency initialization failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Initialise in the background so the server accepts connections immediately;
    # endpoints return 503 until the assistant is ready.
    task = asyncio.create_task(_init_dependencies())
    yield
    task.cancel()


fastapi_app = FastAPI(title="BOOKLY AI Appointment Agent", lifespan=lifespan)
cors_origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",") if origin.strip()]
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials="*" not in cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

fastapi_app.include_router(api_router)

# Socket.IO and REST share one ASGI app; uvicorn serves `app.main:app`.
app = create_socket_app(fastapi_app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", os.getenv("APP_PORT", "5000"))))
