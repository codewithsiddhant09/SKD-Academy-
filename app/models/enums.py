from enum import Enum


class IntentType(str, Enum):
    """What the assistant did in a turn, derived from the tools it called."""

    FAQ = "faq"
    CATEGORY_LIST = "category_list"
    SALON_SEARCH = "salon_search"
    APPOINTMENT_BOOKING = "appointment_booking"
    GENERAL_CONVERSATION = "general_conversation"
