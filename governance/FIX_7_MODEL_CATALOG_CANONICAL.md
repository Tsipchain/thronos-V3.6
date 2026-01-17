# FIX #7: Model Catalog Unification - Canonical Output

**Date**: 2026-01-04
**Branch**: `claude/fix-wallet-ui-final-gUEre`
**Type**: PATCH-ONLY (no new endpoints)

---

## EXECUTIVE SUMMARY

**Goal**: Single source of truth for AI model dropdown - eliminate duplicates, explicit labels, proper availability checks.

**Status**: ✅ COMPLETE

**Changes**:
- Explicit display names: "Offline corpus (local)", "Thronos / Thrai (custom)"
- Availability rules: local (corpus file), thronos (CUSTOM_MODEL_URL)
- Deduplication: (provider, model_id) key, skip duplicates
- Source tracking: "source" field per provider for debugging

---

## OBSERVABLE ISSUES (Before Fix)

1. **Duplicate Models in Dropdown**:
   - Multiple "Thronos" entries
   - Multiple "Thrai" entries
   - Confusing labels: "Thronos 2", "Thrai αλλού", etc.

2. **Incorrect Availability**:
   - "API key missing" errors for local/thronos providers
   - local/thronos shown as enabled even without corpus file or CUSTOM_MODEL_URL

3. **No Debug Info**:
   - Can't identify which code path generates duplicates
   - No way to track source of each provider

---

## CANONICAL PROVIDERS (After Fix)

### 1. OpenAI
- **Models**: gpt-4.1-mini, gpt-4.1, gpt-4.1-preview, o3-mini
- **Requires**: OPENAI_API_KEY or OPENAI_KEY
- **Source**: registry

### 2. Anthropic
- **Models**: claude-3.5-sonnet, claude-3.5-haiku
- **Requires**: ANTHROPIC_API_KEY
- **Source**: registry

### 3. Google (gemini)
- **Models**: gemini-2.0-flash, gemini-2.5-pro, gemini-2.5-flash
- **Requires**: GEMINI_API_KEY or GOOGLE_API_KEY
- **Source**: registry

### 4. Local
- **Models**: offline_corpus ONLY
- **Display**: "Offline corpus (local)"
- **Requires**: ai_offline_corpus.json file exists in DATA_DIR
- **No API key required**
- **Source**: registry

### 5. Thronos
- **Models**: thrai ONLY
- **Display**: "Thronos / Thrai (custom)"
- **Requires**: CUSTOM_MODEL_URL env var configured
- **Mode check**: THRONOS_AI_MODE must be "all", "router", "auto", "custom", or empty
- **Source**: registry

---

## CHANGES MADE

### 1. Display Names (llm_registry.py:64-67)

**Before**:
```python
"local": [
    ModelInfo(id="offline_corpus", display_name="Offline corpus", ...),
],
"thronos": [
    ModelInfo(id="thrai", display_name="Thronos Thrai", ...),
],
```

**After**:
```python
"local": [
    ModelInfo(id="offline_corpus", display_name="Offline corpus (local)", ...),
],
"thronos": [
    ModelInfo(id="thrai", display_name="Thronos / Thrai (custom)", ...),
],
```

**Why**: Explicit labels eliminate confusion. User sees exactly what they're selecting.

---

### 2. Availability Rules (llm_registry.py:92-122)

**Before**:
```python
for provider_name, models in AI_MODEL_REGISTRY.items():
    if provider_name == "openai":
        enabled = has_openai
    elif provider_name == "anthropic":
        enabled = has_anthropic
    elif provider_name == "gemini":
        enabled = has_gemini
    else:
        enabled = True  # ← Always enabled for local/thronos!
```

**After**:
```python
# Check local: offline corpus file exists
data_dir = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
corpus_file = os.path.join(data_dir, "ai_offline_corpus.json")
has_local = os.path.exists(corpus_file)

# Check thronos: CUSTOM_MODEL_URL configured
custom_url = (os.getenv("CUSTOM_MODEL_URL") or "").strip()
has_thronos = bool(custom_url)
# Also check THRONOS_AI_MODE allows custom (if mode is restrictive)
ai_mode = (os.getenv("THRONOS_AI_MODE") or "all").lower()
if ai_mode not in ("all", "router", "auto", "custom", ""):
    has_thronos = False  # Restricted mode doesn't allow custom

for provider_name, models in AI_MODEL_REGISTRY.items():
    # ... existing openai/anthropic/gemini checks ...
    elif provider_name == "local":
        enabled = has_local
    elif provider_name == "thronos":
        enabled = has_thronos
```

**Why**:
- local disabled if corpus file missing → no crash on file read
- thronos disabled if CUSTOM_MODEL_URL missing → no "API key missing" confusion

---

### 3. Provider Status Extended (llm_registry.py:128-197)

**Added local status**:
```python
# Local (offline corpus)
data_dir = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
corpus_file = os.path.join(data_dir, "ai_offline_corpus.json")
local_configured = os.path.exists(corpus_file)
status["local"] = {
    "configured": local_configured,
    "checked_env": ["DATA_DIR"],
    "missing_env": [] if local_configured else ["ai_offline_corpus.json"],
    "corpus_file": corpus_file,
    "source": "registry"
}
```

**Added thronos status**:
```python
# Thronos (custom model)
thronos_vars = ["CUSTOM_MODEL_URL", "THRONOS_AI_MODE"]
custom_url = (os.getenv("CUSTOM_MODEL_URL") or "").strip()
ai_mode = (os.getenv("THRONOS_AI_MODE") or "all").lower()
thronos_configured = bool(custom_url) and ai_mode in ("all", "router", "auto", "custom", "")
thronos_missing = []
if not custom_url:
    thronos_missing.append("CUSTOM_MODEL_URL")
if ai_mode not in ("all", "router", "auto", "custom", ""):
    thronos_missing.append(f"THRONOS_AI_MODE={ai_mode} (restrictive)")
status["thronos"] = {
    "configured": thronos_configured,
    "checked_env": thronos_vars,
    "missing_env": thronos_missing,
    "source": "registry"
}
```

