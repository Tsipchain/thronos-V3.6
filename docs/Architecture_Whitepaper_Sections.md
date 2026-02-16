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
5. [Driver / Telemetry (Proofs & Privacy)](#5-driver--telemetry)
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

## 5. Driver / Telemetry

### 5.1 Overview

The Driver Telemetry system collects vehicle route data for autonomous driving AI training. It is designed with **privacy-by-design** principles — no raw GPS coordinates are ever stored on-chain.

### 5.2 Proof Architecture

```
┌─────────────────┐
│  Driver's Device │
│  (Phone/OBD-II)  │
│                   │
│  1. Collect GPS   │
│  2. Hash locally  │──── SHA256(lat,lon,timestamp,device_id)
│  3. Generate      │
│     proof-of-route│
└───────┬───────────┘
        │
        ▼ (only hash + metadata sent)
┌───────────────────┐
│  Node 1 API       │
│  /api/telemetry/  │
│  submit           │
│                   │
│  Stores:          │
│  - route_hash     │
│  - distance_km    │
│  - duration_s     │
│  - quality_score  │
│  - device_id      │
│  (verified via    │
│   VerifyID)       │
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│  T2E Reward       │
│  Calculation      │
│                   │
│  THR = f(distance,│
│    quality, time) │
└───────────────────┘
```

### 5.3 What is Stored vs What is NOT

| Stored On-Chain | NOT Stored |
|:----------------|:-----------|
| Route hash (SHA256) | Raw GPS coordinates |
| Distance (km) | Street names or addresses |
| Duration (seconds) | Speed at specific points |
| Quality score (0-100) | Passenger information |
| Device ID (VerifyID-attested) | Driver personal identity |
| Timestamp (block height) | Photos or video |

### 5.4 Privacy Guarantees

1. **Client-side hashing**: GPS → SHA256 hash happens on the device. Server never sees raw coordinates.
2. **Proof-of-route**: Mathematical proof that a route was driven, without revealing the route.
3. **No PII on-chain**: Device ID is a pseudonymous identifier linked via VerifyID.
4. **GDPR compliance**: Off-chain data (device registration) subject to right-to-erasure.
5. **No third-party sharing**: Aggregated training data is anonymized before feeding AI models.

### 5.5 T2E Reward Formula

```
reward_thr = base_rate × distance_km × quality_multiplier × time_bonus

Where:
  base_rate         = 0.01 THR/km (adjustable by governance)
  quality_multiplier = 0.5 to 2.0 (based on data completeness, consistency)
  time_bonus        = 1.0 to 1.5 (off-peak hours bonus)
```

### 5.6 Driver/Telemetry — GR (Ελληνικά)

Το σύστημα Driver Telemetry συλλέγει δεδομένα διαδρομών για εκπαίδευση AI αυτόνομης οδήγησης. **Κανένα raw GPS δεν αποθηκεύεται** — μόνο SHA256 hash της διαδρομής. Οι οδηγοί κερδίζουν THR (Train-to-Earn) ανάλογα με απόσταση και ποιότητα δεδομένων.

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
