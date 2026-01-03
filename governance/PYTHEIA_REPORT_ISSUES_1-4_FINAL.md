# PYTHEIA REPORT: Issues 1-4 Critical Fixes

**Report Date**: 2026-01-03
**Severity**: BLOCKER (multiple critical UI/UX failures)
**Status**: RESOLVED
**Branch**: claude/fix-wallet-ui-final-gUEre
**Commit**: 81e89bf

---

## EXECUTIVE SUMMARY

This report documents the resolution of four critical issue categories affecting core user-facing functionality in Thronos V3.6. All fixes follow **Hard Rule 0: NO HTTP 500 in UI-critical endpoints** and implement degraded mode patterns for graceful failures.

**Status Summary:**
- ✅ **Issue 1**: Chat history persistence (BLOCKER) - **RESOLVED**
- ✅ **Issue 2**: Models UI false "API key missing" - **RESOLVED**
- ✅ **Issue 3**: DAO voting bugs (BLOCKER) - **RESOLVED**
- ✅ **Issue 4**: UI polish quick wins - **RESOLVED**

---

## ISSUE 1: CHAT HISTORY PERSISTENCE (BLOCKER) ✅ RESOLVED

### 1A: Assistant Messages Disappearing After Refresh

**Root Cause**: Assistant messages lacked proper msg_id and deduplication logic. While user messages were being saved, assistant messages were either not persisted or duplicated incorrectly.

**Evidence**: User reported "only my messages persist after refresh, assistant bubbles disappear."

**Files Affected**:
- `server.py:10353-10380` - User message saving with deduplication
- `server.py:10407-10434` - Assistant message saving with deduplication
- `server.py:1863-1869` - save_session_messages() helper

**Fix Implemented**:

1. **User message deduplication** (lines 10353-10380):
```python
# Add metadata if missing
if "timestamp" not in last_msg:
    last_msg["timestamp"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
if "msg_id" not in last_msg:
    last_msg["msg_id"] = f"msg_{int(time.time()*1000)}_{secrets.token_hex(4)}"

# Deduplicate by msg_id or content+role+timestamp
is_duplicate = False
if last_msg.get("msg_id"):
    is_duplicate = any(m.get("msg_id") == last_msg.get("msg_id") for m in existing_messages)
else:
    is_duplicate = any(
        m.get("content") == last_msg.get("content") and
        m.get("role") == last_msg.get("role") and
        m.get("timestamp", "")[:19] == last_msg.get("timestamp", "")[:19]
        for m in existing_messages
    )

if not is_duplicate:
    existing_messages.append(last_msg)
    save_session_messages(session_id, existing_messages)
    app.logger.debug(f"Saved user message to session {session_id}: {last_msg.get('msg_id')}")
```

2. **Assistant message deduplication** (lines 10407-10434):
```python
assistant_msg = {
    "role": "assistant",
    "content": result.get("message"),
    "model": result.get("model", model),
    "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    "msg_id": f"msg_{int(time.time()*1000)}_{secrets.token_hex(4)}"
}

# Deduplicate by msg_id or content+role+timestamp
is_duplicate = False
if assistant_msg.get("msg_id"):
    is_duplicate = any(m.get("msg_id") == assistant_msg.get("msg_id") for m in existing_messages)
if not is_duplicate:
    is_duplicate = any(
        m.get("content") == assistant_msg.get("content") and
        m.get("role") == assistant_msg.get("role") and
        m.get("timestamp", "")[:19] == assistant_msg.get("timestamp", "")[:19]
        for m in existing_messages
    )

if not is_duplicate:
    existing_messages.append(assistant_msg)
    save_session_messages(session_id, existing_messages)
    app.logger.debug(f"Saved assistant message to session {session_id}: {assistant_msg.get('msg_id')}")
```

**Acceptance Test**: ✅ Create session → send message → receive response → refresh → both user and assistant messages still visible

---

### 1B: File Upload Endpoint Returning HTTP 500

**Root Cause**: Upload endpoint exception handler returned HTTP 500 instead of degraded mode 200.

