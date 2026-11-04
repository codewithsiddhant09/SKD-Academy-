from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
import asyncio
import json

from app.api import deps
from app.models.schemas import ChatRequest, ChatResponse, DebugRagRequest, DebugRagResponse
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


def _assistant():
    if deps.assistant is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return deps.assistant


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    from app.core.logging import get_logger
    logger = get_logger(__name__)
    
    logger.info("=== CHAT REQUEST RECEIVED ===")
    logger.info("session_id: %s", payload.session_id)
    logger.info("platform: %s", payload.platform)
    logger.info("user_id: %s", payload.user_id)
    
    # Check for token in request body
    body_token = payload.auth_token
    logger.info("auth_token in BODY: %s", bool(body_token))
    
    # Check for token in headers
    header_token = request.headers.get("x-auth-token") or request.headers.get("x-auth-token-user")
    logger.info("auth_token in HEADERS: %s", bool(header_token))
    
    # Use token from body first, fallback to headers
    final_token = body_token or header_token
    
    if final_token:
        logger.info("✅ TOKEN FOUND: %s... (length=%d)", final_token[:20], len(final_token))
    else:
        logger.warning("❌ NO TOKEN FOUND in body or headers!")
    
    assistant = _assistant()
    session = assistant.sessions.get(payload.session_id)
    session.booking_platform = payload.platform
    session.whatsapp_phone = payload.user_id if payload.platform == "whatsapp" else None
    session.whatsapp_name = payload.user_name if payload.platform == "whatsapp" else None
    
    # Save token to session (from body OR headers)
    if payload.platform == "app" and final_token:
        session.jwt_token = final_token
        logger.info("✅ Auth token saved to session.jwt_token")
    else:
        logger.warning("⚠️ No auth_token saved! platform=%s, token=%s", payload.platform, bool(final_token))
    
    if payload.payment_option:
        session.payment_option = payload.payment_option
    
    return assistant.chat(session_id=payload.session_id, user_message=payload.message, user_id=payload.user_id if payload.platform == "app" else None)


@router.post("/debug-rag", response_model=DebugRagResponse)
def debug_rag(payload: DebugRagRequest) -> DebugRagResponse:
    """Show which knowledge-base passages a question retrieves."""
    knowledge = _assistant().knowledge
    if knowledge is None:
        raise HTTPException(status_code=503, detail="Knowledge base not configured")
    hits = knowledge.retrieve_with_scores(payload.question)
    return DebugRagResponse(
        question=payload.question,
        retrieved_chunks=[doc.page_content for doc, _ in hits],
        similarity_scores=[score for _, score in hits],
        sources=[(doc.metadata or {}).get("source") for doc, _ in hits],
    )



@router.get("/chat/stream/{session_id}")
async def payment_status_stream(session_id: str, request: Request):
    """
    Server-Sent Events endpoint for real-time payment status updates.
    
    Automatically monitors pending PayNow payments and sends status updates
    when payment is completed or failed.
    
    Usage:
    const eventSource = new EventSource('/chat/stream/{session_id}');
    eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'payment_status') {
            showMessage(data.message);
        }
    };
    """
    logger.info(f"SSE stream started for session: {session_id}")
    
    async def event_generator():
        """Generate server-sent events for payment status updates"""
        assistant = _assistant()
        session = assistant.sessions.get(session_id)
        check_count = 0
        max_checks = 24  # 2 minutes (24 * 5 seconds)
        
        try:
            # Send initial connection message
            yield f"data: {json.dumps({'type': 'connected', 'message': 'Payment monitoring started'})}\n\n"
            
            while check_count < max_checks:
                # Check if client disconnected
                if await request.is_disconnected():
                    logger.info(f"Client disconnected from SSE stream: {session_id}")
                    break
                
                # Check if there's a pending payment to verify
                pending_check = getattr(session, 'pending_payment_check', False)
                last_booking_id = getattr(session, 'last_booking_id', None)
                
                if pending_check and last_booking_id:
                    logger.info(f"Checking payment status for booking: {last_booking_id}")
                    
                    try:
                        # Get auth token
                        token = session.jwt_token or session.auth_token
                        if token:
                            auth_headers = {
                                "x-auth-language": "English",
                                "x-user-type": "User",
                                "x-auth-token-user": token
                            }
                            
                            # Check payment status
                            result = assistant.bookings.verify_payment_status(last_booking_id, auth_headers)
                            
                            payment_status = result.get('payment_status', 'Unknown')
                            payment_complete = result.get('payment_complete', False)
                            tell_customer = result.get('tell_customer', '')
                            
                            # If payment is complete or explicitly failed
                            if payment_complete or payment_status in ['Paid', 'Failed']:
                                logger.info(f"Payment status changed: {payment_status}")
                                
                                # Send payment status update
                                event_data = {
                                    'type': 'payment_status',
                                    'status': payment_status,
                                    'message': tell_customer,
                                    'complete': payment_complete,
                                    'booking_id': last_booking_id,
                                    'order_id': result.get('order_id', '')
                                }
                                
                                yield f"data: {json.dumps(event_data)}\n\n"
                                
                                # Clear the pending check flag
                                session.pending_payment_check = False
                                
                                # Send completion event
                                yield f"data: {json.dumps({'type': 'stream_end', 'message': 'Monitoring complete'})}\n\n"
                                break
                            
                    except Exception as e:
                        logger.error(f"Error checking payment status: {e}")
                        # Continue checking despite errors
                
                check_count += 1
                
                # Send heartbeat to keep connection alive
                if check_count % 6 == 0:  # Every 30 seconds
                    yield f"data: {json.dumps({'type': 'heartbeat', 'count': check_count})}\n\n"
                
                # Wait 5 seconds before next check
                await asyncio.sleep(5)
            
            # Timeout reached
            if check_count >= max_checks:
                logger.info(f"SSE stream timeout for session: {session_id}")
                yield f"data: {json.dumps({'type': 'timeout', 'message': 'Payment monitoring timed out'})}\n\n"
        
        except asyncio.CancelledError:
            logger.info(f"SSE stream cancelled for session: {session_id}")
        except Exception as e:
            logger.error(f"SSE stream error for session {session_id}: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )
