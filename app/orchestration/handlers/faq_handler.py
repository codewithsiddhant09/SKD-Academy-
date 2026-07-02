from __future__ import annotations

from app.agents.faq_agent import FaqAgent
from app.models.enums import IntentType
from app.orchestration.models import HandlerResult, OrchestrationContext
from app.orchestration.response_generator import ResponseGenerator
from app.orchestration.session_manager import SessionManager


class FaqHandler:
    def __init__(self, faq_agent: FaqAgent, session: SessionManager) -> None:
        self.faq_agent = faq_agent
        self.session = session

    def handle(self, ctx: OrchestrationContext) -> HandlerResult:
        answer = self.faq_agent.answer(ctx.user_message)
        reply = answer
        if ctx.resume_booking_after_faq or self._should_resume(ctx.session_id):
            resume = self._resume_prompt(ctx.session_id)
            reply = f"Sure.\n\n{answer}\n\nNow let's continue your booking.\n\n{resume}"
            mem = self.session.get_memory(ctx.session_id)
            status = "awaiting_confirmation" if mem.awaiting_confirmation else "collecting"
            self.session.update_memory(ctx.session_id, booking_status=status)

        intent = ctx.intent.intent
        if intent not in {IntentType.FAQ, IntentType.POLICY, IntentType.APPOINTMENT_CANCELLATION}:
            intent = IntentType.FAQ
        return HandlerResult(intent=intent, reply=reply)

    def _should_resume(self, session_id: str) -> bool:
        mem = self.session.get_memory(session_id)
        if mem.booking_status == "paused":
            return True
        if self.session.has_active_booking(session_id):
            return True
        draft = self.session.get_booking_draft(session_id)
        return any(getattr(draft, f) for f in ("service", "salon", "date", "time"))

    def _resume_prompt(self, session_id: str) -> str:
        mem = self.session.get_memory(session_id)
        draft = self.session.get_booking_draft(session_id)
        if mem.awaiting_confirmation:
            return (
                "Please confirm your appointment when you are ready, or let me know if you "
                "would like to change any detail."
            )
        for field in ("date", "time", "salon", "service"):
            if not getattr(draft, field):
                return ResponseGenerator.booking_field_prompt(field, draft)
        return "Please confirm your appointment when you are ready."
