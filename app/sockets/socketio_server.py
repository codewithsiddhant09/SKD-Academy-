from __future__ import annotations

import asyncio
from typing import Any

import socketio
from socketio import AsyncServer, ASGIApp

from app.api import deps
from app.core.logging import get_logger

logger = get_logger(__name__)

# Async Socket.IO server configured for ASGI
sio: AsyncServer = AsyncServer(async_mode="asgi", cors_allowed_origins="*")


@sio.event
async def connect(sid: str, environ: dict[str, Any], auth: dict[str, Any] | None = None) -> None:
    logger.info("socket connect: %s", sid)
    await sio.emit(
        "bot_response",
        {
            "session_id": sid,
            "reply": (
                "Welcome to Bookly.\n\n"
                "I am your AI appointment assistant, here to help you discover salons "
                "and book beauty services.\n\n"
                "How may I assist you today?"
            ),
        },
        to=sid,
    )


@sio.event
async def disconnect(sid: str) -> None:
    logger.info("socket disconnect: %s", sid)


@sio.event
async def user_message(sid: str, data: dict[str, Any]) -> None:
    """Handle incoming user messages over socket.

    Expects data: { session_id: str, message: str }
    Emits: typing_start, bot_response, salon_cards (optional), typing_end
    """
    session_id = data.get("session_id", "anonymous")
    message = data.get("message", "")
    user_id = data.get("user_id") or data.get("userId")

    logger.info("socket user_message from %s: %s", session_id, message)

    # Notify client we are typing
    await sio.emit("typing_start", {"session_id": session_id}, to=sid)

    orchestrator = deps.orchestrator_service
    if orchestrator is None:
        await sio.emit(
            "bot_response",
            {
                "session_id": session_id,
                "reply": (
                    "I apologize, the service is temporarily unavailable. "
                    "Please try again in a moment."
                ),
            },
            to=sid,
        )
        await sio.emit("typing_end", {"session_id": session_id}, to=sid)
        return

    # Load user context (no-op when user_id is absent) before running the workflow
    if user_id:
        orchestrator.ensure_user_context(session_id, user_id)

    # Record user message
    orchestrator.memory.add_message(session_id, "user", message)

    # Run orchestrator workflow
    state = {"session_id": session_id, "user_message": message}
    result = orchestrator.workflow.run(state)

    reply = result.get(
        "reply",
        (
            "I am here to assist you. Please let me know which service "
            "you are looking for or how I can help."
        ),
    )

    # Save assistant reply into memory
    orchestrator.memory.add_message(session_id, "assistant", reply)

    # Emit the bot response
    intent = None
    if result.get("intent_analysis"):
        intent = getattr(result.get("intent_analysis"), "intent", None)

    await sio.emit(
        "bot_response",
        {
            "session_id": session_id,
            "reply": reply,
            "intent": str(intent) if intent else None,
            "structured": result.get("structured") if result.get("structured") else {},
        },
        to=sid,
    )

    # If there are salon recommendations, emit salon_cards
    recommendations = result.get("recommendations") or []
    if recommendations:
        salons = []
        for r in recommendations:
            vendor_id = getattr(r, "vendor_id", None) or ""
            salons.append(
                {
                    "salonId": vendor_id,
                    "salonName": getattr(r, "salon_name", None),
                    "rating": getattr(r, "rating", None),
                    "distance": getattr(r, "distance", None),
                    "location": getattr(r, "location", None),
                    "services": getattr(r, "services", None) or [],
                    "reason": getattr(r, "reason", None),
                    "redirectUrl": getattr(r, "redirect_url", None) or (f"/salon/{vendor_id}" if vendor_id else None),
                }
            )

        await sio.emit("salon_cards", {"salons": salons}, to=sid)

    # End typing
    await sio.emit("typing_end", {"session_id": session_id}, to=sid)


def create_socket_app(fastapi_app) -> ASGIApp:
    """Wrap the provided FastAPI app with Socket.IO ASGI app."""
    return ASGIApp(sio, other_asgi_app=fastapi_app, socketio_path="/socket.io")
