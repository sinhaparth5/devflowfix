# Email Service Integration Documentation

This document outlines all email notification requirements for integration with the .NET Email Microservice via REST API.

**Base URL:** `https://devflowfix-mail-service.azurewebsites.net`

---

## Architecture Overview

```
┌─────────────────────┐       REST API        ┌─────────────────────┐
│   DevFlowFix API    │ ───────────────────── │  .NET Email Service │
│   (FastAPI/Python)  │                       │    (Microservice)   │
└─────────────────────┘                       └─────────────────────┘
                                                        │
                                                        ▼
                                              ┌─────────────────────┐
                                              │   Email Provider    │
                                              │ (Azure Comm Svc)    │
                                              └─────────────────────┘
```

---

## API Endpoints Summary

| # | Email Type | API Endpoint | Method | Priority |
|---|------------|--------------|--------|----------|
| 1 | Welcome Email | `/api/email/welcome` | POST | HIGH |
| 2 | Email Verification | `/api/email/verification` | POST | HIGH |
| 3 | Password Reset Link | `/api/email/password-reset-link` | POST | CRITICAL |
| 4 | Password Reset Confirmation | `/api/email/password-reset-confirmation` | POST | HIGH |
| 5 | Password Change Confirmation | `/api/email/password-change-confirmation` | POST | HIGH |
| 6 | MFA Setup Instructions | `/api/email/mfa-setup` | POST | MEDIUM |
| 7 | MFA Enabled Notification | `/api/email/mfa-enabled` | POST | MEDIUM |
| 8 | MFA Disabled Warning | `/api/email/mfa-disabled` | POST | MEDIUM |
| 9 | New Login Alert | `/api/email/new-login-alert` | POST | MEDIUM |
| 10 | Account Locked Warning | `/api/email/account-locked` | POST | HIGH |
| 11 | Session Revoked Notification | `/api/email/session-revoked` | POST | MEDIUM |
| 12 | OAuth Account Created | `/api/email/oauth-account-created` | POST | MEDIUM |
| 13 | API Key Created | `/api/email/api-key-created` | POST | LOW |
| 14 | API Key Revoked | `/api/email/api-key-revoked` | POST | LOW |

---

## Response Format

All endpoints return the same response format:

```json
{
  "success": true,
  "messageId": "email-provider-message-id",
  "errorMessage": null
}
```

---

## Detailed API Specifications

### 1. Welcome Email

**Endpoint:** `POST /api/email/welcome`

**Request:**
```json
{
  "email": "user@example.com",
  "fullName": "John Doe",
  "username": "johndoe",
  "createdAt": "2025-01-15T10:30:00Z",
  "loginUrl": "https://devflowfix.com/login"
}
```

**cURL:**
```bash
curl -X POST https://devflowfix-mail-service.azurewebsites.net/api/email/welcome \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "fullName": "John Doe",
    "username": "johndoe",
    "createdAt": "2025-01-15T10:30:00Z",
    "loginUrl": "https://devflowfix.com/login"
  }'
```

**Email Content:**
- Subject: "Welcome to DevFlowFix!"
- Body: Greeting, platform overview, getting started guide, login link

---

### 2. Email Verification

**Endpoint:** `POST /api/email/verification`

**Request:**
```json
{
  "email": "user@example.com",
  "fullName": "John Doe",
  "verificationToken": "jwt-token-here",
  "verificationUrl": "https://devflowfix.com/verify-email?token=jwt-token",
  "expiresInHours": 24
}
```

**cURL:**
```bash
curl -X POST https://devflowfix-mail-service.azurewebsites.net/api/email/verification \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "fullName": "John Doe",
    "verificationToken": "jwt-token-here",
    "verificationUrl": "https://devflowfix.com/verify-email?token=jwt-token",
    "expiresInHours": 24
  }'
```

**Email Content:**
- Subject: "Verify Your Email Address"
- Body: Verification link, expiration notice, instructions

---

### 3. Password Reset Link (CRITICAL)

**Endpoint:** `POST /api/email/password-reset-link`

**Request:**
```json
{
  "email": "user@example.com",
  "fullName": "John Doe",
  "resetToken": "jwt-reset-token",
  "resetUrl": "https://devflowfix.com/reset-password?token=jwt-reset-token",
  "expiresInMinutes": 60,
  "requestIp": "192.168.1.1",
  "requestTimestamp": "2025-01-15T10:30:00Z"
}
```

