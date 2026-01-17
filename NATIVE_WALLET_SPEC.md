# THRONOS NATIVE WALLET - COMPLETE SPECIFICATION

**Date**: 2026-01-17
**Status**: Ready for Implementation
**Based on**: Existing wallet widget + Mobile SDK

---

## 📱 OVERVIEW

The Thronos Native Wallet is a complete mobile + browser wallet supporting:
- ✅ Multi-chain HD wallets (Thronos, BTC, SOL - coming soon)
- ✅ Cross-chain swaps
- ✅ Liquidity pools
- ✅ RCP-based tokens for bridge
- ✅ T2E integration
- ✅ Beautiful UI (no more widget distortion on mobile!)

---

## 🎯 KEY REQUIREMENTS

### 1. HD Wallet Support

**BIP39/BIP44 Standard**:
```
Mnemonic (12/24 words)
  ↓
Seed
  ↓
Master Private Key
  ↓
Derivation Paths:
  - m/44'/0'/0'/0/0  → Bitcoin
  - m/44'/501'/0'/0' → Solana (future)
  - m/44'/60'/0'/0/0 → Ethereum-like
  - m/44'/9001'/0'/0/0 → Thronos (custom)
```

**Implementation**:
- Use `bip39` for mnemonic generation
- Use `bip32` for key derivation
- Store encrypted seed in secure storage
- Support multiple accounts per chain

### 2. Multi-Token Support

**Native Tokens**:
- THR (Thronos native)
- WBTC (Wrapped Bitcoin via bridge)
- L2E (Learn-to-Earn)
- T2E (Train-to-Earn) ← **NEW!**

**Custom Tokens**:
- ERC20-like standard
- User-created tokens
- Auto-detection from blockchain

**RCP Tokens** (for Bridge):
- Configure RCP endpoints
- Support BTC, ETH, SOL (future)
- Real-time balance queries

### 3. Cross-Chain Swap

**Swap Interface**:
```
FROM: [Token A ▼]  Amount: [___]
TO:   [Token B ▼]  Amount: [___]

Price: 1 THR = 0.0001 BTC
Slippage: 0.5%
Fee: 0.09% (Slow) | 0.5% (Fast)

[SWAP NOW]
```

**Supported Swaps**:
- THR ↔ Custom Tokens (via DEX pools)
- THR ↔ WBTC (via bridge)
- WBTC ↔ BTC (via atomic swap)
- SOL ↔ THR (future)

**API Integration**:
- `/api/v1/pools/swap` - Execute swap
- `/api/prices/convert` - Get conversion rates
- `/api/bridge/...` - Bridge operations

### 4. Liquidity Pools

**Pool Interface**:
```
ADD LIQUIDITY
Token A: THR     Amount: [___]
Token B: CUSTOM  Amount: [___]

Pool Share: 2.5%
LP Tokens: 125.4

[ADD LIQUIDITY]
```

**Pool Operations**:
- View all pools (`/api/v1/pools`)
- Add liquidity
- Remove liquidity
- Claim fees

### 5. T2E Integration

**T2E Dashboard**:
```
T2E Balance: 45.7 T2E
Projects Completed: 3
Multiplier: 1.6x
Total Earned: 120.3 T2E

[VIEW HISTORY]
```

**T2E Earning Methods**:
- Architect project generation
- Thumbs up on helpful AI responses
- Manual contributions (code, docs, datasets)

**API Endpoints**:
- `GET /api/t2e/balance/<wallet>` ← **NEW!**
- `GET /api/architect_t2e_history/<wallet>` ← **NEW!**

---

## 🏗️ ARCHITECTURE

### File Structure

