# Application Logging Integration Guide

Complete guide for tracking your CI/CD workflow with application logs and real-time SSE streaming.

## What's Been Implemented ✅

### 1. Database Table: `application_logs`
Tracks the entire workflow from webhook to remediation completion.

**Fields:**
- **Association:** `incident_id`, `user_id`, `session_id`
- **Classification:** `level` (debug/info/warning/error/critical), `category` (webhook/llm/analysis/remediation/github)
- **Content:** `message`, `stage`, `details` (JSON)
- **Error Tracking:** `error`, `stack_trace`
- **LLM Metrics:** `llm_model`, `llm_tokens_used`, `llm_response_time_ms`
- **Timing:** `created_at`, `duration_ms`

### 2. Logging Utility: `AppLogger`
**Location:** `app/utils/app_logger.py`

Easy-to-use helper class for logging throughout your code.

### 3. Webhook Logging ✅
**Location:** `app/api/v1/webhook.py`

Already integrated! Logs:
- Webhook received
- Payload parsed
- Queued for processing
- Errors during parsing

### 4. SSE Streaming Endpoints
**Endpoint:** `GET /api/v1/logs/stream`

Real-time streaming of application logs for users.

---

## How to Use AppLogger in Your Code

### Basic Usage

```python
from app.utils.app_logger import AppLogger
from sqlalchemy.orm import Session

# Create logger instance
app_logger = AppLogger(
    db=db_session,
    incident_id="inc_123",
    user_id="user_456"
)

# Log webhook received
app_logger.webhook_received(
    "GitHub workflow_run webhook received",
    details={"pr": 123, "branch": "main"}
)

# Log LLM analysis starting
app_logger.llm_start(
    "Analyzing error logs with GPT-4",
    model="gpt-4",
    details={"prompt_tokens": 500}
)

# Log LLM complete
app_logger.llm_complete(
    "Analysis complete: Found dependency conflict",
    model="gpt-4",
    tokens_used=1200,
    response_time_ms=3500,
    details={"root_cause": "npm version mismatch"}
)

# Log errors
app_logger.error(
    "LLM API timeout",
    error_obj=exception,
    category=LogCategory.LLM,
    stage="llm_analyzing"
)

# Log remediation
app_logger.remediation_start(
    "Creating fix for dependency conflict"
)

app_logger.github_pr_created(
    "PR #456 created with fix",
    pr_url="https://github.com/user/repo/pull/456"
)

# Log workflow complete
app_logger.workflow_complete(
    "CI/CD failure resolved successfully",
    details={"pr_number": 456, "fix_type": "dependency_update"}
)
```

### Quick Logging (One-liner)

```python
from app.utils.app_logger import quick_log

quick_log(
    db,
    "Something important happened",
    level="info",
    category="system",
    incident_id="inc_123"
)
```

---

## Where to Add Logging

### 1. Event Processor / Analysis Service

**File:** `app/services/event_processor.py` (or wherever your analysis happens)

```python
from app.utils.app_logger import AppLogger

class EventProcessor:
    def process_incident(self, incident_id, user_id, db):
        app_logger = AppLogger(db, incident_id=incident_id, user_id=user_id)

        try:
            # Log analysis start
            app_logger.analysis_start(
                "Starting failure analysis",
                details={"incident_type": "workflow_failure"}
            )

            # Your analysis code here
            result = self.analyze_logs(...)

            # Log analysis complete
            app_logger.analysis_complete(
                "Analysis identified root cause",
                details={"root_cause": result.root_cause}
            )

        except Exception as e:
            app_logger.error(
                "Analysis failed",
                error_obj=e,
                category=LogCategory.ANALYSIS
            )
            raise
```

### 2. LLM Service

**File:** Wherever you call LLM (e.g., `app/services/llm_analyzer.py`)

