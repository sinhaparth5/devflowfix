# Email Service Integration Documentation

This document outlines all email notification requirements for integration with the .NET Email Microservice via gRPC.

---

## Architecture Overview

```
┌─────────────────────┐         gRPC          ┌─────────────────────┐
│   DevFlowFix API    │ ───────────────────── │  .NET Email Service │
│   (FastAPI/Python)  │                       │    (Microservice)   │
└─────────────────────┘                       └─────────────────────┘
                                                        │
                                                        ▼
                                              ┌─────────────────────┐
                                              │   Email Provider    │
                                              │ (SendGrid/SES/SMTP) │
                                              └─────────────────────┘
```

---

## Email Types Summary

| # | Email Type | Trigger Endpoint | Priority | File Location |
|---|------------|------------------|----------|---------------|
| 1 | Welcome Email | POST /auth/register | HIGH | auth.py:185 |
| 2 | Email Verification | POST /auth/register | HIGH | auth.py:185 |
| 3 | Password Reset Link | POST /auth/password/reset/request | CRITICAL | auth.py:822 |
| 4 | Password Reset Confirmation | POST /auth/password/reset/confirm | HIGH | auth.py:848 |
| 5 | Password Change Confirmation | POST /auth/password/change | HIGH | auth.py:779 |
| 6 | MFA Setup Instructions | POST /auth/mfa/setup | MEDIUM | auth.py:880 |
| 7 | MFA Enabled Notification | POST /auth/mfa/enable | MEDIUM | auth.py:913 |
| 8 | MFA Disabled Warning | POST /auth/mfa/disable | MEDIUM | auth.py:952 |
| 9 | New Login Alert | POST /auth/login | MEDIUM | auth.py:399 |
| 10 | Account Locked Warning | POST /auth/login (failed) | HIGH | auth.py:374 |
| 11 | Session Revoked Notification | POST /auth/sessions/revoke | MEDIUM | auth.py:1030 |
| 12 | OAuth Account Created | POST /auth/oauth/google, /auth/oauth/github | MEDIUM | auth.py:1131, 1262 |
| 13 | API Key Created | POST /auth/api-key | LOW | auth.py:1074 |
| 14 | API Key Revoked | DELETE /auth/api-key | LOW | auth.py:1103 |

---

## Detailed Email Specifications

### 1. Welcome Email

**Trigger:** User completes registration
**Endpoint:** `POST /api/v1/auth/register`
**File:** `app/api/v1/auth.py:185`

**gRPC Request Payload:**
```protobuf
message WelcomeEmailRequest {
    string email = 1;
    string full_name = 2;
    string username = 3;
    string created_at = 4;  // ISO 8601 timestamp
    string login_url = 5;
}
```

**Email Content:**
- Subject: "Welcome to DevFlowFix!"
- Body: Greeting, platform overview, getting started guide, login link

---

### 2. Email Verification

**Trigger:** User completes registration (combined with welcome or separate)
**Endpoint:** `POST /api/v1/auth/register`
**File:** `app/api/v1/auth.py:185`

**gRPC Request Payload:**
```protobuf
message EmailVerificationRequest {
    string email = 1;
    string full_name = 2;
    string verification_token = 3;  // JWT token
    string verification_url = 4;    // {FRONTEND_URL}/verify-email?token={token}
    int32 expires_in_hours = 5;     // Token validity period
}
```

**Email Content:**
- Subject: "Verify Your Email Address"
- Body: Verification link, expiration notice, instructions

---

### 3. Password Reset Link (CRITICAL)

**Trigger:** User requests password reset
**Endpoint:** `POST /api/v1/auth/password/reset/request`
**File:** `app/api/v1/auth.py:822`
**Note:** There's an existing TODO at line 834

**gRPC Request Payload:**
```protobuf
message PasswordResetLinkRequest {
    string email = 1;
    string full_name = 2;
    string reset_token = 3;         // JWT token with 1-hour expiry
    string reset_url = 4;           // {FRONTEND_URL}/reset-password?token={token}
    int32 expires_in_minutes = 5;   // 60 minutes
    string request_ip = 6;          // IP address of requester
    string request_timestamp = 7;   // ISO 8601 timestamp
}
```

