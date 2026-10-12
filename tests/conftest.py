"""Shared offline fixtures: mock salons (no MongoDB) and a scripted fake LLM."""
import json

from openai.types.chat import ChatCompletion

from app.agent.assistant import BookingAssistant
from app.agent.tools import TOOLS, ToolContext
from app.services.booking_service import BookingService
from app.services.salon_service import SalonService

FUTURE = "2099-01-15"
# Mock salons (app/data/mock_salons.json):
MARINA_LUXE = "101"  # Dubai Marina: Hair Smoothing, Hair Coloring, Bridal Makeup
JUMEIRAH_GLOW = "102"  # Jumeirah: Facial, Bridal Makeup, Waxing
NAILS_BEYOND = "103"  # Sharjah: Pedicure, Manicure, Spa Bath
ABU_DHABI_HAIR = "104"  # Abu Dhabi: Hair Smoothing, Henna Art, Hair Cut


class NoMongo:
    """Stands in for SalonRepository/BookingRepository so tests never touch a real database."""

    def is_available(self) -> bool:
        return False


class FakeCategories:
    def get_category_names(self) -> list[str]:
        return ["Hair", "Makeup", "Face", "Nails"]


class FakeUsers:
    def __init__(self, profiles: dict | None = None) -> None:
        self.profiles = profiles or {}

    def get_user_profile(self, user_id):
        return self.profiles.get(user_id)

    def build_session_context(self, user_id, profile):
        from app.models.schemas import SessionContext

        return SessionContext(user_id=user_id, full_name=profile)


class ScriptedLLM:
    """Plays back queued steps. A step is a text reply, a list of (tool, args)
    calls, or an Exception to raise. Records every request it receives."""

    def __init__(self) -> None:
        self.queue: list = []
        self.requests: list[dict] = []
        self.chat = self
        self.completions = self

    def create(self, **kwargs) -> ChatCompletion:
        self.requests.append(kwargs)
        step = self.queue.pop(0)
        if isinstance(step, Exception):
            raise step
        if isinstance(step, str):
            message = {"role": "assistant", "content": step}
        else:
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"c{i}",
                        "type": "function",
                        "function": {"name": n, "arguments": a if isinstance(a, str) else json.dumps(a)},
                    }
                    for i, (n, a) in enumerate(step)
                ],
            }
        return ChatCompletion.model_validate(
            {
                "id": "x", "object": "chat.completion", "created": 0, "model": "fake",
                "choices": [{"index": 0, "finish_reason": "stop", "message": message}],
            }
        )


def make_assistant(users=None, knowledge=None) -> tuple[BookingAssistant, ScriptedLLM]:
    llm = ScriptedLLM()
    assistant = BookingAssistant(
        categories=FakeCategories(),
        users=users or FakeUsers(),
        salons=SalonService(repository=NoMongo()),
        bookings=BookingService(repository=NoMongo()),
        knowledge=knowledge,
        client=llm,
    )
    return assistant, llm


def call(assistant: BookingAssistant, session_id: str, tool: str, **args) -> dict:
    """Invoke a tool directly, as the LLM would (unspecified args are null)."""
    model, handler = TOOLS[tool]
    ctx = ToolContext(
        session=assistant.sessions.get(session_id),
        categories=assistant.categories,
        salons=assistant.salons,
        bookings=assistant.bookings,
        knowledge=assistant.knowledge,
    )
    full = {name: None for name in model.model_fields} | args
    return handler(ctx, model.model_validate(full))


def booking(service=None, salon_id=None, date=None, time=None, mentioned_as="specific_service") -> dict:
    """update_booking args; by default the customer named the service explicitly."""
    return {
        "service": service,
        "salon_id": salon_id,
        "date": date,
        "time": time,
        "service_mentioned_as": mentioned_as if service else None,
    }
