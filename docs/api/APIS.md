# DevFlowFix Dashboard - API Documentation

This document outlines all the APIs implemented and used in the DevFlowFix Dashboard frontend application.

## Base Configuration

- **Base URL**: `https://devflowfix-new-production.up.railway.app/api/v1`
- **Authentication**: Bearer token-based (JWT) via Authorization header
- **HTTP Client**: Angular HttpClient
- **Security**: Auth interceptor for token management, XSS sanitization interceptor

---

## 1. Authentication APIs

**Service File**: `src/app/shared/components/auth/auth.service.ts`

### 1.1 User Registration
```
POST /auth/register
```
**Request Body**:
```json
{
  "email": "string",
  "password": "string",
  "first_name": "string",
  "last_name": "string"
}
```

### 1.2 User Login
```
POST /auth/login
```
**Request Body**:
```json
{
  "email": "string",
  "password": "string",
  "device_fingerprint": "string (auto-generated)",
  "mfa_code": "string (optional)",
  "remember_me": "boolean (optional)"
}
```
**Response**:
```json
{
  "access_token": "string",
  "refresh_token": "string",
  "token_type": "string",
  "expires_in": "number",
  "user": {
    "user_id": "string",
    "email": "string",
    "full_name": "string",
    "role": "string",
    "is_active": "boolean",
    "is_mfa_enabled": "boolean",
    "avatar_url": "string",
    "github_username": "string",
    "organization_id": "string",
    "team_id": "string",
    "preferences": "object"
  }
}
```

### 1.3 Logout
```
POST /auth/logout
```
**Request Body** (optional):
```json
{
  "all_sessions": "boolean"
}
```

### 1.4 Refresh Token
```
POST /auth/refresh
```
**Request Body**:
```json
{
  "refresh_token": "string"
}
```

### 1.5 Get Current User Profile
```
GET /auth/me
```
**Response**: User object

### 1.6 Upload User Avatar
```
POST /auth/me/avatar
```
**Request**: FormData with `avatar_file`

### 1.7 Update User Information
```
PATCH /auth/me
```
**Request Body**:
```json
{
  "full_name": "string (optional)",
  "github_username": "string (optional)",
  "organization_id": "string (optional)",
  "team_id": "string (optional)",
  "preferences": "object (optional)"
}
```

---

## 2. PR Management APIs

**Service File**: `src/app/shared/services/pr-management.service.ts`

### 2.1 Token Management

#### 2.1.1 Register GitHub Token
```
POST /pr-management/tokens/register?token=<github_token>
```
**Query Parameters**:
- `token` (required): GitHub token
- `owner` (optional): Repository owner
- `repo` (optional): Repository name
- `description` (optional): Token description
- `scopes` (optional): Token scopes

#### 2.1.2 List Registered Tokens
```
GET /pr-management/tokens?owner=<owner>&active_only=<true|false>
```
**Query Parameters**:
- `owner` (optional): Filter by repository owner
- `active_only` (default: true): Only show active tokens

#### 2.1.3 Deactivate Token
```
POST /pr-management/tokens/{token_id}/deactivate
```

### 2.2 Pull Request Tracking

#### 2.2.1 List Pull Requests
```
GET /pr-management/pulls
```
**Query Parameters**:
- `incident_id` (optional): Filter by incident ID
- `repository` (optional): Filter by repository
- `status_filter` (optional): Filter by status
- `skip` (default: 0): Pagination offset
- `limit` (default: 20, max: 100): Results per page

**Response**:
```json
{
  "items": [
    {
      "id": "string",
      "incident_id": "string",
      "pr_number": "number",
      "pr_url": "string",
      "repository": "string",
      "title": "string",
      "branch": "string",
      "status": "string",
      "failure_type": "string",
      "confidence_score": "number",
      "files_changed": "number",
      "additions": "number",
      "deletions": "number",
      "created_at": "string",
      "merged_at": "string",
      "approved_by": "string"
    }
  ],
  "total": "number",
  "skip": "number",
  "limit": "number"
}
```

