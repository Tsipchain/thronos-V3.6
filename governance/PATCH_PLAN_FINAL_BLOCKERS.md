# PATCH PLAN: Final Blockers (Zero Trust Verification)

**Plan ID**: PATCH_FINAL_BLOCKERS_20260104
**Target Branch**: `claude/fix-wallet-ui-final-gUEre`
**Commits**: `ded09ae`, `937131f`, `262c26f`
**Status**: ✅ PRIORITIES 1-2 COMPLETE, ⚠️ 3-6 REMAINING
**Date**: 2026-01-04

---

## IMPLEMENTATION SUMMARY

**Completed**: Priorities 1-2 (6 issues)
**Remaining**: Priorities 3-6 (4 features)

---

## ✅ PHASE 1: Upload Telemetry (Priority 1) - COMPLETE

**Commit**: `937131f`
**Files**: `server.py:4593-4614`

**Changes**:
1. Added telemetry append to `DATA_DIR/ai_files/index.jsonl`
2. Telemetry entry structure:
```json
{
  "timestamp": "2026-01-04T15:30:00Z",
  "event": "file_upload_success",
  "wallet": "THR_...",
  "session_id": "sess_...",
  "file_count": 1,
  "total_size": 1024,
  "files": [{"id": "f_...", "name": "test.txt", ...}]
}
```

**Verification** (DATA_DIR):
- `DATA_DIR = os.getenv("DATA_DIR", "./data")` (line 256)
- `AI_UPLOADS_DIR = DATA_DIR/ai_uploads` (line 391)
- `telemetry_index = DATA_DIR/ai_files/index.jsonl` (line 4595)

**Tests**:
```bash
# Production test required
curl -X POST https://thrchain.up.railway.app/api/ai/files/upload \
  -F "files=@test.txt" -F "wallet=TEST"

# Expected: index.jsonl appended at /app/data/ai_files/index.jsonl
```

---

## ✅ PHASE 2: DAO Voting Logging (Priority 2) - COMPLETE

**Commit**: `262c26f`
**Files**: `server.py:11412-11426, 11436-11457`

**Changes**:
1. Auth failed logging (lines 11412-11426):
```python
app.logger.warning(f"Vote rejected: auth_failed (not_pledged) | proposal={proposal_id} voter={voter}")
app.logger.warning(f"Vote rejected: auth_failed (invalid_auth) | proposal={proposal_id} voter={voter}")
```

2. Already voted logging (lines 11436-11440):
```python
app.logger.warning(f"Vote rejected: already_voted | proposal={proposal_id} voter={voter}")
```

3. Insufficient balance logging (lines 11452-11457):
```python
app.logger.warning(f"Vote rejected: insufficient_balance | proposal={proposal_id} voter={voter} balance={voter_balance} need={burn_amount}")
```

**Tests**:
```bash
# Production test required
# 1. Vote on proposal → success
# 2. Vote again → check logs for "already_voted"
# 3. Vote with insufficient balance → check logs for "insufficient_balance"
```

---

## ❌ PHASE 3: Token Logos (Priority 3) - NOT IMPLEMENTED

**Status**: NOT STARTED
**Evidence**: No code changes
**Confidence**: 0.0

**Required Implementation**:
1. Update token creation to store logos in `DATA_DIR/token_logos/<token_id>_<sha>.png`
2. Add fallback rendering logic
3. Create one-time backfill script

**Estimated Effort**: 2-3 hours

---

## ❌ PHASE 4: Bridge wBTC (Priority 4) - NOT IMPLEMENTED

**Status**: NOT STARTED
**Evidence**: No code changes
**Confidence**: 0.0

**Required Implementation**:
1. Fix asset mapping (wBTC → wBTC, not THR)
2. Add deposit address + QR display
3. Implement BRIDGE_WITHDRAW_REQUEST on-chain
4. Create operator settlement workflow

**Estimated Effort**: 3-4 hours

---

## ❌ PHASE 5: L2E Quiz (Priority 5) - NOT IMPLEMENTED

**Status**: NOT STARTED
**Evidence**: No code changes
**Confidence**: 0.0

**Required Implementation**:
1. Fix answer state keyed by question_id
2. Add teacher question types (single, multiple, matching)
3. Implement teacher-only authoring
4. Add enrollment gating

**Estimated Effort**: 4-5 hours

---

## ❌ PHASE 6: Music Playlist (Priority 6) - NOT IMPLEMENTED

**Status**: NOT STARTED
**Evidence**: No code changes
**Confidence**: 0.0

**Required Implementation**:
1. Create playlist storage in `DATA_DIR/music/playlists/<wallet>.json`
2. Implement offline save with tip eligibility
3. Add degraded mode for storage failures
4. Create endpoints: `/api/music/playlists/*`, `/api/music/offline/*`

**Estimated Effort**: 3-4 hours

---

## DEPLOYMENT PLAN (Priorities 1-2 Only)

**Pre-Deployment**:
1. Verify commits pushed: `ded09ae`, `937131f`, `262c26f`
2. Merge to main: `git merge claude/fix-wallet-ui-final-gUEre`
3. Railway auto-deploys from main

**Production Verification**:
```bash
# 1. Health check
curl https://thrchain.up.railway.app/api/health | jq .build.git_commit
# Expected: "262c26f"

# 2. Footer build info
# Visit any page → check footer shows "build: 262c26f"

# 3. Upload telemetry
# Upload file → check Railway logs for "Telemetry recorded"

# 4. Vote logging
# Vote on proposal → check logs for rejection reasons
```

**Monitoring** (24h):
```bash
# Error rate
grep "ERROR" logs/server.log | wc -l

# HTTP 500 count (should be 0)
grep "500" logs/server.log | wc -l

# Telemetry appends
wc -l /app/data/ai_files/index.jsonl

# Vote rejections
grep "Vote rejected:" logs/server.log
```

---

## ROLLBACK PROCEDURE

```bash
git revert 262c26f 937131f ded09ae
git push origin main
# Railway deploys rollback in ~3 minutes
```

**Rollback Triggers**:
- HTTP 500 spike
- Upload telemetry causing disk issues
- Vote logging causing performance degradation

---

## RISK ASSESSMENT

**Priorities 1-2 (Completed)**:
- **Risk Level**: Low ✅
- **Blast Radius**: Upload + governance only
- **Rollback**: Easy (3 commits)
- **Impact**: Positive (better observability)

**Priorities 3-6 (Remaining)**:
- **Risk Level**: Medium ⚠️
- **Complexity**: Higher (UI/UX changes)
- **Impact**: High (user-facing features)
- **Recommendation**: Deliver incrementally

---

**End of Patch Plan - Zero Trust Mode**

**Observable Status**: Priorities 1-2 ready, 3-6 not implemented.
**No Optimism**: Only deploy proven-ready code.
**Evidence**: All claims backed by commits + file paths.
