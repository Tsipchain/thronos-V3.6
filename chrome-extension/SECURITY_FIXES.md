# Chrome Extension Wallet Security Fixes

## Critical Issues

### 1. Secret Stored in chrome.storage.local (Line 240, 274)

```javascript
// ❌ INSECURE
chrome.storage.local.set({ thr_address: address, thr_secret: secret }, ...)
```

**Threats:**
- Storage is persistent across sessions
- Accessible to other extensions if compromised
- Extractable via extension inspection tools

**Fix:**
- Store only address locally
- Never persist secrets
- Keep secrets in memory only

### 2. Secret Displayed in HTML (Line 220-223)

```javascript
// ❌ INSECURE - displayed in popup
<code>${data.secret}</code>
<p>⚠️ Save this secret key securely! You cannot recover it later.</p>
```

**Threats:**
- User can screenshot/screen record
- Visible in browser history
- Accessible via DOM inspection

**Fix:**
- Remove secret display from UI entirely
- Only show address QR code
- Only show mnemonic in explicit backup screen (one-time, not reusable)

### 3. Secret Transmitted to API (Line 28, 354)

```javascript
// ❌ INSECURE
secret: result.thr_secret  // Line 28, sent to backend
secret: currentWallet.secret  // Line 354, sent to backend
```

**Threats:**
- Network interception
- Backend logs may contain secrets
- Man-in-the-middle exposure

**Fix:**
- Never include secret in any request
- Sign transaction client-side
- Send only signature + public key

### 4. No Client-Side Signing

**Current flow:**
Device → Secret → Backend → Sign → Broadcast

**Secure flow:**
Device → Sign locally → Signature → Backend → Verify → Broadcast

## Required Changes

### File: popup.js (Lines to change)

**Change 1: Remove secret storage (Line 240)**

```javascript
// OLD
chrome.storage.local.set({ thr_address: address, thr_secret: secret }, ...)

// NEW
chrome.storage.local.set({ thr_address: address }, ...)
// Secret not stored; generated during transaction signing
```

**Change 2: Remove secret display (Lines 220-223)**

```javascript
// OLD
<code>${data.secret}</code>
<br><br>
<p>⚠️ Save this secret key securely!</p>

// NEW
<!-- Secret never displayed -->
<p>Wallet created. Use this address to receive funds.</p>
```

**Change 3: Remove secret transmission (Line 28)**

```javascript
// OLD
fetch(apiUrl + '/api/wallet/send', {
  method: 'POST',
  body: JSON.stringify({
    from: wallet.address,
    to: recipientAddress,
    amount: amount,
    secret: result.thr_secret  // ❌
  })
})

// NEW
const signedTx = await signTransaction({
  from: wallet.address,
  to: recipientAddress,
  amount: amount,
  nonce: Date.now()
});

fetch(apiUrl + '/api/v1/tx/send', {
  method: 'POST',
  body: JSON.stringify({
    tx: signedTx  // ✅
  })
})
```

**Change 4: Remove secret from memory (Line 354)**

```javascript
// OLD
const secret = document.getElementById('importSecret').value.trim();
fetch(apiUrl + '/api/wallet/send', {
  body: JSON.stringify({
    secret: secret  // ❌
  })
})

// NEW
const walletData = await getWallet(); // From local storage (address only)
const signedTx = await signTransaction({...});
fetch(apiUrl + '/api/v1/tx/send', {
  body: JSON.stringify({
    tx: signedTx  // ✅
  })
})
```

### File: background.js (or create new signing service)

**Add signing function:**

```javascript
async function signTransaction(params) {
  const wallet = await chrome.storage.local.get(['thr_address']);
  
  // Sign locally
  const message = JSON.stringify(params);
  const signature = hmacSign(message, privateKey); // Private key in memory only
  
  return {
    from: params.from,
    to: params.to,
    amount: params.amount,
    nonce: params.nonce,
    timestamp: Date.now(),
    signature: signature,
    publicKey: publicKeyHex
  };
}
```

## Security Requirements

- [ ] No `thr_secret` in chrome.storage.local
- [ ] No secret in any HTML popup display
- [ ] No secret in any API request body
- [ ] All transactions signed before sending
- [ ] Private key only in memory (cleared after use)
- [ ] Backend rejects unsigned or legacy secret requests

## Testing Checklist

```bash
# Check for secret storage
grep -n "thr_secret" chrome-extension/popup.js
# Should return: 0 results

# Check for secret in requests
grep -n "secret:" chrome-extension/popup.js | grep -v "Wallet Secret"
# Should return: 0 results

# Check for secret display in HTML
grep -n "\${data.secret}" chrome-extension/popup.js
# Should return: 0 results
```
