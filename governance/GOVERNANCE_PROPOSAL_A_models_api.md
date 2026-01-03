# GOVERNANCE PROPOSAL A: Fix /api/ai/models Error Handling

**Proposal ID**: GOV-2026-A-001
**Type**: Technical Fix
**Priority**: BLOCKER
**Voting Period**: Immediate (emergency fix)
**Quorum Required**: Simple majority

## Problem Statement

`/api/ai/models` returns HTTP 500 when providers fail to initialize, breaking `/chat` and `/architect` pages. Users experience blank pages and cannot select AI models.

## Option A: Graceful Degradation with Fallback Models

**Description**: Return HTTP 200 with degraded mode indicator and fallback model list when providers fail.

### Implementation
- Wrap all provider/stats loading in try-except
- Return 200 with `{ok: false, mode: "degraded", error_code: "PROVIDER_INIT_FAILED", fallback_models: [...]}`
- Frontend detects degraded mode and shows warning + fallback models
- Preserve AUTO option always

### Pros
- Users can still use AUTO routing even when discovery fails
- Frontend never crashes
- Clear error messaging to users
- Gradual degradation, not catastrophic failure

### Cons
- Requires frontend changes to handle degraded mode
- May mask underlying configuration issues if not logged properly

### Estimated Effort
- Backend: 30 lines of code changes in server.py
- Frontend: 20 lines in chat.html, 20 lines in architect.html
- Testing: 15 minutes

## Option B: Silent Fallback with Curated Models

**Description**: On provider failure, return 200 with curated static model list from `ai_models_config.py`.

### Implementation
- On exception, return CURATED_MODELS directly
- No `ok: false` flag
- Frontend treats as normal response
- Log errors server-side

### Pros
- Minimal frontend changes
- Users see models immediately
- Simple implementation

### Cons
- Hides errors from users (less transparent)
- Curated list may be stale
- No indication of degraded state
- Users may select models that aren't actually available

### Estimated Effort
- Backend: 15 lines of code
- Frontend: No changes needed
- Testing: 10 minutes

## Recommendation

**Option A** is recommended for transparency and user experience. Users should know when the system is degraded and why.

## Voting Instructions

DAO members vote:
- `A` for Option A (Graceful Degradation)
- `B` for Option B (Silent Fallback)
- `ABSTAIN` to abstain

## Implementation Timeline

Upon approval:
1. Implement chosen option
2. Test with missing API keys
3. Deploy to Railway
4. Monitor for 24 hours
5. Post PYTHEIA_ADVICE to DAO

## Appendix: Technical References

- server.py:10387-10459
- ai_models_config.py:15-58
- templates/chat.html:1759-1835
- templates/architect.html:505-551
