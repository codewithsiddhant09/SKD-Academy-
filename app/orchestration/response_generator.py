from __future__ import annotations

from app.models.enums import IntentType
from app.models.schemas import BookingPayload


class ResponseGenerator:
    """Natural language only — never makes business decisions."""

    PLATFORM_REPLY = (
        "Bookly is an online salon and wellness booking platform that helps customers "
        "discover nearby salons, explore beauty and wellness services, compare service providers, "
        "and book appointments online. Customers can also manage bookings, payments, "
        "cancellations, reviews, and recommendations through one seamless experience."
    )

    AI_REPLY = (
        "I am Bookly's AI Assistant.\n\n"
        "I can help you discover salons, explore services, book appointments, and answer "
        "questions about Bookly's policies and features.\n\n"
        "How may I assist you today?"
    )

    @classmethod
    def category_list(cls, names: list[str]) -> str:
        if not names:
            return (
                "I am unable to retrieve the category list at the moment. "
                "Please try again shortly."
            )
        body = "\n".join(f"• {name}" for name in names)
        return (
            f"Available Categories:\n\n{body}\n\n"
            "How can I assist you with one of these services?"
        )

    @classmethod
    def category_detail(cls, category: str) -> str:
        return (
            f"Certainly!\n\n"
            f"{category} is one of our available service categories.\n\n"
            f"It includes various {category.lower()}-related beauty and grooming services "
            f"offered by our partner salons.\n\n"
            f"Would you like me to help you find salons offering this service?"
        )

    @classmethod
    def location_prompt(cls) -> str:
        return "May I know your preferred location so I can recommend nearby salons?"

    @classmethod
    def service_prompt(cls, category_names: list[str]) -> str:
        if category_names:
            body = "\n".join(f"• {name}" for name in category_names)
            return (
                "Thank you for reaching out.\n\n"
                "To assist you, could you please let me know which service you are looking for?\n\n"
                f"You may explore the following categories:\n\n{body}\n\n"
                "Please let me know which service you would like to book."
            )
        return (
            "Thank you for reaching out.\n\n"
            "To assist you, could you please let me know which service you are looking for?"
        )

    @classmethod
    def salon_results(cls, location: str, service: str | None, *, salon_search: bool) -> str:
        if salon_search or not service:
            return (
                f"Thank you.\n\n"
                f"I found several salons in {location}.\n\n"
                f"Please select your preferred salon to continue."
            )
        return (
            f"Thank you.\n\n"
            f"I found several salons in {location} that offer {service}.\n\n"
            f"Please select your preferred salon to continue."
        )

    @classmethod
    def no_salons(cls, location: str, service: str | None) -> str:
        if not service:
            return (
                f"Thank you.\n\n"
                f"There are currently no salons available in {location}.\n\n"
                f"You may try a nearby location, or let me know a specific service you are looking for."
            )
        return (
            f"Thank you.\n\n"
            f"Although {service} is available on our platform, there are currently no salons "
            f"offering this service in {location}.\n\n"
            f"You may try a nearby location or explore alternative services."
        )

    @classmethod
    def booking_summary(cls, payload: BookingPayload, *, updated: bool = False) -> str:
        heading = "Updated appointment details:" if updated else "Please confirm your booking details:"
        return (
            f"{heading}\n\n"
            f"Salon:\n{payload.salon}\n\n"
            f"Service:\n{payload.service}\n\n"
            f"Date:\n{payload.date}\n\n"
            f"Time:\n{payload.time}\n\n"
            "Would you like me to confirm this appointment?"
        )

    @classmethod
    def booking_success(cls, payload: BookingPayload) -> str:
        return (
            "Your appointment request has been submitted successfully.\n\n"
            f"Salon:\n{payload.salon}\n\n"
            f"Service:\n{payload.service}\n\n"
            f"Date:\n{payload.date}\n\n"
            f"Time:\n{payload.time}\n\n"
            "Thank you for choosing Bookly."
        )

    @classmethod
    def fallback(cls, full_name: str | None = None) -> str:
        if full_name:
            return (
                f"Welcome back {full_name}.\n\n"
                "I can assist you with salon discovery, appointment bookings, and any questions "
                "about our services or policies.\n\n"
                "How may I assist you today?"
            )
        return (
            "Welcome to Bookly.\n\n"
            "I can assist you with salon discovery, appointment bookings, and any questions "
            "about our services or policies.\n\n"
            "How may I assist you today?"
        )

    @classmethod
    def booking_field_prompt(cls, field: str, draft: BookingPayload) -> str:
        service = draft.service or "appointment"
        salon = draft.salon
        prompts = {
            "service": (
                "Certainly!\n\n"
                "Could you please let me know which service you would like to book?"
            ),
            "salon": (
                f"Certainly!\n\n"
                f"I'd be happy to help you book a {service} appointment.\n\n"
                f"Which salon would you prefer?"
            ),
            "date": (
                f"Certainly!\n\n"
                f"I'd be happy to help you book a {service} appointment"
                + (f" at {salon}" if salon else "")
                + ".\n\nMay I know your preferred appointment date?"
            ),
            "time": (
                f"Great choice.\n\n"
                f"May I know your preferred appointment time"
                + (f" for {service} at {salon}" if salon and service else "")
                + "?"
            ),
        }
        return prompts.get(field, "Could you please share the next booking detail?")
