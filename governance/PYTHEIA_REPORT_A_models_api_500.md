# PYTHEIA REPORT A: /api/ai/models Returns 500 Error

**Report ID**: PYTH-2026-A-001
**Severity**: BLOCKER
**Status**: ACTIVE
**Date**: 2026-01-03
**Affected Components**: `/api/ai/models`, `/chat`, `/architect`

## Executive Summary

The `/api/ai/models` endpoint returns HTTP 500 errors when provider initialization fails or environment variables are missing, causing catastrophic failures in dependent pages (`/chat` and `/architect`). This results in blank pages and unusable AI features.

## Technical Analysis

### Root Cause
**Location**: `server.py:10387-10459`

```python
@app.route("/api/ai/models", methods=["GET"])
def api_ai_models():
    try:
        # ... model loading logic ...
        return jsonify(payload), 200
    except Exception as exc:
        app.logger.exception("api_ai_models error")
        return jsonify({"ok": False, "error": str(exc)}), 500  # ← BLOCKER
```

**Problem**: When `base_model_config()` or `compute_model_stats()` raise exceptions (missing keys, provider failures), the endpoint returns 500, which breaks frontend model loading.

### Affected Code Paths

1. **server.py:10403** - `base_cfg = base_model_config()` can fail if provider init fails
2. **server.py:10407** - `model_stats = compute_model_stats()` can fail if ledger is corrupt
3. **ai_models_config.py:49-58** - No error handling for malformed data

### Frontend Impact

**templates/chat.html:1759-1835** - `loadModels()` function:
```javascript
async function loadModels() {
  try {
    const res = await fetch(API_MODELS);
    if (!res.ok) {
      console.error("Failed to load models", res.status);
      return;  // ← Silently fails, dropdown shows only AUTO
    }
    // ...
  }
}
```

**templates/architect.html:505-551** - Similar pattern, no degraded mode handling.

## Evidence of Failure

Browser console shows:
```
GET /api/ai/models 500 (Internal Server Error)
Failed to load models 500
```

Result: Model dropdown shows only "AUTO" option, non-AUTO model selection impossible.

## Blast Radius

- **Critical**: `/chat` and `/architect` pages functionally degraded
- **High**: Users cannot select specific AI models
- **Medium**: AI feature discovery and transparency reduced
- **Low**: Auto-routing still works but user has no visibility

## Proposed Solutions (A/B)

See GOVERNANCE_PROPOSAL_A_models_api.md