**Email Content:**
- Subject: "Reset Your Password"
- Body: Reset link, expiration warning (1 hour), security notice if not requested

---

### 4. Password Reset Confirmation

**Trigger:** User successfully resets password with valid token
**Endpoint:** `POST /api/v1/auth/password/reset/confirm`
**File:** `app/api/v1/auth.py:848`

**gRPC Request Payload:**
```protobuf
message PasswordResetConfirmationRequest {
    string email = 1;
    string full_name = 2;
    string reset_timestamp = 3;     // ISO 8601 timestamp
    string reset_ip = 4;            // IP address
    string login_url = 5;
}
```

**Email Content:**
- Subject: "Your Password Has Been Reset"
- Body: Confirmation, timestamp, security warning if not user, contact support link

---

### 5. Password Change Confirmation

**Trigger:** Authenticated user changes their password
**Endpoint:** `POST /api/v1/auth/password/change`
**File:** `app/api/v1/auth.py:779`
**Note:** All sessions are revoked after password change (lines 950-958)

**gRPC Request Payload:**
```protobuf
message PasswordChangeConfirmationRequest {
    string email = 1;
    string full_name = 2;
    string change_timestamp = 3;    // ISO 8601 timestamp
    string change_ip = 4;           // IP address
    string user_agent = 5;          // Browser/device info
    bool sessions_revoked = 6;      // Always true - all sessions are revoked
}
```

**Email Content:**
- Subject: "Your Password Has Been Changed"
- Body: Confirmation, all sessions logged out notice, security warning

---

### 6. MFA Setup Instructions

**Trigger:** User initiates MFA setup
**Endpoint:** `POST /api/v1/auth/mfa/setup`
**File:** `app/api/v1/auth.py:880`

**gRPC Request Payload:**
```protobuf
message MfaSetupRequest {
    string email = 1;
    string full_name = 2;
    string secret_key = 3;              // TOTP secret (also shown in UI)
    repeated string backup_codes = 4;   // Recovery codes
    string setup_timestamp = 5;         // ISO 8601 timestamp
}
```

**Email Content:**
- Subject: "MFA Setup Instructions"
- Body: Secret key, backup codes (important!), instructions to save securely

---

### 7. MFA Enabled Notification

**Trigger:** User successfully enables MFA
**Endpoint:** `POST /api/v1/auth/mfa/enable`
**File:** `app/api/v1/auth.py:913`

**gRPC Request Payload:**
```protobuf
message MfaEnabledRequest {
    string email = 1;
    string full_name = 2;
    string enabled_timestamp = 3;   // ISO 8601 timestamp
    string enabled_ip = 4;          // IP address
}
```

**Email Content:**
- Subject: "Two-Factor Authentication Enabled"
- Body: Confirmation, next login requires MFA code, recovery options

---

### 8. MFA Disabled Warning

**Trigger:** User disables MFA
**Endpoint:** `POST /api/v1/auth/mfa/disable`
**File:** `app/api/v1/auth.py:952`

**gRPC Request Payload:**
```protobuf
message MfaDisabledRequest {
    string email = 1;
    string full_name = 2;
    string disabled_timestamp = 3;  // ISO 8601 timestamp
    string disabled_ip = 4;         // IP address
    string user_agent = 5;          // Browser/device info
}
```

**Email Content:**
- Subject: "Two-Factor Authentication Disabled - Security Alert"
- Body: Warning about reduced security, timestamp, re-enable instructions

---

### 9. New Login Alert

**Trigger:** Successful login (especially from new device/location)
**Endpoint:** `POST /api/v1/auth/login`
**File:** `app/api/v1/auth.py:399`
**Note:** Device fingerprint tracking exists at line 419