**cURL:**
```bash
curl -X POST https://devflowfix-mail-service.azurewebsites.net/api/email/password-reset-link \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "fullName": "John Doe",
    "resetToken": "jwt-reset-token",
    "resetUrl": "https://devflowfix.com/reset-password?token=jwt-reset-token",
    "expiresInMinutes": 60,
    "requestIp": "192.168.1.1",
    "requestTimestamp": "2025-01-15T10:30:00Z"
  }'
```

**Email Content:**
- Subject: "Reset Your Password"
- Body: Reset link, expiration warning (1 hour), security notice if not requested

---

### 4. Password Reset Confirmation

**Endpoint:** `POST /api/email/password-reset-confirmation`

**Request:**
```json
{
  "email": "user@example.com",
  "fullName": "John Doe",
  "resetTimestamp": "2025-01-15T10:30:00Z",
  "resetIp": "192.168.1.1",
  "loginUrl": "https://devflowfix.com/login"
}
```

**cURL:**
```bash
curl -X POST https://devflowfix-mail-service.azurewebsites.net/api/email/password-reset-confirmation \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "fullName": "John Doe",
    "resetTimestamp": "2025-01-15T10:30:00Z",
    "resetIp": "192.168.1.1",
    "loginUrl": "https://devflowfix.com/login"
  }'
```

**Email Content:**
- Subject: "Your Password Has Been Reset"
- Body: Confirmation, timestamp, security warning if not user, contact support link

---

### 5. Password Change Confirmation

**Endpoint:** `POST /api/email/password-change-confirmation`

**Request:**
```json
{
  "email": "user@example.com",
  "fullName": "John Doe",
  "changeTimestamp": "2025-01-15T10:30:00Z",
  "changeIp": "192.168.1.1",
  "userAgent": "Mozilla/5.0 Chrome/120",
  "sessionsRevoked": true
}
```

**cURL:**
```bash
curl -X POST https://devflowfix-mail-service.azurewebsites.net/api/email/password-change-confirmation \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "fullName": "John Doe",
    "changeTimestamp": "2025-01-15T10:30:00Z",
    "changeIp": "192.168.1.1",
    "userAgent": "Mozilla/5.0 Chrome/120",
    "sessionsRevoked": true
  }'
```

**Email Content:**
- Subject: "Your Password Has Been Changed"
- Body: Confirmation, all sessions logged out notice, security warning

---

### 6. MFA Setup Instructions

**Endpoint:** `POST /api/email/mfa-setup`

**Request:**
```json
{
  "email": "user@example.com",
  "fullName": "John Doe",
  "secretKey": "JBSWY3DPEHPK3PXP",
  "backupCodes": ["ABC123", "DEF456", "GHI789", "JKL012"],
  "setupTimestamp": "2025-01-15T10:30:00Z"
}
```

**cURL:**
```bash
curl -X POST https://devflowfix-mail-service.azurewebsites.net/api/email/mfa-setup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "fullName": "John Doe",
    "secretKey": "JBSWY3DPEHPK3PXP",
    "backupCodes": ["ABC123", "DEF456", "GHI789", "JKL012"],
    "setupTimestamp": "2025-01-15T10:30:00Z"
  }'
```

**Email Content:**
- Subject: "MFA Setup Instructions"
- Body: Secret key, backup codes (important!), instructions to save securely

---

### 7. MFA Enabled Notification

**Endpoint:** `POST /api/email/mfa-enabled`

**Request:**
```json
{
  "email": "user@example.com",
  "fullName": "John Doe",
  "enabledTimestamp": "2025-01-15T10:30:00Z",
  "enabledIp": "192.168.1.1"
}
```

**cURL:**
```bash
curl -X POST https://devflowfix-mail-service.azurewebsites.net/api/email/mfa-enabled \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "fullName": "John Doe",
    "enabledTimestamp": "2025-01-15T10:30:00Z",
    "enabledIp": "192.168.1.1"
  }'
```

**Email Content:**
- Subject: "Two-Factor Authentication Enabled"
- Body: Confirmation, next login requires MFA code, recovery options

---

### 8. MFA Disabled Warning

**Endpoint:** `POST /api/email/mfa-disabled`

**Request:**
```json
{
  "email": "user@example.com",
  "fullName": "John Doe",
  "disabledTimestamp": "2025-01-15T10:30:00Z",
  "disabledIp": "192.168.1.1",
  "userAgent": "Mozilla/5.0 Chrome/120"
}
```

