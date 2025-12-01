# Thronos Chain & THR Token - Complete Whitepaper

## 🔥 Introduction

Thronos Chain is a next-generation, SHA256-based blockchain project focused on survivability, decentralization, and freedom. It merges the core values of Bitcoin with innovative data transport technologies and fully offline, censorship-resistant communication.

---

## ⚙️ Technical Characteristics

- **Algorithm**: SHA256 (Bitcoin-compatible)
- **Compatibility**: Works with existing ASIC miners (Antminers)
- **Transaction Speed**: Instant finality through asynchronous node syncing
- **Fees**: Ultra-low fees comparable to XRP
- **Smart Signing**: TXs are signed and distributed via multiple real-world mediums (images, audio, QR, etc.)

---

## ⚖️ Governance & Management

Thronos Chain introduces a decentralized governance model where THR holders can vote on critical network parameters (e.g., fee limits, protocol upgrades). Voting is conducted via Signed Governance Messages recorded on the blockchain, ensuring transparency and immutability.

---

## 📈 Detailed Tokenomics

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

## 💡 Use Cases

### 1. Crypto Hunters Game
A Play-to-Earn game where players physically move to specific geo-locations to find hidden "chests". Rewards are paid in THR, driving real-world adoption and movement.

### 2. Offline Payments
Enables financial transactions in areas without internet access using QR codes and audio signal transmission.

### 3. IoT Vehicle Nodes
Vehicles act as mobile nodes, collecting telemetry data (GPS, speed) and transmitting it via steganography (embedded in images) to the network. This creates a moving mesh network of validators.

---

## 🌉 Bitcoin Bridge (Watcher Service)

Connection to the Bitcoin network is achieved through a trustless bridge mechanism:

- **Watcher Service**: An automated service that monitors specific Bitcoin addresses. When a deposit is detected, it validates the transaction and automatically mints the equivalent amount of THR to the user's Thronos wallet.
- **Atomic Swaps**: Future implementation will allow direct, peer-to-peer exchange of BTC and THR using Hashed Time-Lock Contracts (HTLC), removing the need for centralized intermediaries.

---

## 🛡️ Security & Compatibility

- **Audits**: The Thronos codebase is Open Source and subject to continuous review by the community and automated AI agents.
- **BTC Fork Compatibility**: Thronos shares the SHA256 architecture with Bitcoin, making it compatible with existing mining hardware (Antminers) and pools, ensuring a robust hashrate from day one.

---

## 💻 Developer Guide

Developers are encouraged to build on top of Thronos.

- **GitHub Repository**: [Thronos V2](https://github.com/Tsipchain/thronos-V2)
- **API Documentation**: Available at `/docs` on any running node.
- **Key Scripts**:
  - `iot_vehicle_node.py`: Python script for integrating vehicles as nodes.
  - `watchers_service.py`: Service for monitoring BTC deposits.

---

## 🧬 PhantomFace (Steganography Layer)

The PhantomFace module allows encoding of signed TX data into images (e.g., KYC selfies). Using LSB-based steganography, the block payload is undetectably embedded into visual files.

- Phantom-encoded images look normal.
- Once uploaded (e.g., to exchanges), the node gets activated.
- Used for stealth propagation of nodes into existing image infrastructure.

---

## 🔊 WhisperNote & RadioNode

- **WhisperNote**: Uses sound waves to carry block payloads encoded via tone-shifting. WAV files created with encoded TXs can be played via speakers or embedded in videos.
- **RadioNode**: Support for **offline propagation** through RF-based transmission. Nodes communicate via radio without need for internet or power grid.

---

## 🗺️ Roadmap Milestones

| Phase | Status | Description |
| :--- | :--- | :--- |
| **Core v2.0** | ✅ Completed | Stealth propagation, PDF Pledge, Bilingual UI |
| **Miner Kit** | ✅ Completed | CPU/ASIC Mining Support |
| **AI Agent** | ✅ Completed | Pythia Prototype, Stats Analysis |
| **Bridge & Watcher** | 🔄 In Progress | BTC-THR Bridge, Watcher Service |
| **Crypto Hunters** | 🔄 In Progress | Game Integration, Mobile App |
| **IoT Nodes** | 🔜 Upcoming | Vehicle Nodes, ATM Agents |

---

## 🎯 Vision

To establish Thronos as the survival layer of the modern digital world. One that can be:
- Embedded in every image
- Heard in every wave
- Hidden inside every voice
- Spread across every collapse

**Thronos is not just a blockchain. It's memory against forgetting.**

---

## 📎 Appendix

- `phantom_encode.py`: Image steganography encoder
- `watchers_service.py`: BTC Bridge Watcher
- `iot_vehicle_node.py`: Vehicle Telemetry Node
- `radio_encode.py`: TX-to-audio encoder
- `qr_to_audio.py`: QR as WAV for transmission
- `pledge_generator.py`: Signature contract builder