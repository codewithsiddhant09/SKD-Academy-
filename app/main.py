import sys
from pathlib import Path

# Ensure project root is on sys.path regardless of PM2 cwd or entrypoint.
# Required when PM2 runs "python app/main.py" instead of "uvicorn app.main:app".
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("bookly")

from app.api.router import api_router
from app.api import deps

app = FastAPI(title="BOOKLY AI Appointment Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    logger.info("Starting BOOKLY AI - dependencies will be initialized on first request")
    # Initialize dependencies lazily in a background task to avoid blocking startup
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=1)
    
    def init_deps():
        try:
            deps.initialize_dependencies()
            logger.info("Dependencies initialized successfully")
        except Exception as e:
            logger.exception("Dependency initialization failed: %s", e)
    
    # Run initialization in thread pool to not block async event loop
    loop.run_in_executor(executor, init_deps)


app.include_router(api_router)

# Mount Socket.IO ASGI wrapper so Socket.IO and REST share the same server
try:
    from app.sockets.socketio_server import create_socket_app

    # Wrap the FastAPI app with the Socket.IO ASGI app
    asgi_app = create_socket_app(app)
    # Rebind the name `app` so Uvicorn serves the combined ASGI app
    app = asgi_app
except Exception:
    logger.exception("Failed to initialize Socket.IO app; continuing with REST only")