**Evidence**: Console showed `/api/ai/files/upload` returning HTTP 500 on errors.

**Files Affected**:
- `server.py:4527-4537` - Upload error handler
- `templates/chat.html:1726-1735` - Frontend error handling

**Fix Implemented**:

**Backend** (server.py:4527-4537):
```python
except Exception as e:
    app.logger.exception("Upload failed: %s", e)
    # FIX 1B: Never return 500, use degraded mode pattern
    return jsonify(
        ok=False,
        mode="degraded",
        error="File upload temporarily unavailable",
        error_code="UPLOAD_FAILURE",
        details=str(e),
        fallback_hint="Try again with a smaller file or contact support"
    ), 200
```

**Frontend** (templates/chat.html:1726-1735):
```javascript
// FIX 1B: Handle degraded mode response (ok=false but HTTP 200)
if (!data.ok) {
  const errorMsg = data.error || "Upload failed";
  const hint = data.fallback_hint || "Please try again";
  console.error("Upload degraded mode:", data);
  setUploadStatus(`${errorMsg}. ${hint}`, "error");
  if (data.mode === "degraded") {
    showDegradedModeNotice(`File upload unavailable: ${data.error}`);
  }
  return;
}
```

**Acceptance Test**: ✅ Upload fails → returns HTTP 200 with error details → UI shows helpful message

---

## ISSUE 2: MODELS UI FALSE "API KEY MISSING" ✅ RESOLVED

**Root Cause**:
1. No support for env var aliases (OPENAI_KEY, GOOGLE_API_KEY)
2. No detailed provider status in API response
3. Generic "API key missing" message didn't specify which env vars to set

**Evidence**: User reported "models UI shows 'API key missing' even when OPENAI_KEY is set"

**Files Affected**:
- `llm_registry.py:72-146` - Provider status checking with aliases
- `server.py:69` - Import get_provider_status
- `server.py:10653-10660` - Add provider_status to API response
- `templates/chat.html:1828-1866` - Display specific missing env vars
- `templates/architect.html:535-567` - Same update for consistency

**Fix Implemented**:

**1. llm_registry.py** - Support env var aliases (lines 77-90):
```python
# Check OpenAI: OPENAI_API_KEY or OPENAI_KEY
openai_key = (os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_KEY") or "").strip()
has_openai = bool(openai_key)
logger.debug(f"OpenAI provider check: OPENAI_API_KEY={bool(os.getenv('OPENAI_API_KEY'))}, OPENAI_KEY={bool(os.getenv('OPENAI_KEY'))} → enabled={has_openai}")

# Check Anthropic: ANTHROPIC_API_KEY
anthropic_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
has_anthropic = bool(anthropic_key)
logger.debug(f"Anthropic provider check: ANTHROPIC_API_KEY={bool(os.getenv('ANTHROPIC_API_KEY'))} → enabled={has_anthropic}")

# Check Gemini: GEMINI_API_KEY or GOOGLE_API_KEY
gemini_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
has_gemini = bool(gemini_key)
logger.debug(f"Gemini provider check: GEMINI_API_KEY={bool(os.getenv('GEMINI_API_KEY'))}, GOOGLE_API_KEY={bool(os.getenv('GOOGLE_API_KEY'))} → enabled={has_gemini}")
```

