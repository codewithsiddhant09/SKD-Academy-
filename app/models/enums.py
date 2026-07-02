from enum import Enum


class IntentType(str, Enum):
    FAQ = "faq"
    POLICY = "policy"
    SMALL_TALK = "small_talk"
    CATEGORY_LIST = "category_list"
    SERVICE_SEARCH = "service_search"
    SALON_SEARCH = "salon_search"
    LOCATION_SEARCH = "location_search"
    SALON_DISCOVERY = "salon_discovery"
    APPOINTMENT_BOOKING = "appointment_booking"
    APPOINTMENT_CANCELLATION = "appointment_cancellation"
    CATEGORY_DETAIL = "category_detail"
    BOOKLY_PLATFORM_INFORMATION = "bookly_platform_information"
    BOOKLY_AI_INFORMATION = "bookly_ai_information"
    GENERAL_CONVERSATION = "general_conversation"
