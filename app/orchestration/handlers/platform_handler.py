from __future__ import annotations

from app.models.enums import IntentType
from app.orchestration.models import HandlerResult, OrchestrationContext
from app.orchestration.response_generator import ResponseGenerator


class PlatformHandler:
    def handle_platform(self, ctx: OrchestrationContext) -> HandlerResult:
        return HandlerResult(
            intent=IntentType.BOOKLY_PLATFORM_INFORMATION,
            reply=ResponseGenerator.PLATFORM_REPLY,
        )

    def handle_ai(self, ctx: OrchestrationContext) -> HandlerResult:
        return HandlerResult(
            intent=IntentType.BOOKLY_AI_INFORMATION,
            reply=ResponseGenerator.AI_REPLY,
        )