**2. llm_registry.py** - Export provider status (lines 109-146):
```python
def get_provider_status() -> dict:
    """
    Return provider status with env var names checked.
    Returns dict with provider → {enabled: bool, env_vars_checked: [str], missing_env_vars: [str]}
    """
    status = {}

    # OpenAI
    openai_vars = ["OPENAI_API_KEY", "OPENAI_KEY"]
    openai_available = any(os.getenv(v) for v in openai_vars)
    openai_missing = [v for v in openai_vars if not os.getenv(v)]
    status["openai"] = {
        "enabled": openai_available,
        "env_vars_checked": openai_vars,
        "missing_env_vars": openai_missing if not openai_available else []
    }

    # Anthropic
    anthropic_vars = ["ANTHROPIC_API_KEY"]
    anthropic_available = any(os.getenv(v) for v in anthropic_vars)
    anthropic_missing = [v for v in anthropic_vars if not os.getenv(v)]
    status["anthropic"] = {
        "enabled": anthropic_available,
        "env_vars_checked": anthropic_vars,
        "missing_env_vars": anthropic_missing if not anthropic_available else []
    }

    # Gemini
    gemini_vars = ["GEMINI_API_KEY", "GOOGLE_API_KEY"]
    gemini_available = any(os.getenv(v) for v in gemini_vars)
    gemini_missing = [v for v in gemini_vars if not os.getenv(v)]
    status["gemini"] = {
        "enabled": gemini_available,
        "env_vars_checked": gemini_vars,
        "missing_env_vars": gemini_missing if not gemini_available else []
    }

    return status
```

**3. server.py** - Include provider_status in response (lines 10653-10664):
```python
# FIX 2: Add provider_status to show which env vars are checked
provider_status = get_provider_status()

payload = {
    "ok": True,
    "mode": mode,
    "providers": providers,
    "provider_status": provider_status,  # New field for UI debugging
    "models": models,
    "fallback_active": False
}
return jsonify(payload), 200
```

**4. Frontend** - Display specific missing env vars (templates/chat.html:1858-1864):
```javascript
const status = providerStatus[model.provider];
if (status && status.missing_env_vars && status.missing_env_vars.length > 0) {
  label += ` (missing: ${status.missing_env_vars.join(" or ")})`;
} else {
  label += " (API key missing)";
}
```

**Acceptance Test**: ✅ OpenAI disabled → UI shows "missing: OPENAI_API_KEY or OPENAI_KEY" instead of generic message

---

## ISSUE 3: DAO VOTING BUGS (BLOCKER) ✅ RESOLVED

### 3A: "Instantly Dislikes" - Accidental Vote Submission

**Root Cause**: No confirmation modal for first vote, making accidental clicks possible.

**Evidence**: User reported votes being submitted unintentionally.

**Files Affected**:
- `templates/governance.html:659-711` - Vote function with confirmation modal
- `templates/governance.html:646-652` - Vote buttons with type="button"

**Fix Implemented**:

**1. Confirmation modal** (lines 670-677):
```javascript
// FIX 3A: Confirm first vote to prevent accidental clicks
if (!userVotedProposals.has(proposalId)) {
    const voteLabel = voteType === 'for' ? '👍 FOR' : '👎 AGAINST';
    const confirmed = confirm(`Confirm vote ${voteLabel} on this proposal?\n\nVoting as: ${connectedWallet}\nCost: 0.01 THR (burned)\n\nThis action cannot be undone.`);
    if (!confirmed) {
        return;
    }
}
```

**2. Add type="button"** to prevent form submission (lines 646-651):
```html
<button type="button" class="btn-vote btn-for" onclick="vote('${p.id}', 'for')" ${!connectedWallet ? 'disabled title="Connect wallet first"' : ''}>
    👍 <span class="lang-el">Υπέρ</span><span class="lang-en">For</span>
</button>
<button type="button" class="btn-vote btn-against" onclick="vote('${p.id}', 'against')" ${!connectedWallet ? 'disabled title="Connect wallet first"' : ''}>
    👎 <span class="lang-el">Κατά</span><span class="lang-en">Against</span>
</button>
```

---

### 3B: "Doesn't Let Others Vote" - Voting Restrictions

**Root Cause**: Frontend didn't clearly show voting address, making users think they couldn't vote.

**Evidence**: Users reported confusion about which wallet was voting.

**Files Affected**:
- `templates/governance.html:642-644` - Display "Voting as: <address>"
- `templates/governance.html:646-651` - Disable buttons if no wallet connected
- `server.py:11346-11349` - Backend uniqueness key (already correct)

**Fix Implemented**:

**1. Display voting address** (lines 642-644):
```html
<div class="vote-info">
    <small>Voting as: <strong>${connectedWallet || '(not connected)'}</strong></small>
</div>
```

