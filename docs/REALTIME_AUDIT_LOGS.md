# Real-Time Audit Log Streaming

This document describes the Server-Sent Events (SSE) implementation for streaming audit logs in real-time from the backend to the frontend.

## Table of Contents
- [Overview](#overview)
- [Why SSE Instead of Thrift](#why-sse-instead-of-thrift)
- [Architecture](#architecture)
- [Backend Implementation](#backend-implementation)
- [Frontend Integration](#frontend-integration)
- [API Reference](#api-reference)
- [Performance & Scalability](#performance--scalability)
- [Troubleshooting](#troubleshooting)

---

## Overview

The real-time audit log streaming feature allows users to receive their audit logs as they are created, without polling. This provides immediate visibility into security events, authentication attempts, and user actions.

**Key Features:**
- ✅ Real-time streaming of audit logs
- ✅ Automatic reconnection on disconnect
- ✅ Low latency (~2 seconds)
- ✅ Efficient - only sends new logs
- ✅ User-specific - each user only sees their own logs
- ✅ Secure - requires authentication

---

## Why SSE Instead of Thrift

### ❌ Why NOT Thrift?

| Issue | Description |
|-------|-------------|
| **No Browser Support** | Thrift has no native browser API - requires compilation/transpilation |
| **Web Incompatible** | Designed for microservices, not web browsers |
| **Complex Setup** | Requires .thrift files, code generation for both Python and TypeScript |
| **No Streaming** | Thrift doesn't natively support streaming to browsers |
| **Overkill** | Too much overhead for simple log streaming |

### ✅ Why SSE?

| Benefit | Description |
|---------|-------------|
| **Native Browser API** | `EventSource` is built into all modern browsers |
| **Simple** | No compilation, no code generation, just HTTP |
| **Auto-Reconnect** | Browser automatically reconnects on disconnect |
| **Efficient** | HTTP/2 multiplexing, long-lived connections |
| **FastAPI Support** | Perfect integration with FastAPI's `StreamingResponse` |
| **TypeScript Ready** | Native TypeScript/JavaScript support |

### Comparison Table

| Feature | Thrift | SSE | WebSocket | REST Polling |
|---------|--------|-----|-----------|--------------|
| Browser Native | ❌ | ✅ | ✅ | ✅ |
| Setup Complexity | High | Low | Medium | Low |
| Real-time | ❌ | ✅ | ✅ | ❌ |
| Auto-Reconnect | ❌ | ✅ | ❌ | N/A |
| Bidirectional | ✅ | ❌ | ✅ | ❌ |
| Server Push | ❌ | ✅ | ✅ | ❌ |
| Best For | Microservices | One-way streaming | Chat/Gaming | Simple updates |

**Decision: SSE is the best choice for streaming audit logs to a web frontend.**

---

## Architecture

```
┌─────────────────┐                    ┌─────────────────┐
│   TypeScript    │                    │   FastAPI       │
│   Frontend      │                    │   Backend       │
│                 │                    │                 │
│  EventSource ───┼───── HTTPS ────────┼──→ /logs/stream │
│      API        │   (Keep-Alive)     │                 │
│                 │                    │  ┌──────────┐   │
│  onmessage() ←──┼────── SSE ─────────┼──┤ Polling  │   │
│                 │   (Server Push)    │  │ Database │   │
│                 │                    │  └──────────┘   │
└─────────────────┘                    └─────────────────┘
         │                                      │
         │                                      │
         └──────── User's Audit Logs ───────────┘
```

**Flow:**
1. Frontend creates `EventSource` connection to `/api/v1/auth/logs/stream`
2. Backend authenticates user via JWT token
3. Backend polls database every 2 seconds for new logs
4. New logs are sent to frontend as SSE events
5. Frontend receives and displays logs in real-time
6. Connection stays open until client disconnects

---

## Backend Implementation

### Endpoint Details

**URL:** `GET /api/v1/auth/logs/stream`

**Authentication:** Bearer Token (JWT)

**Response Type:** `text/event-stream`

### Implementation (Python/FastAPI)

Located in `app/api/v1/auth.py`:

```python
async def audit_log_stream(
    user_id: str,
    auth_service: AuthService,
) -> AsyncIterator[str]:
    """
    Stream audit logs for a user in real-time.
    Polls database every 2 seconds for new logs.
    """
    last_log_time = datetime.now(timezone.utc)

    try:
        while True:
            # Fetch new logs since last check
            logs, _ = auth_service.audit_repo.get_by_user(
                user_id=user_id,
                start_date=last_log_time,
                limit=50
            )

            # Send each new log as SSE event
            for log in reversed(logs):
                log_data = {
                    "log_id": log.log_id,
                    "action": log.action,
                    "success": log.success,
                    "created_at": log.created_at.isoformat(),
                    # ... more fields
                }
                yield f"data: {json.dumps(log_data)}\n\n"

                if log.created_at:
                    last_log_time = max(last_log_time, log.created_at)

            await asyncio.sleep(2)  # Poll interval

    except asyncio.CancelledError:
        logger.info("Stream closed", user_id=user_id)
        yield f"data: {json.dumps({'event': 'stream_closed'})}\n\n"

@router.get("/logs/stream")
async def stream_audit_logs(
    current_user: dict = Depends(get_current_active_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    return StreamingResponse(
        audit_log_stream(current_user["user"].user_id, auth_service),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
```

### Database Query

The backend uses the existing `AuditLogRepository.get_by_user()` method:

```python
logs, total = audit_repo.get_by_user(
    user_id=user_id,
    start_date=last_log_time,  # Only fetch logs after this time
    limit=50                     # Max logs per poll
)
```

---

## Frontend Integration

### Basic Usage (Vanilla JavaScript/TypeScript)

```typescript
// Connect to SSE endpoint
const eventSource = new EventSource(
  'http://localhost:8000/api/v1/auth/logs/stream'
);

// Handle incoming logs
eventSource.onmessage = (event) => {
  const log = JSON.parse(event.data);
  console.log('New audit log:', log);

  // Update UI
  displayLog(log);
};

// Handle errors
eventSource.onerror = (error) => {
  console.error('SSE error:', error);
  eventSource.close();
};

// Clean up when done
window.addEventListener('beforeunload', () => {
  eventSource.close();
});
```

### With Authentication Token

**Problem:** Native `EventSource` doesn't support custom headers.

**Solution 1: Use EventSource Polyfill**

```bash
npm install eventsource
```

```typescript
import EventSource from 'eventsource';

const eventSource = new EventSource(
  'http://localhost:8000/api/v1/auth/logs/stream',
  {
    headers: {
      'Authorization': `Bearer ${accessToken}`
    }
  }
);
```

**Solution 2: Pass Token in Query String** (Less secure)

```typescript
const eventSource = new EventSource(
  `http://localhost:8000/api/v1/auth/logs/stream?token=${accessToken}`
);
```

Then update backend to accept token from query params.

### React Example

```typescript
import { useEffect, useState } from 'react';

interface AuditLog {
  log_id: string;
  action: string;
  success: boolean;
  created_at: string;
  ip_address: string;
  details: any;
}

function AuditLogStream() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const eventSource = new EventSource('/api/v1/auth/logs/stream');

    eventSource.onopen = () => {
      setConnected(true);
      console.log('SSE connected');
    };

    eventSource.onmessage = (event) => {
      const log: AuditLog = JSON.parse(event.data);

      // Add new log to the top
      setLogs(prevLogs => [log, ...prevLogs]);
    };

    eventSource.onerror = (error) => {
      console.error('SSE error:', error);
      setConnected(false);
      eventSource.close();
    };

    // Cleanup on unmount
    return () => {
      eventSource.close();
    };
  }, []);

  return (
    <div>
      <h2>
        Real-Time Audit Logs
        {connected ? '🟢' : '🔴'}
      </h2>

      <div className="log-stream">
        {logs.map(log => (
          <div key={log.log_id} className="log-entry">
            <span className={log.success ? 'success' : 'error'}>
              {log.action}
            </span>
            <span>{new Date(log.created_at).toLocaleString()}</span>
            <span>{log.ip_address}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

### Vue.js Example

```vue
<template>
  <div>
    <h2>Real-Time Audit Logs <span :class="connected ? 'online' : 'offline'"></span></h2>

    <div v-for="log in logs" :key="log.log_id" class="log-entry">
      <span :class="log.success ? 'success' : 'error'">{{ log.action }}</span>
      <span>{{ formatDate(log.created_at) }}</span>
      <span>{{ log.ip_address }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';

const logs = ref<any[]>([]);
const connected = ref(false);
let eventSource: EventSource | null = null;

onMounted(() => {
  eventSource = new EventSource('/api/v1/auth/logs/stream');

  eventSource.onopen = () => {
    connected.value = true;
  };

  eventSource.onmessage = (event) => {
    const log = JSON.parse(event.data);
    logs.value.unshift(log);
  };

  eventSource.onerror = () => {
    connected.value = false;
  };
});

onUnmounted(() => {
  eventSource?.close();
});

function formatDate(date: string) {
  return new Date(date).toLocaleString();
}
</script>
```

---

## API Reference

### Endpoint

```
GET /api/v1/auth/logs/stream
```

### Headers

| Header | Value | Required |
|--------|-------|----------|
| Authorization | `Bearer <jwt_token>` | Yes |
| Accept | `text/event-stream` | Recommended |

### Response

**Content-Type:** `text/event-stream`

**Format:** Server-Sent Events

### Event Data Structure

Each SSE event contains a JSON object:

```json
{
  "log_id": "log_abc123",
  "action": "login",
  "resource_type": "user",
  "resource_id": "user_123",
  "success": true,
  "error_message": null,
  "ip_address": "192.168.1.100",
  "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)...",
  "details": {
    "session_id": "ses_xyz789",
    "device": "desktop"
  },
  "created_at": "2025-12-27T15:30:45.123Z"
}
```

### Event Types

All events use the default SSE event type. The `action` field determines the log type:

| Action | Description |
|--------|-------------|
| `login` | User login attempt |
| `logout` | User logout |
| `register` | New user registration |
| `oauth_login` | OAuth authentication |
| `password_change` | Password changed |
| `mfa_enabled` | MFA enabled |
| `token_refresh` | Token refreshed |
| `session_revoked` | Session terminated |

### Error Handling

The stream may close with an error for:
- **401 Unauthorized:** Invalid or expired token
- **403 Forbidden:** User account disabled
- **500 Internal Server Error:** Backend error

The browser will automatically attempt to reconnect.

---

## Performance & Scalability

### Resource Usage

| Metric | Value | Notes |
|--------|-------|-------|
| Polling Interval | 2 seconds | Configurable |
| Max Logs per Poll | 50 | Prevents overwhelming client |
| Connection Timeout | None | Kept alive indefinitely |
| Memory per Connection | ~10KB | Minimal overhead |

### Scaling Considerations

**For 100 concurrent users:**
- Database queries: 50/second (1 query per user every 2s)
- Network bandwidth: ~5KB/s per user with logs
- Server memory: ~1MB total

**For 1000+ concurrent users:**
- Consider using Redis pub/sub for log distribution
- Add load balancer with sticky sessions
- Implement rate limiting
- Use database read replicas

### Optimization Tips

1. **Increase Polling Interval** - For less critical logs:
   ```python
   await asyncio.sleep(5)  # Poll every 5 seconds
   ```

2. **Add Filters** - Let users filter by action type:
   ```python
   logs, _ = auth_service.audit_repo.get_by_user(
       user_id=user_id,
       action=filter_action,  # e.g., "login"
       start_date=last_log_time
   )
   ```

3. **Use Redis** - For high-scale deployments:
   ```python
   # Publish logs to Redis when created
   redis.publish(f"user:{user_id}:logs", json.dumps(log_data))

   # Subscribe in SSE handler
   pubsub = redis.pubsub()
   pubsub.subscribe(f"user:{user_id}:logs")
   ```

---

## Troubleshooting

### Issue: Connection Drops Frequently

**Cause:** Network proxy or firewall closing idle connections

**Solution:**
1. Send heartbeat/keep-alive messages:
   ```python
   # In backend
   yield f": heartbeat\n\n"  # Comment line, ignored by client
   ```

2. Adjust nginx/proxy timeout:
   ```nginx
   proxy_read_timeout 300s;
   proxy_connect_timeout 300s;
   ```

### Issue: No Logs Received

**Checklist:**
- ✅ Is user authenticated? Check JWT token
- ✅ Are logs being created? Check database
- ✅ Is polling interval too high?
- ✅ Check browser console for errors
- ✅ Verify CORS headers if cross-origin

### Issue: Old Logs Repeating

**Cause:** `last_log_time` not updating correctly

**Fix:** Ensure timestamps are being compared properly:
```python
if log.created_at:
    last_log_time = max(last_log_time, log.created_at)
```

### Issue: High Database Load

**Cause:** Too many connections polling too frequently

**Solution:**
- Increase polling interval
- Implement Redis pub/sub
- Add database query caching
- Use database connection pooling

### Issue: CORS Errors

**Solution:** Add CORS middleware in FastAPI:
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## Testing

### Manual Testing with cURL

```bash
# Test SSE endpoint
curl -N -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  http://localhost:8000/api/v1/auth/logs/stream
```

### Browser Console Testing

```javascript
// Open browser console
const es = new EventSource('http://localhost:8000/api/v1/auth/logs/stream');
es.onmessage = (e) => console.log(JSON.parse(e.data));
```

### Generate Test Logs

Trigger actions to create logs:
- Login/logout
- Change password
- Enable MFA
- Create API keys

---

## Security Considerations

1. **Authentication Required** - All connections must have valid JWT
2. **User Isolation** - Users only see their own logs
3. **Rate Limiting** - Consider limiting connections per user
4. **Token Expiry** - Handle token refresh gracefully
5. **HTTPS Only** - Always use HTTPS in production

---

## Future Enhancements

- [ ] Add log filtering by action type
- [ ] Implement Redis pub/sub for scalability
- [ ] Add pagination for historical logs
- [ ] Support multiple stream types (incidents, notifications)
- [ ] Add WebSocket fallback option
- [ ] Implement log retention policies
- [ ] Add log export functionality

---

## References

- [Server-Sent Events Specification](https://html.spec.whatwg.org/multipage/server-sent-events.html)
- [FastAPI StreamingResponse](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse)
- [MDN EventSource API](https://developer.mozilla.org/en-US/docs/Web/API/EventSource)
- [EventSource Polyfill](https://github.com/EventSource/eventsource)

---

**Created:** 2025-12-27
**Last Updated:** 2025-12-27
**Version:** 1.0.0
