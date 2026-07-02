from __future__ import annotations

from app.orchestration.handlers.booking_handler import BookingHandler
from app.orchestration.handlers.category_handler import CategoryHandler
from app.orchestration.handlers.fallback_handler import FallbackHandler
from app.orchestration.handlers.faq_handler import FaqHandler
from app.orchestration.handlers.greeting_handler import GreetingHandler
from app.orchestration.handlers.platform_handler import PlatformHandler
from app.orchestration.handlers.salon_handler import SalonHandler
from app.orchestration.models import HandlerResult, OrchestrationContext, RouteTarget


class HandlerRegistry:
    def __init__(
        self,
        greeting: GreetingHandler,
        platform: PlatformHandler,
        category: CategoryHandler,
        salon: SalonHandler,
        booking: BookingHandler,
        faq: FaqHandler,
        fallback: FallbackHandler,
    ) -> None:
        self.greeting = greeting
        self.platform = platform
        self.category = category
        self.salon = salon
        self.booking = booking
        self.faq = faq
        self.fallback = fallback

    def dispatch(self, target: RouteTarget, ctx: OrchestrationContext) -> HandlerResult:
        if target == RouteTarget.GREETING:
            return self.greeting.handle(ctx)
        if target == RouteTarget.PLATFORM_INFORMATION:
            return self.platform.handle_platform(ctx)
        if target == RouteTarget.AI_INFORMATION:
            return self.platform.handle_ai(ctx)
        if target == RouteTarget.CATEGORY_LIST:
            return self.category.handle_list(ctx)
        if target == RouteTarget.CATEGORY_DETAIL:
            return self.category.handle_detail(ctx)
        if target == RouteTarget.SALON_SEARCH:
            return self.salon.handle(ctx)
        if target == RouteTarget.BOOKING:
            return self.booking.handle(ctx)
        if target == RouteTarget.FAQ:
            return self.faq.handle(ctx)
        return self.fallback.handle(ctx)
