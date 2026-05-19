#!/usr/bin/env node
/**
 * Generate Fresh Wallet V1 Signed Transaction
 *
 * Generates a valid ECDSA/secp256k1 signed transaction with:
 * - Current UNIX timestamp (within ±5 minute validity window)
 * - Fresh unique nonce
 * - Correct from address derived from compressed publicKey
 * - DER-encoded ECDSA signature
 *
 * Usage:
 *   node scripts/generate-fresh-wallet-v1-tx.js > valid-tx.json
 *   curl -i -X POST "$STAGING_URL/api/v1/tx/send" \
 *     -H "Content-Type: application/json" \
 *     --data-binary "@valid-tx.json"
 */

const elliptic = require('elliptic');
const crypto = require('crypto');

const ec = new elliptic.ec('secp256k1');

// Golden Vector 1 - Private key and compressed public key
const privateKeyHex = 'c9f6f913d0dbd9860690b01b2a3e4fe40f2582f539860dd8a8d9999e9d12b3cd';
const publicKeyCompressed = '0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798';

// Derive correct address from public key
const publicKeyBuffer = Buffer.from(publicKeyCompressed, 'hex');
const sha256Hash = crypto.createHash('sha256').update(publicKeyBuffer).digest();
const ripemd160 = crypto.createHash('ripemd160').update(sha256Hash).digest('hex');
const correctAddress = 'THR' + ripemd160.substring(0, 40).toUpperCase();

// Generate fresh timestamp and nonce
const now = Math.floor(Date.now() / 1000);
const nonce = `tx_staging_${now}`;

// Create transaction payload
const txPayload = {
  from: correctAddress,
  to: 'THRC0FFEE0C0FFEE0C0FFEE0C0FFEE0C0FF',
  amount: 100,
  token: 'THR',
  nonce: nonce,
  timestamp: now
};

// Create canonical payload string with sorted keys
const obj = {
  amount: txPayload.amount,
  from: txPayload.from,
  nonce: txPayload.nonce,
  timestamp: txPayload.timestamp,
  to: txPayload.to,
  token: txPayload.token,
};

const canonical = JSON.stringify(obj, Object.keys(obj).sort());

// Hash with SHA256
const canonicalBytes = Buffer.from(canonical, 'utf8');
const hash = crypto.createHash('sha256').update(canonicalBytes).digest();

// ECDSA sign with secp256k1
const keyPair = ec.keyFromPrivate(privateKeyHex);
const signature = keyPair.sign(hash);
const signatureHex = signature.toDER('hex');

// Output signed transaction (to stdout as JSON)
const signedTx = {
  tx: {
    from: txPayload.from,
    to: txPayload.to,
    amount: txPayload.amount,
    token: txPayload.token,
    nonce: txPayload.nonce,
    timestamp: txPayload.timestamp,
    signature: signatureHex,
    publicKey: publicKeyCompressed
  }
};

console.log(JSON.stringify(signedTx, null, 2));
