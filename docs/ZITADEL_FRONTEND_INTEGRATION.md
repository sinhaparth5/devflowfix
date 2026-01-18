# Zitadel Frontend Integration Guide

## Overview

This document explains how the Angular frontend integrates with Zitadel for authentication. The integration uses the **Authorization Code Flow with PKCE** (Proof Key for Code Exchange), which is the recommended approach for Single Page Applications (SPAs).

---

## Architecture

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│                  │     │                  │     │                  │
│  Angular App     │────▶│  Zitadel Cloud   │     │  Python Backend  │
│  devflowfix.com  │◀────│  (Identity)      │     │  api.devflowfix  │
│                  │     │                  │     │                  │
└──────────────────┘     └──────────────────┘     └──────────────────┘
        │                                                  ▲
        │                                                  │
        └──────────── API calls with token ────────────────┘
```

**Key Principle:** The frontend handles all authentication with Zitadel directly. The backend only validates tokens - it never participates in the login flow.

---

## Zitadel Console Setup

### Step 1: Create a Project

1. Log in to Zitadel Console
2. Navigate to **Projects** → **Create New Project**
3. Name it "DevFlowFix"

### Step 2: Create an Application

1. Inside the project, click **New Application**
2. Enter name: "DevFlowFix Web"
3. **Select Application Type: User Agent** (this is for SPAs)
4. Click Continue

### Step 3: Configure Authentication

1. Authentication Method: **PKCE** (auto-selected for User Agent apps)
2. This means no client secret is needed - the app uses a dynamically generated code verifier

### Step 4: Configure Redirect URIs

**Redirect URIs** (where Zitadel sends users after login):
```
https://devflowfix.com/auth/callback
http://localhost:4200/auth/callback
```

**Post-Logout URIs** (where users go after logout):
```
https://devflowfix.com
http://localhost:4200
```

### Step 5: Save and Copy Credentials

After saving, copy:
- **Client ID** (you'll need this in your Angular config)
- **Issuer URL** (your Zitadel instance URL)

---

## Frontend File Structure

```
src/app/auth/
├── auth.config.ts        → Zitadel connection settings
├── auth.service.ts       → Core authentication logic
├── auth.guard.ts         → Route protection
├── auth.interceptor.ts   → Automatic token attachment
└── callback/
    └── callback.component.ts → Handles login redirect
```

---

## How Each File Works

### 1. Auth Configuration (`auth.config.ts`)

**Purpose:** Stores all Zitadel-related settings in one place.

**What it contains:**
- **Issuer URL:** Your Zitadel instance (e.g., `https://devflowfix-xxx.zitadel.cloud`)
- **Client ID:** The identifier for your app from Zitadel Console
- **Redirect URI:** Where Zitadel sends users after successful login
- **Scopes:** What information and permissions we're requesting:
  - `openid` - Required for OIDC
  - `profile` - User's name and basic info
  - `email` - User's email address
  - `offline_access` - Allows token refresh without re-login

**Why PKCE?**
PKCE adds security for browser-based apps. Instead of a static secret (which could be stolen from browser code), PKCE generates a unique random code for each login attempt.

---

### 2. Auth Service (`auth.service.ts`)

**Purpose:** Central service that manages all authentication operations.

**What it does:**

1. **Initialization:**
   - Loads Zitadel's configuration (discovery document)
   - Checks if user is already logged in (from previous session)
   - Sets up automatic token refresh

2. **Login:**
   - Stores the current page URL (to return after login)
   - Redirects user to Zitadel's login page
   - User authenticates at Zitadel (not our app)

3. **Handle Callback:**
   - Receives the authorization code from Zitadel
   - Exchanges it for access and ID tokens
   - Extracts user information from ID token
   - Redirects user to their original destination

4. **Logout:**
   - Clears local tokens
   - Redirects to Zitadel to end the session there too
   - Returns user to home page

5. **Token Management:**
   - Provides access token for API calls
   - Automatically refreshes tokens before they expire
   - Detects when tokens are invalid

**Reactive State:**
The service exposes authentication state as signals:
- `isAuthenticated` - Boolean indicating login status
- `user` - Current user's information (name, email, etc.)
- `isLoading` - True while checking authentication

---

### 3. Auth Guard (`auth.guard.ts`)

**Purpose:** Protects routes that require authentication.

**How it works:**

1. User tries to navigate to a protected route (e.g., `/dashboard`)
2. Guard checks `authService.isAuthenticated()`
3. If authenticated → Allow access
4. If not authenticated → Redirect to Zitadel login, storing the intended URL

**Two guards provided:**
- `authGuard` - Requires login (for protected pages)
- `noAuthGuard` - Requires NOT logged in (for login page - redirects to dashboard if already logged in)

---

### 4. Auth Interceptor (`auth.interceptor.ts`)

**Purpose:** Automatically attaches the access token to API requests.

**How it works:**

1. Intercepts every HTTP request from the app
2. Checks if the request is going to our backend API
3. If yes, adds the Authorization header: `Bearer <access_token>`
4. Passes the modified request along

