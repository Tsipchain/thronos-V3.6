# PYTHEIA Full Report — Thronos V3.6

> **Scope:** Front-end ↔ server mapping, API coverage, operational status, and wallet modal flows.
> **Source of truth:** Codebase inspection only (no runtime secrets or external calls).

---

## 1) System Overview

- The main application is a monolithic Flask server in `server.py` that renders HTML templates and exposes a large API surface area.
- The AI subsystem routes to OpenAI/Anthropic/Gemini via `ai/llm_router.py` and respects `THRONOS_AI_MODE`.
- Health monitoring is provided by `pytheia_worker.py`, which checks critical endpoints and can post advice to governance.

---

## 2) Front-End Pages and Connected APIs

### 2.1 Chat (`/chat`)

**Front-end:** `templates/chat.html`

**APIs called by the UI:**
- `/api/chat`
- `/api/chat/sessions`
- `/api/chat/session/<id>`
- `/api/chat/session/<id>/messages`
- `/api/ai/wallet`
- `/api/ai/telemetry`
- `/api/ai_models`
- `/api/ai/providers/health`
- `/api/ai/files/upload`
- `/api/ai/feedback`

**Back-end handlers:**
- `/chat` renders `chat.html` (passes wallet cookie).
- `/api/chat` unified AI chat endpoint (sessions + credits + offline corpus).
- `/api/chat/*` handles session create/rename/delete/list for guest or wallet.

**Status notes:**
- **OK** when `ai_agent` is available and at least one model is callable.
- **Fails** with 503 if `ai_agent` is unavailable.
- **Degraded** if providers lack API keys: `/api/ai_models` returns disabled models (never 500).

---

### 2.2 Architect (`/architect`)

**Front-end:** `templates/architect.html`

**APIs called by the UI:**
- `/api/ai_blueprints`
- `/api/architect_generate`
- `/api/ai_models`

**Back-end handlers:**
- `/architect` renders `architect.html`.
- `/api/ai_blueprints` reads `data/ai_blueprints`.
- `/api/architect_generate` builds a full project output, writes files, and charges THR.

**Status notes:**
- **OK** if `ai_agent` exists, a blueprint file exists, and a wallet is provided.
- **Fails** with 400 if wallet missing.
- **Fails** with 503 if `ai_agent` is unavailable.

---

### 2.3 Bridge (`/bridge`)

**Front-end:** `templates/bridge.html`

**Back-end APIs:**
- `/api/bridge/status`
- `/api/bridge/stats`
- `/api/bridge/txs`
- `/api/bridge/history/<address>`
- `/api/bridge/burn`
- `/api/bridge/deposit`

**Status notes:**
- **OK** for status/stats if ledgers exist.
- **Degraded** data if watchers/ledgers are not populated.

---

### 2.4 Wallet Viewer (`/wallet`)

**Front-end:** `templates/wallet_viewer.html`

**Back-end APIs used:**
- `/wallet_data/<thr_addr>`
- `/api/tx_feed?wallet=...`
- `/api/wallet/qr/<thr_addr>`
- `/api/wallet/audio/<thr_addr>`

**Status notes:**
- **OK** for inline history view, wallet QR/audio.

**PYTHEIA mismatch:**
- PYTHEIA checks `/wallet_viewer`, but the server route is `/wallet`. This can cause false “down” reports.

---

### 2.5 Courses (`/courses`) and Train‑to‑Earn (`/train2earn`)

**Front-end:** `templates/courses.html`, `templates/course_detail.html`, `templates/train2earn.html`

**Back-end APIs:**
- `/api/v1/courses` (list/create)
- `/api/v1/courses/<id>` (details)
- `/api/v1/courses/<id>/enroll`
- `/api/v1/courses/<id>/complete`
- `/api/v1/train2earn/contribute`

**Status notes:**
- **OK** with valid pledged wallet + auth hash.
- **Fails** with 400/403/404 if auth or pledge data missing.

---

### 2.6 Music (`/music`)

**Front-end:** `templates/music.html`

**Back-end APIs:**
- `/api/music/status`

**Status notes:**
- **OK**; endpoint is tolerant and returns "no tracks" if registry empty.

---

### 2.7 NFT + Governance + Explorer

**Front-end:** `templates/nft.html`, `templates/governance.html`, `templates/explorer.html`

**Back-end APIs:**
- `/api/v1/nfts`, `/api/v1/nfts/mint`, `/api/v1/nfts/buy`
- `/api/v1/governance/proposals`, `/api/v1/governance/vote`, `/api/v1/governance/finalize`
- `/api/governance/pytheia/advice`

**Status notes:**
- **OK** for JSON-backed registry flows.
- **Not on‑chain**; stored in local JSON files.