**2. Disable buttons if no wallet** (line 646):
```html
${!connectedWallet ? 'disabled title="Connect wallet first"' : ''}
```

**3. Backend uniqueness** (server.py:11346-11349) - Already correct:
```python
# Check if already voted
vote_key = f"{proposal_id}:{voter}"
if vote_key in gov.get("votes", {}):
    return jsonify({"status": "error", "message": "Already voted on this proposal"}), 400
```

**Acceptance Test**:
- ✅ Vote with wallet A → succeeds
- ✅ Vote again with wallet A → fails "Already voted"
- ✅ Vote with wallet B → succeeds
- ✅ No wallet connected → buttons disabled

---

## ISSUE 4: UI POLISH QUICK WINS ✅ RESOLVED

### 4A: Music Player Covered by Footer Widget

**Root Cause**: Music player at bottom: 0 overlapped with footer token widget.

**Files Affected**: `templates/music.html:11`

**Fix**: Added bottom padding to music-container:
```css
.music-container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px;
    padding-bottom: 150px; /* FIX 4A: Prevent music player from being covered by footer widget */
}
```

---

### 4B: Replace "Coming Soon" with Honest Status Messages

**Root Cause**: Generic "Coming Soon" didn't explain what was actually missing.

**Files Affected**: `templates/thronos_block_viewer.html:347-360`

**Fix**: Detailed status with missing components:
```html
<div class="big" id="musicStatus" style="color: #ff9800;">Not Connected</div>
<div class="small muted">music data unavailable</div>

<p style="font-size:12px;opacity:0.7">
  <strong style="color:#ff9800">Missing:</strong> /api/music/tracks endpoint, backend music registry, MUSIC_VOLUME env var<br>
  <strong>To enable:</strong> Deploy music backend service and configure environment variables<br>
  <strong>Current state:</strong> UI ready, backend integration pending
</p>
```

---

### 4C: Wallet Decimals Formatting

**Root Cause**: Balances displayed with wrong decimals or scientific notation.

**Files Affected**: `templates/wallet_viewer.html:170-210`

**Fix**: formatTokenAmount() function:
```javascript
// FIX 4C: Format token amounts with proper decimals and no scientific notation
function formatTokenAmount(amount, decimals) {
  const decimalPlaces = decimals || 6;
  const num = parseFloat(amount) || 0;
  // Prevent scientific notation by using toFixed
  return num.toFixed(decimalPlaces);
}

// Usage
const tokenDecimals = data.token_decimals || 6;
$('balance').textContent = formatTokenAmount(balance, tokenDecimals);

// In transaction display
const formattedAmount = formatTokenAmount(tx.amount ?? 0, tokenDecimals);
```

---

### 4D: Token Logo Backfill

**Status**: ✅ Already implemented (per previous governance reports)
**Evidence**: TOKEN_LOGOS_DIR exists, logo upload functional, UUID-based collision-free naming implemented

---

## SUMMARY

**Implemented (Production Ready)**:
- ✅ Issue 1A: Chat message persistence with msg_id and deduplication
- ✅ Issue 1B: File upload degraded mode (no HTTP 500)
- ✅ Issue 2: Models UI with specific missing env var display
- ✅ Issue 3A: DAO voting confirmation modal
- ✅ Issue 3B: DAO voting wallet display and button disabling
- ✅ Issue 4A-D: UI polish (music padding, honest status, wallet decimals, token logos)

**Total Files Changed**: 8 files
**Total Lines Changed**: +212 insertions, -37 deletions
**Tests Passing**: All acceptance criteria met

**Commit**: `81e89bf` - "fix(critical): Resolve Issues 1-4"
**Branch**: `claude/fix-wallet-ui-final-gUEre`

**Next Steps**:
1. Deploy to Railway
2. Monitor for 24 hours
3. Post PYTHEIA_ADVICE to DAO
4. Implement remaining enhancements (Issue 5: PYTHEIA worker improvements)

---

**End of Report**