#### 2.2.2 Get Pull Request Details
```
GET /pr-management/pulls/{pr_id}
```
**Response**: Extended PR object with description, base_branch, root_cause, commits_count, review_comments_count, has_conflicts, metadata

#### 2.2.3 Update Pull Request Status
```
POST /pr-management/pulls/{pr_id}/update-status
```
**Request Body**:
```json
{
  "new_status": "string (required)",
  "metadata": "object (optional)"
}
```

### 2.3 Statistics

#### 2.3.1 Get PR Statistics
```
GET /pr-management/stats
```
**Response**:
```json
{
  "total_prs": "number",
  "merged_count": "number",
  "merge_rate": "number",
  "status_distribution": "object",
  "avg_files_per_pr": "number",
  "total_additions": "number",
  "total_deletions": "number"
}
```

---

## 3. Analytics APIs

**Service File**: `src/app/shared/services/analytics.service.ts`

### 3.1 Incident Statistics
```
GET /analytics/stats?start_date=<date>&end_date=<date>&source=<source>
```
**Response**:
```json
{
  "total_incidents": "number",
  "resolved_incidents": "number",
  "failed_incidents": "number",
  "pending_incidents": "number",
  "escalated_incidents": "number",
  "rolled_back_incidents": "number",
  "success_rate": "number",
  "average_resolution_time_seconds": "number"
}
```

### 3.2 Breakdown Endpoints

#### 3.2.1 Breakdown by Source
```
GET /analytics/breakdown/source?start_date=<date>&end_date=<date>
```

#### 3.2.2 Breakdown by Severity
```
GET /analytics/breakdown/severity?start_date=<date>&end_date=<date>
```

#### 3.2.3 Breakdown by Failure Type
```
GET /analytics/breakdown/failure-type?start_date=<date>&end_date=<date>
```

#### 3.2.4 Breakdown by Outcome
```
GET /analytics/breakdown/outcome?start_date=<date>&end_date=<date>
```

### 3.3 Trend Analysis

#### 3.3.1 Incident Trends
```
GET /analytics/trends?days=<number>&granularity=<hour|day|week>
```
**Query Parameters**:
- `days` (default: 30): Number of days to analyze
- `granularity` (default: day): Time granularity

### 3.4 Performance Metrics

#### 3.4.1 Mean Time To Repair (MTTR)
```
GET /analytics/mttr?start_date=<date>&end_date=<date>&source=<source>
```
**Response**:
```json
{
  "average_seconds": "number",
  "min_seconds": "number",
  "max_seconds": "number",
  "median_seconds": "number",
  "p95_seconds": "number",
  "sample_size": "number"
}
```

#### 3.4.2 Auto-Fix Rate
```
GET /analytics/auto-fix-rate?start_date=<date>&end_date=<date>
```

#### 3.4.3 Confidence Score Distribution
```
GET /analytics/confidence-distribution?start_date=<date>&end_date=<date>
```

#### 3.4.4 Remediation Success
```
GET /analytics/remediation-success?start_date=<date>&end_date=<date>
```

### 3.5 User Feedback
```
GET /analytics/feedback?start_date=<date>&end_date=<date>
```

### 3.6 Top Lists

#### 3.6.1 Top Failure Types
```
GET /analytics/top/failure-types?limit=<number>&start_date=<date>&end_date=<date>
```

#### 3.6.2 Top Repositories
```
GET /analytics/top/repositories?limit=<number>&start_date=<date>&end_date=<date>
```

### 3.7 Time Distribution

#### 3.7.1 Hourly Distribution
```
GET /analytics/distribution/hourly?days=<number>
```

#### 3.7.2 Daily Distribution
```
GET /analytics/distribution/daily?days=<number>
```

### 3.8 Overview & Dashboard

#### 3.8.1 Comprehensive Overview
```
GET /analytics/overview?days=<number>
```
**Response**: Complex object with period, summary, breakdowns, trends, performance metrics, top failure types, and hourly distribution

#### 3.8.2 Dashboard Summary
```
GET /analytics/dashboard
```

---

## 4. Webhook APIs

**Service File**: `src/app/shared/services/webhook.service.ts`

