# Thronos Chain & THR Token - Complete Whitepaper

## Version 2026.1 | Thronos Network V3.6: The Survival Blueprint

---

## Introduction

Thronos Chain is a next-generation, SHA256-based blockchain project focused on survivability, decentralization, and freedom. It merges the core values of Bitcoin with innovative data transport technologies and fully offline, censorship-resistant communication.

Thronos V3.6 represents a paradigm shift: a blockchain that operates not only on the internet, but through sound, radio waves, images, and light. A network designed to survive grid collapse, censorship, and infrastructure failure.

---

## Technical Characteristics

- **Algorithm**: SHA256 (Bitcoin-compatible)
- **Compatibility**: Works with existing ASIC miners (Antminers, Block Erupters)
- **Transaction Speed**: Instant finality through asynchronous node syncing
- **Fees**: Ultra-low fees comparable to XRP
- **Smart Signing**: TXs are signed and distributed via multiple real-world mediums (images, audio, QR, radio)
- **Max Supply**: 21,000,001 THR (1 more than BTC)
- **Halving**: Every 4 years (Bitcoin-compatible)
- **Peg**: 1 THR = 0.0001 BTC (Soft Peg maintained via Watcher Service)

---

## 1. Hardware Architecture (The Arsenal)

### A. The "Brains" (Local Compute Cluster)

**G1 Mini Gaming PC (Ryzen 9 8945HS, 32GB DDR5)**
- Role: Main Node, Blockchain Indexer, API Host (Railway Bridge)
- Function: Manages VerifyID (KYC) and the central ledger
- Services: Master chain writer, public API, scheduler jobs

**Mini PC (Ryzen 7 8745HS, 32GB DDR4)**
- Role: AI/LLM Node & Autodriver Controller
- Function: Runs local LLM for decision-making and GPS telemetry processing
- Services: AI inference, model routing, telemetry aggregation

### B. Network & Infrastructure (Backbone)

**Cisco 1121 Router**
- Network fortress with hardware firewall
- Segregates IoT miners from main network
- Provides VLAN isolation for mining and validation traffic

**LoRa High-Gain Antenna**
- 15km radius connectivity with IoT nodes
- Data reception without internet dependency
- Off-grid block propagation

**Peiko Translator X9**
- Wireless Bluetooth Audio Interface
- Voice commands and audio transaction reception (WAV)
- Bridge between audio layer and blockchain

### C. Mining & Validation (Legacy Revitalization)

**USB Block Erupters**
- Legacy ASICs repurposed as "Identity Validators"
- Proof of Work shares required for VerifyID finalization
- Provides SHA256 hardware attestation

**Powered USB Hub (7+ ports)**
- Stable power delivery (0.5A per stick)
- Supports parallel ASIC validation

---

## 2. Survival Mode: Communication Without Internet (Audio-Fi)

Thronos V3.6 introduces data transmission via Audio (Audio-Fi):

1. **Encoding**: Transaction (JSON) is converted to QR Code
2. **Modulation**: QR is converted to WAV file (via FSK modulation)
3. **Transmission**: Audio is broadcast via wireless, Peiko X9, or LoRa
4. **Decoding**: The Ryzen 7 AI node "listens" to the audio, cleans it via AI noise reduction, and executes the transaction offline

### WhisperNote Protocol
- Transaction data encoded as frequency-shifted audio tones
- Selectable frequencies: 1kHz, 2kHz, 4kHz
- Web Audio API generation for browser-based transmission
- WAV download capability for offline transfer

### RadioNode
- RF-based block propagation without internet or power grid
- Compatible with SDR (Software Defined Radio) hardware
- LoRa modulation for long-range mesh networking

---

## 3. Off-Grid Operation (Solar Energy)

Full system autonomy through photovoltaic integration:

**Solar Controller (Victron/RS485)** sends battery data to the G1 node.

### Energy-Aware Operating Modes:

| Mode | Battery Level | Active Services |
|:-----|:-------------|:----------------|
| **Full Mode** | >80% | CPU Mining, ASIC Validation, Full API, AI Inference |
| **Eco Mode** | 30-80% | VerifyID only, AI Inference, Reduced API |
| **Survival Mode** | <30% | LoRa & Audio-Link only, All else shutdown |

---

## 4. Security & Network Defense (Kali Linux Integration)

Hardened security using Kali Linux tools:

- **SDR (Software Defined Radio)**: Spectrum monitoring for jamming detection
- **Bettercap**: Protection of IoT miners from Man-in-the-Middle attacks
- **Wireshark**: Traffic analysis on Cisco 1121 router
- **Hardware Firewall**: Cisco 1121 provides enterprise-grade packet filtering

---

## 5. Multi-Node Architecture

### Node Roles