```python
import time
from app.utils.app_logger import AppLogger

class LLMAnalyzer:
    def analyze_with_llm(self, error_logs, db, incident_id, user_id):
        app_logger = AppLogger(db, incident_id=incident_id, user_id=user_id)

        # Log LLM start
        app_logger.llm_start(
            "Analyzing error logs with LLM",
            model=self.model_name,
            details={"log_lines": len(error_logs)}
        )

        start_time = time.time()

        try:
            # Call LLM
            response = self.llm_client.chat.completions.create(...)

            # Calculate metrics
            response_time_ms = int((time.time() - start_time) * 1000)
            tokens_used = response.usage.total_tokens

            # Log LLM complete
            app_logger.llm_complete(
                "LLM analysis completed successfully",
                model=self.model_name,
                tokens_used=tokens_used,
                response_time_ms=response_time_ms,
                details={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                }
            )

            return response.choices[0].message.content

        except Exception as e:
            app_logger.error(
                f"LLM API call failed: {str(e)}",
                error_obj=e,
                category=LogCategory.LLM,
                stage="llm_analyzing"
            )
            raise
```

### 3. Remediation Service

**File:** Wherever you execute fixes (e.g., `app/services/remediation.py`)

```python
from app.utils.app_logger import AppLogger

class RemediationService:
    def execute_fix(self, fix_plan, db, incident_id, user_id):
        app_logger = AppLogger(db, incident_id=incident_id, user_id=user_id)

        # Log remediation start
        app_logger.remediation_start(
            "Starting automated remediation",
            details={"fix_type": fix_plan.type}
        )

        try:
            # Execute fix
            app_logger.remediation_executing(
                "Applying code changes",
                details={"files_modified": len(fix_plan.files)}
            )

            result = self.apply_fix(fix_plan)

            # Log complete
            app_logger.remediation_complete(
                "Remediation executed successfully",
                duration_ms=result.duration_ms,
                details={"changes_applied": result.changes}
            )

        except Exception as e:
            app_logger.error(
                "Remediation failed",
                error_obj=e,
                category=LogCategory.REMEDIATION,
                stage="remediation_executing"
            )
            raise
```

### 4. GitHub PR Creation

**File:** Wherever you create PRs (e.g., `app/adapters/external/github/client.py`)

```python
from app.utils.app_logger import AppLogger

class GitHubClient:
    def create_pull_request(self, repo, branch, title, body, db, incident_id, user_id):
        app_logger = AppLogger(db, incident_id=incident_id, user_id=user_id)

        # Log PR creation start
        app_logger.github_pr_creating(
            f"Creating PR in {repo}",
            details={"branch": branch, "base": "main"}
        )

        try:
            pr = self.github_api.create_pull_request(...)

            # Log PR created
            app_logger.github_pr_created(
                f"PR #{pr.number} created successfully",
                pr_url=pr.html_url,
                details={
                    "pr_number": pr.number,
                    "title": title,
                }
            )

            return pr

        except Exception as e:
            app_logger.error(
                "Failed to create PR",
                error_obj=e,
                category=LogCategory.GITHUB,
                stage="github_pr_creating"
            )
            raise
```

---

## Workflow Stages Reference

Use these standard stage names for consistency:

| Stage | When to Use |
|-------|-------------|
| `webhook_received` | Webhook arrives |
| `webhook_parsed` | Payload parsed successfully |
| `webhook_queued` | Queued for background processing |
| `analysis_started` | Beginning failure analysis |
| `analysis_complete` | Analysis finished |
| `llm_analyzing` | LLM is processing |
| `llm_complete` | LLM finished |
| `remediation_started` | Starting fix |
| `remediation_executing` | Applying changes |
| `remediation_complete` | Fix applied |
| `github_pr_creating` | Creating PR |
| `github_pr_created` | PR created successfully |
| `workflow_complete` | Everything done |
| `error` | Any error occurred |

---

## Frontend Integration

### React Example: Real-time Workflow Tracker