**cURL:**
```bash
curl -X POST https://devflowfix-mail-service.azurewebsites.net/api/email/mfa-disabled \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "fullName": "John Doe",
    "disabledTimestamp": "2025-01-15T10:30:00Z",
    "disabledIp": "192.168.1.1",
    "userAgent": "Mozilla/5.0 Chrome/120"
  }'
```

**Email Content:**
- Subject: "Two-Factor Authentication Disabled - Security Alert"
- Body: Warning about reduced security, timestamp, re-enable instructions

---

### 9. New Login Alert

**Endpoint:** `POST /api/email/new-login-alert`

**Request:**
```json
{
  "email": "user@example.com",
  "fullName": "John Doe",
  "loginTimestamp": "2025-01-15T10:30:00Z",
  "loginIp": "192.168.1.100",
  "userAgent": "Mozilla/5.0 Chrome/120",
  "deviceFingerprint": "abc123fingerprint",
  "approximateLocation": "New York, US",
  "isNewDevice": true
}
```

**cURL:**
```bash
curl -X POST https://devflowfix-mail-service.azurewebsites.net/api/email/new-login-alert \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "fullName": "John Doe",
    "loginTimestamp": "2025-01-15T10:30:00Z",
    "loginIp": "192.168.1.100",
    "userAgent": "Mozilla/5.0 Chrome/120",
    "deviceFingerprint": "abc123fingerprint",
    "approximateLocation": "New York, US",
    "isNewDevice": true
  }'
```

**Email Content:**
- Subject: "New Login to Your Account" (or "New Device Login" if isNewDevice=true)
- Body: Login details, location, device info, "wasn't me" instructions

---

### 10. Account Locked Warning

**Endpoint:** `POST /api/email/account-locked`

**Request:**
```json
{
  "email": "user@example.com",
  "fullName": "John Doe",
  "failedAttempts": 5,
  "lockedTimestamp": "2025-01-15T10:30:00Z",
  "lockoutDurationMinutes": 30,
  "unlockTimestamp": "2025-01-15T11:00:00Z",
  "lastAttemptIp": "192.168.1.50"
}
```

**cURL:**
```bash
curl -X POST https://devflowfix-mail-service.azurewebsites.net/api/email/account-locked \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "fullName": "John Doe",
    "failedAttempts": 5,
    "lockedTimestamp": "2025-01-15T10:30:00Z",
    "lockoutDurationMinutes": 30,
    "unlockTimestamp": "2025-01-15T11:00:00Z",
    "lastAttemptIp": "192.168.1.50"
  }'
```

**Email Content:**
- Subject: "Account Temporarily Locked - Security Alert"
- Body: Lockout reason, duration, unlock time, password reset suggestion

---

### 11. Session Revoked Notification

**Endpoint:** `POST /api/email/session-revoked`

**Request:**
```json
{
  "email": "user@example.com",
  "fullName": "John Doe",
  "revokedSessionId": "session-id-123",
  "revokedDeviceInfo": "Chrome on Windows",
  "revokedIp": "192.168.1.100",
  "revocationTimestamp": "2025-01-15T10:30:00Z",
  "revokedByIp": "192.168.1.1"
}
```

**cURL:**
```bash
curl -X POST https://devflowfix-mail-service.azurewebsites.net/api/email/session-revoked \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "fullName": "John Doe",
    "revokedSessionId": "session-id-123",
    "revokedDeviceInfo": "Chrome on Windows",
    "revokedIp": "192.168.1.100",
    "revocationTimestamp": "2025-01-15T10:30:00Z",
    "revokedByIp": "192.168.1.1"
  }'
```

**Email Content:**
- Subject: "Session Revoked"
- Body: Which session was ended, device info, security notice

---

### 12. OAuth Account Created

**Endpoint:** `POST /api/email/oauth-account-created`

**Request:**
```json
{
  "email": "user@example.com",
  "fullName": "John Doe",
  "oAuthProvider": "google",
  "oAuthEmail": "johndoe@gmail.com",
  "createdTimestamp": "2025-01-15T10:30:00Z",
  "loginUrl": "https://devflowfix.com/login"
}
```

**cURL:**
```bash
curl -X POST https://devflowfix-mail-service.azurewebsites.net/api/email/oauth-account-created \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "fullName": "John Doe",
    "oAuthProvider": "google",
    "oAuthEmail": "johndoe@gmail.com",
    "createdTimestamp": "2025-01-15T10:30:00Z",
    "loginUrl": "https://devflowfix.com/login"
  }'
```

