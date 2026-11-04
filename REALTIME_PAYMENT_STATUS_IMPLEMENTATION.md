# Real-Time Payment Status Implementation Guide

## 🎯 Goal
Show payment confirmation message in chatbot automatically after user completes payment, without user sending another message.

## ✅ Backend Status (COMPLETED)

### What's Already Done:
1. ✅ SSE endpoint created: `GET /chat/stream/{session_id}`
2. ✅ Payment verification polling (every 5 seconds for 10 minutes)
3. ✅ Session flag `pending_payment_check` set after PayNow booking
4. ✅ Automatic payment status monitoring via `check_payment_status` tool
5. ✅ Fallback to `viewBooking` API when verify returns empty results

### Files Modified:
- `app/api/routes/chat.py` - Added SSE endpoint
- `app/agent/tools.py` - Payment checking logic
- `app/agent/session.py` - Added session flags
- `app/services/booking_service.py` - Payment verification

## ❌ Current Problem

**Frontend is NOT connecting to SSE endpoint!**

Looking at the logs from your booking:
```
0|agentserver  | 2026-11-04 08:20:15,499 | INFO | app.agent.assistant | TOOL: confirm_booking(...)
0|agentserver  | 2026-11-04 08:20:17,161 | INFO | app.agent.assistant | CHAT: session=1793780287845_3cva94fn
0|agentserver  | INFO:     103.225.186.22:37441 - "POST /chat HTTP/1.1" 200 OK
```

**Missing:** No SSE connection logs! The SSE endpoint is never called.

## 🔧 Frontend Implementation Required

### Step 1: Establish SSE Connection

After user sends a chat message, establish an SSE connection:

```javascript
// In your chat component after sending message
const sessionId = getUserSessionId(); // Get from your session management

// Open SSE connection
const eventSource = new EventSource(
    `https://test.bookly.ae:2087/chat/stream/${sessionId}`
);

eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('SSE Event:', data);
    
    switch (data.type) {
        case 'connected':
            console.log('✅ SSE Connected');
            break;
            
        case 'payment_status':
            // PAYMENT STATUS CHANGED!
            console.log('💰 Payment Status:', data.status);
            console.log('📝 Message:', data.message);
            
            // Add AI message to chat UI
            addMessageToChat({
                role: 'assistant',
                content: data.message,
                booking_id: data.booking_id,
                order_id: data.order_id,
                status: data.status
            });
            
            // Close connection after receiving status
            eventSource.close();
            break;
            
        case 'heartbeat':
            // Keep-alive signal (every 30 seconds)
            console.log('💓 Heartbeat:', data.count);
            break;
            
        case 'timeout':
            // Monitoring timed out after 10 minutes
            console.log('⏱️ Timeout:', data.message);
            eventSource.close();
            break;
            
        case 'stream_end':
            // Monitoring complete
            console.log('✅ Stream ended:', data.message);
            eventSource.close();
            break;
    }
};

eventSource.onerror = (error) => {
    console.error('❌ SSE Error:', error);
    eventSource.close();
};

// Clean up when component unmounts
onUnmount(() => {
    eventSource.close();
});
```

### Step 2: When to Establish Connection

```javascript
async function sendChatMessage(message) {
    // 1. Send user message to chat API
    const response = await fetch('https://test.bookly.ae:2087/chat', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'x-auth-token-user': authToken
        },
        body: JSON.stringify({
            session_id: sessionId,
            message: message,
            // ... other params
        })
    });
    
    const chatResponse = await response.json();
    
    // 2. Display AI response
    addMessageToChat({
        role: 'assistant',
        content: chatResponse.response
    });
    
    // 3. If response contains payment link, establish SSE connection
    if (chatResponse.response.includes('pay.ziina.com') || 
        chatResponse.response.includes('payment link')) {
        
        console.log('🔗 Payment link detected, establishing SSE...');
        establishSSEConnection(sessionId);
    }
}
```

### Step 3: React/Vue Example

#### React Example:

```javascript
import { useEffect, useState } from 'react';

