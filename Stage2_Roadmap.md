# Thronos Chain - Stage 2 Roadmap: Expansion & Utility

This roadmap outlines the next phase of development for the Thronos Chain, focusing on utility, gaming integration, and real-world value connection.

## ✅ Completed
- [x] **Core Upgrade (v2.0)**: Implemented secure PDF contracts, steganography recovery, and bilingual UI.
- [x] **Miner Kit**: Released CPU miner and Stratum proxy for ASIC support.
- [x] **AI Agent Prototype**: Created the base for the autonomous agent "Pythia".
- [x] **Fee Logic Update**: Implemented 80% Miner / 10% AI / 10% Burn reward split.
- [x] **BTC Value Display**: Added BTC exchange rate display in Wallet and Home (Peg: 1 THR = 0.0001 BTC).

## 🚧 In Progress
- [ ] **Crypto Hunters Integration**:
    - Deploy backend (`drx.js`) on the main server.
    - Connect game economy to Thronos Chain (Play-to-Earn).
    - Release Mobile App Demo (.apk).
- [ ] **Watcher Service**:
    - Fully implement `verify_btc_payment` to automate BTC deposit verification.
    - Monitor BTC network for "Burn-to-Mint" transactions.

## 🔮 BTC Fork & Off-Chain Cash Integration (The "Hard Fork" Goal)

Our ultimate vision is to function as a specialized execution layer (or "Fork") of Bitcoin, enabling instant liquidity and real-world utility.

### 1. Atomic Swaps / Bridge
*Objective: Instant, trustless conversion between BTC and THR.*
- **Mechanism**: We will implement Hashed TimeLock Contracts (HTLCs) or a simplified "Vault" system.
- **Flow**: Users lock BTC in a designated Vault address -> Thronos Chain mints equivalent THR. Conversely, burning THR releases BTC from the Vault.

### 2. The Watcher Role
*Objective: The bridge between on-chain Bitcoin and Thronos Chain.*
- **Function**: The Watcher is a decentralized service that monitors the Bitcoin Mainnet.
- **Verification**: It verifies payments to the Vault or specific "Burn" addresses and automatically triggers the release of THR assets or game items.

### 3. Cash Out & Off-Chain Agents
*Objective: Turning digital assets into physical reality.*
- **Off-Chain Agents**: Trusted nodes (ATMs or human agents) that accept THR transfers and dispense cash.
- **Integration**: The AI Agent will manage liquidity pools to ensure these agents are funded, effectively creating a distributed ATM network for Bitcoin via Thronos.

## 📅 Upcoming Features (Q1 2025)

### AI Agent Evolution ("Pythia")
- **Autonomous Trading**: Allow the AI to manage its own 10% fee treasury to buy/sell assets or reward specific network behaviors.
- **Oracle Services**: The AI will verify real-world data (e.g., BTC price, game results) and post it to the Thronos Chain.

### Mobile Wallet App
- Native Android/iOS app for managing THR, scanning QRs, and playing Crypto Hunters.

### Decentralized Governance
- Allow THR holders to vote on network parameters (fee rates, burn rates) using signed messages.

---
*Thronos Chain: Resistance is not futile. It is profitable.*