**Why this approach?**
- Components don't need to manually add tokens
- Centralized token management
- Easy to add error handling (e.g., redirect to login on 401)

---

### 5. Callback Component (`callback.component.ts`)

**Purpose:** Landing page after Zitadel authentication.

**What happens:**

1. Zitadel redirects to `https://devflowfix.com/auth/callback?code=xxx`
2. This component loads automatically
3. Shows a loading spinner to the user
4. Calls `authService.handleCallback()`
5. Service exchanges the code for tokens
6. User is redirected to their destination (dashboard or stored URL)

**Why a dedicated component?**
- Clean separation of concerns
- Can show loading state during token exchange
- Can handle errors gracefully

---

## Complete Login Flow

```
1. USER CLICKS LOGIN
   └── authService.login() called
   └── Current URL stored in sessionStorage
   └── Browser redirects to Zitadel

2. AT ZITADEL
   └── User sees Zitadel login page
   └── User enters credentials (or uses social login)
   └── Zitadel validates credentials
   └── Zitadel redirects to our callback URL with auth code

3. CALLBACK HANDLING
   └── CallbackComponent loads
   └── authService.handleCallback() called
   └── Auth code exchanged for tokens (via PKCE)
   └── Tokens stored in memory/storage
   └── User info extracted from ID token

4. POST-LOGIN
   └── User redirected to stored URL or dashboard
   └── authService.isAuthenticated = true
   └── UI updates to show logged-in state
```

---

## Complete API Call Flow

```
1. COMPONENT MAKES REQUEST
   └── httpClient.get('/api/v2/workflows')

2. INTERCEPTOR ACTIVATES
   └── Checks if URL matches API
   └── Gets access token from authService
   └── Adds Authorization header

3. REQUEST SENT
   └── GET https://api.devflowfix.com/api/v2/workflows
   └── Headers: { Authorization: Bearer eyJhbG... }

4. BACKEND VALIDATES
   └── Extracts token from header
   └── Validates with Zitadel's public keys
   └── Extracts user ID from token

5. RESPONSE RETURNED
   └── Data flows back to component
```

---

## Token Types

| Token | Purpose | Lifetime |
|-------|---------|----------|
| **Access Token** | Sent to backend API for authorization | Short (minutes to hours) |
| **ID Token** | Contains user information (name, email) | Short (matches access token) |
| **Refresh Token** | Used to get new access tokens without re-login | Long (days to weeks) |

---

## Security Considerations

### Why PKCE?
Traditional OAuth required a client secret, but secrets can't be safely stored in browser code (anyone can view it). PKCE solves this by:
1. Generating a random "code verifier" for each login
2. Creating a "code challenge" (hash of verifier)
3. Sending challenge during login request
4. Sending verifier during token exchange
5. Zitadel verifies they match

### Token Storage
- Tokens are stored in memory by default (most secure)
- Optional: sessionStorage for persistence across page refreshes
- Never use localStorage for tokens (XSS vulnerable)

### Automatic Refresh
- Tokens are refreshed before expiry
- If refresh fails, user is logged out
- Prevents sudden session termination

---

## Routes Configuration

| Route | Protection | Purpose |
|-------|------------|---------|
| `/` | Public | Home/landing page |
| `/auth/callback` | Public | Zitadel redirect handler |
| `/dashboard` | Protected | User dashboard |
| `/repositories` | Protected | Repository management |
| `/incidents` | Protected | Incident management |
| `/settings` | Protected | User settings |

---

## Environment Configuration

### Development
```
Issuer: https://devflowfix-xxx.zitadel.cloud
Redirect URI: http://localhost:4200/auth/callback
API URL: http://localhost:8000
```

### Production
```
Issuer: https://devflowfix-xxx.zitadel.cloud
Redirect URI: https://devflowfix.com/auth/callback
API URL: https://api.devflowfix.com
```

---

## Social Login Setup (Optional)

To enable "Login with Google/GitHub":

1. In Zitadel Console → Settings → Identity Providers
2. Add Google:
   - Create OAuth app in Google Cloud Console
   - Add Client ID and Secret to Zitadel
3. Add GitHub:
   - Create OAuth app in GitHub Developer Settings
   - Add Client ID and Secret to Zitadel

Users will see social login buttons on the Zitadel login page automatically.

---

## Troubleshooting

### "Invalid redirect URI"
- Ensure the redirect URI in your code exactly matches what's configured in Zitadel
- Check for trailing slashes

### "CORS error"
- Add your frontend URL to Allowed Origins in Zitadel Console

### "Token expired"
- Check that automatic refresh is set up
- Verify refresh token scope (`offline_access`) is requested

### "User null after login"
- Ensure `openid` and `profile` scopes are requested
- Check that ID token is being parsed correctly

---

## Summary

The frontend handles authentication entirely through Zitadel:

1. **No passwords stored** - Zitadel manages all credentials
2. **No session management** - Tokens handle authentication state
3. **Automatic token refresh** - Users stay logged in
4. **Protected routes** - Guards prevent unauthorized access
5. **Seamless API calls** - Interceptor handles token attachment

The backend's only job is to validate the tokens it receives - it never participates in the login flow itself.