### 4.1 Generate Webhook Secret
```
POST /webhook/secret/generate/me
```
**Response**:
```json
{
  "user_id": "string",
  "email": "string",
  "webhook_secret": "string",
  "webhook_url": "string",
  "secret_length": "number",
  "algorithm": "string",
  "created_at": "string",
  "github_configuration": {
    "payload_url": "string",
    "content_type": "string",
    "secret": "string",
    "ssl_verification": "boolean",
    "events": "array",
    "active": "boolean"
  },
  "setup_instructions": "array",
  "test_configuration": "object"
}
```

### 4.2 Get Webhook Configuration Info
```
GET /webhook/secret/info/me
```
**Response**:
```json
{
  "user_id": "string",
  "email": "string",
  "webhook_configuration": {
    "secret_configured": "boolean",
    "secret_preview": "string",
    "secret_length": "number",
    "webhook_url": "string",
    "last_updated": "string"
  },
  "github_settings": "object",
  "status": {
    "ready": "boolean",
    "message": "string"
  },
  "actions": "array"
}
```

---

## 5. User Details APIs

**Service File**: `src/app/shared/services/user-details.service.ts`

### 5.1 Get User Details
```
GET /user-details/me
```
**Response**:
```json
{
  "country": "string",
  "city": "string",
  "postal_code": "string",
  "facebook_link": "string",
  "twitter_link": "string",
  "linkedin_link": "string",
  "instagram_link": "string",
  "github_link": "string",
  "user_id": "string",
  "created_at": "string",
  "updated_at": "string"
}
```

### 5.2 Update User Details
```
PUT /user-details/me
```
**Request Body**:
```json
{
  "country": "string (optional)",
  "city": "string (optional)",
  "postal_code": "string (optional)",
  "facebook_link": "string (optional)",
  "twitter_link": "string (optional)",
  "linkedin_link": "string (optional)",
  "instagram_link": "string (optional)",
  "github_link": "string (optional)"
}
```

---

## Security Features

### Authentication & Authorization
- JWT Bearer token authentication for all API calls
- Token refresh mechanism with automatic retry on 401 errors
- Cookie-based token storage with HttpOnly, Secure, and SameSite=Strict flags
- Device fingerprinting for login tracking
- Auth interceptor for automatic token attachment and refresh

### Security Configuration
**Service File**: `src/app/shared/services/security-config.service.ts`

- Content Security Policy (CSP) enabled
- Strict sanitization mode for XSS protection
- Input validation: Maximum 10,000 characters
- Allowed file types: JPEG, PNG, GIF, WebP
- Maximum file size: 5MB

---

## Components Using APIs

### 1. Analytics Dashboard
- Location: `/pages/dashboard/analytics/`
- Uses: Analytics Service (all endpoints)

### 2. PR Management
- Location: `/pages/dashboard/pr-management/`
- Components:
  - PR list table
  - PR details modal
  - PR statistics dashboard
  - Token registration form
  - Token list table
- Uses: PR Management Service (all endpoints)

### 3. Webhooks Configuration
- Location: `/pages/dashboard/webhooks/`
- Uses: Webhook Service

### 4. User Profile
- Location: `/pages/profile/`
- Components:
  - User address card
  - User meta card
- Uses: User Details Service, Auth Service

### 5. Authentication Pages
- Location: `/pages/auth-pages/`
- Pages:
  - Sign-in
  - Sign-up
- Uses: Auth Service

### 6. Home Page
- Location: `/pages/home/`
- Uses: Various services for dashboard widgets

---

## 6. Incidents APIs

**Service File**: `src/app/shared/services/incidents.service.ts` (to be implemented)

### 6.1 List User Incidents
```
GET /incidents
```
**Query Parameters**:
- `skip` (default: 0): Pagination offset
- `limit` (default: 100, max: 1000): Records per page
- `source` (optional): Filter by incident source (github, argocd, kubernetes, etc.)
- `severity` (optional): Filter by severity (critical, high, medium, low)
- `outcome` (optional): Filter by outcome (resolved, pending, failed, escalated, rolled_back)
- `failure_type` (optional): Filter by failure type
- `start_date` (optional): Filter incidents after this date
- `end_date` (optional): Filter incidents before this date
- `search` (optional): Search in error logs