```typescript
import { useEffect, useState } from 'react';

interface WorkflowLog {
  log_id: string;
  incident_id: string;
  level: string;
  category: string;
  message: string;
  stage: string;
  details: any;
  llm_model?: string;
  llm_tokens_used?: number;
  created_at: string;
}

function WorkflowTracker({ incidentId }: { incidentId: string }) {
  const [logs, setLogs] = useState<WorkflowLog[]>([]);
  const [currentStage, setCurrentStage] = useState('');
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const eventSource = new EventSource(
      `/api/v1/logs/stream?incident_id=${incidentId}`
    );

    eventSource.onmessage = (event) => {
      const log: WorkflowLog = JSON.parse(event.data);

      // Add log to list
      setLogs(prev => [log, ...prev]);

      // Update current stage
      setCurrentStage(log.stage);

      // Update progress based on stage
      const stageProgress = {
        'webhook_received': 10,
        'webhook_parsed': 20,
        'analysis_started': 30,
        'llm_analyzing': 50,
        'llm_complete': 60,
        'remediation_started': 70,
        'remediation_executing': 80,
        'github_pr_created': 95,
        'workflow_complete': 100,
      };

      setProgress(stageProgress[log.stage] || progress);
    };

    eventSource.onerror = () => {
      eventSource.close();
    };

    return () => eventSource.close();
  }, [incidentId]);

  return (
    <div>
      <h2>Workflow Progress</h2>
      <div className="progress-bar">
        <div style={{ width: `${progress}%` }}>{progress}%</div>
      </div>

      <p className="current-stage">{formatStage(currentStage)}</p>

      <div className="logs">
        {logs.map(log => (
          <div key={log.log_id} className={`log-entry ${log.level}`}>
            <span className="timestamp">
              {new Date(log.created_at).toLocaleTimeString()}
            </span>
            <span className="category">[{log.category}]</span>
            <span className="message">{log.message}</span>

            {log.llm_tokens_used && (
              <span className="tokens">
                {log.llm_tokens_used} tokens
              </span>
            )}

            {log.level === 'error' && (
              <div className="error-details">{log.error}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function formatStage(stage: string): string {
  const stages = {
    'webhook_received': '📨 Webhook Received',
    'webhook_parsed': '✅ Payload Parsed',
    'analysis_started': '🔍 Analyzing Failure',
    'llm_analyzing': '🤖 AI Analyzing Logs...',
    'llm_complete': '✨ Analysis Complete',
    'remediation_started': '🔧 Creating Fix',
    'remediation_executing': '⚙️ Applying Changes',
    'github_pr_created': '🎉 PR Created!',
    'workflow_complete': '✅ Complete!',
  };

  return stages[stage] || stage;
}
```

---

## Testing

### 1. Trigger a Webhook

Send a webhook to test the logging:

```bash
curl -X POST http://localhost:8000/api/v1/webhook/github/user_123 \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: workflow_run" \
  -H "X-Hub-Signature-256: sha256=YOUR_SIGNATURE" \
  -d '{"action": "completed", "workflow_run": {"conclusion": "failure"}}'
```

### 2. Watch Logs Stream

Open your browser console:

```javascript
const es = new EventSource('http://localhost:8000/api/v1/logs/stream?incident_id=inc_123');
es.onmessage = (e) => console.log(JSON.parse(e.data));
```

### 3. Check Database

```sql
SELECT
  incident_id,
  level,
  category,
  stage,
  message,
  created_at
FROM application_logs
WHERE incident_id = 'inc_123'
ORDER BY created_at ASC;
```

---

## Next Steps

1. ✅ **Webhook logging** - Already integrated!
2. **Add logging to your event processor/analysis service**
3. **Add logging to LLM calls**
4. **Add logging to remediation execution**
5. **Add logging to GitHub PR creation**
6. **Test end-to-end workflow with SSE streaming**

---

## Summary

**What You Have:**
- ✅ Database table ready
- ✅ AppLogger utility ready
- ✅ Webhook endpoint logging
- ✅ SSE streaming endpoint
- ✅ REST API for historical logs

**What You Need to Do:**
- Add `AppLogger` calls to your LLM service
- Add `AppLogger` calls to your remediation service
- Add `AppLogger` calls to your GitHub client
- Test the complete workflow

**Result:**
Real-time visibility into every step of your CI/CD failure detection and remediation workflow! 🚀

---

**Created:** 2025-12-28
**Version:** 1.0.0
