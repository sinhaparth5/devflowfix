# DevFlowFix - New API Endpoints Documentation

**Date:** December 28, 2025
**Features:** Enhanced Search, Background Jobs, CSV/PDF Exports

---

## 🔍 1. Enhanced Search API

### POST `/api/v1/incidents/search`

Advanced search for incidents with comprehensive filtering and pagination.

#### Request Body

```json
{
  "search_query": "timeout error",           // Optional: Full-text search
  "sources": ["github_actions", "jenkins"],  // Optional: Array of sources
  "severities": ["high", "critical"],        // Optional: Array of severities
  "outcomes": ["success", "pending"],        // Optional: Array of outcomes
  "failure_types": ["build_failure"],        // Optional: Array of failure types
  "tags": ["backend", "api"],                // Optional: Array of tags
  "repository": "owner/repo-name",           // Optional: Repository filter
  "min_confidence": 0.7,                     // Optional: Min confidence (0-1)
  "max_confidence": 1.0,                     // Optional: Max confidence (0-1)
  "date_preset": "last_7_days",              // Optional: Date preset
  "start_date": "2025-01-01T00:00:00Z",      // Optional: Custom start date
  "end_date": "2025-12-28T23:59:59Z",        // Optional: Custom end date
  "sort_by": "created_at",                   // Optional: Field to sort by
  "sort_order": "desc",                      // Optional: "asc" or "desc"
  "page": 1,                                 // Optional: Page number (default: 1)
  "page_size": 20                            // Optional: Items per page (default: 20)
}
```

#### Date Presets

- `today` - Today's incidents
- `yesterday` - Yesterday's incidents
- `this_week` - Current week
- `last_week` - Previous week
- `this_month` - Current month
- `last_month` - Previous month
- `last_7_days` - Last 7 days
- `last_30_days` - Last 30 days
- `last_90_days` - Last 90 days

#### Sort Fields

- `created_at` - Creation date
- `updated_at` - Last update date
- `severity` - Severity level
- `confidence` - Confidence score
- `resolution_time_seconds` - Resolution time

#### Response

```json
{
  "success": true,
  "incidents": [
    {
      "incident_id": "inc_abc123",
      "timestamp": "2025-12-28T10:30:00Z",
      "source": "github_actions",
      "severity": "high",
      "failure_type": "build_failure",
      "error_message": "Timeout error in CI pipeline",
      "root_cause": "Network timeout during dependency installation",
      "confidence": 0.85,
      "outcome": "success",
      "created_at": "2025-12-28T10:30:00Z",
      "resolved_at": "2025-12-28T10:45:00Z",
      "resolution_time_seconds": 900
    }
  ],
  "pagination": {
    "current_page": 1,
    "page_size": 20,
    "total_items": 150,
    "total_pages": 8,
    "has_previous": false,
    "has_next": true,
    "previous_url": null,
    "next_url": "http://api.example.com/api/v1/incidents/search?page=2&page_size=20",
    "first_url": "http://api.example.com/api/v1/incidents/search?page=1&page_size=20",
    "last_url": "http://api.example.com/api/v1/incidents/search?page=8&page_size=20",
    "next_cursor": "bmV4dF9jdXJzb3I=",
    "previous_cursor": null
  },
  "summary": {
    "total_results": 150,
    "filters_applied": {
      "search_query": "timeout error",
      "severities": ["high", "critical"],
      "min_confidence": 0.7
    },
    "search_duration_ms": 45,
    "date_range": {
      "start_date": "2025-12-21T00:00:00Z",
      "end_date": "2025-12-28T23:59:59Z",
      "preset": "last_7_days"
    }
  }
}
```

#### Example Usage (JavaScript/Fetch)

```javascript
const searchIncidents = async () => {
  const response = await fetch('/api/v1/incidents/search', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({
      search_query: 'timeout',
      severities: ['high', 'critical'],
      date_preset: 'last_7_days',
      page: 1,
      page_size: 20
    })
  });

  const data = await response.json();
  return data;
};
```

---

## 📋 2. Background Jobs API

### 2.1 Create Background Job

**POST** `/api/v1/jobs`

Create a new background job for long-running operations.

#### Request Body

```json
{
  "job_type": "export_csv",      // Required: Job type
  "parameters": {                 // Optional: Job parameters
    "export_type": "incidents",
    "format": "csv",
    "filters": {}
  }
}
```