**gRPC Request Payload:**
```protobuf
message NewLoginAlertRequest {
    string email = 1;
    string full_name = 2;
    string login_timestamp = 3;     // ISO 8601 timestamp
    string login_ip = 4;            // IP address
    string user_agent = 5;          // Browser/device info
    string device_fingerprint = 6;  // Device identifier
    string approximate_location = 7; // City/Country (from IP)
    bool is_new_device = 8;         // First time from this device
}
```

**Email Content:**
- Subject: "New Login to Your Account"
- Body: Login details, location, device info, "wasn't me" instructions

---

### 10. Account Locked Warning

**Trigger:** Account locked after failed login attempts
**Endpoint:** `POST /api/v1/auth/login` (on failure)
**File:** `app/api/v1/auth.py:374-377`

**gRPC Request Payload:**
```protobuf
message AccountLockedRequest {
    string email = 1;
    string full_name = 2;
    int32 failed_attempts = 3;          // Number of failed attempts
    string locked_timestamp = 4;         // ISO 8601 timestamp
    int32 lockout_duration_minutes = 5;  // From LOCKOUT_DURATION_MINUTES config
    string unlock_timestamp = 6;         // When account will be unlocked
    string last_attempt_ip = 7;          // IP of last failed attempt
}
```

**Email Content:**
- Subject: "Account Temporarily Locked - Security Alert"
- Body: Lockout reason, duration, unlock time, password reset suggestion

---

### 11. Session Revoked Notification

**Trigger:** User manually revokes a session
**Endpoint:** `POST /api/v1/auth/sessions/revoke`
**File:** `app/api/v1/auth.py:1030`

**gRPC Request Payload:**
```protobuf
message SessionRevokedRequest {
    string email = 1;
    string full_name = 2;
    string revoked_session_id = 3;      // Session that was revoked
    string revoked_device_info = 4;     // Device/browser of revoked session
    string revoked_ip = 5;              // IP of revoked session
    string revocation_timestamp = 6;    // ISO 8601 timestamp
    string revoked_by_ip = 7;           // IP of user who revoked
}
```

**Email Content:**
- Subject: "Session Revoked"
- Body: Which session was ended, device info, security notice

---

### 12. OAuth Account Created

**Trigger:** New user created via OAuth (Google/GitHub)
**Endpoints:**
- `POST /api/v1/auth/oauth/google` (auth.py:1131)
- `POST /api/v1/auth/oauth/github` (auth.py:1262)

**gRPC Request Payload:**
```protobuf
message OAuthAccountCreatedRequest {
    string email = 1;
    string full_name = 2;
    string oauth_provider = 3;          // "google" or "github"
    string oauth_email = 4;             // Email from OAuth provider
    string created_timestamp = 5;       // ISO 8601 timestamp
    string login_url = 6;
}
```

**Email Content:**
- Subject: "Welcome to DevFlowFix!"
- Body: Account created via OAuth, linked provider info, getting started

---

### 13. API Key Created

**Trigger:** User creates new API key
**Endpoint:** `POST /api/v1/auth/api-key`
**File:** `app/api/v1/auth.py:1074`

**gRPC Request Payload:**
```protobuf
message ApiKeyCreatedRequest {
    string email = 1;
    string full_name = 2;
    string key_prefix = 3;              // First few chars for identification
    string key_name = 4;                // User-provided name for the key
    string created_timestamp = 5;       // ISO 8601 timestamp
    string created_ip = 6;              // IP address
}
```

**Email Content:**
- Subject: "New API Key Created"
- Body: Key created confirmation, key prefix, security reminder

---

### 14. API Key Revoked

**Trigger:** User revokes an API key
**Endpoint:** `DELETE /api/v1/auth/api-key`
**File:** `app/api/v1/auth.py:1103`

**gRPC Request Payload:**
```protobuf
message ApiKeyRevokedRequest {
    string email = 1;
    string full_name = 2;
    string key_prefix = 3;              // First few chars for identification
    string key_name = 4;                // User-provided name for the key
    string revoked_timestamp = 5;       // ISO 8601 timestamp
    string revoked_ip = 6;              // IP address
}
```

**Email Content:**
- Subject: "API Key Revoked"
- Body: Key revoked confirmation, affected services warning

---

