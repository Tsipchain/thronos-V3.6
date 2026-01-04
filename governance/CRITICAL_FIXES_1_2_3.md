# CRITICAL FIXES #1-#3 (PATCHES ONLY)

**Commit**: `51723c9`
**Branch**: `claude/fix-wallet-ui-final-gUEre`
**Date**: 2026-01-04

---

## ✅ FIX #1: Upload Endpoint Crash (NameError: secure_filename)

### Observable Proof
Production logs showed: `NameError: name 'secure_filename' is not defined` at `server.py:4548`

### Changes Made
**File**: `server.py`

**Lines 65-79**: Added import with fallback
```python
# CRITICAL FIX #1: Import secure_filename with fallback
try:
    from werkzeug.utils import secure_filename
except ImportError:
    # Fallback sanitizer if werkzeug doesn't have secure_filename
    def secure_filename(filename):
        """Minimal filename sanitizer - replace non-alphanumeric with underscore"""
        if not filename:
            return "unnamed"
        import re
        name, ext = os.path.splitext(filename)
        name = re.sub(r'[^a-zA-Z0-9_.-]', '_', name)[:100]
        ext = re.sub(r'[^a-zA-Z0-9.]', '', ext)[:10]
        return (name + ext) if name else "unnamed" + ext
```

### Verification
- ✅ Used in 8 places (lines 3250, 3713, 4417, 4449, 4531, 5423, 5483, 11027)
- ✅ AI_UPLOADS_DIR = DATA_DIR/ai_uploads (line 408)
- ✅ Telemetry appends to DATA_DIR/ai_files/index.jsonl (line 4615)
- ✅ Exception handler returns HTTP 200 degraded mode (lines 4640-4646)

### Acceptance Tests
- [ ] Upload .txt file in chat → HTTP 200 {ok:true}
- [ ] Check logs → zero NameError tracebacks
- [ ] Force empty file → HTTP 200 {ok:false, mode:"degraded"}
- [ ] Verify file exists at /app/data/ai_uploads/f_*
- [ ] Verify /app/data/ai_files/index.jsonl has new line

---

## ✅ FIX #2: Token Logos 404s

### Observable Proof
Console shows 404 for paths like:
- `/static/token_logos/T_949fe6f8185cd.jpg`
- Expected: `/media/token_logos/...` (DATA_DIR-backed)

### Root Cause
Custom tokens store logos in `DATA_DIR/media/token_logos/` but were being served with `/static/` prefix, causing 404s. Built-in tokens are in `/static/img/` or `/static/img/tokens/`.

### Changes Made
**File**: `server.py`

**Lines 5281-5337**: Patched `resolve_token_logo()` to return relative paths
```python
def resolve_token_logo(token_data: dict) -> str:
    """
    CRITICAL FIX #2: Resolve token logo with canonical path mapping.
    Returns relative path - caller adds /media/ or /static/ prefix.

    Fallback order:
    1. token_data['logo_path'] (custom tokens in DATA_DIR/media/token_logos)
    2. DATA_DIR/media/token_logos/<SYMBOL>_*.* (uploaded custom logos)
    3. /static/img/tokens/<SYMBOL>.png (built-in tokens)
    4. /static/img/<SYMBOL>.png (legacy built-in)
    5. None (frontend shows circle letter icon)
    """
    # Returns relative path without prefix:
    # - "token_logos/SYMBOL_timestamp.ext" for custom tokens
    # - "img/tokens/SYMBOL.png" for built-in tokens
    # - "img/SYMBOL.png" for legacy built-in
```

**Lines 1396-1407**: Patched caller to add correct URL prefix
```python
# CRITICAL FIX #2: Use correct logo URL (media vs static)
logo_path = resolve_token_logo(token_data)

# If logo_path starts with "token_logos/", it's in MEDIA_DIR → use /media/
# Otherwise (e.g., "img/..."), it's in static → use /static/
if logo_path:
    if logo_path.startswith("token_logos/"):
        logo_url = f"/media/{logo_path}"
    else:
        logo_url = f"/static/{logo_path}"
else:
    logo_url = None
```

### Canonical URL Patterns
- **Custom tokens**: `/media/token_logos/SYMBOL_timestamp.ext`
  - Routes to: `DATA_DIR/media/token_logos/` (line 2508-2512)
- **Built-in tokens**: `/static/img/tokens/SYMBOL.png`
  - Routes to: `BASE_DIR/static/img/tokens/` (line 159-161)
- **Legacy built-in**: `/static/img/SYMBOL.png`
  - Routes to: `BASE_DIR/static/img/` (line 159-161)

### Routing Endpoints
- **Line 159-161**: `/static/<path>` → `send_from_directory("static", filename)`
- **Line 2508-2512**: `/media/<path>` → `send_from_directory(MEDIA_DIR, filename)`

### Acceptance Tests
- [ ] Refresh wallet → zero 404s for token logos
- [ ] Network tab → custom tokens load from /media/token_logos/ (HTTP 200)
- [ ] Network tab → built-in tokens load from /static/img/ (HTTP 200)
- [ ] THR logo visible
- [ ] All custom tokens show correct logos

---

## ✅ FIX #3: git_commit Shows "unknown"

### Observable Proof
`/api/health` returns `"git_commit": "unknown"`
Footer shows `build: unknown`

### Changes Made
**File**: `server.py`

**Lines 3529-3567**: Patched git commit loading
```python
# CRITICAL FIX #3: Get git commit from env vars (Railway, Vercel, etc) or git command
git_commit = "unknown"
checked_env = []

# Try environment variables first (Railway, Vercel, etc)
env_vars = ["RAILWAY_GIT_COMMIT_SHA", "GIT_COMMIT", "COMMIT_SHA", "VERCEL_GIT_COMMIT_SHA"]
for env_var in env_vars:
    checked_env.append(env_var)
    commit_sha = os.getenv(env_var)
    if commit_sha:
        # Take first 7 chars for short hash
        git_commit = commit_sha[:7] if len(commit_sha) > 7 else commit_sha
        break

# Fallback: try git command (for local dev)
if git_commit == "unknown":
    try:
        import subprocess
        result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], ...)
        if result.returncode == 0:
            git_commit = result.stdout.strip()
    except Exception:
        pass

build_info = {
    "git_commit": git_commit,
    "checked_env": checked_env,  # Show which env vars we checked
    ...
}
```

### Acceptance Tests
- [ ] After deploy: `curl /api/health | jq .build.git_commit` → NOT "unknown"
- [ ] Footer shows `build: <7-char-hash>`
- [ ] Both match same commit hash

---

## Summary

**Type**: PATCHES ONLY
- ✅ No new endpoints created
- ✅ No new widgets created
- ✅ No architectural expansion
- ✅ Patched existing logic only

**Files Modified**: 1
- `server.py` (3 sections patched)

**Hard Rules Compliance**:
- ✅ No HTTP 500 (degraded mode maintained)
- ✅ DATA_DIR=/app/data (verified)
- ✅ Telemetry append-only JSONL
- ✅ Observable changes only

**Awaiting**: LIVE production verification after deployment

---

**End of Fixes Report**
