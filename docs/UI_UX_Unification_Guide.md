# Thronos — UI/UX Unification Guide

**Version**: 2026.2
**Purpose**: Single voice, single terminology, consistent templates across all landings.
**Last Updated**: 2026-02-15

---

## 1. Terminology Standard

All landing pages, portals, and service UIs MUST use the following canonical terms. No synonyms, no variations.

### 1.1 Core Product Names

| Canonical Name | DO NOT USE | Context |
|:---------------|:-----------|:--------|
| **Thronos** | Thronos Chain, ThronosChain, ThrChain | Brand name, always capitalized |
| **THR** | THR Token, $THR, Thronos Coin | Token ticker |
| **VerifyID** | Verify-ID, VerifyId, verify_id | Identity/device service |
| **Decent Music** | Decentralized Music, D-Music, DecentMusic | Music platform |
| **Crypto Hunters** | CryptoHunters, Crypto Hunter | P2E game |
| **Pytheia** | Pythia, PYTHEIA, πυθεία | AI agent (note spelling) |
| **AI Core** | AI Node, LLM Node | AI inference service |
| **Sentinel** | Monitor, Watcher, Health Check | Network monitoring dashboard |
| **Explorer** | Block Explorer, Chain Explorer | Blockchain explorer |
| **App Hub** | Application Hub, Apps Page, Hub | Service directory |
| **WhisperNote** | Whisper Note, AudioTX | Audio-Fi protocol |
| **RadioNode** | Radio Node, RF Node | RF protocol |
| **PhantomFace** | Phantom Face, StegTX | Steganography protocol |

### 1.2 Feature Terminology

| Canonical Term | DO NOT USE | Meaning |
|:---------------|:-----------|:--------|
| **Train-to-Earn (T2E)** | Train2Earn, T-2-E | IoT/driver data rewards |
| **Learn-to-Earn (L2E)** | Learn2Earn, L-2-E | Education rewards |
| **Play-to-Earn (P2E)** | Play2Earn, P-2-E | Gaming rewards |
| **Pledge** | Deposit, Lock, Stake (for BTC bridge) | BTC bridge entry |
| **Bridge** | Swap (for cross-chain) | Cross-chain transfer |
| **Swap** | Exchange, Trade (for AMM) | AMM token swap |
| **Pool** | Liquidity Pool, LP | AMM pool |
| **Quorum** | Consensus, Voting (alone) | BFT validator consensus |

### 1.3 Technical Terms

| Canonical Term | Explanation for UI Copy |
|:---------------|:------------------------|
| **SHA256** | "Military-grade encryption (same as Bitcoin)" |
| **Multisig** | "Multiple signatures required — no single point of failure" |
| **On-chain** | "Permanently recorded on the blockchain" |
| **Off-grid** | "Works without internet — via radio, audio, or solar" |
| **Non-custodial** | "You hold your own keys — we never have access" |

---

## 2. Portal Copy — "One Voice" (Μια Φωνή)

### 2.1 Voice Principles

| Principle | Description | Example |
|:----------|:-----------|:--------|
| **Direct** | Short sentences. Active voice. No jargon without explanation. | "Send THR in 3 seconds." not "Transactions are processed rapidly." |
| **Confident** | State facts. No hedging. | "Your keys. Your crypto." not "We try to keep your assets safe." |
| **Technical but accessible** | Explain tech simply when user-facing. Keep depth in docs. | "SHA256-secured (same as Bitcoin)" not just "SHA256" |
| **Survival ethos** | Subtly reference resilience, independence, freedom. | "Works when nothing else does." |
| **Multilingual parity** | EN is source. DE, EL, ES, FR, JA, ZH must match tone. | Professional DE (Sie-form B2B, Du-form B2C) |

### 2.2 Standard Copy Blocks

**Hero / Tagline**:
> "Pledge to the unburnable. Strength in every Block."

**Wallet CTA**:
> "Your wallet. Your rules. Send, swap, and earn — in one place."

**VerifyID CTA**:
> "Hardware identity you can trust. Register. Verify. Prove."

**AI Core CTA**:
> "On-chain intelligence. Multi-provider AI. One API."

**Sentinel CTA**:
> "Every node. Every heartbeat. Real-time network health."

**Explorer CTA**:
> "Every block. Every transaction. Transparent and immutable."

**Music CTA**:
> "Stream. Tip. Earn. Music that pays the artist — 80% direct."

**Crypto Hunters CTA**:
> "Hunt. Collect. Earn. The real world is your game board."

**Bridge CTA**:
> "BTC to Thronos. Non-custodial. Three confirmations. Done."

### 2.3 Footer Standard

Every landing page footer MUST include:
```
Thronos FlexCo e.U. (Austria)
"Pledge to the unburnable"
[Wallet] [Explorer] [Docs] [GitHub]
© 2026 Thronos. All rights reserved.
```

---

## 3. Landing Page Templates

### 3.1 Template Structure (FastAPI/Flask)

Every new Thronos service landing page follows this structure:

