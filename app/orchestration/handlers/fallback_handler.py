from __future__ import annotations

from app.models.enums import IntentType
from app.orchestration.models import HandlerResult, OrchestrationContext
from app.orchestration.response_generator import ResponseGenerator
from app.orchestration.session_manager import SessionManager


class FallbackHandler:
    def __init__(self, session: SessionManager) -> None:
        self.session = session

    def handle(self, ctx: OrchestrationContext) -> HandlerResult:
        context = self.session.get_user_context(ctx.session_id)
        name = context.full_name if context else None
        return HandlerResult(
            intent=IntentType.GENERAL_CONVERSATION,
            reply=ResponseGenerator.fallback(name),
        )