```
mobile-wallet/
├── src/
│   ├── screens/
│   │   ├── WalletHome.tsx       # Main wallet view
│   │   ├── SendTokens.tsx       # Send interface
│   │   ├── ReceiveTokens.tsx    # Receive/QR code
│   │   ├── SwapTokens.tsx       # Cross-swap
│   │   ├── Pools.tsx            # Liquidity pools
│   │   ├── T2EDashboard.tsx     # T2E tracking
│   │   ├── History.tsx          # Transaction history
│   │   └── Settings.tsx         # Wallet settings
│   ├── components/
│   │   ├── TokenList.tsx        # Token balance list
│   │   ├── TransactionItem.tsx  # TX list item
│   │   ├── PoolCard.tsx         # Pool display
│   │   └── T2EStats.tsx         # T2E statistics
│   ├── services/
│   │   ├── WalletService.ts     # HD wallet ops
│   │   ├── APIService.ts        # Backend communication
│   │   ├── SwapService.ts       # Swap logic
│   │   └── PoolService.ts       # Pool operations
│   └── utils/
│       ├── bip39.ts             # Mnemonic generation
│       ├── bip32.ts             # Key derivation
│       ├── encryption.ts        # Secure storage
│       └── formatters.ts        # Display helpers
├── android/                     # Android-specific code
├── ios/                         # iOS-specific code
└── package.json
```

### State Management

**Use Redux/Zustand**:
```typescript
interface WalletState {
  // Wallet
  mnemonic?: string;
  addresses: {
    thronos: string;
    bitcoin?: string;
    solana?: string;
  };

  // Balances
  tokens: {
    symbol: string;
    balance: number;
    logo?: string;
  }[];

  // T2E
  t2e: {
    balance: number;
    projectsCompleted: number;
    multiplier: number;
  };

  // Pools
  pools: Pool[];

  // History
  transactions: Transaction[];
}
```

---

## 🔐 SECURITY

### Seed Storage

**React Native**:
```typescript
import * as SecureStore from 'expo-secure-store';

// Save
await SecureStore.setItemAsync('wallet_seed', encryptedSeed);

// Load
const seed = await SecureStore.getItemAsync('wallet_seed');
```

**iOS (Keychain)**:
```swift
let query = [
    kSecClass: kSecClassGenericPassword,
    kSecAttrAccount: "thronos_seed",
    kSecValueData: encryptedData
] as CFDictionary

SecItemAdd(query, nil)
```

**Android (EncryptedSharedPreferences)**:
```kotlin
val masterKey = MasterKey.Builder(context)
    .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
    .build()

val prefs = EncryptedSharedPreferences.create(
    context,
    "thronos_wallet",
    masterKey,
    EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
    EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
)
```

### Biometric Auth

**React Native**:
```typescript
import * as LocalAuthentication from 'expo-local-authentication';

const authenticate = async () => {
  const result = await LocalAuthentication.authenticateAsync({
    promptMessage: 'Unlock Thronos Wallet',
    fallbackLabel: 'Use Passcode'
  });

  return result.success;
};
```

---

## 🎨 UI/UX DESIGN

### Theme (Thronos Brand)

```typescript
const theme = {
  colors: {
    primary: '#00ff66',      // Thronos green
    secondary: '#ffd700',    // Gold
    background: '#000000',   // Black
    surface: '#071810',      // Dark green
    text: '#e6ffe5',         // Light green
    error: '#ff4d4d'
  },
  gradients: {
    primary: 'linear-gradient(135deg, #d4af37 0%, #00ff66 50%, #ffd700 100%)',
    background: 'linear-gradient(135deg, #000000 0%, #071810 50%, #000000 100%)'
  }
};
```

### Screens

#### 1. Wallet Home
```
┌──────────────────────────────┐
│ THRONOS WALLET       ☰       │
├──────────────────────────────┤
│                              │
│   Total Value                │
│   $1,234.56                  │
│   ≈ 12.345 THR               │
│                              │
├──────────────────────────────┤
│                              │
│  📊 THR          125.4       │
│  💰 WBTC         0.025       │
│  🎓 T2E          45.7        │
│  📚 L2E          12.0        │
│                              │
│  [+ Add Token]               │
│                              │
├──────────────────────────────┤
│                              │
│ [📤 Send] [📥 Receive]       │
│ [🔄 Swap] [💧 Pools]         │
│                              │
└──────────────────────────────┘
```