function ChatComponent() {
    const [messages, setMessages] = useState([]);
    const [sseConnection, setSSEConnection] = useState(null);
    
    const establishSSE = (sessionId) => {
        // Close existing connection
        if (sseConnection) {
            sseConnection.close();
        }
        
        const eventSource = new EventSource(
            `https://test.bookly.ae:2087/chat/stream/${sessionId}`
        );
        
        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            
            if (data.type === 'payment_status') {
                // Add automatic message
                setMessages(prev => [...prev, {
                    role: 'assistant',
                    content: data.message,
                    timestamp: new Date()
                }]);
                
                eventSource.close();
                setSSEConnection(null);
            }
        };
        
        setSSEConnection(eventSource);
    };
    
    useEffect(() => {
        // Clean up on unmount
        return () => {
            if (sseConnection) {
                sseConnection.close();
            }
        };
    }, [sseConnection]);
    
    // ... rest of component
}
```

#### Vue Example:

```javascript
export default {
    data() {
        return {
            messages: [],
            sseConnection: null
        }
    },
    
    methods: {
        establishSSE(sessionId) {
            if (this.sseConnection) {
                this.sseConnection.close();
            }
            
            const eventSource = new EventSource(
                `https://test.bookly.ae:2087/chat/stream/${sessionId}`
            );
            
            eventSource.onmessage = (event) => {
                const data = JSON.parse(event.data);
                
                if (data.type === 'payment_status') {
                    this.messages.push({
                        role: 'assistant',
                        content: data.message,
                        timestamp: new Date()
                    });
                    
                    eventSource.close();
                    this.sseConnection = null;
                }
            };
            
            this.sseConnection = eventSource;
        }
    },
    
    beforeDestroy() {
        if (this.sseConnection) {
            this.sseConnection.close();
        }
    }
}
```

## 🧪 Testing

### Test SSE Endpoint Directly:

```bash
curl -N -H "Accept: text/event-stream" \
  "https://test.bookly.ae:2087/chat/stream/test-session-123"
```

Should return:
```
data: {"type":"connected","session_id":"test-session-123"}

data: {"type":"heartbeat","count":6}
```

### Test Complete Flow:

1. User books service with "Pay Now"
2. User receives payment link
3. **Check browser console:** Should see "✅ SSE Connected"
4. User completes payment on Ziina
5. **Within 5-15 seconds:** Payment status message appears automatically
6. **Check browser console:** Should see "💰 Payment Status: Paid"

## 📊 SSE Event Types

| Event Type | Description | Action Required |
|------------|-------------|-----------------|
| `connected` | SSE connection established | Log only |
| `payment_status` | Payment completed/failed | Display message in chat |
| `heartbeat` | Keep-alive signal (every 30s) | Log only |
| `timeout` | 10-minute monitoring timeout | Close connection |
| `stream_end` | Monitoring complete | Close connection |

## 🔍 Debugging

### Check if SSE is working:

```javascript
// Add this to your code temporarily
eventSource.onopen = () => {
    console.log('✅ SSE Connection OPENED');
};

eventSource.onerror = (error) => {
    console.error('❌ SSE Connection ERROR:', error);
    console.log('ReadyState:', eventSource.readyState);
    // 0 = CONNECTING, 1 = OPEN, 2 = CLOSED
};
```

### Backend Logs to Monitor:

```bash
ssh root@178.128.102.23
pm2 logs agentserver --lines 100

# Look for:
# - "Starting SSE stream for session: ..."
# - "Checking payment status for booking: ..."
# - "Payment status changed: ..."
```

## 🚨 Important Notes

1. **Session ID:** Must be the same session ID used for chat
2. **Connection Management:** Close connection after receiving payment status
3. **Error Handling:** Handle connection errors gracefully
4. **Mobile Support:** EventSource is supported in all modern browsers
5. **CORS:** Already configured in backend
6. **Timeout:** Connection auto-closes after 10 minutes

## 📝 Backend Deployment Status

**Current Status:** ⚠️ Needs deployment

**Deploy command:**
```bash
ssh root@178.128.102.23
cd /var/www/a-agent-base
git pull origin fixes
pm2 restart agentserver
pm2 logs agentserver
```

**Verify deployment:**
```bash
curl -N "https://test.bookly.ae:2087/chat/stream/test-123"
# Should NOT return 404
```

## ✅ Checklist

Backend (Completed):
- [x] SSE endpoint created
- [x] Payment verification logic
- [x] Session flags
- [ ] **Deployed to production server**

Frontend (Required):
- [ ] EventSource connection established
- [ ] Message handling implemented
- [ ] Connection cleanup on unmount
- [ ] Error handling
- [ ] Testing complete

## 🆘 Need Help?

Contact backend team if:
- SSE endpoint returns 404 (not deployed)
- No payment status events received (check backend logs)
- Connection fails immediately (check CORS/firewall)

---

**Last Updated:** 2026-11-04  
**Backend Version:** commit `07ed501`