#### Job Types

- `incident_analysis` - Analyze incidents
- `incident_reanalysis` - Re-analyze existing incidents
- `export_csv` - Export data to CSV
- `export_pdf` - Export data to PDF
- `bulk_update` - Bulk update operations
- `bulk_delete` - Bulk delete operations
- `pr_creation` - Create pull requests

#### Response

```json
{
  "job_id": "job_abc123def456",
  "job_type": "export_csv",
  "status": "queued",
  "progress": 0,
  "current_step": null,
  "created_at": "2025-12-28T10:00:00Z",
  "started_at": null,
  "completed_at": null,
  "estimated_completion": null,
  "result": null,
  "error_message": null,
  "user_id": "user_123",
  "parameters": {
    "export_type": "incidents",
    "format": "csv"
  },
  "status_url": "http://api.example.com/api/v1/jobs/job_abc123def456",
  "result_url": null
}
```

---

### 2.2 Get Job Status

**GET** `/api/v1/jobs/{job_id}`

Get the current status and progress of a background job.

#### Response

```json
{
  "job_id": "job_abc123def456",
  "job_type": "export_csv",
  "status": "processing",        // queued, processing, completed, failed, cancelled
  "progress": 45,                // 0-100
  "current_step": "Generating CSV file",
  "created_at": "2025-12-28T10:00:00Z",
  "started_at": "2025-12-28T10:00:05Z",
  "completed_at": null,
  "estimated_completion": "2025-12-28T10:05:00Z",
  "result": null,
  "error_message": null,
  "user_id": "user_123",
  "parameters": {},
  "status_url": "http://api.example.com/api/v1/jobs/job_abc123def456",
  "result_url": null
}
```

#### Example Usage (Polling)

```javascript
const pollJobStatus = async (jobId) => {
  const checkStatus = async () => {
    const response = await fetch(`/api/v1/jobs/${jobId}`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const job = await response.json();

    if (job.status === 'completed') {
      // Job done! Download result
      window.location.href = job.result_url;
    } else if (job.status === 'failed') {
      console.error('Job failed:', job.error_message);
    } else {
      // Still processing, check again in 2 seconds
      setTimeout(checkStatus, 2000);
    }
  };

  checkStatus();
};
```

---

### 2.3 List Background Jobs

**GET** `/api/v1/jobs`

List all background jobs for the current user.

#### Query Parameters

- `job_type` (optional): Filter by job type
- `status` (optional): Filter by status
- `page` (optional): Page number (default: 1)
- `page_size` (optional): Items per page (default: 20, max: 100)

#### Response

```json
{
  "jobs": [
    {
      "job_id": "job_abc123",
      "job_type": "export_csv",
      "status": "completed",
      "progress": 100,
      "created_at": "2025-12-28T10:00:00Z",
      "completed_at": "2025-12-28T10:02:30Z",
      "status_url": "/api/v1/jobs/job_abc123",
      "result_url": "/api/v1/jobs/job_abc123/download"
    }
  ],
  "total": 15,
  "page": 1,
  "page_size": 20
}
```

#### Example Usage

```javascript
const listJobs = async (filters = {}) => {
  const params = new URLSearchParams({
    page: 1,
    page_size: 20,
    ...filters
  });

  const response = await fetch(`/api/v1/jobs?${params}`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });

  return await response.json();
};

// Get all export jobs
const exportJobs = await listJobs({ job_type: 'export_csv' });

// Get only completed jobs
const completed = await listJobs({ status: 'completed' });
```

---

### 2.4 Cancel Background Job

**POST** `/api/v1/jobs/{job_id}/cancel`

Cancel a queued or processing background job.

#### Response

```json
{
  "job_id": "job_abc123",
  "job_type": "export_csv",
  "status": "cancelled",
  "progress": 30,
  "completed_at": "2025-12-28T10:02:00Z",
  "status_url": "/api/v1/jobs/job_abc123",
  "result_url": null
}
```

---

### 2.5 Delete Background Job

**DELETE** `/api/v1/jobs/{job_id}`

Delete a completed, failed, or cancelled job.

#### Response

`204 No Content` on success

---

### 2.6 Get Job Statistics

**GET** `/api/v1/jobs/stats/overview`

Get statistics about background jobs for the current user.

#### Response

