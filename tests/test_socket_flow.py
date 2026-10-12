"""Socket.IO handler contract: bot_response, salon_cards and typing events."""
import asyncio

from app.api import deps
from app.models.enums import IntentType
from app.models.schemas import ChatResponse, SalonRecommendation
from app.sockets import socketio_server


class FakeAssistant:
    def chat(self, session_id, message, user_id=None):
        return ChatResponse(
            session_id=session_id,
            reply="Here are salons.",
            intent=IntentType.SALON_SEARCH,
            recommendations=[SalonRecommendation(vendor_id="101", salon_name="Marina Luxe Salon", reason="Rated 4.8/5")],
        )


def test_user_message_emits_reply_and_cards(monkeypatch):
    events = []

    async def fake_emit(event, data, to=None):
        events.append((event, data))

    monkeypatch.setattr(socketio_server.sio, "emit", fake_emit)
    monkeypatch.setattr(deps, "assistant", FakeAssistant())

    asyncio.run(socketio_server.user_message("sid1", {"session_id": "s1", "message": "salons in dubai"}))

    names = [name for name, _ in events]
    assert names == ["typing_start", "bot_response", "salon_cards", "typing_end"]
    assert events[1][1]["intent"] == "salon_search"
    assert events[2][1]["salons"][0]["salonName"] == "Marina Luxe Salon"


def test_user_message_when_not_initialized(monkeypatch):
    events = []

    async def fake_emit(event, data, to=None):
        events.append((event, data))

    monkeypatch.setattr(socketio_server.sio, "emit", fake_emit)
    monkeypatch.setattr(deps, "assistant", None)

    asyncio.run(socketio_server.user_message("sid1", {"message": "hi"}))
    assert [name for name, _ in events] == ["typing_start", "bot_response", "typing_end"]