## gRPC Service Definition

```protobuf
syntax = "proto3";

package devflowfix.email;

service EmailService {
    // Authentication Emails
    rpc SendWelcomeEmail(WelcomeEmailRequest) returns (EmailResponse);
    rpc SendEmailVerification(EmailVerificationRequest) returns (EmailResponse);
    rpc SendPasswordResetLink(PasswordResetLinkRequest) returns (EmailResponse);
    rpc SendPasswordResetConfirmation(PasswordResetConfirmationRequest) returns (EmailResponse);
    rpc SendPasswordChangeConfirmation(PasswordChangeConfirmationRequest) returns (EmailResponse);

    // MFA Emails
    rpc SendMfaSetupInstructions(MfaSetupRequest) returns (EmailResponse);
    rpc SendMfaEnabledNotification(MfaEnabledRequest) returns (EmailResponse);
    rpc SendMfaDisabledWarning(MfaDisabledRequest) returns (EmailResponse);

    // Security Alerts
    rpc SendNewLoginAlert(NewLoginAlertRequest) returns (EmailResponse);
    rpc SendAccountLockedWarning(AccountLockedRequest) returns (EmailResponse);
    rpc SendSessionRevokedNotification(SessionRevokedRequest) returns (EmailResponse);

    // Account Emails
    rpc SendOAuthAccountCreated(OAuthAccountCreatedRequest) returns (EmailResponse);
    rpc SendApiKeyCreated(ApiKeyCreatedRequest) returns (EmailResponse);
    rpc SendApiKeyRevoked(ApiKeyRevokedRequest) returns (EmailResponse);
}

message EmailResponse {
    bool success = 1;
    string message_id = 2;          // Email provider's message ID
    string error_message = 3;       // Error details if failed
    int32 retry_after_seconds = 4;  // If rate limited
}
```

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

## Integration Points in Python Code

For each email, you'll need to call the gRPC service. Example integration:

```python
# In app/api/v1/auth.py - Password Reset Request endpoint (line 834)

# Replace the TODO comment with:
from app.adapters.email_grpc import email_service_stub

async def request_password_reset(request: PasswordResetRequest, db: Session):
    # ... existing code ...

    # After generating reset_token:
    try:
        await email_service_stub.SendPasswordResetLink(
            PasswordResetLinkRequest(
                email=user.email,
                full_name=user.full_name,
                reset_token=reset_token,
                reset_url=f"{settings.FRONTEND_URL}/reset-password?token={reset_token}",
                expires_in_minutes=60,
                request_ip=request.client.host,
                request_timestamp=datetime.utcnow().isoformat()
            )
        )
    except Exception as e:
        logger.error(f"Failed to send password reset email: {e}")
        # Don't fail the request - log and continue

    # ... rest of code ...
```

---

## Configuration Requirements

Your .NET Email Microservice will need these environment variables:

```env
# gRPC Server
GRPC_PORT=50051
GRPC_HOST=0.0.0.0

# Email Provider (choose one)
EMAIL_PROVIDER=sendgrid  # or "ses", "smtp"

# SendGrid
SENDGRID_API_KEY=your_api_key

# AWS SES
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_REGION=us-east-1

# SMTP
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your_username
SMTP_PASSWORD=your_password
SMTP_USE_TLS=true

# Email Settings
FROM_EMAIL=noreply@devflowfix.com
FROM_NAME=DevFlowFix
FRONTEND_URL=https://app.devflowfix.com

# Rate Limiting
MAX_EMAILS_PER_MINUTE=100
MAX_EMAILS_PER_USER_PER_HOUR=20
```

---

## Notes

1. **Security**: Never log full email content or tokens in production
2. **Retry Logic**: Implement exponential backoff for failed emails
3. **Rate Limiting**: Prevent abuse by limiting emails per user
4. **Templates**: Use HTML email templates with plain text fallback
5. **Tracking**: Consider adding email open/click tracking for analytics
6. **Unsubscribe**: Add unsubscribe links for non-transactional emails

---

*Generated for DevFlowFix Email Microservice Integration*