```json
{
  "success": true,
  "statistics": {
    "total_jobs": 50,
    "by_status": {
      "queued": 2,
      "processing": 1,
      "completed": 45,
      "failed": 2,
      "cancelled": 0
    },
    "by_type": {
      "export_csv": 20,
      "export_pdf": 15,
      "bulk_update": 10,
      "pr_creation": 5
    },
    "success_rate": 95.74,
    "active_jobs": 3
  }
}
```

---

### 2.7 Get Active Jobs

**GET** `/api/v1/jobs/active`

Get all currently running or queued jobs.

#### Response

```json
{
  "success": true,
  "count": 3,
  "jobs": [
    {
      "job_id": "job_abc123",
      "job_type": "export_pdf",
      "status": "processing",
      "progress": 65,
      "current_step": "Generating PDF pages",
      "created_at": "2025-12-28T10:00:00Z",
      "started_at": "2025-12-28T10:00:05Z"
    }
  ]
}
```

---

### 2.8 Download Job Result

**GET** `/api/v1/jobs/{job_id}/download`

Download the result file from a completed export job.

#### Response

Binary file download with appropriate content-type header.

#### Example Usage

```javascript
const downloadJobResult = (jobId) => {
  // Simple redirect to trigger download
  window.location.href = `/api/v1/jobs/${jobId}/download`;

  // Or with fetch for more control
  fetch(`/api/v1/jobs/${jobId}/download`, {
    headers: { 'Authorization': `Bearer ${token}` }
  })
    .then(response => response.blob())
    .then(blob => {
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `export_${jobId}.csv`;
      a.click();
    });
};
```

---

## 📤 3. Export APIs

### 3.1 Export Incidents

**GET** `/api/v1/incidents/export`

Export incidents to CSV or PDF format.

#### Query Parameters

- `format` (required): `csv` or `pdf`
- `source` (optional): Filter by source
- `severity` (optional): Filter by severity
- `outcome` (optional): Filter by outcome
- `start_date` (optional): Start date (ISO 8601)
- `end_date` (optional): End date (ISO 8601)
- `limit` (optional): Max incidents to export (1-1000, default: 100)

#### Behavior

- **≤100 items**: Returns file immediately (direct download)
- **>100 items**: Creates background job, returns job ID

#### Response (Direct Download)

Binary file with appropriate headers.

#### Response (Background Job)

```json
{
  "success": true,
  "message": "Export job created for 500 incidents",
  "job_id": "job_abc123",
  "status_url": "/api/v1/jobs/job_abc123",
  "estimated_time": "2-5 minutes"
}
```

#### Example Usage

```javascript
// Small export - direct download
const exportSmall = () => {
  window.location.href = '/api/v1/incidents/export?format=csv&limit=50&severity=high';
};

// Large export - background job
const exportLarge = async () => {
  const response = await fetch(
    '/api/v1/incidents/export?format=pdf&limit=500',
    { headers: { 'Authorization': `Bearer ${token}` } }
  );

  const data = await response.json();

  if (data.job_id) {
    // Poll job status
    pollJobStatus(data.job_id);
  }
};
```

---

### 3.2 Export Analytics

**GET** `/api/v1/analytics/export`

Export analytics data to CSV or PDF format.

#### Query Parameters

- `format` (required): `csv` or `pdf`
- `days` (optional): Number of days to analyze (1-365, default: 30)

#### Response

Binary file download (always direct, no background job).

#### Example Usage

```javascript
const exportAnalytics = (format = 'pdf', days = 30) => {
  window.location.href = `/api/v1/analytics/export?format=${format}&days=${days}`;
};

// Export last 30 days as PDF
exportAnalytics('pdf', 30);

// Export last 90 days as CSV
exportAnalytics('csv', 90);
```

---

## 🎨 Frontend Integration Examples

### Complete Search & Export Flow