#### 2. Cross-Swap
```
┌──────────────────────────────┐
│ ← SWAP                       │
├──────────────────────────────┤
│ FROM                         │
│ ┌──────────────────────────┐│
│ │ THR ▼        [MAX]       ││
│ │ 100.0                    ││
│ │ ≈ $0.01 USD              ││
│ └──────────────────────────┘│
│              ⇅               │
│ TO                           │
│ ┌──────────────────────────┐│
│ │ CUSTOM ▼                 ││
│ │ 950.2                    ││
│ │ ≈ $0.095 USD             ││
│ └──────────────────────────┘│
│                              │
│ Price: 1 THR = 9.502 CUSTOM  │
│ Slippage: 0.5%               │
│ Fee: 0.09%                   │
│                              │
│ [SWAP NOW]                   │
└──────────────────────────────┘
```

#### 3. T2E Dashboard
```
┌──────────────────────────────┐
│ ← TRAIN-TO-EARN              │
├──────────────────────────────┤
│                              │
│ T2E Balance: 45.7 T2E        │
│ Worth: 4.57 THR (approx)     │
│                              │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                              │
│ Projects Completed: 3        │
│ Current Multiplier: 1.6x     │
│ Next Level: 5 projects → 2.0x│
│                              │
│ Total Earned: 120.3 T2E      │
│ Total Spent (THR): 0.45 THR  │
│                              │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                              │
│ Earning Methods:             │
│ 🏗️  Architect Projects       │
│ 👍 Helpful AI Responses      │
│ 💡 Manual Contributions      │
│                              │
│ [VIEW HISTORY]               │
│ [CONTRIBUTE NOW]             │
└──────────────────────────────┘
```

---

## 🔌 API ENDPOINTS (New/Updated)

### T2E Endpoints

```typescript
// Get T2E balance
GET /api/t2e/balance/<wallet>
Response: {
  balance: 45.7,
  projects_completed: 3,
  multiplier: 1.6,
  total_earned: 120.3,
  total_thr_spent: 0.45
}

// Get T2E history
GET /api/architect_t2e_history/<wallet>
Response: {
  wallet: "THR...",
  projects: [
    {
      session_id: "sess_123",
      blueprint: "web_app_fullstack.md",
      timestamp: "2026-01-17T12:00:00Z",
      thr_spent: 0.15,
      t2e_earned: 1.5,
      multiplier: 1.0
    }
  ]
}
```

### Swap Endpoints

```typescript
// Get swap quote
POST /api/swap/quote
Body: {
  from_token: "THR",
  to_token: "CUSTOM",
  amount: 100.0
}
Response: {
  from_amount: 100.0,
  to_amount: 950.2,
  price: 9.502,
  slippage: 0.5,
  fee: 0.09,
  route: ["THR", "POOL_THR_CUSTOM", "CUSTOM"]
}

// Execute swap
POST /api/swap/execute
Body: {
  wallet: "THR...",
  from_token: "THR",
  to_token: "CUSTOM",
  amount: 100.0,
  min_received: 940.0,
  auth_secret: "..."
}
```

---

## 📦 IMPLEMENTATION PLAN

### Phase 1: Core Wallet (Week 1)
- [x] HD wallet generation (BIP39/BIP44)
- [x] Secure storage
- [ ] Token balance display
- [ ] Send/Receive UI
- [ ] Transaction history

### Phase 2: T2E Integration (Week 2)
- [ ] T2E balance API
- [ ] T2E dashboard UI
- [ ] Project history display
- [ ] Contribution interface

### Phase 3: Cross-Swap (Week 3)
- [ ] Swap quote API
- [ ] Swap execution
- [ ] Price oracle integration
- [ ] Slippage protection

### Phase 4: Pools (Week 4)
- [ ] Pool listing
- [ ] Add/Remove liquidity
- [ ] LP token tracking
- [ ] Fee claiming

### Phase 5: Multi-Chain (Week 5+)
- [ ] Bitcoin integration (via RCP)
- [ ] SOL integration (future)
- [ ] Cross-chain bridge UI

---

## 🧪 TESTING CHECKLIST

### Wallet Operations
- [ ] Create wallet (12-word mnemonic)
- [ ] Restore wallet from mnemonic
- [ ] View balances (all tokens)
- [ ] Send THR
- [ ] Send custom token
- [ ] Receive (QR code generation)
- [ ] Transaction history loads correctly

