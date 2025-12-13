# Analytics API

The Analytics API provides comprehensive incident monitoring, performance metrics, and reporting capabilities for DevFlowFix. All endpoints are prefixed with `/api/v1/analytics`.

## Endpoints

### Dashboard Summary

**GET** `/dashboard`

Get comprehensive dashboard data including today, week, and month statistics.

**Response:**
```json
{
  "today": {...},
  "week": {...},
  "month": {...}
}
```

**Status Codes:**
- `200 OK` - Successfully retrieved dashboard data
- `500 Internal Server Error` - Failed to retrieve dashboard data

---

### Incident Statistics

**GET** `/stats`

Get incident counts and success rates with optional date filtering.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | datetime | No | Filter incidents from this date |
| `end_date` | datetime | No | Filter incidents to this date |
| `source` | string | No | Filter by source (e.g., "github", "gitlab") |

**Response:**
```json
{
  "total_incidents": 150,
  "success_rate": 0.85,
  "total_resolved": 127,
  "total_pending": 23
}
```

**Status Codes:**
- `200 OK` - Successfully retrieved statistics
- `400 Bad Request` - Invalid source value
- `500 Internal Server Error` - Failed to retrieve statistics

---

### Incident Breakdown

#### By Source

**GET** `/breakdown/source`

Get incident count breakdown by source platform (GitHub, GitLab, etc.).

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | datetime | No | Filter incidents from this date |
| `end_date` | datetime | No | Filter incidents to this date |

**Response:**
```json
{
  "github": 85,
  "gitlab": 45,
  "jenkins": 20
}
```

**Status Codes:**
- `200 OK` - Successfully retrieved breakdown
- `500 Internal Server Error` - Failed to retrieve source breakdown

---

#### By Severity

**GET** `/breakdown/severity`

Get incident count breakdown by severity level.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | datetime | No | Filter incidents from this date |
| `end_date` | datetime | No | Filter incidents to this date |

**Response:**
```json
{
  "critical": 15,
  "high": 45,
  "medium": 60,
  "low": 30
}
```

**Status Codes:**
- `200 OK` - Successfully retrieved breakdown
- `500 Internal Server Error` - Failed to retrieve severity breakdown

---

#### By Failure Type

**GET** `/breakdown/failure-type`

Get incident count breakdown by failure type (build failures, test failures, deployment issues, etc.).

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | datetime | No | Filter incidents from this date |
| `end_date` | datetime | No | Filter incidents to this date |

**Response:**
```json
{
  "build_failure": 55,
  "test_failure": 40,
  "deployment_failure": 30,
  "configuration_error": 25
}
```

**Status Codes:**
- `200 OK` - Successfully retrieved breakdown
- `500 Internal Server Error` - Failed to retrieve failure type breakdown

---

#### By Outcome

**GET** `/breakdown/outcome`

Get incident count breakdown by outcome status (auto-fixed, escalated, etc.).

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | datetime | No | Filter incidents from this date |
| `end_date` | datetime | No | Filter incidents to this date |

**Response:**
```json
{
  "auto_fixed": 100,
  "escalated": 30,
  "pending": 20
}
```

**Status Codes:**
- `200 OK` - Successfully retrieved breakdown
- `500 Internal Server Error` - Failed to retrieve outcome breakdown

---

### Incident Trends

**GET** `/trends`

Get incident trends over time with configurable granularity.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `days` | integer | No | Number of days to look back (1-365, default: 30) |
| `granularity` | string | No | Time granularity: "hour", "day", or "week" (default: "day") |

**Response:**
```json
[
  {
    "timestamp": "2025-12-13T00:00:00Z",
    "incident_count": 12,
    "auto_fixed_count": 10,
    "escalated_count": 2
  },
  {
    "timestamp": "2025-12-14T00:00:00Z",
    "incident_count": 8,
    "auto_fixed_count": 7,
    "escalated_count": 1
  }
]
```

**Status Codes:**
- `200 OK` - Successfully retrieved trends
- `500 Internal Server Error` - Failed to retrieve trends

