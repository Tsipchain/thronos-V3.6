# PATCH PLAN A: Implement Degraded Mode for /api/ai/models

**Plan ID**: PATCH-2026-A-001
**Implements**: GOV-2026-A-001 Option A
**Author**: PYTHEIA Node
**Status**: Ready for Implementation

## Changes Required

### 1. Backend: server.py

**File**: `server.py`
**Lines**: 10387-10459
**Action**: Wrap in comprehensive error handling

```python
@app.route("/api/ai/models", methods=["GET"])
def api_ai_models():
    """
    Returns unified model list with degraded mode fallback.
    NEVER returns 500 - always returns 200 with appropriate payload.
    """
    try:
        mode = (os.getenv("THRONOS_AI_MODE") or "all").lower()
        if mode in ("", "router", "auto"):
            mode = "all"

        # Attempt to load base config
        try:
            base_cfg = base_model_config() or {}
            enabled_providers = set((base_cfg.get("providers") or {}).keys())
        except Exception as cfg_err:
            app.logger.warning(f"base_model_config failed: {cfg_err}")
            # Fallback to curated models
            return jsonify({
                "ok": False,
                "mode": "degraded",
                "error_code": "PROVIDER_CONFIG_FAILED",
                "error_message": "Provider configuration unavailable",
                "providers": {},
                "models": _get_fallback_models(),
                "fallback_active": True
            }), 200

        # Attempt to load model stats
        try:
            model_stats = compute_model_stats() or {}
        except Exception as stats_err:
            app.logger.warning(f"compute_model_stats failed: {stats_err}")
            model_stats = {}

        # Build model list...
        # (existing logic continues)

        payload = {
            "ok": True,
            "mode": mode,
            "providers": providers,
            "models": models,
            "fallback_active": False
        }
        return jsonify(payload), 200

    except Exception as exc:
        app.logger.exception("api_ai_models catastrophic error")
        # Last resort fallback
        return jsonify({
            "ok": False,
            "mode": "degraded",
            "error_code": "CATASTROPHIC_FAILURE",
            "error_message": str(exc),
            "providers": {},
            "models": _get_fallback_models(),
            "fallback_active": True
        }), 200  # ← ALWAYS 200


def _get_fallback_models():
    """Return minimal curated model list for degraded mode."""
    from ai_models_config import CURATED_MODELS
    fallback = []
    for provider, data in CURATED_MODELS.items():
        for model in data.get("models", []):
            fallback.append({
                "id": model["id"],
                "provider": provider,
                "label": model["label"],
                "enabled": False,  # Mark as disabled in degraded mode
                "degraded": True,
                "tier": "fallback"
            })
    return fallback
```

### 2. Frontend: templates/chat.html

**File**: `templates/chat.html`
**Lines**: 1759-1835
**Action**: Add degraded mode detection

```javascript
async function loadModels() {
  if (!modelSelectEl) return;

  const previousValue = modelSelectEl.value || "auto";
  modelSelectEl.innerHTML = "";
  const autoOpt = document.createElement("option");
  autoOpt.value = "auto";
  autoOpt.textContent = "Auto (Thronos chooses)";
  modelSelectEl.appendChild(autoOpt);

  try {
    const res = await fetch(API_MODELS);

    // Always attempt to parse JSON, even on error status
    let data = null;
    try {
      data = await res.json();
    } catch (e) {
      console.error("Failed to parse models response", e);
      showDegradedModeNotice("Models API unreachable");
      return;
    }

    // Check for degraded mode
    if (data.ok === false || data.fallback_active === true) {
      showDegradedModeNotice(data.error_message || "Provider configuration unavailable");
      // Still populate fallback models
      populateModelsFromData(data);
      return;
    }

    // Normal mode
    hideDegradedModeNotice();
    populateModelsFromData(data);

  } catch (e) {
    console.warn("model load failed", e);
    showDegradedModeNotice("Failed to load models");
  }
}

function showDegradedModeNotice(message) {
  const noticeId = "degraded-mode-notice";
  let notice = document.getElementById(noticeId);
  if (!notice) {
    notice = document.createElement("div");
    notice.id = noticeId;
    notice.style.cssText = "background: rgba(255, 75, 129, 0.15); border: 1px solid var(--danger); border-radius: 12px; padding: 10px 14px; margin: 8px 0; font-size: 12px; color: var(--danger);";
    document.querySelector(".chat-input-block").insertAdjacentElement("afterbegin", notice);
  }
  notice.innerHTML = `⚠️ <strong>Degraded Mode:</strong> ${message}. AUTO routing still available.`;
}

function hideDegradedModeNotice() {
  const notice = document.getElementById("degraded-mode-notice");
  if (notice) notice.remove();
}

function populateModelsFromData(data) {
  // Extract model population logic into separate function
  const providers = data.providers || {};
  const models = data.models || [];
  const providerOrder = ["openai", "anthropic", "gemini", "local", "thronos"];
  // ... (existing population logic)
}
```

