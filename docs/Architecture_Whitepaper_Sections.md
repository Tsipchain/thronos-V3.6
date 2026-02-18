# Thronos V3.6 — Architecture Whitepaper Sections

**Version**: 2026.2 | **Language**: EN/GR
**Status**: Canonical Reference
**Last Updated**: 2026-02-15

---

## Table of Contents

1. [AI Layer 2 (AI L2)](#1-ai-layer-2-ai-l2)
2. [Bridge & Cross-Chain Events Lifecycle](#2-bridge--cross-chain-events-lifecycle)
3. [Utilities via Mining (Treasury Splits & Incentives)](#3-utilities-via-mining)
4. [Music Economy (Tips vs Plays)](#4-music-economy)
5. [Driver Platform & Autopilot Telemetry](#5-driver-platform--autopilot-telemetry)
6. [Gaming Layer (Crypto Hunters & Beyond)](#6-gaming-layer)

---

## 1. AI Layer 2 (AI L2)

### 1.1 What AI L2 Does

AI L2 is Thronos's on-chain intelligence layer. It sits above the base blockchain (L1) and provides:

- **Multi-provider LLM inference**: Routes requests to OpenAI, Anthropic (Claude), or Google Gemini based on availability, cost, and task complexity.
- **Pytheia autonomous agent**: A self-governing AI node that monitors network health, optimizes AMM pools, detects bugs, and provides governance advice.
- **Oracle services**: AI-verified data points signed on-chain for use by smart contracts.
- **Anomaly detection**: Real-time analysis of IoT sensor streams, flagging outliers.
- **Model catalog management**: Automatic refresh and routing across provider models.

### 1.2 What AI L2 Does NOT Do

- **Does not replace human decision-making**: All autonomous actions by Pytheia are logged and can be overridden by admin/quorum vote.
- **Does not store or train on personal data**: No PII enters the AI pipeline. GPS data is hashed client-side.
- **Is not a general-purpose chatbot service**: AI L2 serves ecosystem-specific tasks (chain analytics, device verification, trading signals), not arbitrary chat.
- **Does not guarantee AI output correctness**: Oracle signatures attest to provenance, not truth. Consumers must validate.
- **Does not run on-chain inference directly**: Inference runs on Node 4 (Render/local Ryzen 7). Results are posted on-chain as signed attestations.

### 1.3 Architecture

```
User / dApp / IoT Device
        │
        ▼
[Node 1 Master] ── /api/ai/* proxy ──▶ [Node 4 AI Core]
        │                                     │
        │                               ┌─────┴─────┐
        │                               │ OpenAI    │
        │                               │ Anthropic │
        │                               │ Gemini    │
        │                               └─────┬─────┘
        │                                     │
        │◀── signed result ───────────────────┘
        │
        ▼
[On-chain attestation] → block N
```

### 1.4 AI L2 — GR (Ελληνικά)

Το AI L2 είναι το επίπεδο τεχνητής νοημοσύνης του Thronos. Λειτουργεί πάνω από το βασικό blockchain (L1) και παρέχει:

- **Πολυ-πάροχο LLM inference**: Δρομολογεί αιτήματα σε OpenAI, Anthropic ή Gemini.
- **Pytheia**: Αυτόνομος AI agent που παρακολουθεί το δίκτυο, βελτιστοποιεί pools, εντοπίζει bugs.
- **Oracle υπηρεσίες**: Υπογεγραμμένα δεδομένα on-chain για smart contracts.

**Τι ΔΕΝ κάνει**: Δεν αντικαθιστά ανθρώπινες αποφάσεις, δεν αποθηκεύει προσωπικά δεδομένα, δεν εγγυάται ορθότητα εξόδων AI.

---

## 2. Bridge & Cross-Chain Events Lifecycle

### 2.1 Overview

The Thronos bridge connects THR (native chain) with external blockchains: Bitcoin, BSC, Ethereum, XRP, and Solana. The primary bridge is BTC ↔ WBTC (Wrapped Bitcoin on Thronos).

### 2.2 BTC Pledge Lifecycle (Step by Step)

```
Step 1: USER INITIATES PLEDGE
  User → /api/bridge/pledge
  Payload: { btc_address, thr_address, amount_btc }
  Result: Pledge record created (status: PENDING)
         PDF contract generated with steganography (send_secret embedded)

Step 2: BTC PAYMENT DETECTED
  Node 2 (Watcher) polls Blockstream API every 60s
  Detects payment to pledge vault address
  Waits for ≥ 3 confirmations
  Calls Node 1: /api/bridge/confirm { pledge_id, tx_hash, confirmations }

Step 3: WBTC MINTING
  Node 1 verifies:
    - pledge exists and status == PENDING
    - BTC tx_hash matches expected amount
    - confirmations ≥ 3
  Mints equivalent WBTC to user's THR address
  Updates pledge status: CONFIRMED
  Emits on-chain event: BridgeMint(thr_address, amount_wbtc, btc_tx_hash)

Step 4: WITHDRAWAL (Reverse)
  User → /api/bridge/withdraw { thr_address, btc_address, amount_wbtc }
  Node 1 burns WBTC from user's balance
  Queues BTC release from vault (manual or multisig-automated)
  Emits on-chain event: BridgeBurn(thr_address, amount_wbtc, btc_address)

Step 5: BTC RELEASE
  Treasury multisig (2-of-3) signs BTC transaction
  BTC sent to user's BTC address
  Pledge status: COMPLETED
```

### 2.3 Cross-Chain Event Bus

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  External    │     │  Node 2      │     │  Node 1         │
│  Blockchain  │────▶│  Watcher     │────▶│  Event Handler  │
│  (BTC/BSC/   │     │  (poll/ws)   │     │  (validate +    │
│   ETH/XRP)   │     │              │     │   write chain)  │
└─────────────┘     └──────────────┘     └────────┬────────┘
                                                   │
                                          ┌────────▼────────┐
                                          │  On-Chain Event  │
                                          │  Log (immutable) │
                                          └─────────────────┘
```

**Event types**:
- `BridgeMint` — external deposit confirmed, WBTC minted
- `BridgeBurn` — user withdrawal, WBTC burned
- `PledgeCreated` — new pledge initiated
- `PledgeExpired` — pledge TTL exceeded without payment
- `CrossChainSync` — balance reconciliation event

### 2.4 Fallback Chain

1. Primary: Blockstream API (public, no key required)
2. Secondary: Local BTC RPC (`BTC_RPC_URL`)
3. Tertiary: `btc-api.thronoschain.org` (Thronos-owned adapter)
4. Emergency: Manual admin approval via admin console

### 2.5 Bridge — GR (Ελληνικά)

Η γέφυρα Thronos συνδέει το THR με εξωτερικά blockchains (BTC, BSC, ETH, XRP, SOL). Κύρια λειτουργία: BTC Pledge → WBTC στο Thronos.

**Κύκλος ζωής**: Pledge → BTC πληρωμή → 3 confirmations → WBTC mint → Ανάληψη → WBTC burn → BTC release (multisig).

---

## 3. Utilities via Mining

### 3.1 Mining on Thronos

Thronos uses SHA256 Proof-of-Work, compatible with Bitcoin ASICs (Block Erupters, Antminers) and CPU/GPU miners. Mining serves dual purpose:

1. **Block production**: Miners produce blocks and earn THR rewards.
2. **Identity attestation**: USB Block Erupters provide hardware PoW for VerifyID device registration.

### 3.2 Treasury Splits

Every block reward is split according to the ecosystem treasury model:

```
Block Reward (e.g., 50 THR)
├── 60% → Miner (block producer)
├── 20% → Network Pool (validators, node operators)
├── 10% → AI/T2E Pool (Pytheia treasury, Train-to-Earn rewards)
└── 10% → Development Fund (core team, grants, bug bounties)
```

### 3.3 Incentive Layers

| Incentive | Mechanism | Reward Source |
|:----------|:----------|:-------------|
| Block mining | SHA256 PoW, Stratum port 3334 | Block reward (60%) |
| Validation | BFT quorum voting, BLS signatures | Network Pool (20%) |
| Train-to-Earn (T2E) | IoT/ASIC miners storing AI training data | AI/T2E Pool (10%) |
| Learn-to-Earn (L2E) | Complete courses, pass quizzes | Development Fund |
| Play-to-Earn (P2E) | Crypto Hunters game achievements | Game reward pool |
| Music tips | Listeners tip artists in THR | Direct wallet transfer |
| Referral bonus | DEX swap referrals | AMM fee share |

### 3.4 Halving Schedule

Following Bitcoin's model:
- **Halving interval**: Every 4 years (210,000 blocks)
- **Max supply**: 21,000,001 THR
- **Soft peg**: 1 THR = 0.0001 BTC (maintained via Watcher Service)

### 3.5 Treasury — GR (Ελληνικά)

Κάθε block reward μοιράζεται: 60% miner, 20% δίκτυο, 10% AI/T2E, 10% ανάπτυξη. Halving κάθε 4 χρόνια. Max supply: 21,000,001 THR.

---

## 4. Music Economy

### 4.1 Decent Music Platform

Decent Music is Thronos's decentralized music streaming and distribution platform. Artists register, upload tracks, and earn THR from both plays and tips.

### 4.2 Tips vs Plays — Economic Model

| Revenue Stream | Mechanism | Flow |
|:---------------|:----------|:-----|
| **Tips** | Listener sends THR directly to artist wallet | Instant, peer-to-peer, no platform cut |
| **Play royalties** | Per-stream reward from the Music Pool | Calculated per play, distributed daily |

### 4.3 Revenue Split (80/10/10)

```
Every music stream generates micro-reward:
├── 80% → Artist (direct to wallet)
├── 10% → Network Pool (validators who serve the stream)
└── 10% → AI/T2E Pool (IoT miners who cache/distribute content)
```

**Tips are 100% to the artist** — no platform fee, no intermediary.

### 4.4 Artist Lifecycle

1. **Register**: Artist creates profile with wallet address.
2. **Upload**: Tracks uploaded with metadata (title, genre, cover art).
3. **Streaming**: Listeners play tracks; each play triggers micro-reward.
4. **Tips**: Listeners can tip any amount of THR directly.
5. **Royalties**: Daily settlement of accumulated play rewards.
6. **Analytics**: Artist dashboard shows plays, tips, total earnings.

### 4.5 Music + Telemetry Integration

Music streams double as data transport:
- **WhisperNote**: TX data encoded as audio tones within music playback.
- **GPS correlation**: Driver telemetry timestamped alongside music plays for T2E rewards.
- IoT miners that cache and relay music content earn T2E rewards.

### 4.6 Music Economy — GR (Ελληνικά)

Το Decent Music είναι η αποκεντρωμένη πλατφόρμα μουσικής του Thronos. Μοντέλο 80/10/10: 80% στον καλλιτέχνη, 10% δίκτυο, 10% AI/T2E. Τα tips πάνε 100% στον καλλιτέχνη χωρίς προμήθεια.

---

## 5. Driver Platform & Autopilot Telemetry

### 5.1 Overview

The **Driver Platform** (`Tsipchain/driver-platform`) is a FastAPI/SQLite edge API deployed on Railway. It is the primary ingestion service for real-world driving data from three tenant categories:

| Tenant | Region | Mode |
|:-------|:-------|:-----|
| Independent taxi drivers | Thessaloniki | standard |
| Taxi companies (fleet) | TH / regional | fleet |
| Driving schools | Volos | lesson (opt-in) |

This platform feeds the **Thronos Autopilot / Driver AI** training pipeline and also drives the T2E (Train-to-Earn) reward system. The existing on-chain `driver-telemetry` module (Node 1, proof-of-route hashes) continues to handle chain-level reward attestations; `driver-platform` is the **off-chain operational layer** that collects the richest raw signal.

---

### 5.2 Two-Layer Architecture

```
Layer 1 — Operational (driver-platform)          Layer 2 — Analytical (ai-core)
─────────────────────────────────────────        ───────────────────────────────
mobile_app (driver)                              AI Core (Node 4 / Render)
        │                                                │
        │ GPS, speed, events, voice, CB                  │
        ▼                                                │
[driver-platform]  FastAPI / Railway                     │
        │                                                │
        │ SQLite write                                   │
        ▼                                                │
[driver_service.db]  ← node-2-volume                    │
  /app/data/                                             │
  (90-day retention)                                     │
        │                                                │
        │ batch export job (daily)                       │
        │ PII stripped, GPS rounded/aggregated           │
        └────────────────────────────────────────────────▶
                                                 [driver_telemetry_features]
                                                  feature store / training bucket
                                                         │
                                           ┌─────────────┴────────────┐
                                           │                           │
                                  verifyid_identity             music_route_telemetry
                                  (pseudonymous join)           (session_id join)
```

**Node-2 volume** is the operational store (raw data, PII present, 90-day retention).
**AI Core** is the analytical/ML store (PII-free, pseudonymized, long-term archive).

---

### 5.3 Data Collected

#### 5.3.1 Mandatory fields (every trip event)

| Field | Type | Description |
|:------|:-----|:------------|
| `trip_id` | UUID | Unique trip identifier |
| `session_id` | UUID | Driving session (spans multiple events) |
| `driver_id` | String | Pseudonymous; maps to VerifyID via identity bridge |
| `gps_lat` / `gps_lng` | Float | Raw GPS (operational DB only; stripped before ML export) |
| `speed_kmh` | Float | Vehicle speed at event time |

#### 5.3.2 Optional fields

| Field | Description | Notes |
|:------|:------------|:------|
| `harsh_events` | JSON: harsh braking, sharp turns, rapid acceleration | For safety scoring |
| `weather` | Ambient conditions | Enriches road-condition model |
| `comment` | Free-text driver note | Driver-initiated, unstructured |
| `voice_message_ref` | Reference to CB/voice audio message | Content analyzed separately |

#### 5.3.3 Lesson mode (driving schools, Volos — opt-in)

| Field | Description |
|:------|:-----------|
| `instructor_id` | Pseudonymous instructor identifier |
| `student_id` | Pseudonymous student identifier |

Lesson mode requires **explicit tenant configuration**. It is never enabled by default.

---

### 5.4 Proof Architecture (On-Chain Layer)

The existing on-chain proof-of-route system (Node 1) remains the canonical reward attestation layer:

```
Driver Device
        │
        │  1. Collect GPS
        │  2. Hash locally: SHA256(lat, lon, timestamp, device_id)
        │  3. Generate proof-of-route
        ▼
Node 1 API  /api/telemetry/submit
        │
        │  Stores on-chain:
        │    route_hash, distance_km, duration_s,
        │    quality_score, device_id (VerifyID-attested)
        ▼
T2E Reward Calculation
  reward_thr = base_rate × distance_km × quality_multiplier × time_bonus
```

Driver-platform extends this by capturing the **full raw signal** off-chain for AI training, while the on-chain layer retains privacy-preserving proofs only.

---

### 5.5 What is Stored, Where, and What is NOT Exported

| Data | Operational DB (Node-2 vol.) | AI Core Feature Store | On-Chain |
|:-----|:----------------------------:|:---------------------:|:--------:|
| Raw GPS coordinates | ✅ | ✗ stripped | ✗ |
| Speed, harsh events | ✅ | ✅ | ✗ |
| Weather, comment | ✅ | ✅ | ✗ |
| Voice/CB message ref | ✅ | ✅ (ref only) | ✗ |
| `phone`, `email` | ✅ (registration only) | ✗ never | ✗ |
| Route hash (SHA256) | ✅ | ✅ | ✅ |
| Distance, quality score | ✅ | ✅ | ✅ |
| `driver_id` (pseudonymous) | ✅ | ✅ | ✅ |
| Photos / video | ✗ | ✗ | ✗ |

---

### 5.6 Privacy Guarantees

1. **PII boundary**: `phone` and `email` never leave `driver_service.db`. They are collected at registration and never included in telemetry payloads or exports.
2. **Pseudonymous IDs**: All cross-service joins use `hashed(phone)` or `verifyid_driver_id`. Raw identity never crosses the PII boundary.
3. **GPS precision control**: Raw GPS is stored operationally; before ML export, coordinates are aggregated or rounded to configurable precision (default: 2 decimal places ≈ ~1 km grid).
4. **Identity bridge**: A dedicated service generates a pseudonymous mapping between `driver-platform.driver_id` and `verifyid.drivers.id`. The mapping lives in AI Core (pseudonymous only).
5. **GDPR right-to-erasure**: Operational records in `driver_service.db` are deleted on request. The identity bridge mapping is purged simultaneously. AI Core retains only pseudonymized features; if the mapping is deleted, pseudonymous features become permanently unlinked.
6. **Lesson mode isolation**: Driving school sessions are partitioned by `tenant_id` and `session_type=lesson`. Instructor and student IDs are pseudonymous throughout.

---

### 5.7 Data Flows

#### Flow 1 — Mobile → Operational Store
```
mobile_app → POST /trips, /gps, /voice, /cb-message
          → driver-platform (FastAPI)
          → driver_service.db (node-2-volume)
```

#### Flow 2 — Export to AI Core (daily batch)
```
driver_service.db → export job (PII stripped)
                  → ai-core ingest endpoint
                  → driver_telemetry_features (feature store)
```

#### Flow 3 — Identity Join (VerifyID)
```
verifyid_api (Postgres) → identity bridge
                        → pseudonymous mapping table (AI Core)
                        → JOIN with driver_telemetry_features via driver_id
```

#### Flow 4 — Music + Route Session Join
```
music/iot-service → music_route_telemetry (Node 1 ledger)
                  → AI Core JOIN on session_id
                  → enriched feature: route + music/artist signals
                  → combined T2E reward multiplier
```

---

### 5.8 T2E Reward Formula

```
reward_thr = base_rate × distance_km × quality_multiplier × time_bonus × session_bonus

Where:
  base_rate          = 0.01 THR/km (governance-adjustable)
  quality_multiplier = 0.5 to 2.0  (data completeness, consistency, harsh events)
  time_bonus         = 1.0 to 1.5  (off-peak hours incentive)
  session_bonus      = 1.0 to 1.2  (bonus when session has combined music/IoT signals)
```

Lesson mode sessions may carry an additional `lesson_quality_bonus` factor, set by driving school governance parameters.

---

### 5.9 Autopilot / Driver AI Pipeline

The driver telemetry features feed the following model training goals:

| Model | Input Features | Output |
|:------|:--------------|:-------|
| **Safety Scorer** | speed, harsh_events, weather, route_hash | Safety score 0–100 |
| **Route Efficiency** | GPS (aggregated), speed, trip duration | Optimal route suggestions |
| **Driving School Assessment** | lesson sessions (pseudonymized) | Student progress score |
| **T2E Multiplier Model** | quality_score, session_bonus, completeness | Dynamic reward multiplier |
| **Autopilot Training** | all features (enriched with music/IoT join) | Driving behavior model |

All models that consume driver telemetry features carry a `pii_free: true` attestation in the AI Core model registry. Training runs are logged in the AI audit ledger.

---

### 5.10 Driver Platform — GR (Ελληνικά)

Το **Driver Platform** είναι το κεντρικό σύστημα συλλογής τηλεμετρίας οδήγησης. Συλλέγει GPS, ταχύτητα, events και φωνητικά μηνύματα από:

- Ανεξάρτητους ταξιτζήδες (Θεσσαλονίκη)
- Εταιρείες ταξί (fleet mode)
- Σχολές Οδηγών Βόλου (lesson mode — opt-in)

**Αποθήκευση**: Raw δεδομένα (συμπεριλαμβανομένου GPS) στο `driver_service.db` στο Node-2 volume (Railway). Διατήρηση: **90 ημέρες**. Μετά, τα δεδομένα αρχειοθετούνται στο AI Core (Node 4).

**Privacy**: `phone` και `email` **δεν εξάγονται ποτέ** σε ML pipelines. Χρησιμοποιούμε pseudonymous IDs για όλα τα cross-service joins. Το GPS ακατέργαστο ανωνυμοποιείται/συγκεντρώνεται πριν από κάθε export στο AI Core.

**AI Training**: Το AI Core χρησιμοποιεί τα features για εκπαίδευση μοντέλων Autopilot, αξιολόγηση οδηγών και route analytics.

---

## 6. Gaming Layer

### 6.1 Crypto Hunters — Play-to-Earn

Crypto Hunters is a geolocation-based Play-to-Earn game where players explore real-world locations to find virtual crypto collectibles.

### 6.2 Game Mechanics

| Mechanic | Description |
|:---------|:-----------|
| **Geolocation hunting** | Players walk/drive to GPS hotspots to claim crypto drops |
| **NFT drops** | Rare collectibles minted as NFTs on Thronos chain |
| **Leaderboards** | Weekly/monthly rankings with THR prize pools |
| **Team raids** | Cooperative events requiring multiple players at one location |
| **Staking bonuses** | Players who stake THR get better drop rates |

### 6.3 Reward Structure

```
Game Reward Pool (funded by: 5% of block reward Development Fund)
├── 50% → Daily drop rewards (distributed across active players)
├── 30% → Leaderboard prizes (weekly/monthly top players)
└── 20% → Special events (team raids, seasonal events)
```

### 6.4 Integration with Ecosystem

- **VerifyID**: Anti-cheat — devices must be VerifyID-attested to play.
- **Driver Telemetry**: Driving to game locations earns T2E rewards simultaneously.
- **Music**: In-game soundtrack streams via Decent Music (artists earn royalties).
- **Wallet**: All rewards, NFTs, and purchases flow through the Thronos wallet.

### 6.5 Future Gaming Layer

Beyond Crypto Hunters, the gaming layer is designed to support:
- Third-party game developers deploying on Thronos (EVM smart contracts for game logic)
- Cross-game NFT interoperability
- AI-generated game content (powered by AI L2)
- VR/AR integration for immersive crypto hunting

### 6.6 Gaming — GR (Ελληνικά)

Το Crypto Hunters είναι ένα Play-to-Earn παιχνίδι βασισμένο σε GPS. Οι παίκτες εξερευνούν τοποθεσίες, συλλέγουν NFTs και κερδίζουν THR. Anti-cheat μέσω VerifyID. Μελλοντικά: third-party games, cross-game NFTs, AI-generated content.

---

*"In Crypto we Trust, in Survival we Mine." — Thronos Network V3.6*
