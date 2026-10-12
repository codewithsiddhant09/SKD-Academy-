from __future__ import annotations

import asyncio
from typing import Any

from socketio import ASGIApp, AsyncServer

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
    session_id = data.get("session_id") or sid
    message = data.get("message", "")
    user_id = data.get("user_id") or data.get("userId")

    logger.info("socket user_message from %s: %s", session_id, message)

    # Notify client we are typing
    await sio.emit("typing_start", {"session_id": session_id}, to=sid)

    assistant = deps.assistant
    if assistant is None:
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

    # Same code path as POST /chat; run in a thread so a slow LLM call does not
    # block every other socket connection on the event loop.
    try:
        response = await asyncio.to_thread(assistant.chat, session_id, message, user_id)
    except Exception:
        logger.exception("socket chat failed: session=%s", session_id)
        await sio.emit(
            "bot_response",
            {"session_id": session_id, "reply": "I apologize, something went wrong. Please try again."},
            to=sid,
        )
        await sio.emit("typing_end", {"session_id": session_id}, to=sid)
        return

    await sio.emit(
        "bot_response",
        {
            "session_id": session_id,
            "reply": response.reply,
            "intent": response.intent.value,
            "structured": response.structured,
        },
        to=sid,
    )

    if response.recommendations:
        salons = [
            {
                "salonId": r.vendor_id,
                "salonName": r.salon_name,
                "rating": r.rating,
                "location": r.location,
                "services": r.services,
                "image": r.image,
                "reason": r.reason,
                "redirectUrl": r.redirect_url,
            }
            for r in response.recommendations
        ]
        await sio.emit("salon_cards", {"salons": salons}, to=sid)

    # End typing
    await sio.emit("typing_end", {"session_id": session_id}, to=sid)


def create_socket_app(fastapi_app) -> ASGIApp:
    """Wrap the provided FastAPI app with Socket.IO ASGI app."""
    return ASGIApp(sio, other_asgi_app=fastapi_app, socketio_path="/socket.io")
