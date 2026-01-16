# Email Service Integration

## Service Details

| Property | Value |
|----------|-------|
| Base URL | `https://devflowfix-mail-service.azurewebsites.net` |
| Protocol | REST API (POST) |
| Content-Type | `application/json` |
| Provider | Azure Communication Services |

### Response Format

```json
{
  "success": true,
  "messageId": "email-provider-message-id",
  "errorMessage": null
}
```

---

## Email Templates

### 1. Welcome Email
**Endpoint:** `/api/email/welcome`

| Variable | Type | Description |
|----------|------|-------------|
| email | string | Recipient email |
| fullName | string | User's full name |
| username | string | User's username |
| createdAt | string | ISO 8601 timestamp |
| loginUrl | string | Login page URL |

---

### 2. Email Verification
**Endpoint:** `/api/email/verification`

| Variable | Type | Description |
|----------|------|-------------|
| email | string | Recipient email |
| fullName | string | User's full name |
| verificationToken | string | JWT verification token |
| verificationUrl | string | Full verification URL with token |
| expiresInHours | int | Token expiration hours |

---

### 3. Password Reset Link
**Endpoint:** `/api/email/password-reset-link`

| Variable | Type | Description |
|----------|------|-------------|
| email | string | Recipient email |
| fullName | string | User's full name |
| resetToken | string | JWT reset token |
| resetUrl | string | Full reset URL with token |
| expiresInMinutes | int | Token expiration minutes |
| requestIp | string | IP that requested reset |
| requestTimestamp | string | ISO 8601 timestamp |

---

### 4. Password Reset Confirmation
**Endpoint:** `/api/email/password-reset-confirmation`

| Variable | Type | Description |
|----------|------|-------------|
| email | string | Recipient email |
| fullName | string | User's full name |
| resetTimestamp | string | ISO 8601 timestamp |
| resetIp | string | IP where reset occurred |
| loginUrl | string | Login page URL |

---

### 5. Password Change Confirmation
**Endpoint:** `/api/email/password-change-confirmation`

| Variable | Type | Description |
|----------|------|-------------|
| email | string | Recipient email |
| fullName | string | User's full name |
| changeTimestamp | string | ISO 8601 timestamp |
| changeIp | string | IP where change occurred |
| userAgent | string | Browser/client info |
| sessionsRevoked | bool | Whether sessions were revoked |

---

### 6. MFA Setup Instructions
**Endpoint:** `/api/email/mfa-setup`

| Variable | Type | Description |
|----------|------|-------------|
| email | string | Recipient email |
| fullName | string | User's full name |
| secretKey | string | TOTP secret key |
| backupCodes | string[] | Array of backup codes |
| setupTimestamp | string | ISO 8601 timestamp |

---

### 7. MFA Enabled Notification
**Endpoint:** `/api/email/mfa-enabled`

| Variable | Type | Description |
|----------|------|-------------|
| email | string | Recipient email |
| fullName | string | User's full name |
| enabledTimestamp | string | ISO 8601 timestamp |
| enabledIp | string | IP where MFA was enabled |

---

### 8. MFA Disabled Warning
**Endpoint:** `/api/email/mfa-disabled`

| Variable | Type | Description |
|----------|------|-------------|
| email | string | Recipient email |
| fullName | string | User's full name |
| disabledTimestamp | string | ISO 8601 timestamp |
| disabledIp | string | IP where MFA was disabled |
| userAgent | string | Browser/client info |

---

### 9. New Login Alert
**Endpoint:** `/api/email/new-login-alert`

| Variable | Type | Description |
|----------|------|-------------|
| email | string | Recipient email |
| fullName | string | User's full name |
| loginTimestamp | string | ISO 8601 timestamp |
| loginIp | string | IP of the login |
| userAgent | string | Browser/client info |
| deviceFingerprint | string | Device fingerprint |
| approximateLocation | string | Location (e.g., "New York, US") |
| isNewDevice | bool | Whether device is new |

---

### 10. Account Locked Warning
**Endpoint:** `/api/email/account-locked`

| Variable | Type | Description |
|----------|------|-------------|
| email | string | Recipient email |
| fullName | string | User's full name |
| failedAttempts | int | Number of failed attempts |
| lockedTimestamp | string | ISO 8601 timestamp |
| lockoutDurationMinutes | int | Lockout duration |
| unlockTimestamp | string | When account unlocks |
| lastAttemptIp | string | IP of last failed attempt |

---

### 11. Session Revoked Notification
**Endpoint:** `/api/email/session-revoked`

| Variable | Type | Description |
|----------|------|-------------|
| email | string | Recipient email |
| fullName | string | User's full name |
| revokedSessionId | string | ID of revoked session |
| revokedDeviceInfo | string | Device info of session |
| revokedIp | string | IP of revoked session |
| revocationTimestamp | string | ISO 8601 timestamp |
| revokedByIp | string | IP that revoked session |

---

### 12. OAuth Account Created
**Endpoint:** `/api/email/oauth-account-created`

| Variable | Type | Description |
|----------|------|-------------|
| email | string | Recipient email |
| fullName | string | User's full name |
| oAuthProvider | string | Provider (google, github) |
| oAuthEmail | string | Email from OAuth provider |
| createdTimestamp | string | ISO 8601 timestamp |
| loginUrl | string | Login page URL |

---

### 13. API Key Created
**Endpoint:** `/api/email/api-key-created`

| Variable | Type | Description |
|----------|------|-------------|
| email | string | Recipient email |
| fullName | string | User's full name |
| keyPrefix | string | API key prefix (e.g., "dff_abc") |
| keyName | string | Name of the API key |
| createdTimestamp | string | ISO 8601 timestamp |
| createdIp | string | IP where key was created |

---

### 14. API Key Revoked
**Endpoint:** `/api/email/api-key-revoked`

| Variable | Type | Description |
|----------|------|-------------|
| email | string | Recipient email |
| fullName | string | User's full name |
| keyPrefix | string | API key prefix |
| keyName | string | Name of the API key |
| revokedTimestamp | string | ISO 8601 timestamp |
| revokedIp | string | IP where key was revoked |