---

### Performance Metrics

#### Mean Time To Repair (MTTR)

**GET** `/mttr`

Get MTTR statistics including average, minimum, maximum, median, and 95th percentile.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | datetime | No | Filter incidents from this date |
| `end_date` | datetime | No | Filter incidents to this date |
| `source` | string | No | Filter by source platform |

**Response:**
```json
{
  "average_seconds": 450,
  "min_seconds": 60,
  "max_seconds": 3600,
  "median_seconds": 300,
  "p95_seconds": 1200,
  "sample_size": 150
}
```

**Status Codes:**
- `200 OK` - Successfully retrieved MTTR
- `400 Bad Request` - Invalid source value
- `500 Internal Server Error` - Failed to retrieve MTTR

---

#### Auto-Fix Rate

**GET** `/auto-fix-rate`

Get auto-fix vs escalation rate statistics.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | datetime | No | Filter incidents from this date |
| `end_date` | datetime | No | Filter incidents to this date |

**Response:**
```json
{
  "total_incidents": 150,
  "auto_fixed": 120,
  "escalated": 30,
  "auto_fix_rate": 0.80,
  "escalation_rate": 0.20
}
```

**Status Codes:**
- `200 OK` - Successfully retrieved auto-fix rate
- `500 Internal Server Error` - Failed to retrieve auto-fix rate

---

### AI Metrics

#### Confidence Score Distribution

**GET** `/confidence-distribution`

Get distribution of AI confidence scores across incidents.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | datetime | No | Filter incidents from this date |
| `end_date` | datetime | No | Filter incidents to this date |

**Response:**
```json
{
  "0-20": 5,
  "20-40": 10,
  "40-60": 25,
  "60-80": 60,
  "80-100": 50
}
```

**Status Codes:**
- `200 OK` - Successfully retrieved confidence distribution
- `500 Internal Server Error` - Failed to retrieve confidence distribution

---

#### Remediation Success by Action Type

**GET** `/remediation-success`

Get success rates for each remediation action type.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | datetime | No | Filter incidents from this date |
| `end_date` | datetime | No | Filter incidents to this date |

**Response:**
```json
[
  {
    "action_type": "dependency_update",
    "total_attempts": 50,
    "successful": 45,
    "success_rate": 0.90
  },
  {
    "action_type": "configuration_fix",
    "total_attempts": 30,
    "successful": 25,
    "success_rate": 0.83
  }
]
```

**Status Codes:**
- `200 OK` - Successfully retrieved remediation success rates
- `500 Internal Server Error` - Failed to retrieve remediation success rates

---

### User Feedback

**GET** `/feedback`