**Response**:
```json
{
  "incidents": [
    {
      "incident_id": "string",
      "source": "string",
      "severity": "string",
      "outcome": "string",
      "failure_type": "string",
      "error_log": "string",
      "created_at": "string",
      "resolved_at": "string",
      "user_id": "string"
    }
  ],
  "total": "number",
  "skip": "number",
  "limit": "number",
  "has_more": "boolean"
}
```

### 6.2 Get Incident Details
```
GET /incidents/{incident_id}
```
**Response**: Detailed incident information including analysis, remediation steps, and context

### 6.3 Get User Incident Statistics
```
GET /incidents/stats
```
**Query Parameters**:
- `start_date` (optional): Stats after this date
- `end_date` (optional): Stats before this date

**Response**:
```json
{
  "total_incidents": "number",
  "resolved_count": "number",
  "failed_count": "number",
  "pending_count": "number",
  "escalated_count": "number",
  "rolled_back_count": "number",
  "success_rate": "number",
  "average_resolution_time": "number",
  "by_source": "object",
  "by_severity": "object",
  "by_failure_type": "object"
}
```

### 6.4 Admin Endpoints

#### 6.4.1 List All Incidents (Admin Only)
```
GET /incidents/admin/all
```
**Query Parameters**:
- `skip`, `limit`: Pagination
- `user_id` (optional): Filter by user ID
- `source`, `severity`, `outcome`: Filters

**Response**: Same as regular list but includes incidents from all users

#### 6.4.2 Get Global Incident Statistics (Admin Only)
```
GET /incidents/admin/stats
```
**Response**: Aggregated statistics across all users

#### 6.4.3 Assign Incident to User (Admin Only)
```
POST /incidents/{incident_id}/assign
```
**Request Body**:
```json
{
  "user_id": "string"
}
```

---

## Backend API Implementation Guide

### Base URL
All backend APIs are served from:
```
https://devflowfix-new-production.up.railway.app/api/v1
```

### Authentication Requirements
Most endpoints require JWT Bearer token authentication:
```
Authorization: Bearer <access_token>
```

### Error Handling
All endpoints return standardized error responses:
```json
{
  "detail": "Error message description",
  "status_code": 400
}
```

Common status codes:
- `200`: Success
- `201`: Created
- `400`: Bad Request
- `401`: Unauthorized
- `403`: Forbidden
- `404`: Not Found
- `423`: Locked (account locked)
- `500`: Internal Server Error

---

## How to Implement Frontend Services

### 1. Authentication Service
Already implemented in `src/app/shared/components/auth/auth.service.ts`

**Key Features**:
- User registration with avatar upload (base64 or file upload)
- Login with MFA support
- Token refresh mechanism
- Session management
- Password change/reset
- MFA setup/enable/disable
- API key management

### 2. Incidents Service (To Implement)

**Recommended Implementation**:
```typescript
// src/app/shared/services/incidents.service.ts
import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '@environments/environment';

@Injectable({
  providedIn: 'root'
})
export class IncidentsService {
  private apiUrl = `${environment.apiUrl}/incidents`;

  constructor(private http: HttpClient) {}

  listIncidents(filters?: {
    skip?: number;
    limit?: number;
    source?: string;
    severity?: string;
    outcome?: string;
    failure_type?: string;
    start_date?: string;
    end_date?: string;
    search?: string;
  }): Observable<any> {
    let params = new HttpParams();
    if (filters) {
      Object.keys(filters).forEach(key => {
        if (filters[key] !== undefined && filters[key] !== null) {
          params = params.set(key, filters[key]);
        }
      });
    }
    return this.http.get(`${this.apiUrl}`, { params });
  }

  getIncident(incidentId: string): Observable<any> {
    return this.http.get(`${this.apiUrl}/${incidentId}`);
  }

  getIncidentStats(startDate?: string, endDate?: string): Observable<any> {
    let params = new HttpParams();
    if (startDate) params = params.set('start_date', startDate);
    if (endDate) params = params.set('end_date', endDate);
    return this.http.get(`${this.apiUrl}/stats`, { params });
  }

  // Admin endpoints
  listAllIncidents(filters?: any): Observable<any> {
    let params = new HttpParams();
    if (filters) {
      Object.keys(filters).forEach(key => {
        if (filters[key]) params = params.set(key, filters[key]);
      });
    }
    return this.http.get(`${this.apiUrl}/admin/all`, { params });
  }

  getGlobalStats(startDate?: string, endDate?: string): Observable<any> {
    let params = new HttpParams();
    if (startDate) params = params.set('start_date', startDate);
    if (endDate) params = params.set('end_date', endDate);
    return this.http.get(`${this.apiUrl}/admin/stats`, { params });
  }

  assignIncident(incidentId: string, userId: string): Observable<any> {
    return this.http.post(`${this.apiUrl}/${incidentId}/assign`, { user_id: userId });
  }
}
```

