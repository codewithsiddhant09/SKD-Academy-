from __future__ import annotations

from app.graph.workflow import OrchestratorWorkflow
from app.models.state import GraphState
from app.orchestration.models import HandlerResult, OrchestrationContext
from app.orchestration.session_manager import SessionManager


class BookingHandler:
    """Delegates booking slot-filling and confirmation to existing booking engine."""

    def __init__(self, workflow: OrchestratorWorkflow, session: SessionManager) -> None:
        self.workflow = workflow
        self.session = session

    def handle(self, ctx: OrchestrationContext) -> HandlerResult:
        state: GraphState = {
            "session_id": ctx.session_id,
            "user_message": ctx.user_message,
            "history": ctx.history,
            "intent_analysis": ctx.intent,
        }
        if ctx.resume_booking_after_faq:
            state["resume_booking_after_faq"] = True
            result = self.workflow.faq_policy(state)
        else:
            result = self.workflow.booking(state)

        intent = result.get("intent_analysis")
        return HandlerResult(
            intent=intent.intent if intent else ctx.intent.intent,
            reply=result.get("reply", ""),
            service=result.get("service") or (intent.service if intent else None),
            category=result.get("category") or (intent.category if intent else None),
            location_analysis=result.get("location_analysis"),
            recommendations=result.get("recommendations") or [],
            booking_payload=result.get("booking_payload"),
            booking_response=result.get("booking_response"),
            booking_stage=result.get("booking_stage"),
        )