| Node | Role | Hardware | Function |
|:-----|:-----|:---------|:---------|
| **Node 1 (Master)** | Chain Writer | G1 Mini (Ryzen 9) | Public API, ledger writes, scheduler, block production |
| **Node 2 (Replica)** | Read-Only Worker | Railway Cloud | Background workers, API reads, RPC relay |
| **Node 3 (Vercel)** | Static Frontend | Vercel CDN | Static assets, native wallet hosting, CDN delivery |
| **Node 4 (AI Core)** | AI/LLM Processing | Mini PC (Ryzen 7) | Model inference, autonomous trading, Pytheia governance |

### Service Discovery
- `bootstrap.json` for node registration and health
- Heartbeat protocol between master and replicas
- Automatic failover with READ_ONLY enforcement

---

## 6. Tokenomics

- **Token Name**: THR (Thronos)
- **Max Supply**: 21,000,001 (1 more than BTC)
- **Mining Algorithm**: SHA256 (ASIC & CPU)
- **Distribution**:
  - 80% Mining Rewards
  - 10% AI Treasury (for automated development & defense)
  - 10% Burn Mechanism (deflationary)
- **Halving**: Every 4 years (similar to Bitcoin)
- **Peg**: 1 THR = 0.0001 BTC (Soft Peg maintained via Watcher Service)

---

## 7. Governance & Management

Thronos Chain uses a decentralized governance model:
- THR holders vote on critical network parameters (fee limits, protocol upgrades)
- Voting via Signed Governance Messages recorded on the blockchain
- **PYTHEIA AI Agent**: Automated system health monitoring, governance advice, and proposal generation
- DAO-style proposal workflow with community voting

---

## 8. DeFi Ecosystem

### Token Swap (DEX)
- Constant product AMM formula
- Referral bonus system
- Instant token exchange

### Liquidity Pools
- Multiple trading pairs (THR/wBTC, THR/custom tokens)
- Fee tier system with LP rewards
- TVL tracking and analytics

### BTC Bridge
- **Deposit**: BTC to vault address -> auto-mint equivalent THR
- **Withdrawal**: Burn THR -> release BTC from vault
- **Watcher Service**: Automated BTC payment detection (Blockstream API + RPC fallback)
- **Security**: Multi-signature validation, 3 confirmation requirement
- **Rate**: 1 BTC = 10,000 THR (configurable via THR_BTC_RATE)

### Fiat Gateway
- Stripe integration for buying THR with credit/debit cards
- Tiered pricing with volume discounts

---

## 9. AI Ecosystem (Pythia & Pytheia)

### AI Agent Service
- Multi-provider support: OpenAI (GPT-4), Google Gemini, Anthropic Claude, Local LLMs
- Model routing with automatic fallback
- On-chain AI interaction ledger (every query/response recorded)
- AI Credits system for pay-per-use inference

### Pythia AI Node Manager
- 3rd AI node for autonomous site management
- Bug detection and auto-remediation
- AMM optimization and rebalancing
- Code analysis and smart contract auditing

### PYTHEIA Worker (System Health Monitor)
- Continuous monitoring of all endpoints and services
- Automated governance advice generation
- Rate-limited posting to DAO
- Status change detection to minimize noise
- Schema-validated advice documents (PYTHEIA Advice v1.0.0)

### On-Chain AI Developer
- Autonomous code analysis and optimization
- Smart contract creation and deployment
- AI-generated contracts tracked on-chain
- Performance scoring and reward calculations

### Autonomous Trading
- AI-managed treasury (10% fee allocation)
- Rebalancing and yield optimization
- Market-making and liquidity provision

---

## 10. Use Cases

### Crypto Hunters (Play-to-Earn)
A location-based game where players physically move to geo-locations to find hidden "chests". Rewards are paid in THR, driving real-world adoption.

### Learn-to-Earn (L2E)
Educational courses with THR rewards for completion. Quiz system with multiple question types, enrollment tracking, and certificate generation.

### Train-to-Earn (T2E)
IoT/ASIC miners earn rewards for storing AI training data. GPS telemetry from vehicles feeds autonomous driving models.

### Music Platform (Decentralized)
- Artist registration, track uploads, streaming
- 80/10/10 reward split: 80% Artist, 10% Network, 10% AI/T2E
- Tip distribution and royalty payments
- WhisperNote audio encoding integration

### IoT Smart Parking
Real-time parking management with THR payments. Device verification through on-chain VerifyID.

### VerifyID (On-Chain KYC)
- BTC pledge-based identity verification
- PDF contracts with steganographic embedding
- ASIC Proof-of-Work share requirement for finalization
- Recovery protocol via steganography + AES decryption

---

## 11. PhantomFace (Steganography Layer)

The PhantomFace module allows encoding of signed TX data into images (e.g., KYC selfies). Using LSB-based steganography, the block payload is undetectably embedded into visual files.

- Phantom-encoded images appear completely normal
- Once uploaded (e.g., to exchanges), the embedded node gets activated
- Used for stealth propagation of nodes into existing image infrastructure
- Recovery protocol can extract send_secret from PDF/image via AES decryption

---

## 12. Mobile & Native Wallet

### Mobile SDK (React Native)
- Full Android and iOS support
- HD wallet generation with multi-chain support (BTC, ETH, SOL, THR)
- QR scanning and audio transaction capability
- GPS telemetry for T2E integration

