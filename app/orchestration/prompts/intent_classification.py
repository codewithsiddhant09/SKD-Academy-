"""Classify-only prompt — never generate user-facing answers."""


def build_intent_classification_prompt(categories: list[str]) -> str:
    category_lines = "\n".join(f"- {name}" for name in categories)
    return (
        "You are an intent classifier for Bookly, a salon and wellness booking platform.\n"
        "Your ONLY job is to classify the user message and extract entities.\n"
        "Do NOT generate conversational replies.\n\n"
        f"Available categories:\n{category_lines}\n\n"
        "Classify into exactly ONE intent:\n"
        "- small_talk: hi, hello, thanks, bye, how are you (no booking/service/policy content)\n"
        "- bookly_platform_information: what Bookly / this platform / this application is or does\n"
        "- bookly_ai_information: who the chatbot/assistant is, what you can do\n"
        "- category_list: list/show available categories or services to book\n"
        "- category_detail: explain a specific category (e.g. Tell me about Hair)\n"
        "- service_search: user names a specific service/treatment, optionally with location\n"
        "- salon_search: user wants salons listed without naming a specific service\n"
        "- location_search: user gives only a location for salon search\n"
        "- salon_discovery: general explore/discover salons\n"
        "- appointment_booking: book/reserve with service/salon/date/time context\n"
        "- appointment_cancellation: cancel an existing appointment\n"
        "- faq: general FAQ not covered by policy keywords\n"
        "- policy: cancellation/refund/privacy/terms/payments\n"
        "- general_conversation: fallback when nothing else fits\n\n"
        "Entity rules:\n"
        "- service: only when user names a concrete service; else null\n"
        "- category: only when service clearly maps to a listed category; else null\n"
        "- location: city/area if mentioned; else null\n"
        "- For salon_search/location_search: service and category MUST be null\n"
        "- Never invent salon names, dates, or times\n"
    )
