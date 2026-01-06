# AI-Powered PR Creation Guide

## Overview

The PR creation system now uses AI to automatically analyze workflow failures, identify the exact files and lines causing errors, and generate intelligent fixes.

## How It Works

### 1. Error Detection & Analysis

When a workflow fails and creates an incident:

```
Workflow Failure
    ↓
Webhook creates Incident
    ↓
User calls POST /v2/prs/create
```

### 2. AI Fix Generation Flow

**Step 1: Fetch Workflow Logs**
- Retrieves logs from GitHub Actions for the failed workflow
- Parses logs using `GitHubLogParser`
- Extracts error information including:
  - File paths (e.g., `src/components/Button.tsx`)
  - Line numbers (e.g., line 42)
  - Error types (lint errors, build failures, etc.)
  - Error messages

**Step 2: Fetch File Content**
- For each file with errors, fetches the current content from GitHub
- Gets the exact code that's causing the problem

**Step 3: AI Analysis**
- Sends to LLM (NVIDIA):
  - Error details (type, message, line number)
  - File content
  - Workflow context
- LLM analyzes and generates:
  - Root cause explanation
  - Specific fix for each error
  - Fixed code

**Step 4: Apply Fixes**
- Applies AI-generated fixes to the files
- Creates `PRFileChange` objects with:
  - File path
  - Fixed content
  - Explanation of what was fixed

**Step 5: Create PR**
- Creates a new branch
- Commits the fixes
- Opens PR with:
  - Detailed description of errors found
  - AI analysis summary
  - List of files modified
  - Testing checklist

## API Usage

### Create AI-Powered Fix PR

```http
POST /api/v2/prs/create
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "incident_id": "INC-abc123",
  "use_ai_analysis": true,
  "branch_name": "devflowfix/fix-inc-abc123",
  "draft_pr": false
}
```

**Parameters:**
- `incident_id` - ID of the incident to fix
- `use_ai_analysis` - Enable AI fix generation (default: true)
- `branch_name` - Custom branch name (optional, auto-generated)
- `draft_pr` - Create as draft PR (default: false)

**Response:**
```json
{
  "success": true,
  "pr_number": 42,
  "pr_url": "https://github.com/owner/repo/pull/42",
  "branch_name": "devflowfix/fix-inc-abc123",
  "files_changed": 3,
  "incident_id": "INC-abc123",
  "ai_analysis_used": true
}
```

## Example Scenarios

### Scenario 1: ESLint Error

**Error Log:**
```
src/components/Button.tsx:42:5 error 'useState' is not defined @react/react-in-jsx-scope
```

**AI Fix:**
1. Identifies file: `src/components/Button.tsx`
2. Identifies line: 42
3. Fetches file content
4. Analyzes: Missing React import
5. Generates fix: Add `import React, { useState } from 'react';`
6. Creates PR with fixed file

### Scenario 2: TypeScript Error

**Error Log:**
```
src/api/user.ts:15:3 error Type 'string' is not assignable to type 'number'
```

**AI Fix:**
1. Identifies the type mismatch at line 15
2. Analyzes the context and expected type
3. Generates fix: Converts string to number or updates type definition
4. Creates PR with explanation

### Scenario 3: Build Failure

**Error Log:**
```
Module not found: Error: Can't resolve './config' in 'src/utils'
```

**AI Fix:**
1. Identifies missing import
2. Analyzes project structure
3. Suggests correct import path
4. Updates the file with correct import
5. Creates PR

## Implementation Details

### AIFixGenerator Service

Located at: `app/services/ai_fix_generator.py`

**Key Methods:**

```python
async def generate_fixes_for_incident(
    db: Session,
    incident: IncidentTable,
    user_id: str,
) -> Tuple[List[PRFileChange], str]:
    """
    Main entry point - generates fixes for an incident.

    Returns:
        - List of file changes with fixes
        - AI analysis summary markdown
    """
```

**Configuration:**
- `max_files_to_fix` - Limit files per PR (default: 3)
- Prevents creating oversized PRs
- Focuses on critical errors first

### Error Parsing

Uses `GitHubLogParser` to extract:

```python
@dataclass
class ErrorBlock:
    step_name: str          # e.g., "Build / Lint"
    error_type: str         # e.g., "lint_error"
    error_message: str      # Full error message
    file_path: str          # e.g., "src/app.ts"
    line_number: int        # Exact line number
    severity: str           # "low", "medium", "high", "critical"
```

### LLM Integration

Uses `LLMAdapter` from `app/adapters/ai/nvidia/llm.py`:

```python
solution = await llm.generate_solution(
    error_log=error_context,
    failure_type="build_failure",
    root_cause="Code errors detected",
    context={
        "file_path": "src/app.ts",
        "repository": "owner/repo",
        "workflow": "CI",
    },
    repository_code=file_content,
)
```

Returns:
```python
{
    "immediate_fix": {...},
    "code_changes": [
        {
            "line_number": 42,
            "fixed_line": "import React from 'react';",
            "explanation": "Added missing React import"
        }
    ],
    "prevention_measures": [...]
}
```

## PR Description Format

Generated PRs include:

```markdown
## 🤖 Automated Fix by DevFlowFix

### Incident Details
- **Incident ID:** `INC-abc123`
- **Repository:** owner/repo
- **Branch:** `main`
- **Workflow:** CI Build
- **Commit:** `a1b2c3d`

### AI Analysis

**Errors Detected:** 3
**Files Fixed:** 2

#### Issues Found:
- **lint_error**: 2 occurrence(s)
- **build_failure**: 1 occurrence(s)

#### Files Modified:
- `src/components/Button.tsx` - Fix 2 error(s): lint_error
- `src/api/user.ts` - Fix 1 error(s): build_failure

#### Recommended Action:
1. Review the automated fixes in this PR
2. Run tests to verify the fixes work correctly
3. Merge if tests pass

### Changes Made
This PR modifies 2 file(s):

- `src/components/Button.tsx` - Added missing React import
- `src/api/user.ts` - Fixed module import path

### Testing
- [ ] Verify that the workflow runs successfully
- [ ] Check that the fix addresses the root cause
- [ ] Review code changes for correctness

---

_This PR was automatically generated by DevFlowFix._
```

## Fallback Behavior

If AI fix generation fails:

1. Logs error details
2. Creates placeholder PR with error message
3. Prompts manual review
4. Preserves incident for retry

## Best Practices

1. **Review AI Fixes**: Always review before merging
2. **Run Tests**: Verify fixes don't break other functionality
3. **Limit Files**: Keep PRs focused (max 3 files)
4. **Enable AI**: Always use `use_ai_analysis: true`
5. **Check Logs**: Review incident logs if fix fails

## Limitations

- **Max 3 files per PR**: Prevents oversized PRs
- **Requires workflow logs**: Incident must have log data
- **GitHub only**: Currently supports GitHub Actions only
- **Code errors only**: Works best with syntax/lint/build errors
- **May need refinement**: AI fixes should always be reviewed

## Future Enhancements

- Support for test failures
- Multi-file dependency fixes
- GitLab CI/CD support
- Learning from merged PRs
- Auto-merge on passing tests
- Regression detection