### T2E System
- [ ] T2E balance displays correctly
- [ ] Multiplier updates after Architect use
- [ ] Thumbs up rewards 0.5 T2E
- [ ] History shows all projects

### Swap/Pools
- [ ] Swap quote calculates correctly
- [ ] Swap executes successfully
- [ ] Pool balances update
- [ ] LP tokens tracked

### Security
- [ ] Biometric auth works
- [ ] Seed never exposed
- [ ] Encrypted storage verified
- [ ] Private keys never transmitted

---

## 📝 EXAMPLE CODE

### Wallet Creation

```typescript
import { generateMnemonic, mnemonicToSeed } from 'bip39';
import HDKey from 'hdkey';
import * as SecureStore from 'expo-secure-store';
import CryptoJS from 'crypto-js';

async function createWallet(password: string) {
  // Generate mnemonic
  const mnemonic = generateMnemonic(128); // 12 words

  // Convert to seed
  const seed = await mnemonicToSeed(mnemonic);

  // Derive Thronos address (m/44'/9001'/0'/0/0)
  const root = HDKey.fromMasterSeed(seed);
  const thronos = root.derive("m/44'/9001'/0'/0/0");
  const address = `THR${thronos.publicKey.toString('hex').substring(0, 33)}`;

  // Encrypt mnemonic
  const encrypted = CryptoJS.AES.encrypt(mnemonic, password).toString();

  // Store securely
  await SecureStore.setItemAsync('wallet_mnemonic', encrypted);
  await SecureStore.setItemAsync('wallet_address', address);

  return {
    mnemonic, // Show once, then destroy!
    address,
    privateKey: thronos.privateKey.toString('hex')
  };
}
```

### T2E Balance Fetch

```typescript
async function getT2EBalance(wallet: string) {
  const response = await fetch(`${API_URL}/api/t2e/balance/${wallet}`);
  const data = await response.json();

  return {
    balance: data.balance,
    projectsCompleted: data.projects_completed,
    multiplier: data.multiplier,
    totalEarned: data.total_earned
  };
}
```

### Swap Execution

```typescript
async function executeSwap(params: {
  wallet: string;
  fromToken: string;
  toToken: string;
  amount: number;
  authSecret: string;
}) {
  // Get quote first
  const quote = await fetch(`${API_URL}/api/swap/quote`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      from_token: params.fromToken,
      to_token: params.toToken,
      amount: params.amount
    })
  }).then(r => r.json());

  // Execute with slippage protection
  const minReceived = quote.to_amount * 0.995; // 0.5% slippage tolerance

  const result = await fetch(`${API_URL}/api/swap/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      wallet: params.wallet,
      from_token: params.fromToken,
      to_token: params.toToken,
      amount: params.amount,
      min_received: minReceived,
      auth_secret: params.authSecret
    })
  }).then(r => r.json());

  return result;
}
```

---

## 🚀 DEPLOYMENT

### App Store Requirements
- [ ] iOS App Store submission
- [ ] Android Play Store submission
- [ ] Privacy policy
- [ ] Terms of service
- [ ] App screenshots
- [ ] App description

### Distribution
- [ ] TestFlight (iOS beta)
- [ ] APK direct download
- [ ] Play Store release
- [ ] Web PWA version

---

## 📊 SUCCESS METRICS

### KPIs
- Daily Active Users (DAU)
- Transaction Volume
- T2E participation rate
- Swap volume
- Pool liquidity

### Goals (3 months)
- 1,000+ downloads
- 100+ daily active users
- $10,000+ swap volume
- 500+ T2E contributions

---

## ✅ READY FOR DEVELOPMENT!

This specification provides everything needed to build a complete native Thronos wallet that:
- Fixes mobile widget distortion
- Supports HD wallets
- Enables cross-swaps
- Integrates pools
- Tracks T2E earnings
- Prepares for SOL integration

**Next Steps**:
1. Set up React Native project
2. Implement core wallet (Phase 1)
3. Add T2E dashboard (Phase 2)
4. Integrate swaps/pools (Phases 3-4)
5. Launch beta!

**Timeline**: 5 weeks to MVP, 8 weeks to full release

🚀 **Let's build the best mobile crypto wallet!**
