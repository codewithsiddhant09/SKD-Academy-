# Real-Time Payment Status Updates (SSE)

## Overview
Server-Sent Events (SSE) endpoint for automatic payment status notifications without user interaction.

## Backend Endpoint

### URL
```
GET /chat/stream/{session_id}
```

### How It Works
1. User creates PayNow booking → Payment link sent
2. Frontend opens SSE connection to `/chat/stream/{session_id}`
3. Backend automatically checks payment status every 5 seconds
4. When payment completes → Event sent to frontend
5. Frontend displays congratulations message automatically

### Event Types

#### 1. Connected
```json
{
  "type": "connected",
  "message": "Payment monitoring started"
}
```

#### 2. Payment Status (Main Event)
```json
{
  "type": "payment_status",
  "status": "Paid",
  "message": "🎉 Congratulations! Your payment has been successfully completed...",
  "complete": true,
  "booking_id": "6aeae3bb45ecb752aea15a4b",
  "order_id": "BKLY-04112026-004"
}
```

#### 3. Heartbeat (Keep-Alive)
```json
{
  "type": "heartbeat",
  "count": 6
}
```

#### 4. Stream End
```json
{
  "type": "stream_end",
  "message": "Monitoring complete"
}
```

#### 5. Timeout (2 minutes)
```json
{
  "type": "timeout",
  "message": "Payment monitoring timed out"
}
```

#### 6. Error
```json
{
  "type": "error",
  "message": "Error description"
}
```

---

## Frontend Integration

### React/React Native Example

```typescript
import { useEffect, useState } from 'react';

interface PaymentStatusEvent {
  type: 'payment_status' | 'connected' | 'heartbeat' | 'timeout' | 'error';
  status?: 'Paid' | 'Failed' | 'Pending';
  message?: string;
  complete?: boolean;
  booking_id?: string;
  order_id?: string;
}

export function usePaymentStatusStream(sessionId: string, enabled: boolean) {
  const [status, setStatus] = useState<PaymentStatusEvent | null>(null);
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    if (!enabled || !sessionId) return;

    const eventSource = new EventSource(
      `${API_BASE_URL}/chat/stream/${sessionId}`
    );

    eventSource.onopen = () => {
      console.log('SSE connection opened');
      setIsConnected(true);
    };

    eventSource.onmessage = (event) => {
      const data: PaymentStatusEvent = JSON.parse(event.data);
      console.log('SSE event received:', data);

      setStatus(data);

      // Handle payment status
      if (data.type === 'payment_status') {
        // Show message in chat
        if (data.message) {
          addMessageToChat({
            role: 'assistant',
            content: data.message,
            isAutomatic: true,
          });
        }

        // Show notification
        if (data.complete) {
          showNotification('Payment Successful!', data.message);
        }

        // Close connection after receiving status
        eventSource.close();
      }

      // Handle timeout
      if (data.type === 'timeout' || data.type === 'stream_end') {
        eventSource.close();
      }
    };

    eventSource.onerror = (error) => {
      console.error('SSE error:', error);
      setIsConnected(false);
      eventSource.close();
    };

    // Cleanup
    return () => {
      eventSource.close();
      setIsConnected(false);
    };
  }, [sessionId, enabled]);

  return { status, isConnected };
}

// Usage in component
function ChatScreen() {
  const [monitoringPayment, setMonitoringPayment] = useState(false);
  
  const { status } = usePaymentStatusStream(sessionId, monitoringPayment);

  const handlePayNowBooking = async (bookingId: string) => {
    // Booking created with payment link
    // Start SSE monitoring
    setMonitoringPayment(true);
  };

  useEffect(() => {
    if (status?.type === 'payment_status' && status.complete) {
      // Payment confirmed!
      setMonitoringPayment(false);
      // Update UI
    }
  }, [status]);

  return <ChatUI />;
}
```

### Vanilla JavaScript Example

