from __future__ import annotations

from app.models.enums import IntentType
from app.orchestration.intent_classifier import IntentClassifier
from app.orchestration.models import HandlerResult, OrchestrationContext
from app.orchestration.response_generator import ResponseGenerator
from app.services.category_service import CategoryService


class CategoryHandler:
    def __init__(
        self,
        category_service: CategoryService | None,
        categories: list[str],
    ) -> None:
        self.category_service = category_service
        self.categories = categories
        self._classifier = IntentClassifier(categories)

    def _active_names(self) -> list[str]:
        if self.category_service is not None:
            try:
                return [c.name for c in self.category_service.get_categories(force_refresh=False)]
            except Exception:
                pass
        return list(self.categories)

    def handle_list(self, ctx: OrchestrationContext) -> HandlerResult:
        names = self._active_names()
        return HandlerResult(
            intent=IntentType.CATEGORY_LIST,
            reply=ResponseGenerator.category_list(names),
        )

    def handle_detail(self, ctx: OrchestrationContext) -> HandlerResult:
        names = self._active_names()
        category = ctx.intent.category or self._classifier._detect_category_detail(
            ctx.user_message, names
        )
        if not category:
            return self.handle_list(ctx)
        return HandlerResult(
            intent=IntentType.CATEGORY_DETAIL,
            category=category,
            reply=ResponseGenerator.category_detail(category),
        )