```javascript
class IncidentSearchExport {
  constructor(apiBaseUrl, authToken) {
    this.apiUrl = apiBaseUrl;
    this.token = authToken;
  }

  // Search incidents
  async search(filters) {
    const response = await fetch(`${this.apiUrl}/api/v1/incidents/search`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.token}`
      },
      body: JSON.stringify(filters)
    });

    return await response.json();
  }

  // Export with automatic job handling
  async export(format, filters, limit = 100) {
    const params = new URLSearchParams({
      format,
      limit,
      ...filters
    });

    const response = await fetch(
      `${this.apiUrl}/api/v1/incidents/export?${params}`,
      { headers: { 'Authorization': `Bearer ${this.token}` } }
    );

    // Check if it's a background job response
    const contentType = response.headers.get('content-type');

    if (contentType?.includes('application/json')) {
      const data = await response.json();

      if (data.job_id) {
        // Background job created - poll for completion
        return await this.pollJob(data.job_id);
      }
    } else {
      // Direct download
      const blob = await response.blob();
      this.downloadBlob(blob, `incidents_export.${format}`);
      return { success: true, type: 'direct' };
    }
  }

  // Poll job until completion
  async pollJob(jobId) {
    return new Promise((resolve, reject) => {
      const checkStatus = async () => {
        const response = await fetch(`${this.apiUrl}/api/v1/jobs/${jobId}`, {
          headers: { 'Authorization': `Bearer ${this.token}` }
        });

        const job = await response.json();

        if (job.status === 'completed') {
          // Download the result
          await this.downloadJob(jobId);
          resolve({ success: true, type: 'background', job });
        } else if (job.status === 'failed') {
          reject(new Error(job.error_message || 'Job failed'));
        } else {
          // Update progress in UI if needed
          this.onProgress?.(job.progress, job.current_step);

          // Check again in 2 seconds
          setTimeout(checkStatus, 2000);
        }
      };

      checkStatus();
    });
  }

  // Download job result
  async downloadJob(jobId) {
    const response = await fetch(`${this.apiUrl}/api/v1/jobs/${jobId}/download`, {
      headers: { 'Authorization': `Bearer ${this.token}` }
    });

    const blob = await response.blob();
    const contentDisposition = response.headers.get('content-disposition');
    const filename = contentDisposition?.match(/filename="(.+)"/)?.[1] || 'export.csv';

    this.downloadBlob(blob, filename);
  }

  // Helper to trigger browser download
  downloadBlob(blob, filename) {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  }
}

// Usage
const api = new IncidentSearchExport('http://localhost:8000', authToken);

// Set progress callback
api.onProgress = (progress, step) => {
  console.log(`${progress}% - ${step}`);
  // Update progress bar in UI
};

// Search
const results = await api.search({
  search_query: 'timeout',
  severities: ['high'],
  date_preset: 'last_7_days'
});

// Export (handles both small and large exports automatically)
await api.export('pdf', { severity: 'high' }, 200);
```

---

## 🔑 Authentication

All endpoints require Bearer token authentication:

```javascript
headers: {
  'Authorization': `Bearer ${YOUR_JWT_TOKEN}`
}
```

---

## ⚠️ Error Handling

All endpoints return standard error responses:

```json
{
  "error": "validation_error",
  "message": "Invalid request parameters",
  "errors": [...],
  "request_id": "req_xyz789",
  "timestamp": "2025-12-28T10:00:00Z"
}
```

**Common HTTP Status Codes:**
- `200` - Success
- `201` - Created
- `204` - No Content
- `400` - Bad Request
- `401` - Unauthorized
- `403` - Forbidden
- `404` - Not Found
- `422` - Validation Error
- `429` - Too Many Requests
- `500` - Internal Server Error

---

## 📊 Rate Limits

- **Production**: 120 requests per minute per user
- **Development**: Unlimited

---

## 🎯 Quick Reference

| Endpoint | Method | Purpose | Returns File? |
|----------|--------|---------|---------------|
| `/api/v1/incidents/search` | POST | Advanced search | No |
| `/api/v1/incidents/export` | GET | Export incidents | Yes/Job ID |
| `/api/v1/analytics/export` | GET | Export analytics | Yes |
| `/api/v1/jobs` | POST | Create job | No |
| `/api/v1/jobs` | GET | List jobs | No |
| `/api/v1/jobs/{id}` | GET | Job status | No |
| `/api/v1/jobs/{id}/cancel` | POST | Cancel job | No |
| `/api/v1/jobs/{id}` | DELETE | Delete job | No |
| `/api/v1/jobs/{id}/download` | GET | Download result | Yes |
| `/api/v1/jobs/stats/overview` | GET | Job statistics | No |
| `/api/v1/jobs/active` | GET | Active jobs | No |

---

## 📦 Dependencies

For PDF exports, ensure `reportlab` is installed:

```bash
uv pip install reportlab
```

---

**Generated:** December 28, 2025
**Version:** 1.0.0