```javascript
// Start monitoring after PayNow booking created
function startPaymentMonitoring(sessionId) {
  const eventSource = new EventSource(`/chat/stream/${sessionId}`);
  
  eventSource.addEventListener('open', () => {
    console.log('Payment monitoring started');
  });
  
  eventSource.addEventListener('message', (event) => {
    const data = JSON.parse(event.data);
    
    switch (data.type) {
      case 'connected':
        console.log('Connected:', data.message);
        break;
      
      case 'payment_status':
        // Payment status received!
        console.log('Payment Status:', data.status);
        
        // Show message in chat automatically
        addMessageToChat({
          sender: 'bot',
          text: data.message,
          timestamp: new Date()
        });
        
        // Show notification
        if (data.complete) {
          showNotification('🎉 Payment Successful!');
        }
        
        // Close connection
        eventSource.close();
        break;
      
      case 'heartbeat':
        // Connection still alive
        console.log('Heartbeat:', data.count);
        break;
      
      case 'timeout':
        console.log('Monitoring timeout');
        eventSource.close();
        break;
      
      case 'error':
        console.error('SSE Error:', data.message);
        eventSource.close();
        break;
    }
  });
  
  eventSource.addEventListener('error', (error) => {
    console.error('EventSource error:', error);
    eventSource.close();
  });
  
  // Auto-close after 3 minutes (safety)
  setTimeout(() => {
    eventSource.close();
  }, 180000);
}

// Call after receiving PayNow booking confirmation
startPaymentMonitoring(sessionId);
```

### Flutter/Dart Example

```dart
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

class PaymentMonitor {
  Stream<PaymentStatusEvent> monitorPayment(String sessionId) async* {
    final client = http.Client();
    final request = http.Request(
      'GET',
      Uri.parse('$apiBaseUrl/chat/stream/$sessionId'),
    );

    final response = await client.send(request);
    
    await for (var line in response.stream
        .transform(utf8.decoder)
        .transform(LineSplitter())) {
      
      if (line.startsWith('data: ')) {
        final data = line.substring(6);
        final event = PaymentStatusEvent.fromJson(jsonDecode(data));
        yield event;
        
        if (event.type == 'payment_status' || event.type == 'timeout') {
          break;
        }
      }
    }
    
    client.close();
  }
}

// Usage
class ChatScreen extends StatefulWidget {
  @override
  _ChatScreenState createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  StreamSubscription? _paymentSubscription;
  
  void startPaymentMonitoring() {
    _paymentSubscription = PaymentMonitor()
        .monitorPayment(sessionId)
        .listen((event) {
      if (event.type == 'payment_status') {
        // Show message in chat
        setState(() {
          messages.add(Message(
            text: event.message,
            sender: 'bot',
            isAutomatic: true,
          ));
        });
        
        // Show notification
        if (event.complete) {
          showNotification('Payment Successful!');
        }
      }
    });
  }
  
  @override
  void dispose() {
    _paymentSubscription?.cancel();
    super.dispose();
  }
}
```

---

## Testing

### Using curl
```bash
curl -N http://localhost:5000/chat/stream/test_session_123
```

### Using Browser
Open browser console and run:
```javascript
const eventSource = new EventSource('http://localhost:5000/chat/stream/test_session_123');
eventSource.onmessage = (event) => console.log(JSON.parse(event.data));
```

---

## Configuration

### Timing
- Check interval: **5 seconds**
- Max duration: **2 minutes** (24 checks)
- Heartbeat: Every **30 seconds**

### Modify in `chat.py`:
```python
check_count = 0
max_checks = 24  # 2 minutes (24 * 5 seconds)
await asyncio.sleep(5)  # Check every 5 seconds
```

---

## Benefits

✅ **Real-time**: Instant updates when payment completes  
✅ **No user action**: Automatic, no need to send message  
✅ **Efficient**: Uses SSE (lighter than WebSocket)  
✅ **Reliable**: Heartbeat keeps connection alive  
✅ **Auto-cleanup**: Closes after payment or timeout  

---

## Flow Diagram

```
User Creates Booking
       ↓
Payment Link Sent
       ↓
Frontend Opens SSE Connection
       ↓
User Pays (External Ziina Page)
       ↓
Backend Checks Status (every 5s)
       ↓
Payment Detected: "Paid"
       ↓
Event Sent to Frontend
       ↓
Message Shows Automatically
       ↓
Connection Closed
```

---

## Troubleshooting

### SSE not receiving events
- Check nginx/proxy configuration (disable buffering)
- Verify session_id is correct
- Check backend logs for errors

### Connection closes immediately
- Verify session exists
- Check auth token is valid
- Review backend logs

### Events not firing
- Ensure `pending_payment_check` flag is set
- Verify `last_booking_id` exists
- Check payment verification API works

---

## Next Steps

1. Deploy backend with SSE endpoint
2. Frontend team integrates EventSource
3. Test with real payment flow
4. Monitor logs for performance
5. Adjust timing if needed

**Status**: ✅ Backend Ready  
**Frontend**: Needs Integration  
**Testing**: Required
