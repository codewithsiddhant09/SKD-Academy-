"""Payment result page and payment confirmation endpoints."""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

from app.api import deps
from app.core.logging import get_logger
from app.utils.booking_payment import verify_ziina_payment

logger = get_logger(__name__)

router = APIRouter()


@router.get("/paymentResult", response_class=HTMLResponse)
async def payment_result(
    result: str = Query(..., description="Payment result status"),
    orderId: str = Query(None, description="Booking order ID"),
    payment_intent: str = Query(None, description="Ziina payment intent ID")
) -> HTMLResponse:
    """
    Payment result page shown after Ziina payment redirect.
    
    This endpoint:
    - Displays the payment result to the user
    - On success, verifies payment with Ziina
    - Confirms the booking if payment is successful
    
    Query params:
    - result: success/failure/cancelled
    - orderId: Booking order ID
    - payment_intent: Ziina payment intent ID
    """
    is_success = result.lower() == "success"
    
    # Build HTML response
    if is_success:
        html_title = "Payment Successful"
        html_message = "Your payment has been processed successfully. Your booking is confirmed!"
        html_color = "#4CAF50"
        
        # Attempt to verify and confirm the payment
        if payment_intent and orderId:
            try:
                await confirm_if_paid_on_ziina(orderId, payment_intent)
                logger.info(f"Payment confirmed for booking {orderId}")
            except Exception as e:
                logger.error(f"Error confirming payment for {orderId}: {e}")
                # Don't fail the page - payment might already be confirmed
        
    else:
        html_title = "Payment Failed"
        html_message = "Your payment could not be processed. Please try again or contact support."
        html_color = "#f44336"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{html_title}</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            }}
            .container {{
                background: white;
                padding: 3rem;
                border-radius: 1rem;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                text-align: center;
                max-width: 500px;
                margin: 1rem;
            }}
            .icon {{
                width: 80px;
                height: 80px;
                margin: 0 auto 1.5rem;
                border-radius: 50%;
                background-color: {html_color};
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 3rem;
                color: white;
            }}
            h1 {{
                color: #333;
                margin-bottom: 1rem;
                font-size: 2rem;
            }}
            p {{
                color: #666;
                line-height: 1.6;
                margin-bottom: 2rem;
            }}
            .order-id {{
                background: #f5f5f5;
                padding: 0.75rem;
                border-radius: 0.5rem;
                font-family: monospace;
                margin: 1.5rem 0;
                color: #333;
            }}
            .btn {{
                background-color: {html_color};
                color: white;
                padding: 1rem 2rem;
                border: none;
                border-radius: 0.5rem;
                font-size: 1rem;
                cursor: pointer;
                text-decoration: none;
                display: inline-block;
                transition: opacity 0.2s;
            }}
            .btn:hover {{
                opacity: 0.9;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="icon">{'✓' if is_success else '✗'}</div>
            <h1>{html_title}</h1>
            <p>{html_message}</p>
            {f'<div class="order-id">Order ID: {orderId}</div>' if orderId else ''}
            <a href="/" class="btn">Return to Home</a>
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)


async def confirm_if_paid_on_ziina(order_id: str, payment_intent_id: str) -> dict:
    """
    Verify payment with Ziina and confirm the booking if paid.
    
    This function is idempotent and atomic - safe to call multiple times.
    Can be called by:
    - The payment result page (this file)
    - The payment verification cron
    - The app after payment
    
    Args:
        order_id: Booking order ID
        payment_intent_id: Ziina payment intent ID
    
    Returns:
        Dict with confirmation status
    
    Raises:
        HTTPException: If booking service is not available
    """
    if deps.assistant is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        # Verify payment with Ziina
        payment_status = await verify_ziina_payment(payment_intent_id)
        
        if payment_status["status"] == "completed":
            # Confirm the booking
            result = await deps.assistant.bookings.confirm_online_booking_payment(
                order_id=order_id,
                payment_id=payment_intent_id,
                amount=payment_status["amount"]
            )
            return result
        else:
            logger.warning(f"Payment {payment_intent_id} not completed: {payment_status['status']}")
            return {"confirmed": False, "reason": "Payment not completed"}
            
    except Exception as e:
        logger.error(f"Error confirming payment: {e}")
        raise


@router.post("/confirm-booking-payment")
async def confirm_booking_payment(
    order_id: str,
    payment_intent_id: str
) -> dict:
    """
    Manual endpoint to confirm booking payment.
    
    This calls the same confirmation logic used by the payment result page.
    """
    result = await confirm_if_paid_on_ziina(order_id, payment_intent_id)
    return result