---

## 3) Core API Families

### 3.1 Network / Blockchain State

**Routes:**
- `/api/health`
- `/api/network_stats`
- `/api/network_live`
- `/api/mempool`
- `/api/blocks`
- `/api/tx_feed`
- `/api/transactions`
- `/api/routes`

**Purpose:** Read-only chain status, stats, and diagnostics.

---

### 3.2 Wallet / Tokens / Transfers

**Routes:**
- `/api/wallet/send`
- `/api/tokens/*` (create, transfer, mint, burn, holders, stats)
- `/api/send_token`
- `/send_thr`

**Important behavior:**
- If `NODE_ROLE=replica`, write methods (POST/PUT/PATCH/DELETE) are blocked (403), except heartbeat.

---

### 3.3 AI Models & Provider Health

**Routes:**
- `/api/ai_models`
- `/api/ai/providers/health`
- `/api/ai/provider_status`

**Important behavior:**
- `/api/ai_models` always returns 200 with degraded fallback if providers are unavailable.

---

### 3.4 Governance / PYTHEIA Advice

**Routes:**
- `/api/v1/governance/proposals`
- `/api/v1/governance/vote`
- `/api/governance/pytheia/advice`

**Purpose:** local DAO proposals/votes and PYTHEIA advice posting.

---

## 4) AI Subsystem Notes

- Routing is defined in `ai/llm_router.py`. Mode is controlled by `THRONOS_AI_MODE`.
- `/api/thrai/ask` requires `ANTHROPIC_API_KEY` or returns 500.
- `/api/chat` and `/api/ai/providers/chat` can fail if `ai_agent` is unavailable.

---

## 5) PYTHEIA Worker Notes

- Health checks include `/chat`, `/architect`, `/api/ai/models`, `/api/bridge/status`, `/tokens`, `/nft`, `/governance`, `/wallet_viewer`.
- Can auto-post advice to `/api/governance/pytheia/advice` based on thresholds.

**Mismatch:** `/wallet_viewer` health check, but main server uses `/wallet`.

---

## 6) Wallet Modals (Widget) — Full Mapping

> **The modals exist in the embeddable widget** (`/widget/wallet` → `templates/wallet_widget.html`).
> The full wallet page (`/wallet`) uses inline history (no modals).

### 6.1 Token Info Modal

**DOM:** `#tokenInfoModal`

**Open/Close:**
- `showTokenInfo(token)` opens and populates data.
- `closeTokenInfo()` closes.

**Data source:**
- `/api/wallet/tokens/<thr_addr>?show_zero=...`

**Fields shown:**
- symbol, name, balance, decimals, value in THR, token color, logo.

---

### 6.2 History Modal

**DOM:** `#historyModal`

**Open/Close:**
- `openHistoryModal()` → fetch `/wallet_data/<addr>` → render history.
- `closeHistoryModal()` closes and resets.

**Filters:**
- `all`, `thr`, `tokens`, `swaps`, `l2e`, `ai_credits`, `architect`, `bridge`, `iot`.
- Token sub-filters are shown when `tokens` is active.

**Data source:**
- `/wallet_data/<thr_addr>` — server enriches txs with category_label, direction, decimals, etc.

---

### 6.3 Send Modal

**DOM:** `#sendModal`

**Open/Close:**
- `openSendModal()` populates token dropdown.
- `closeSendModal()` closes and cancels polling.

**Submit:**
- `handleSend()` POSTs to `/send_tokens`.
- Then polls `/api/tx/status` for confirmations.

**Important issue:**
- No `/send_tokens` route exists in `server.py`. This modal likely fails in current backend.

---

### 6.4 Bridge Modal

**DOM:** `#bridgeModal`

**Open/Close:**
- `openBridgeModal()` loads deposit address.
- `closeBridgeModal()` closes modal.

**Data source:**
- `/api/bridge/deposit?wallet=...`

---

## 7) Key Findings (for Governance Vote)

1) **Wallet viewer health check mismatch**
   - PYTHEIA uses `/wallet_viewer`, server uses `/wallet`.
2) **Wallet widget send modal uses missing route**
   - `/send_tokens` is referenced in the widget, but no backend route exists.
3) **AI availability depends on provider keys and `ai_agent`**
   - Missing keys → degraded models, missing `ai_agent` → 503 on chat.

---

## 8) Suggested Practical Tests (no execution)

- `python3 server.py`
- `curl http://localhost:5000/chat`
- `curl http://localhost:5000/api/ai_models`
- `curl http://localhost:5000/api/bridge/status`
- `curl http://localhost:5000/wallet_data/<THR_ADDR>`
- `curl http://localhost:5000/api/tx/status?tx_id=<id>`

---

**End of Report**