### Native Wallet Widget
- Standalone HTML wallet with full modal system
- Token balances, filtering, and selection
- 14-category transaction history (THR, Mining, Tokens, Swaps, L2E, T2E, AI Credits, IoT, Bridge, Liquidity, Gateway, Music, Architect)
- Bridge deposit modal with BTC integration
- Music/Telemetry modal with WhisperNote and GPS
- Multi-language support (Greek, English, Japanese, Russian, Spanish)
- Responsive design with compact mode for embedding
- Memory-optimized (200 transaction limit per view)

### Chrome Extension
- Wallet, balances, send functionality
- dApp provider interface

---

## 13. Blockchain Explorer

Comprehensive block explorer with 9 interactive tabs:
1. **Blocks**: Mining history, rewards, pool burns, AI rewards
2. **Transfers**: All token transfers with volume analytics
3. **Mempool**: Pending transactions with queue position
4. **Live Stats**: Difficulty, hashrate, block time, active miners
5. **Tokens**: All on-chain tokens with holder analytics
6. **Pools**: Liquidity pools with TVL estimation
7. **L2E**: Learn-to-Earn course statistics
8. **Music**: Artist counts, track plays, royalties
9. **VerifyID/T2E**: Device verification, driver stats, GPS telemetry

---

## 14. Deployment Infrastructure

| Service | Platform | Purpose |
|:--------|:---------|:--------|
| Master Node | Railway (G1 Mini) | Chain writer, API, scheduler |
| Replica Node | Railway Cloud | Read-only workers, background jobs |
| Static Frontend | Vercel CDN | Static assets, wallet hosting |
| AI Core | Local (Ryzen 7) | LLM inference, Pytheia monitoring |
| BTC API | btc-api.thronoschain.org | Independent BTC data, no third-party dependency |
| Stratum | Port 3334 | SHA256 mining protocol for ASICs |

---

## 15. Roadmap Summary

| Phase | Version | Status | Key Features |
|:------|:--------|:-------|:-------------|
| Foundation | v1.0-v2.0 | Completed | Core blockchain, THR token, wallet, pledge system |
| DeFi Ecosystem | v3.0-v3.5 | Completed | WBTC, AMM pools, swap, fiat gateway, BTC bridge |
| Platform Expansion | v3.6 | Completed | AI chat, music, L2E, mobile SDK, Chrome extension, IoT |
| Advanced Features | v3.7 | Completed | EVM contracts, Crypto Hunters, BTC withdrawals, i18n |
| Full Decentralization | v4.0 | Completed | Quorum consensus, BLS signatures, validator network |
| AI Autonomy (Pythia) | v5.0 | Completed | AI node manager, autonomous trading, oracle services |
| Music Telemetry & T2E | v5.5 | Completed | 80/10/10 rewards, GPS training, VerifyID integration |
| BTC Bridge & Cross-Chain | v3.6 current | 90% Complete | Multi-sig bridge, Stratum mining, multi-node architecture |
| Survival Blueprint | v3.6 current | In Progress | Audio-Fi, LoRa, solar energy, off-grid operation |
| AI Model Marketplace | v7.0 | Planned Q3-Q4 2026 | Model trading, API credits, inference network |
| Global Scaling | v8.0 | Planned 2027 | Multi-region nodes, IBC, L2 rollups, enterprise |

---

## 16. Hardware Shopping List / Checklist

- [ ] Powered USB Hub (7+ ports) - for ASIC validators
- [ ] RTL-SDR v4 Dongle - for spectrum monitoring
- [ ] LMR-400 Cable for LoRa antenna - for long-range connectivity
- [ ] RS485 to USB Adapter - for solar controller integration
- [ ] Peiko X9 - for audio bridge (pairing with Ryzen 7)
- [ ] Solar Controller (Victron/RS485) - for off-grid operation
- [ ] Additional USB Block Erupters - for identity validation scaling

---

## Developer Guide

- **GitHub Repository**: [Thronos V3.6](https://github.com/Tsipchain/thronos-V3.6)
- **API Documentation**: Available at `/docs` on any running node
- **API Endpoint**: https://api.thronoschain.org
- **Main Site**: https://thronoschain.org
- **Key Scripts**:
  - `iot_vehicle_node.py`: Vehicle telemetry node
  - `watchers_service.py`: BTC deposit watcher
  - `pytheia_worker.py`: System health monitor
  - `phantom_encode.py`: Image steganography encoder
  - `radio_encode.py`: TX-to-audio encoder
  - `qr_to_audio.py`: QR as WAV for transmission
  - `pledge_generator.py`: Signature contract builder

---

## Vision

To establish Thronos as the survival layer of the modern digital world. One that can be:
- Embedded in every image
- Heard in every wave
- Hidden inside every voice
- Spread across every collapse

**"In Crypto we Trust, in Survival we Mine."**

Thronos is not just a blockchain. It's memory against forgetting.

---

*Thronos Chain: Resistance is not futile. It is profitable.*
