# Thronos Architecture: Separated Flows

**Updated:** May 16, 2026  
**Status:** Clean separation of concerns - Pledge System, CEX LP Agent, Native Bridge

---

## The Problem We Solved

Previously, the architecture mixed multiple flows:
- **Pledge System** (user deposits) was queueing Stellar settlements
- **CEX deposits** were using Stellar + USDC conversion (overcomplicated)
- **Native bridge** (Liquidity Pool) was undefined

**Result:** Confusion between systems, unclear data flow

---

## The Solution: Three Separated Systems

### 1️⃣ **Pledge System** (Phase 1B-2)
**User deposits through Thronos UI**

```
User → Unique Address (BIP32) 
     → BTC Deposit 
     → Message Signing (BIP-191)
     → ✅ Instant THR Mint
     → DONE
```

**No Stellar, no async settlement required**
- Files: `bip32_deposit_manager.py`, `bitcoin_pledge_verifier.py`
- Endpoint: `POST /api/pledge/verify-signature`
- Response: Direct THR minting confirmation

---

### 2️⃣ **CEX LP Agent** (Liquidity Pool)
**Autonomous detection of major exchange deposits**

```
CEX Deposit (Binance, MEXC, Kraken, Bybit, OKX)
     → 24/7 Monitoring
     → Linked Thronos account check
     → User KYC verification (1h cache)
     → ✅ LP Conversion: BTC → THR
     → Notification to user
     → DONE
```

**Uses native Liquidity Pool for conversion rates**
- Files: `cex_lp_agent.py`, `bridge_coordinator.py`
- Flow: Deposit detection → KYC check → LP swap → THR minting
- Endpoints: `/api/cex/task/status/<id>`, `/api/cex/pending`, `/api/cex/stats`
- Rate: Uses pool's current exchange rate (dynamic)

---

### 3️⃣ **Stellar Bridge** (Optional)
**Background liquidity management**

```
When: LP reserves get low
     → Stellar network transfer
     → Refill BTC/THR reserves
     → Maintain LP health
     → LOOP
```

**Not part of user-facing flow**
- Files: `stellar_bridge_coordinator.py`
- Purpose: Autonomous liquidity top-up
- Not exposed to users (background process)

---

## Data Flows

### Pledge Deposit (Direct to Thronos)
```
1. User: GET /api/pledge/deposit-address
2. System: Returns unique BTC address (BIP32 derived)
3. User: Sends BTC to address
4. User: GET /api/pledge/get-message-to-sign
5. System: Returns message with THR address, amount, TX ID
6. User: Signs message (BIP-191 with private key)
7. User: POST /api/pledge/verify-signature
8. System: ✅ Verifies signature, mints THR
9. User: Receives THR in wallet
```

**Timeline:** ~2 confirmations + user action time

---

### CEX Deposit (Autonomous)
```
1. User: Deposits BTC to Binance/MEXC/Kraken/Bybit/OKX
2. CEX: Records deposit
3. Agent (every 5 min): Scans CEX APIs
4. Agent: Detects deposit from user email
5. Agent: Checks: Is email linked to Thronos? ✅
6. Agent: Checks: KYC verified? (cache 1h) ✅
7. Agent: Uses LP to swap BTC → THR
8. Agent: Mints THR to user address
9. User: Gets email notification
10. User: Sees balance update in wallet
```

**Timeline:** ~5 minutes (next monitoring cycle)  
**User Action Required:** 0 steps after initial setup

---

### LP Liquidity Management (Background)
```
1. Stellar coordinator monitors: LP reserve levels
2. If reserves low: Initiate Stellar transfer
3. Receive USDC on Stellar network
4. Convert to BTC (if needed)
5. Replenish LP reserves
6. Loop continues
```

**Timeline:** Hourly check, on-demand when needed  
**Visibility:** Internal process (not user-facing)

---

## Three Key Separations

### Separation 1: Pledge ≠ CEX
- **Pledge:** User explicitly sends BTC through Thronos UI
- **CEX:** User deposits on exchange, we auto-detect

### Separation 2: Direct Mint ≠ LP Swap
- **Pledge:** Direct THR minting (instant)
- **CEX:** Use Liquidity Pool exchange rate

### Separation 3: User Flow ≠ Background Process
- **User Flow:** Pledge + CEX (both complete in minutes)
- **Background:** Stellar replenishment (happens continuously)

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    THRONOS SYSTEM                       │
└─────────────────────────────────────────────────────────┘

┌──────────────────────────┐
│   PLEDGE SYSTEM          │  USER DEPOSITS (Thronos UI)
│  (Phase 1B-2)            │  ✓ Instant THR
├──────────────────────────┤  ✓ Direct minting
│ BIP32 Addresses          │
│ Message Signing (BIP191) │
│ Instant Minting          │
└──────────────────────────┘

┌──────────────────────────┐
│   CEX LP AGENT           │  EXCHANGE DEPOSITS (Auto-detect)
│  (Autonomous)            │  ✓ ~5 min detection
├──────────────────────────┤  ✓ KYC verified
│ Exchange Monitoring      │  ✓ LP-based rate
│ KYC Verification         │  ✓ Auto-minting
│ Liquidity Pool Swaps     │
└──────────────────────────┘
          ↓ uses ↓
