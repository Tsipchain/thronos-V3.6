# Thronos Wallet Security Architecture (Production-Hardened)

## Overview

This document outlines the production-ready security model for Thronos wallet systems. The fundamental principle is: **No private keys or mnemonics ever leave the client device.**

## Architecture

### 1. Client-Side HD Wallet (BIP39/BIP32)

```
Mnemonic (12/24 words)
    ↓
PBKDF2(mnemonic) → BIP32 Seed
    ↓
Root Key (BIP32)
    ↓
Derivation Path m/44'/1'/0'/0/0
    ↓
Private Key (Client-side only)
    ↓
Public Key (Exported)
    ↓
THR Address (Derived from public key)
```

### 2. Secure Storage

**Storage Locations:**
- Mnemonic: `expo-secure-store` (OS-level keychain)
- Address: `expo-secure-store` (encrypted)
- Public Key: `expo-secure-store` (encrypted)
- Private Key: **NEVER stored** (derived on-demand from mnemonic)

### 3. Transaction Signing Flow

```
User initiates send
    ↓
TX constructed with public data only
    ↓
Client-side signature (Private key stays on device)
    ↓
SignedTransaction envelope created (no secret included)
    ↓
Network POST {signature, publicKey, tx_details}
    ↓
Server verifies signature with public key
    ↓
Server executes if valid
```

### 4. What NEVER Goes Over Network

❌ Private keys
❌ Mnemonics/seed phrases
❌ Unencrypted secrets
❌ Device-specific encryption keys

### 5. What CAN Go Over Network

✅ Public address
✅ Public key (compressed)
✅ Signed transactions
✅ Messages with signature

## API Changes

### Old Pattern (❌ INSECURE)
```typescript
await sendTHR({
  from: 'THR...',
  to: 'THR...',
  amount: 100,
  secret: 'xxx',  // ❌ NEVER DO THIS
});
```

### New Pattern (✅ SECURE)
```typescript
const signedTx = await signThronosTransaction({
  from: walletAddress,
  to: recipientAddress,
  amount: 100,
  nonce: 1,
});

await sendTHRSigned({
  signedTx,
});
```

## Security Guidelines for Developers

### ✅ DO
- Always sign on the client before sending
- Use device-specific encryption for mnemonic storage
- Derive private key from mnemonic only when signing
- Clear private key from memory after signing
- Return only public key in wallet info
- Validate signatures on the backend

### ❌ DON'T
- Pass secrets to any API endpoint
- Log or print private keys
- Send mnemonic over network
- Store unencrypted secrets on device
- Use hard-coded encryption keys
- Trust client-side verification alone