### 3. Webhook Configuration

**Already Implemented**: Webhook service exists in backend

**Usage Flow**:
1. User authenticates
2. Generate webhook secret via `POST /webhook/secret/generate/me`
3. Configure GitHub webhook with returned URL and secret
4. Receive webhook events at `/webhook/github/{user_id}`
5. Check webhook info via `GET /webhook/secret/info/me`

### 4. PR Management

**Already Implemented**: Available in `src/app/shared/services/pr-management.service.ts`

**Usage Flow**:
1. Register GitHub token via `POST /pr-management/tokens/register`
2. List tokens via `GET /pr-management/tokens`
3. View automated PRs via `GET /pr-management/pulls`
4. Check PR statistics via `GET /pr-management/stats`

### 5. Analytics Dashboard

**Already Implemented**: Available in `src/app/shared/services/analytics.service.ts`

**Key Metrics Available**:
- Incident statistics and trends
- MTTR (Mean Time To Repair)
- Auto-fix rates
- Confidence score distribution
- Top failure types and repositories
- Hourly/daily distribution patterns

---

## Integration Patterns

### Pattern 1: Real-time Incident Monitoring
```typescript
// Component example
export class IncidentsListComponent implements OnInit {
  incidents$ = this.incidentsService.listIncidents({
    limit: 20,
    source: 'github',
    outcome: 'pending'
  });

  ngOnInit() {
    // Refresh every 30 seconds
    interval(30000).pipe(
      switchMap(() => this.incidents$)
    ).subscribe();
  }
}
```

### Pattern 2: Analytics Dashboard
```typescript
export class AnalyticsDashboardComponent {
  overview$ = this.analyticsService.getOverview(30); // 30 days
  stats$ = this.analyticsService.getStats();
  mttr$ = this.analyticsService.getMTTR();
}
```

### Pattern 3: Webhook Setup Wizard
```typescript
export class WebhookSetupComponent {
  async setupWebhook() {
    const result = await this.webhookService.generateSecret().toPromise();
    // Display result.webhook_url and result.webhook_secret
    // Show setup instructions
    return result.setup_instructions;
  }
}
```

---

## Summary

- **Total API Services**: 6
- **Total Endpoints**: 60+
- **Base URL**: `https://devflowfix-new-production.up.railway.app/api/v1`
- **Authentication**: JWT Bearer tokens with auto-refresh
- **Primary Features**:
  - Authentication & User Management
  - Incident Management & Tracking
  - PR Management (GitHub Integration)
  - Analytics & Reporting
  - Webhook Configuration
  - User Profile Management

### Backend Technology Stack
- **Framework**: FastAPI (Python)
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Authentication**: JWT with session management
- **Security**: HMAC-SHA256 webhook signatures, MFA support
- **Background Tasks**: FastAPI BackgroundTasks for async processing

### Frontend Integration
- **HTTP Client**: Angular HttpClient
- **Interceptors**: Auth interceptor, XSS sanitization
- **State Management**: RxJS Observables
- **Security**: Content Security Policy, Input validation

All API calls include proper error handling, logging, and use typed responses for type safety.