┌──────────────────────────┐
│   NATIVE BRIDGE          │  LIQUIDITY POOL
│  (Liquidity Pools)       │  ✓ BTC ⟷ THR rates
├──────────────────────────┤  ✓ Slippage fees
│ Bitcoin-Thronos Pool     │  ✓ Provider shares
│ Dynamic rates            │
│ Volume tracking          │
└──────────────────────────┘
          ↑ refilled by ↑
┌──────────────────────────┐
│   STELLAR BRIDGE         │  BACKGROUND PROCESS
│  (Optional)              │  ✓ LP liquidity top-up
├──────────────────────────┤  ✓ Not user-facing
│ USDC on Stellar network  │  ✓ Hourly checks
│ LP reserve management    │
│ Automatic top-ups        │
└──────────────────────────┘
```

---

## Configuration

### Pledge System
```python
MIN_AMOUNT = Decimal("0.00001")      # ~$0.50 minimum
THR_BTC_RATE = 10000                 # 1 BTC = 10,000 THR
```

### CEX LP Agent
```python
MONITORING_INTERVAL = 300            # Check every 5 minutes
KYC_CACHE_TTL = 3600                 # Cache KYC for 1 hour
MIN_AUTO_DEPOSIT = Decimal("0.00005") # ~$2 minimum
```

### Stellar Bridge (Optional)
```python
STELLAR_NETWORK = "testnet"          # Production: "public"
STELLAR_USDC_ISSUER = "..."          # USDC contract
```

---

## Hot Wallet Problem (SOLVED)

**Why CEX deposits are different:**

Major exchanges (Binance, MEXC, etc.) use **hot wallets** for deposits. This creates a validation problem:

```
❌ WRONG: Direct blocklist of hot wallets
   Problem: Can't verify user ownership

✅ RIGHT: Detect via exchange API + user email
   Method: Link email to Thronos → Auto-mint
```

**The CEX LP Agent solves this by:**
1. Detecting deposits via exchange API (not blockchain)
2. Linking user email to Thronos account
3. Verifying KYC on the exchange (they already did it)
4. Minting THR directly to user's Thronos address

---

## API Endpoints

### Pledge System
- `GET /api/pledge/deposit-address` - Get unique BTC address
- `GET /api/pledge/get-message-to-sign` - Get message for signing
- `POST /api/pledge/verify-signature` - Verify and mint THR

### CEX LP Agent
- `GET /api/cex/task/status/<task_id>` - Check conversion status
- `GET /api/cex/pending` - List pending conversions
- `GET /api/cex/stats` - Agent statistics

### Native Bridge
- `GET /api/bridge/stats` - Pool statistics
- `POST /api/bridge/burn` - Burn THR for BTC
- `GET /api/bridge/history/<address>` - Transaction history

---

## Success Metrics

### Pledge System
- Users: Can verify BTC ownership in <5 minutes
- Conversion: 100% automated (signature verification + instant mint)
- Reliability: No external dependencies (standalone)

### CEX LP Agent
- Detection: All major exchanges (5 platforms)
- Latency: <5 minutes from deposit to THR mint
- User action: 0 steps (completely autonomous)
- KYC: Leverages exchange verification (no duplication)

### LP Health
- Reserves: Monitored and maintained 24/7
- Liquidity: Automatic top-up via Stellar
- Fees: 0.25% slippage (competitive)

---

## Files Organization

```
Core Files:
├── bip32_deposit_manager.py      # Phase 1B: Unique addresses
├── bitcoin_pledge_verifier.py    # Phase 2: Message signing
├── cex_lp_agent.py               # CEX detection + LP conversion
├── bridge_coordinator.py         # Native bridge + LP management
├── stellar_bridge_coordinator.py # Optional liquidity top-up

API Integration:
├── server.py                      # All endpoints wired
│   ├── Pledge endpoints (Phase 1-2)
│   ├── CEX endpoints (LP Agent)
│   └── Bridge endpoints (Native)

UI:
├── templates/bridge.html         # Bridge UI
├── templates/explorer.html       # System status
└── public/static/wallet_sdk.js  # Wallet SDK
```

---

## What Changed

### Before
```
Pledge System → [verification] → Queue Stellar settlement
CEX Agent → [Detect] → Stellar + USDC conversion
Native Bridge → [LP] → Unused/undefined
```

**Problem:** 3 paths, 2 different settlement mechanisms

### After
```
Pledge System → [verification] → ✅ Instant THR mint
CEX Agent → [Detect] → ✅ LP conversion → THR mint
Native Bridge → [LP] → ✅ Primary mechanism + optional Stellar
```

**Solution:** 2 user flows (Pledge + CEX auto), 1 primary mechanism (LP)

---

## Future Enhancements

- [ ] More exchange integrations (Huobi, Gateio, Crypto.com)
- [ ] Batch verification (multiple users per cycle)
- [ ] Advanced LP strategies (dynamic fees, automated market making)
- [ ] Cross-chain liquidity (ETH, SOL, ATOM bridges)
- [ ] Anomaly detection (Pytheia AI monitoring)

---

**Last Updated:** May 16, 2026  
**Status:** Fully operational and documented