**Email Content:**
- Subject: "Welcome to DevFlowFix!"
- Body: Account created via OAuth, linked provider info, getting started

---

### 13. API Key Created

**Endpoint:** `POST /api/email/api-key-created`

**Request:**
```json
{
  "email": "user@example.com",
  "fullName": "John Doe",
  "keyPrefix": "dff_abc",
  "keyName": "Production API Key",
  "createdTimestamp": "2025-01-15T10:30:00Z",
  "createdIp": "192.168.1.1"
}
```

**cURL:**
```bash
curl -X POST https://devflowfix-mail-service.azurewebsites.net/api/email/api-key-created \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "fullName": "John Doe",
    "keyPrefix": "dff_abc",
    "keyName": "Production API Key",
    "createdTimestamp": "2025-01-15T10:30:00Z",
    "createdIp": "192.168.1.1"
  }'
```

**Email Content:**
- Subject: "New API Key Created"
- Body: Key created confirmation, key prefix, security reminder

---

### 14. API Key Revoked

**Endpoint:** `POST /api/email/api-key-revoked`

**Request:**
```json
{
  "email": "user@example.com",
  "fullName": "John Doe",
  "keyPrefix": "dff_abc",
  "keyName": "Production API Key",
  "revokedTimestamp": "2025-01-15T10:30:00Z",
  "revokedIp": "192.168.1.1"
}
```

**cURL:**
```bash
curl -X POST https://devflowfix-mail-service.azurewebsites.net/api/email/api-key-revoked \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "fullName": "John Doe",
    "keyPrefix": "dff_abc",
    "keyName": "Production API Key",
    "revokedTimestamp": "2025-01-15T10:30:00Z",
    "revokedIp": "192.168.1.1"
  }'
```

**Email Content:**
- Subject: "API Key Revoked"
- Body: Key revoked confirmation, affected services warning

---

## Implementation Priority

### Phase 1 - Critical (Must Have)
1. Password Reset Link - Users cannot recover accounts without this
2. Welcome Email - First user impression
3. Email Verification - Account security

### Phase 2 - High Priority
4. Password Reset Confirmation
5. Password Change Confirmation
6. Account Locked Warning

### Phase 3 - Medium Priority
7. MFA Setup/Enable/Disable notifications
8. New Login Alert
9. Session Revoked Notification
10. OAuth Account Created

### Phase 4 - Low Priority
11. API Key Created/Revoked

---

## Integration Example (Python/FastAPI)

```python
import httpx
from datetime import datetime

EMAIL_SERVICE_URL = "https://devflowfix-mail-service.azurewebsites.net"

async def send_welcome_email(email: str, full_name: str, username: str, login_url: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{EMAIL_SERVICE_URL}/api/email/welcome",
            json={
                "email": email,
                "fullName": full_name,
                "username": username,
                "createdAt": datetime.utcnow().isoformat() + "Z",
                "loginUrl": login_url
            }
        )
        return response.json()

async def send_password_reset_link(
    email: str,
    full_name: str,
    reset_token: str,
    reset_url: str,
    request_ip: str
):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{EMAIL_SERVICE_URL}/api/email/password-reset-link",
            json={
                "email": email,
                "fullName": full_name,
                "resetToken": reset_token,
                "resetUrl": reset_url,
                "expiresInMinutes": 60,
                "requestIp": request_ip,
                "requestTimestamp": datetime.utcnow().isoformat() + "Z"
            }
        )
        return response.json()
```

---

## Configuration

The Email Service uses Azure Communication Services and requires these environment variables:

```env
AzureCommunicationServices__ConnectionString=endpoint=https://your-resource.communication.azure.com/;accesskey=your-key
AzureCommunicationServices__SenderAddress=DoNotReply@yourdomain.com
```

---

## Notes

1. **Security**: Never log full email content or tokens in production
2. **Retry Logic**: Implement exponential backoff for failed emails
3. **Rate Limiting**: Prevent abuse by limiting emails per user
4. **Templates**: HTML email templates with plain text fallback (using Handlebars.NET)
5. **Tracking**: Consider adding email open/click tracking for analytics
6. **Unsubscribe**: Add unsubscribe links for non-transactional emails

---

*Generated for DevFlowFix Email Microservice Integration*
