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
    GENERAL_CONVERSATION = "general_conversation"
