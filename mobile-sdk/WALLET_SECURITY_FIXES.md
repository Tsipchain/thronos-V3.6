# Mobile SDK Wallet Security Fixes

## Current Issues

1. **Server-side wallet creation** (line 67)
   - `fetch('/api/wallet/create')` - backend generates wallet
   - Backend knows the secret

2. **Secret transmission** (lines 82, 96)
   - `auth_secret: transaction.secret` in request body
   - Raw secret sent over network

3. **No client-side signing**
   - Wallet operations not signed by device

## Required Changes

### Step 1: Move wallet generation to client

```typescript
// OLD (insecure)
async create() {
  const response = await fetch(`${this.apiUrl}/api/wallet/create`, {
    method: 'POST',
  });
  const data = await response.json();
  const secret = data.secret; // Backend-generated
}

// NEW (secure)
async create() {
  // Generate wallet locally using BIP39/BIP32
  const mnemonic = generateMnemonic();
  const seed = mnemonicToSeed(mnemonic);
  const address = deriveAddress(seed);
  
  // Store locally only
  await this.saveWallet(address, /* no secret */);
  return { address, mnemonic };
}
```

### Step 2: Sign transactions client-side

```typescript
// OLD (insecure)
async send(address, to, amount, secret) {
  return fetch('/api/wallet/send', {
    method: 'POST',
    body: JSON.stringify({
      from: address,
      to: to,
      amount: amount,
      auth_secret: secret  // ❌ Raw secret
    })
  });
}

// NEW (secure)
async send(address, to, amount) {
  // Sign client-side
  const signedTx = await signTransaction({
    from: address,
    to: to,
    amount: amount,
    nonce: Date.now()
  });
  
  return fetch('/api/wallet/send', {
    method: 'POST',
    body: JSON.stringify({
      tx: signedTx  // ✅ Signed envelope only
    })
  });
}
```

### Step 3: Define signature envelope

```typescript
interface SignedTransaction {
  from: string;
  to: string;
  amount: number;
  nonce: number;
  timestamp: number;
  signature: string;      // Device-signed
  publicKey: string;      // Public key for verification
}
```

### Step 4: Never transmit secrets

- ❌ auth_secret parameter
- ❌ send_secret header
- ❌ secret in local storage
- ✅ Signature parameter only
- ✅ Public key parameter only

## Files to Change

1. `src/wallet.js`
   - Remove server-side wallet creation call
   - Add client-side BIP39/BIP32 logic
   - Remove secret from storage

2. `src/api.js`
   - Remove auth_secret from all requests
   - Change to signed envelope submission
   - Add signature verification calls

## Testing Requirements

- [ ] No "secret" in any request body
- [ ] No "mnemonic" in any request body
- [ ] All transactions signed before sending
- [ ] Backend verifies signature
- [ ] Backend rejects unsigned requests
