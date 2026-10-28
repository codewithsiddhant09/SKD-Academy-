from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Bookly AI Appointment Chatbot"
    app_env: str = "development"
    app_port: int = 8000
    # Timezone used to resolve "today"/"tomorrow" and reject past appointments.
    app_timezone: str = "Asia/Dubai"
    
    # Booking timezone for slot/date parsing
    booking_timezone: str = "Asia/Dubai"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    categories_api_url: str = "https://test.bookly.ae:2087/user/allCategories"
    salon_info_api_url: str = "https://test.bookly.ae:2087/user/viewVendor"
    bookly_api_token: str = ""
    whatsapp_booking_secret: str = ""
    booking_create_api_url: str = "http://15.252.235.83:2053/booking/createBooking"
    booking_paynow_api_url: str = "http://15.252.235.83:2053/booking/payNowBooking"
    booking_view_api_url: str = "http://15.252.235.83:2053/booking/viewBooking"
    booking_cancellation_amount_api_url: str = "http://15.252.235.83:2053/booking/getCancellationAmount"
    booking_cancel_api_url: str = "http://15.252.235.83:2053/booking/cancelBookingByUser"
    booking_api_timeout_seconds: int = 15
    booking_api_verify_ssl: bool = True
    booking_vat_percentage: float = 5.0
    
    # Cancellation policy
    free_cancellation_hours: float = 2.0
    cancellation_fee_aed: float = 10.0
    cancellation_fee_percentage: float = 0.0
    
    # Ziina payment integration
    ziina_base_url: str = "https://api.ziina.com/v1"
    ziina_api_key: str = ""
    ziina_test_mode: bool = False
    ziina_refund_mock: bool = False
    
    # Payment settings
    payment_result_base_url: str = "http://localhost:8000/payment/paymentResult"
    payment_hold_minutes: int = 10
    whatsapp_refund_processing_time: str = "24-48 hours"

    # MongoDB source (optional; gracefully skipped when unset)
    mongodb_uri: str = ""
    mongodb_db_name: str = "bookly"
    mongodb_users_collection: str = "users"
    mongodb_addresses_collection: str = "addresses"
    mongodb_services_collection: str = "services"
    mongodb_categories_collection: str = "categories"
    mongodb_reviews_collection: str = "reviews"

    categories_cache_ttl_seconds: int = 3600
    request_timeout_seconds: int = 10
    verify_ssl: bool = True

    rag_persist_directory: str = ".chroma"
    rag_collection_name: str = "bookly_knowledge"
    top_k_retrieval: int = 8

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