Get summary of user feedback on remediations.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_date` | datetime | No | Filter feedback from this date |
| `end_date` | datetime | No | Filter feedback to this date |

**Response:**
```json
{
  "total_feedback": 100,
  "positive": 85,
  "negative": 15,
  "satisfaction_rate": 0.85,
  "average_rating": 4.2
}
```

**Status Codes:**
- `200 OK` - Successfully retrieved feedback summary
- `500 Internal Server Error` - Failed to retrieve feedback summary

---

### Top Lists

#### Top Failure Types

**GET** `/top/failure-types`

Get most common failure types.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | integer | No | Number of results to return (1-50, default: 10) |
| `start_date` | datetime | No | Filter incidents from this date |
| `end_date` | datetime | No | Filter incidents to this date |

**Response:**
```json
[
  {
    "failure_type": "test_failure",
    "count": 55,
    "percentage": 0.37
  },
  {
    "failure_type": "build_failure",
    "count": 40,
    "percentage": 0.27
  }
]
```

**Status Codes:**
- `200 OK` - Successfully retrieved top failure types
- `500 Internal Server Error` - Failed to retrieve top failure types

---

#### Top Repositories

**GET** `/top/repositories`

Get repositories with most incidents.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | integer | No | Number of results to return (1-50, default: 10) |
| `start_date` | datetime | No | Filter incidents from this date |
| `end_date` | datetime | No | Filter incidents to this date |

**Response:**
```json
[
  {
    "repository": "owner/repo-name",
    "incident_count": 45,
    "auto_fix_rate": 0.82
  },
  {
    "repository": "owner/another-repo",
    "incident_count": 30,
    "auto_fix_rate": 0.75
  }
]
```

**Status Codes:**
- `200 OK` - Successfully retrieved top repositories
- `500 Internal Server Error` - Failed to retrieve top repositories

---

### Time Distribution

#### Hourly Distribution

**GET** `/distribution/hourly`

Get incident count by hour of day (0-23).

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `days` | integer | No | Number of days to analyze (1-365, default: 30) |

**Response:**
```json
{
  "0": 5,
  "1": 3,
  "2": 2,
  ...
  "22": 8,
  "23": 6
}
```

**Status Codes:**
- `200 OK` - Successfully retrieved hourly distribution
- `500 Internal Server Error` - Failed to retrieve hourly distribution

---

#### Daily Distribution

**GET** `/distribution/daily`

Get incident count by day of week.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `days` | integer | No | Number of days to analyze (1-365, default: 30) |

**Response:**
```json
{
  "Monday": 25,
  "Tuesday": 30,
  "Wednesday": 28,
  "Thursday": 32,
  "Friday": 35,
  "Saturday": 15,
  "Sunday": 10
}
```

**Status Codes:**
- `200 OK` - Successfully retrieved daily distribution
- `500 Internal Server Error` - Failed to retrieve daily distribution

---

### Analytics Overview

**GET** `/overview`

Get a comprehensive overview combining multiple analytics endpoints for dashboard display.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `days` | integer | No | Number of days to analyze (1-365, default: 30) |

**Response:**
```json
{
  "period": {
    "start_date": "2025-11-13T00:00:00Z",
    "end_date": "2025-12-13T00:00:00Z",
    "days": 30
  },
  "summary": {
    "total_incidents": 150,
    "success_rate": 0.85
  },
  "breakdown": {
    "by_source": {...},
    "by_severity": {...},
    "by_outcome": {...}
  },
  "trends": [...],
  "performance": {
    "mttr": {...},
    "auto_fix_rate": {...}
  },
  "top_failure_types": [...],
  "hourly_distribution": {...},
  "generated_at": "2025-12-13T10:30:00Z"
}
```

**Status Codes:**
- `200 OK` - Successfully retrieved analytics overview
- `500 Internal Server Error` - Failed to retrieve analytics overview

---

## Common Query Parameters

Most analytics endpoints support these common query parameters for filtering:

- `start_date` (datetime): Filter data from this date/time
- `end_date` (datetime): Filter data until this date/time
- `source` (string): Filter by incident source platform

## Date Format

All datetime parameters and responses use ISO 8601 format with UTC timezone:
```
2025-12-13T10:30:00Z
```

## Error Responses

All endpoints may return these error responses:

**400 Bad Request**
```json
{
  "detail": "Invalid source: invalid_platform"
}
```

**500 Internal Server Error**
```json
{
  "detail": "Failed to retrieve analytics data"
}
```

## Usage Examples

### Get incident statistics for the last 7 days

```bash
curl -X GET "http://localhost:8000/api/v1/analytics/stats?start_date=2025-12-06T00:00:00Z&end_date=2025-12-13T23:59:59Z"
```

### Get MTTR for GitHub incidents

```bash
curl -X GET "http://localhost:8000/api/v1/analytics/mttr?source=github"
```

### Get hourly distribution for last 60 days

```bash
curl -X GET "http://localhost:8000/api/v1/analytics/distribution/hourly?days=60"
```

### Get comprehensive dashboard overview

```bash
curl -X GET "http://localhost:8000/api/v1/analytics/overview?days=30"
```

## Notes

- All endpoints are read-only (GET requests only)
- No authentication is currently required (may change in future versions)
- Responses are cached for performance optimization
- Large date ranges may result in slower response times
- All timestamps are in UTC timezone