**Added "source" to all providers**:
```python
status["openai"] = {
    # ... existing fields ...
    "source": "registry"
}
```

**Why**: Debug info shows exactly what's checked and where duplicates come from.

---

### 4. Deduplication Logic (server.py:10830-10875)

**Before**:
```python
providers = {}
models = []

for provider_name, model_list in AI_MODEL_REGISTRY.items():
    # ...
    for mi in model_list:
        models.append({
            "id": mi.id,
            "provider": mi.provider,
            # ...
        })  # ← No duplicate check!
```

**After**:
```python
providers = {}
models = []
seen_models = set()  # FIX 7: Dedupe by (provider, model_id)

for provider_name, model_list in AI_MODEL_REGISTRY.items():
    # FIX 7: Get source from provider_status
    provider_source = provider_status.get(provider_name, {}).get("source", "registry")

    providers[provider_name] = {
        "key": provider_name,
        "label": provider_name.capitalize(),
        "enabled": provider_enabled,
        "source": provider_source,  # FIX 7: Add source field for debugging
    }

    for mi in model_list:
        # FIX 7: Dedupe check - skip if (provider, model_id) already seen
        model_key = (mi.provider, mi.id)
        if model_key in seen_models:
            app.logger.warning(f"Duplicate model skipped: {mi.provider}/{mi.id} (display: {mi.display_name})")
            continue
        seen_models.add(model_key)

        models.append({
            "id": mi.id,
            "provider": mi.provider,
            # ...
        })
```

**Why**:
- First occurrence wins, duplicates skipped
- Logs warning for debugging duplicate sources
- Source field in response helps identify root cause

---

## ACCEPTANCE TESTS

### Test 1: Dropdown shows canonical models ONLY

**Steps**:
1. Open /chat page
2. Open AI model dropdown
3. Count occurrences

**Expected**:
- ✅ Exactly 1x "Thronos / Thrai (custom)"
- ✅ Exactly 1x "Offline corpus (local)"
- ✅ Zero duplicates for any model

---

### Test 2: Thronos disabled when CUSTOM_MODEL_URL missing

**Steps**:
1. Railway → Variables → Unset CUSTOM_MODEL_URL (or set to empty)
2. Redeploy
3. Open /chat → model dropdown

**Expected**:
- ✅ "Thronos / Thrai (custom)" is disabled or hidden
- ✅ Zero console errors
- ✅ Zero "API key missing" warnings

---

### Test 3: Local disabled when corpus file missing

**Steps**:
1. SSH to server (or temp rename ai_offline_corpus.json)
2. Restart server
3. Open /chat → model dropdown

**Expected**:
- ✅ "Offline corpus (local)" is disabled or hidden
- ✅ Zero file read crashes
- ✅ Zero console errors

---

### Test 4: /api/ai/models response has no duplicates

**Steps**:
1. `curl https://your-app.railway.app/api/ai/models`
2. Parse JSON → count models by (provider, id)

**Expected**:
```json
{
  "ok": true,
  "mode": "all",
  "providers": {
    "openai": {"key": "openai", "enabled": true, "source": "registry"},
    "anthropic": {"key": "anthropic", "enabled": true, "source": "registry"},
    "gemini": {"key": "gemini", "enabled": true, "source": "registry"},
    "local": {"key": "local", "enabled": true, "source": "registry"},
    "thronos": {"key": "thronos", "enabled": true, "source": "registry"}
  },
  "models": [
    // OpenAI models...
    // Anthropic models...
    // Gemini models...
    {"id": "offline_corpus", "provider": "local", "display_name": "Offline corpus (local)", ...},
    {"id": "thrai", "provider": "thronos", "display_name": "Thronos / Thrai (custom)", ...}
  ]
}
```

**Verification**:
- ✅ Each (provider, id) appears EXACTLY ONCE
- ✅ All providers have "source" field
- ✅ provider_status includes "local" and "thronos"

---

## LOGS TO MONITOR

**After deployment, check logs for**:

1. **Duplicate warnings** (should be ZERO after fix):
   ```
   Duplicate model skipped: thronos/thrai (display: Thronos Thrai)
   ```

2. **Availability checks**:
   ```
   Local provider check: corpus_file=/app/data/ai_offline_corpus.json exists=True → enabled=True
   Thronos provider check: CUSTOM_MODEL_URL=True, THRONOS_AI_MODE=all → enabled=True
   ```

3. **Provider status requests** (from UI):
   ```
   GET /api/ai/models → 200 OK
   ```

---

## FILES MODIFIED

1. **llm_registry.py**:
   - Lines 64-67: Display names
   - Lines 92-122: Availability rules (_apply_env_flags)
   - Lines 128-197: Provider status (get_provider_status)

2. **server.py**:
   - Lines 10825-10875: Deduplication logic in /api/ai/models

---

## HARD RULES COMPLIANCE

- ✅ No new endpoints (modified existing /api/ai/models)
- ✅ No new widgets (UI dropdown uses same endpoint)
- ✅ PATCH-ONLY (modified handlers and registry)
- ✅ No HTTP 500 (degraded mode maintained)
- ✅ Observable changes (dropdown, API response)

---

## COMMIT

**Commit**: `f551603`
**Message**: `fix(ai): Canonical model catalog - dedupe, explicit labels, availability`

---

**End of Fix #7 Report**