### 3. Frontend: templates/architect.html

**File**: `templates/architect.html`
**Lines**: 505-551
**Action**: Similar degraded mode handling

```javascript
async function loadModels() {
  const modelSel = $("model");
  const previousValue = modelSel.value || "auto";
  modelSel.innerHTML = '<option value="auto">🔀 Auto (Pythia chooses)</option>';

  try {
    const res = await fetch("/api/ai/models");
    let data = null;
    try {
      data = await res.json();
    } catch (e) {
      console.error("Models API parse error", e);
      setStatus(false, "Models unavailable");
      return;
    }

    if (data.ok === false || data.fallback_active === true) {
      setStatus(false, data.error_message || "Degraded mode");
      // Show notice in UI
      const statusPill = document.getElementById("statusPill");
      if (statusPill) {
        statusPill.innerHTML = '<div class="pill-dot" style="background: var(--danger);"></div><span>Degraded Mode</span>';
      }
    }

    // Populate models (works in both normal and degraded mode)
    const models = data.models || [];
    models.forEach(m => {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = `${m.emoji || '🤖'} ${m.label || m.id}`;
      if (m.degraded || !m.enabled) {
        opt.disabled = true;
        opt.textContent += ' (unavailable)';
      }
      modelSel.appendChild(opt);
    });

    if (previousValue && Array.from(modelSel.options).some(o => o.value === previousValue)) {
      modelSel.value = previousValue;
    }
  } catch (e) {
    console.warn("Failed to load models:", e);
    setStatus(false, "Models unavailable");
  }
}
```

## Testing Plan

### Test Case 1: Normal Operation
1. Ensure all provider API keys are set
2. Access `/chat` and `/architect`
3. Verify model dropdown shows all available models
4. Verify no degraded mode notice

### Test Case 2: Missing API Keys
1. Remove OPENAI_API_KEY from environment
2. Access `/chat` and `/architect`
3. Verify HTTP 200 response from `/api/ai/models`
4. Verify degraded mode notice appears
5. Verify AUTO option still available
6. Verify fallback models shown but disabled

### Test Case 3: Complete Provider Failure
1. Corrupt `ai_models_config.py`
2. Access `/chat` and `/architect`
3. Verify HTTP 200 response
4. Verify catastrophic fallback activates
5. Verify pages don't crash
6. Verify AUTO still works

### Test Case 4: Stats Ledger Corruption
1. Create malformed `ai_interaction_ledger.json`
2. Verify stats fail gracefully
3. Verify models still load (without stats)

## Rollback Plan

If issues occur:
1. Revert server.py changes
2. Keep frontend changes (they're defensive)
3. Monitor logs for 24h
4. Re-attempt with adjusted error handling

## Success Criteria

- [ ] `/api/ai/models` NEVER returns 500
- [ ] `/chat` and `/architect` never show blank pages
- [ ] Degraded mode clearly communicated to users
- [ ] AUTO routing always available
- [ ] All error paths logged properly
- [ ] Users can still interact with AI in degraded mode

## Deployment Steps

1. Backup current server.py
2. Apply backend changes
3. Apply frontend changes
4. Restart server
5. Test all paths
6. Monitor logs
7. Post PYTHEIA_ADVICE to DAO