```
templates/landing/service_landing.html
├── Header (nav bar — shared across all landings)
├── Hero Section (service name + one-liner + CTA button)
├── Features Grid (3-4 cards with icons)
├── How It Works (numbered steps, max 4)
├── Technical Specs (collapsible detail panel)
├── Pricing / Get Started (if commercial bundle)
├── Testimonials / Stats (optional)
└── Footer (standard, see 2.3)
```

### 3.2 CSS Variables (from BRANDING.md)

All landings use the shared Thronos design tokens:

```css
:root {
  /* Green Spectrum */
  --text-primary: #00ff00;
  --text-secondary: #00ff66;
  --border-glow: #00ff66;
  --circuit-green: #1a3b2e;

  /* Gold Spectrum */
  --gold: #ffd700;
  --gold-light: #ffed4e;
  --gold-dark: #d4af37;

  /* Dark Spectrum */
  --bg-dark: #000000;
  --bg-panel: #0a0a0a;
  --bg-secondary: #111111;

  /* Accent */
  --accent: #ff6600;
  --text-muted: #666666;

  /* Typography */
  --font-primary: 'Courier New', monospace;
}
```

### 3.3 Shared Components

**Nav Bar** (all pages):
```html
<nav class="thronos-nav">
  <a href="/" class="nav-logo">THRONOS</a>
  <div class="nav-links">
    <a href="/hub">App Hub</a>
    <a href="/ai">AI Core</a>
    <a href="/sentinel">Sentinel</a>
    <a href="/verify">VerifyID</a>
    <a href="/explorer">Explorer</a>
  </div>
  <button class="nav-wallet-btn" onclick="openWallet()">Connect Wallet</button>
</nav>
```

**Hero Section** (per-service):
```html
<section class="hero">
  <h1 class="hero-title gradient-text">{{ service_name }}</h1>
  <p class="hero-subtitle">{{ one_liner }}</p>
  <a href="{{ cta_link }}" class="btn-primary">{{ cta_text }}</a>
</section>
```

**Feature Card**:
```html
<div class="feature-card">
  <div class="feature-icon">{{ icon }}</div>
  <h3>{{ title }}</h3>
  <p>{{ description }}</p>
</div>
```

### 3.4 New Service Checklist

When launching a new Thronos service:

- [ ] Create landing page using template structure (3.1)
- [ ] Use ONLY canonical terminology (Section 1)
- [ ] Apply standard CSS variables (3.2)
- [ ] Include shared nav bar and footer
- [ ] Write copy following "One Voice" principles (Section 2)
- [ ] Add service to `thronos_registry.yaml`
- [ ] Run `python scripts/generate_bootstrap.py`
- [ ] Add landing to `landings` section in registry
- [ ] Test in all 7 languages (EN, DE, EL, ES, FR, JA, ZH)

---

## 4. Page-Specific Copy Guide

### 4.1 App Hub (`/hub`)

**Title**: "Thronos App Hub"
**Subtitle**: "Everything you need. One ecosystem."
**Content**: Grid of all services/apps from registry. Each card shows: name, one-liner, status badge (live/beta/coming soon), link.

### 4.2 AI Core (`/ai`)

**Title**: "Thronos AI Core"
**Subtitle**: "On-chain intelligence. Multi-provider AI. One API."
**Key messages**:
- Multi-model: OpenAI, Anthropic, Gemini
- Pytheia autonomous agent
- Oracle services for smart contracts
- Pay with THR for AI credits

### 4.3 Sentinel (`/sentinel`)

**Title**: "Thronos Sentinel"
**Subtitle**: "Every node. Every heartbeat. Real-time."
**Key messages**:
- Live health status of all 4 nodes
- Response time graphs
- Incident history
- Pytheia-powered alerts

### 4.4 VerifyID (`/verify`)

**Title**: "Thronos VerifyID"
**Subtitle**: "Hardware identity you can trust."
**Key messages**:
- Device registration + SHA256 attestation
- Challenge/response in 5 minutes
- API-first for enterprise integration
- On-chain audit trail

### 4.5 Explorer (`/explorer`)

**Title**: "Thronos Explorer"
**Subtitle**: "Every block. Every transaction. Transparent."
**Key messages**:
- Real-time block feed
- Transaction search
- Address balance lookup
- Smart contract verification

---

## 5. Localization Notes

| Language | Tone | Form of Address |
|:---------|:-----|:----------------|
| **EN** | Direct, confident | Neutral (you) |
| **DE** | Professional | Sie (B2B), Du (B2C/community) |
| **EL** | Warm, direct | Εσύ/Εσείς depending on context |
| **ES** | Professional | Usted (B2B), Tú (B2C) |
| **FR** | Formal | Vous (default) |
| **JA** | Polite/formal | です/ます form |
| **ZH** | Clear, professional | 您 (formal) |

**Rule**: EN is the source language. All translations must match tone and structure. Marketing claims must be legally valid in each locale.

---

*"Pledge to the unburnable — Strength in every Block."*
