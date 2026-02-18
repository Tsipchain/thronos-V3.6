# Thronos FlexCo 2026 — Operating Playbook

**Entity**: Thronos FlexCo e.U. (Austria)
**Version**: 2026.2
**Classification**: Internal / Investor-Ready
**Last Updated**: 2026-02-15

---

## Table of Contents

1. [A — Architecture & Service Inventory](#a--architecture--service-inventory)
2. [B — Security & Threat Model](#b--security--threat-model)
3. [C — Ops Runbook](#c--ops-runbook)
4. [D — Product Packaging (German-First)](#d--product-packaging-german-first)
5. [E — 2026 Roadmap & Grant Narrative](#e--2026-roadmap--grant-narrative)
6. [F — Driver Platform & Autopilot Telemetry](#f--driver-platform--autopilot-telemetry)

---

## A — Architecture & Service Inventory

### A.1 Node Topology

| Node | Role | Platform | URL | Data Store |
|:-----|:-----|:---------|:----|:-----------|
| Node 1 (Master) | Chain Writer, API, Scheduler, AI Proxy | Railway | `thrchain.up.railway.app` | `ledger.sqlite3` (RW) |
| Node 2 (Replica) | Read-Only, BTC Watcher, Cross-Chain | Railway | `node-2.up.railway.app` | `ledger.sqlite3` (RO) |
| Node 3 (CDN) | Static Frontend, Wallet Widget | Vercel | `thronoschain.org` | None (static) |
| Node 4 (AI Core) | LLM Inference, Pytheia, Trading | Render | `thronos-v3-6.onrender.com` | `ai_sessions.db` |

### A.2 Subdomain → Repo → Data Store Map

| Subdomain | Repo | Data Store | Source-of-Truth |
|:----------|:-----|:-----------|:----------------|
| `thrchain.up.railway.app` | `Tsipchain/thronos-V3.6` | `ledger.sqlite3` | Node 1 (master writer) |
| `node-2.up.railway.app` | `Tsipchain/thronos-V3.6` | `ledger.sqlite3` (replicated) | Node 1 via sync |
| `thronoschain.org` | `Tsipchain/thronos-portal` | — | Git (Vercel auto-deploy) |
| `thronos-v3-6.onrender.com` | `Tsipchain/thronos-V3.6` | `ai_sessions.db` | Node 4 local |
| `btc-api.thronoschain.org` | `Tsipchain/thronos-V3.6` | Blockstream + local cache | External BTC RPCs |
| `driverinteligent.thronoschain.org` | `Tsipchain/driver-platform` | `driver_service.db` (Node-2 volume) | driver-platform public URL (CNAME → Railway); events: driver_telemetry, voice_message_emitted, safe_driving_score |
| `driver-platform-production.up.railway.app` | `Tsipchain/driver-platform` | `driver_service.db` (Node-2 volume) | driver-platform Railway origin (internal) |

### A.3 Data Ownership & Source-of-Truth

| Data Domain | Source-of-Truth | Replication | Notes |
|:------------|:----------------|:------------|:------|
| Blockchain ledger (blocks, TXs, balances) | Node 1 `ledger.sqlite3` | → Node 2 (read-only sync) | Node 1 is sole writer |
| AI sessions & chat history | Node 4 `ai_sessions.db` | None (local only) | Proxied via Node 1 |
| BTC bridge state | Node 1 `ledger.sqlite3` | Watcher on Node 2 writes via API to Node 1 | Node 2 detects, Node 1 writes |
| Music tracks / artist profiles | Node 1 `ledger.sqlite3` | — | Uploads stored on Node 1 filesystem |
| VerifyID device registry | Node 1 `ledger.sqlite3` | — | Challenge/response lifecycle |
| Frontend assets (HTML, JS, CSS) | Git → Vercel | Auto-deploy on push | CDN-cached globally |
| Custom tokens & EVM contracts | Node 1 `ledger.sqlite3` | — | On-chain via Node 1 |
| IoT telemetry & parking | Node 1 `ledger.sqlite3` | — | Device → API → DB |
| Driver telemetry (raw) | driver-platform `driver_service.db` (Node-2 volume) | Export job → AI Core | PII stripped before export; 90-day retention on Node-2 |
| Driver telemetry (features) | AI Core (Node 4) feature store / training bucket | — | Pseudonymized; ML-ready; source: driver-platform + music/IoT |
| VerifyID driver identity | VerifyID Postgres (separate Railway service) | Identity bridge → AI Core pseudonymous key | Canonical identity; phone/email never leave VerifyID Postgres |

### A.4 Replication Rules

1. **Master → Replica**: Node 2 syncs ledger from Node 1 via `bootstrap.json` heartbeat (every 30 s).
2. **Write prohibition**: `READ_ONLY=1` enforced on Node 2; any write attempt returns `403`.
3. **AI proxy**: Node 1 proxies `/api/ai/*` to Node 4 (`AI_CORE_URL`). If Node 4 is down, Node 1 falls back to local provider keys.
4. **Static deploy**: Vercel auto-deploys on `main` push. No runtime state.
5. **Cross-chain RPCs**: Only Node 1 holds full RPC keys (BTC, BSC, ETH, XRP, SOL). Node 2 holds BTC-watcher subset only.

### A.5 Offline / Online Node Topology

```
┌───────────────── ONLINE ZONE ──────────────────┐
│                                                  │
│  [Node 1 Master]──API proxy──▶[Node 4 AI Core]  │
│       │                                          │
│       │ heartbeat (30s)                          │
│       ▼                                          │
│  [Node 2 Replica]                                │
│                                                  │
│  [Node 3 Vercel CDN]  (static, no state)         │
│                                                  │
└──────────────────────────────────────────────────┘

┌───────────── OFFLINE / SURVIVAL ZONE ────────────┐
│                                                   │
│  [LoRa Antenna] ──15 km──▶ [IoT Miners]          │
│       │                                           │
│  [Peiko X9] ──Bluetooth──▶ [Audio-Fi / WAV TX]   │
│       │                                           │
│  [Solar Controller] ──RS485──▶ [G1 Mini / Ryzen]  │
│       │                                           │
│  [USB Block Erupters] ──USB──▶ [SHA256 PoW]      │
│                                                   │
│  Modes: Full | Eco | Survival (battery-aware)     │
│                                                   │
└───────────────────────────────────────────────────┘
```

---

## B — Security & Threat Model

### B.1 Wallet Security

| Threat | Control | Status |
|:-------|:--------|:-------|
| Seed phrase theft | BIP39/BIP44 HD derivation; mnemonic encrypted at rest (AES-256); Keychain/SecureEnclave on mobile | Active |
| Hot wallet compromise | Hot wallet holds minimal balance; BTC Pledge Vault is separate multisig | Active |
| Replay attacks | Nonce per TX; chain ID in signature | Active |
| Brute-force on Stratum port | Rate limiting + VerifyID attestation for miners | Active |

### B.2 VerifyID Threats

| Threat | Control |
|:-------|:--------|
| Challenge replay | 300 s TTL on HMAC challenges; single-use tokens |
| Device spoofing | SHA256 hardware attestation from USB Block Erupters |
| Admin bypass abuse | `ADMIN_SECRET` required; whitelist audit-logged |
| JWT forgery | HMAC-SHA256 signing with `JWT_SECRET`; rotation policy quarterly |

### B.3 Cross-Chain Event Bus & BTC Bridge

| Threat | Control |
|:-------|:--------|
| Phantom deposits | Watcher confirms ≥ 3 BTC confirmations via Blockstream + independent RPC |
| Double-spend on bridge | Lock-mint-burn pattern; minting only after finality |
| RPC endpoint poisoning | Fallback chain: Blockstream API → local BTC RPC → manual admin approval |
| Watcher downtime | Node 2 heartbeat monitored by Pytheia; alert after 3 consecutive failures |

### B.4 Peiko X9 Webhook / Audio Bridge

| Threat | Control |
|:-------|:--------|
| Bluetooth MITM | End-to-end encryption on payload; AES-256 pre-shared key |
| Audio injection | CRC-32 checksum embedded in WAV; rejected on mismatch |
| Jamming / DoS | SDR spectrum monitor (RTL-SDR v4) detects anomalous RF; auto-failover to LoRa |

### B.5 Admin Console

| Threat | Control |
|:-------|:--------|
| Unauthorized access | `ADMIN_SECRET` header + IP allowlist (configurable) |
| Privilege escalation | Role-based JWT (admin/operator/viewer); least privilege |
| Audit gap | All admin actions logged to `admin_audit_log` table with timestamp, actor, action |

### B.6 Secrets Hygiene

| Secret | Storage | Rotation |
|:-------|:--------|:---------|
| `ADMIN_SECRET` | Railway/Render env vars | Quarterly |
| `JWT_SECRET` | Railway/Render env vars | Quarterly |
| OpenAI / Anthropic / Google API keys | Railway env vars (Node 1 only) | On compromise |
| BTC/BSC/ETH RPC URLs | Railway env vars (Node 1 only) | Static (provider-managed) |
| Stripe secret key | Railway env vars | Annually |
| `CHAIN_PRIVATE_KEY` | Railway env vars | On compromise |

**Rules**:
- Never commit secrets to Git (`.env` in `.gitignore`).
- No secrets on Node 3 (static CDN).
- Node 2 holds only `ADMIN_SECRET` + BTC watcher subset.

### B.7 Key Custody (Multisig / Quorum)

- **Treasury Wallet**: 2-of-3 multisig (founder + CTO + Pytheia AI signer).
- **BTC Pledge Vault**: Separate cold wallet; manual release only.
- **Quorum Consensus**: BFT with BLS signatures; ≥ 2/3 validator votes to finalize block.
- **Emergency**: Founder holds offline recovery seed in bank safe deposit (Austria).

### B.8 Audit Logging

All critical events written to `admin_audit_log`:
- Wallet creation / large transfers (> 1000 THR)
- Bridge mint / burn operations
- VerifyID registrations
- Admin whitelist changes
- AI model switches
- Pytheia autonomous actions

Retention: 365 days minimum. Export: JSON via `/api/admin/audit-export`.

---

## C — Ops Runbook

### C.1 DNS / CNAME Rules

| Domain | Type | Target | Provider |
|:-------|:-----|:-------|:---------|
| `thronoschain.org` | A (Apex) | Vercel IP | Vercel |
| `www.thronoschain.org` | CNAME | `cname.vercel-dns.com` | Vercel |
| `btc-api.thronoschain.org` | CNAME | Railway custom domain | Railway |
| `driverinteligent.thronoschain.org` | CNAME | `driver-platform-production.up.railway.app` | Railway |
| `thrchain.up.railway.app` | Platform | Railway auto | Railway |
| `thronos-v3-6.onrender.com` | Platform | Render auto | Render |

**Adding a new custom domain**:
1. Add CNAME record at DNS provider → platform target.
2. Platform: Railway → `Settings > Custom Domains > Add`; Render → `Settings > Custom Domains`.
3. Vercel: `vercel domains add <domain>` via CLI.
4. Wait for SSL provisioning (Let's Encrypt, usually < 5 min).
5. Update `thronos_registry.yaml` → `domains` section.
6. Run `python scripts/generate_bootstrap.py` to regenerate portal config.

### C.2 Environment Variables Checklist

**Node 1 (Master) — Required**:
```
NODE_ROLE=master
NODE_NAME=node1-master
THRONOS_ENV=production
READ_ONLY=0
IS_LEADER=1
SCHEDULER_ENABLED=1
ENABLE_CHAIN=1
DOMAIN_URL=https://thrchain.up.railway.app
API_BASE_URL=https://thrchain.up.railway.app
LEADER_URL=https://thrchain.up.railway.app
REPLICA_EXTERNAL_URL=https://node-2.up.railway.app
THRONOS_AI_MODE=proxy
AI_CORE_URL=https://thronos-v3-6.onrender.com
ADMIN_SECRET=<secret>
JWT_SECRET=<secret>
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
BTC_RPC_URL=...
BSC_RPC_URL=https://bsc-dataseed.binance.org
ETH_RPC_URL=...
XRP_RPC_URL=https://s1.ripple.com:51234
SOL_RPC_URL=https://api.mainnet-beta.solana.com
STRIPE_SECRET_KEY=sk_live_...
```

**Node 2 (Replica) — Required**:
```
NODE_ROLE=replica
READ_ONLY=1
SCHEDULER_ENABLED=0
ADMIN_SECRET=<same-secret>
LEADER_URL=https://thrchain.up.railway.app
BTC_RPC_URL=...
```

**Node 4 (AI Core) — Required**:
```
NODE_ROLE=ai-core
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
ADMIN_SECRET=<same-secret>
```

### C.3 Backup & Restore

**Daily automated backup** (via scheduler on Node 1):
```bash
# Backup ledger
sqlite3 /app/data/ledger.sqlite3 ".backup '/app/backups/ledger_$(date +%Y%m%d).sqlite3'"

# Backup AI sessions (Node 4)
sqlite3 /app/data/ai_sessions.db ".backup '/app/backups/ai_sessions_$(date +%Y%m%d).db'"
```

**Restore procedure**:
1. Stop scheduler: set `SCHEDULER_ENABLED=0` on Node 1, redeploy.
2. Copy backup file to `/app/data/ledger.sqlite3`.
3. Re-enable scheduler, redeploy.
4. Verify via `/api/block/latest` — block height should match pre-backup.

**Off-site**: Weekly export to encrypted archive (GPG) on founder's secure storage.

### C.4 Incident Playbook

#### Severity Levels

| Level | Definition | Response Time | Escalation |
|:------|:-----------|:--------------|:-----------|
| SEV-1 | Chain halted, bridge compromised, data loss | 15 min | Founder + CTO immediately |
| SEV-2 | Service degraded (Node down, slow API) | 1 hour | On-call engineer |
| SEV-3 | Minor issue (UI bug, non-critical endpoint) | 24 hours | Next business day |

#### Common Incidents

**Node 1 (Master) Down**:
1. Check Railway dashboard → deployment logs.
2. If OOM: increase memory in Railway settings.
3. If crash loop: check `start.sh` and recent commits.
4. If Railway outage: activate read-mode on Node 2 with `IS_LEADER=1` (emergency failover).
5. Post-mortem within 48 hours.

**BTC Bridge Watcher Stalled**:
1. Check Node 2 logs for `btc_pledge_watcher` errors.
2. Verify BTC RPC endpoint is reachable.
3. Fallback: manually verify via Blockstream.info and admin-approve pledges.

**Render (AI Core) Cold Start**:
1. Render free tier spins down after inactivity.
2. Node 1 auto-falls-back to local AI provider keys.
3. Ping `https://thronos-v3-6.onrender.com/api/health` to wake.
4. Consider upgrading to Render paid plan for zero-downtime.

**Vercel Deploy Failure**:
1. Check Vercel dashboard → build logs.
2. Static site — no runtime risk; previous deploy stays live.
3. Fix build error in repo; push again.

### C.5 Release Discipline

1. **Branch model**: `main` (production), feature branches (`feature/*`), hotfix branches (`hotfix/*`).
2. **PR required**: All changes via Pull Request; minimum 1 review (founder or CTO).
3. **CI checks**: Lint + basic tests must pass before merge.
4. **Deploy**: Railway and Render auto-deploy on merge to `main`. Vercel auto-deploys portal repo.
5. **Rollback**: Railway → "Rollback to previous deployment" button. Render → same. Vercel → `vercel rollback`.
6. **Changelog**: Update `CHANGELOG.md` with version, date, changes.
7. **Registry update**: After adding/removing any service, update `thronos_registry.yaml` and regenerate `bootstrap.json`.

---

## D — Product Packaging (German-First)

### D.1 Three Commercial Bundles

#### Bundle 1: VerifyID Enterprise

**Target**: Logistics, fleet management, KYC-light compliance.

| Feature | Description |
|:--------|:-----------|
| Device registration | Hardware attestation via SHA256 ASIC proof |
| Challenge/response auth | Cryptographic device identity, 5-min TTL |
| API integration | RESTful API for enterprise identity workflows |
| Audit trail | Immutable on-chain log of all verifications |
| Multi-language UI | DE, EN, EL, ES, FR, JA, ZH |

**Pricing Skeleton**:
- Starter: €99/mo — up to 100 devices, 10k verifications/mo
- Business: €499/mo — up to 1,000 devices, 100k verifications/mo
- Enterprise: Custom — unlimited, SLA, dedicated support

**Pilot KPIs**: 3 paying customers in AT/DACH within 6 months; < 200 ms avg verification time; 99.5% uptime.

#### Bundle 2: Driver Telemetry & T2E (Train-to-Earn)

**Target**: Fleet operators, autonomous driving R&D, insurance telematics.

| Feature | Description |
|:--------|:-----------|
| GPS telemetry ingestion | Real-time route data with on-device hashing |
| Privacy-by-design | No raw GPS stored; proof-of-route only |
| T2E rewards | THR token rewards for quality driving data |
| AI training pipeline | Aggregated telemetry feeds autonomous driving models |
| Driver dashboard | Real-time stats, earnings, route quality score |

**Pricing Skeleton**:
- Pilot: €199/mo — up to 50 vehicles
- Fleet: €799/mo — up to 500 vehicles, priority data pipeline
- Enterprise: Custom — white-label, on-prem option

**Pilot KPIs**: 1 fleet operator (20+ vehicles) in AT within 6 months; 10,000 km of telemetry data; measurable model improvement.

#### Bundle 3: IoT Telemetry + AI L2 Intelligence

**Target**: Smart city, parking, environmental monitoring, industrial IoT.

| Feature | Description |
|:--------|:-----------|
| IoT device onboarding | VerifyID-based device registration |
| Sensor data pipeline | LoRa / WiFi / Bluetooth telemetry ingestion |
| AI L2 processing | On-chain AI inference for anomaly detection |
| Smart parking | Real-time parking availability + THR payments |
| Mining rewards | IoT devices earn THR via T2E data contributions |
| Off-grid capability | LoRa + solar for infrastructure-independent operation |

**Pricing Skeleton**:
- City Pilot: €299/mo — up to 200 IoT nodes, basic AI
- City Pro: €999/mo — up to 2,000 nodes, full AI L2
- National: Custom — unlimited, government SLA

**Pilot KPIs**: 1 smart parking pilot (50+ sensors) in Vienna/Graz; sub-second occupancy detection; positive ROI within 12 months.

### D.2 Compliance Notes (AML/KYC Boundaries)

- **Thronos is NOT a bank or payment institution**. THR is a utility token within the ecosystem.
- **VerifyID is NOT a KYC provider** in the regulated sense. It provides device identity and hardware attestation. Human identity verification is delegated to certified partners if required.
- **AML boundary**: Fiat on-ramp (Stripe) handles AML/KYC. Thronos does not custody fiat.
- **BTC Bridge**: Pledge system requires user to self-declare; Thronos does not hold or transmit BTC on behalf of users (non-custodial).
- **GDPR**: No raw personal data stored on-chain. GPS data hashed on-device. Right-to-erasure applies to off-chain databases only.
- **Austrian regulatory**: FlexCo e.U. registered in Austria. Token utility classification under MiCA framework (utility token, not e-money).

---

## E — 2026 Roadmap & Grant Narrative

### E.1 Milestones (Q2–Q4 2026)

#### Q2 2026 (April–June)
- [ ] Complete LoRa antenna integration (15 km off-grid mesh)
- [ ] Solar energy controller (Victron/RS485) production-ready
- [ ] Android APK signed release + Play Store submission
- [ ] VerifyID Enterprise Bundle — beta launch with 1 DACH customer
- [ ] Automated BTC ↔ WBTC bridge (multisig)
- [ ] Driver Telemetry pilot — 1 fleet operator onboarded

#### Q3 2026 (July–September)
- [ ] iOS native wallet (App Store submission)
- [ ] AI Model Marketplace — on-chain model trading with THR
- [ ] Lightning Network integration for micropayments
- [ ] IoT Smart City pilot — Vienna/Graz parking
- [ ] SDR spectrum monitor (RTL-SDR v4) field-tested
- [ ] Peiko X9 audio bridge production-ready

#### Q4 2026 (October–December)
- [ ] API Credits System — pay for AI calls with THR
- [ ] On-chain model attestations
- [ ] Decentralized inference network (multi-node)
- [ ] AI Safety & Governance DAO launch
- [ ] 3 paying enterprise customers (VerifyID + Telemetry)
- [ ] FFG grant milestone report

### E.2 Grant-Fit Narrative (AWS / FFG)

**Thronos is an Austrian-built, privacy-first blockchain OS** that creates value at the intersection of AI, IoT, and decentralized identity — three pillars of Austria's digital transformation strategy.

**Why Austria**: Thronos FlexCo is registered in Austria, employs Austrian talent, and targets DACH-first use cases (fleet management, smart city, industrial IoT). Revenue stays in Austria.

**Innovation**: Thronos is unique in combining SHA256 blockchain with off-grid survival protocols (audio, radio, solar), AI-powered autonomous agents (Pytheia), and Train-to-Earn data economics — capabilities not found in any single platform today.

**FFG alignment**: Fits "IKT der Zukunft" and "Produktion der Zukunft" — enabling Austrian SMEs to leverage blockchain + AI without building infrastructure from scratch.

**AWS Credits alignment**: Cloud-native deployment on Railway/Render today; AWS migration path for enterprise-grade SLA. Credits accelerate time-to-market for 3 commercial bundles.

### E.3 One-Page: "Austrian Value Creation" Story

---

**THRONOS — Blockchain-OS aus Österreich**

Thronos ist ein in Österreich entwickeltes Blockchain-Betriebssystem, das KI, IoT und dezentrale Identität vereint — alles "Made in Austria".

**Was wir bauen**: Eine Plattform, die es Unternehmen ermöglicht, Geräte zu verifizieren (VerifyID), Telemetriedaten sicher zu sammeln (Driver/IoT Telemetry) und KI-Modelle dezentral zu trainieren — alles auf einer eigenen SHA256-Blockchain mit dem Utility-Token THR.

**Wertschöpfung in Österreich**:
- FlexCo e.U. in Österreich registriert
- Erste Kunden und Pilotprojekte in DACH
- Arbeitsplätze in Entwicklung, DevOps und Vertrieb
- Steuereinnahmen und IP verbleiben in Österreich

**Marktchance**: Der globale IoT-Markt wächst auf €1,5 Billionen bis 2030. Österreich kann mit Thronos eine Nische in "vertrauenswürdiger IoT-Identität" besetzen — privacy-by-design, off-grid-fähig, KI-gestützt.

**Nächste Schritte**: 3 kommerzielle Bundles (VerifyID, Driver Telemetry, IoT+AI) mit ersten zahlenden Kunden bis Q4 2026. FFG-Förderung beschleunigt die Markteinführung um 6 Monate.

*"Pledge to the unburnable — Stärke in jedem Block."*

---

## F — Driver Platform & Autopilot Telemetry

### F.1 Overview

The **Driver Platform** (`Tsipchain/driver-platform`) is a FastAPI/SQLite edge API deployed on Railway. It is the operational ingestion point for GPS telemetry, trip events, and voice/CB messages from three tenant categories:

| Tenant | Location | Mode |
|:-------|:---------|:-----|
| Independent taxi drivers | Thessaloniki | standard |
| Taxi companies (fleet) | TH / regional | fleet |
| Driving schools | Volos | lesson (opt-in) |

All raw data lands in `driver_service.db` on the **Node-2 Railway volume** (`node-2-volume` mounted at `/app/data`). This is the **operational store**. AI Core (Node 4) is the **analytical / ML store**; PII is stripped before any export.

---

### F.2 Data Collected

#### F.2.1 Mandatory fields (every trip event)

| Field | Type | Description |
|:------|:-----|:------------|
| `trip_id` | UUID | Unique trip identifier |
| `session_id` | UUID | Driving session (may span multiple trips) |
| `driver_id` | String | Pseudonymous identifier linked via VerifyID |
| `gps_lat` / `gps_lng` | Float | Raw GPS coordinates (operational DB only) |
| `speed_kmh` | Float | Current speed |

#### F.2.2 Optional fields

| Field | Mandatory | Notes |
|:------|:----------|:------|
| `harsh_events` | No | JSON: harsh braking, sharp turns, rapid acceleration |
| `weather` | No | Ambient conditions at time of event |
| `comment` | No | Free-text driver note (driver-initiated) |
| `voice_message_ref` | No | Reference to a CB/voice message recorded during the trip |

#### F.2.3 Lesson mode (driving schools — opt-in)

When a tenant is configured in `lesson` mode, additional fields are captured:

| Field | Description |
|:------|:-----------|
| `instructor_id` | Pseudonymous instructor identifier |
| `student_id` | Pseudonymous student identifier |

Lesson mode requires **explicit tenant opt-in** in the driver-platform configuration. Data handling rules are identical to standard mode (PII stripped before ML export).

---

### F.3 Retention Policy

| Store | Data | Retention |
|:------|:-----|:----------|
| Node-2 volume (`driver_service.db`) | All raw telemetry including GPS | **90 days** |
| AI Core feature store (training bucket) | Pseudonymized, PII-free features | **Long-term archive** (indefinite, governance-controlled) |
| VerifyID Postgres | Driver identity (phone, email) | Per GDPR right-to-erasure on request |

After 90 days, raw records in `driver_service.db` are purged via a scheduled cleanup job. Pseudonymized feature records in AI Core are retained for the duration of the model training lifecycle.

---

### F.4 Privacy & Safety

#### F.4.1 PII boundary

- `phone` and `email` are stored **only** in the operational SQLite DB (`driver_service.db`) at driver registration time.
- They are **never** included in API responses, telemetry event payloads, or ML exports.
- Cross-service joins use `hashed(phone)` or `verifyid_driver_id` as pseudonymous link keys.

#### F.4.2 AI training pipeline

- The export job reads from `driver_telemetry_raw`, **excludes** `phone`, `email`, and raw `gps_lat`/`gps_lng`.
- GPS data may be aggregated or rounded (configurable precision) before landing in the AI Core feature store.
- The resulting `driver_telemetry_features` dataset contains only pseudonymized IDs and derived metrics.

#### F.4.3 Identity bridge

A dedicated identity bridge service:
- Reads from VerifyID Postgres and driver-platform SQLite.
- Produces a stable pseudonymous mapping table (`verifyid_driver_id` ↔ `driver_platform_driver_id`).
- The mapping table lives in AI Core (pseudonymized; no raw PII).
- The same bridge enables consistent cross-ecosystem identity for music module IoT miners who are also registered drivers.

#### F.4.4 Driving schools

- Lesson mode is **tenant opt-in only** — not enabled by default.
- `instructor_id` and `student_id` are pseudonymous in all telemetry.
- School administrators may request data erasure per GDPR; the identity bridge mapping is deleted alongside the operational record.

---

### F.5 Ops Runbook — Driver Platform

#### F.5.1 Environment variables (driver-platform Railway service)

```
DRIVER_DB_PATH=/app/data/driver_service.db
RAILWAY_VOLUME_MOUNT=/app/data
VERIFYID_API_URL=<verifyid service URL>
AI_CORE_EXPORT_URL=<ai-core export endpoint>
EXPORT_SCHEDULE=daily          # or: streaming
EXPORT_GPS_PRECISION=2         # decimal places for GPS aggregation (0=strip)
LOG_LEVEL=INFO
```

#### F.5.2 Backup & restore — `driver_service.db`

**Manual snapshot from Railway volume**:
```bash
# SSH into Railway shell or use Railway CLI
railway run --service driver-platform-production \
  sqlite3 /app/data/driver_service.db \
  ".backup '/app/data/backups/driver_$(date +%Y%m%d_%H%M%S).db'"
```

**Download backup to local machine**:
```bash
# Via Railway CLI (if volume export is available)
railway volume download node-2-volume ./backups/

# Or: trigger a backup endpoint (if implemented)
curl -X POST https://driver-platform-production.up.railway.app/admin/backup \
     -H "Authorization: Bearer $ADMIN_SECRET"
```

**Restore procedure**:
1. Stop any active export jobs: set `EXPORT_SCHEDULE=disabled` in Railway env vars and redeploy.
2. Copy the backup file to the volume: upload via Railway shell or volume CLI.
3. Rename the backup to `driver_service.db` at `/app/data/`.
4. Redeploy the driver-platform service to pick up the restored DB.
5. Verify: `GET /health` → check `db_ok: true` and record count.
6. Re-enable export: restore `EXPORT_SCHEDULE` and redeploy.

#### F.5.3 Re-sync exports to AI Core after a restore

After restoring `driver_service.db`, the AI Core feature store may be ahead of or behind the operational DB. To re-sync:

```bash
# Trigger a full re-export (replace <from_date> with restore point)
curl -X POST https://driver-platform-production.up.railway.app/admin/export/resync \
     -H "Authorization: Bearer $ADMIN_SECRET" \
     -H "Content-Type: application/json" \
     -d '{"from_date": "2026-01-01", "strip_pii": true}'
```

Steps:
1. Confirm the restore point date (last known-good backup timestamp).
2. Call the resync endpoint (or run the export job manually with `--full-resync` flag).
3. Monitor AI Core ingestion logs for duplicate-key errors; the export job should be idempotent (upsert by `trip_id`).
4. Notify the AI team that feature store records before the restore point may need re-validation.

#### F.5.4 Disable exports temporarily (data incident)

If a data incident is detected (e.g., PII leak suspected in export pipeline):

1. **Immediate**: Set `EXPORT_SCHEDULE=disabled` in Railway env vars → redeploy driver-platform.
2. **Verify**: Confirm no export jobs are running: `GET /admin/export/status`.
3. **Isolate**: Block AI Core from accepting new driver telemetry records (coordinate with AI team).
4. **Investigate**: Query the export audit log to determine which records were exported.
5. **Remediate**: If PII was exported, trigger deletion in AI Core feature store for affected `driver_id` range.
6. **Re-enable**: After remediation sign-off, restore `EXPORT_SCHEDULE` and redeploy.
7. **Post-mortem**: Document within 48 hours; update export pipeline PII checks.

#### F.5.5 Health monitoring

| Check | Endpoint | Expected |
|:------|:---------|:---------|
| Service liveness | `GET /health` | `200 OK`, `db_ok: true` |
| Export job status | `GET /admin/export/status` | `last_export_at`, `records_exported` |
| Volume free space | Railway dashboard → Volumes | > 20% free |

Pytheia monitors the `/health` endpoint every 5 minutes. Alert is triggered after 3 consecutive failures (SEV-2).

---

### F.6 Autopilot / Driver AI Training Pipeline

```
mobile_app (driver)
        │
        │  GPS, speed, events, voice/CB
        ▼
[driver-platform]  (FastAPI, Railway, Node-2 volume)
        │
        │  SQLite write → driver_telemetry_raw
        │
        ├──────────────────────────────────────┐
        │  (batch/streaming export, PII stripped)│
        ▼                                       │
[ai-core]  (Node 4, Render)                    │
        │                                       │
        │  driver_telemetry_features             │
        │  (feature store / training bucket)     │
        │                                       │
        ├── verifyid_identity (pseudonymous key) ┘
        │   (VerifyID Postgres → identity bridge)
        │
        ├── music_route_telemetry join
        │   (when session has music/IoT signals)
        │
        ▼
  Autopilot / Driver Scoring / Route Analytics Models
```

**AI outputs**:
- Driver scoring model (safety, efficiency, route quality)
- Route analytics (traffic patterns, Thessaloniki / Volos regional data)
- Lesson mode assessment (driving school student progress — pseudonymized)
- T2E reward multiplier calculation

**Model governance**: All training runs are logged in the AI audit ledger. Models that consume driver telemetry features must carry a `pii_free: true` attestation in the model registry.

---
