// Thronos Wallet App - Transaction Signing Service (FIXED - ECDSA/secp256k1)
// Uses real secp256k1 ECDSA signatures (NOT HMAC-SHA256 placeholder)
// All signing operations occur on-device. Private keys never leave the device.

import { ec as EC } from 'elliptic';
import * as crypto from 'crypto';
import { getMnemonic, deriveHDWalletFromMnemonic } from './wallet';

const ec = new EC('secp256k1');

export interface SignedTransaction {
  nonce: string;
  timestamp: number; // UNIX seconds, NOT milliseconds
  from: string;
  to: string;
  amount: number;
  fee?: number;
  token?: string;
  signature: string; // DER-encoded ECDSA signature (hex)
  publicKey: string; // secp256k1 uncompressed public key (hex, 65 bytes)
}

/**
 * Create canonical payload string for signing.
 * Must match backend's canonicalization exactly.
 *
 * Rules:
 * - JSON object with sorted keys
 * - Compact format (no whitespace)
 * - Timestamp must be UNIX seconds (< 1e10), NOT milliseconds
 */
function canonicalPayloadString(payload: {
  from: string;
  to: string;
  amount: number;
  token: string;
  nonce: string;
  timestamp: number;
}): string {
  // Verify timestamp is in seconds, not milliseconds
  if (payload.timestamp > 1e10) {
    throw new Error(
      `Invalid timestamp ${payload.timestamp}: must be UNIX seconds (< 1e10), not milliseconds`
    );
  }

  const obj = {
    amount: payload.amount,
    from: payload.from,
    nonce: payload.nonce,
    timestamp: payload.timestamp,
    to: payload.to,
    token: payload.token,
  };

  // Compact JSON with sorted keys - must match backend exactly
  return JSON.stringify(obj, Object.keys(obj).sort());
}

/**
 * Sign canonical payload with ECDSA/secp256k1 + SHA256.
 */
function signCanonicalPayload(
  canonical: string,
  privateKeyHex: string
): string {
  const canonicalBytes = Buffer.from(canonical, 'utf8');

  // Hash with SHA256
  const hash = crypto.createHash('sha256').update(canonicalBytes).digest();

  // ECDSA sign using secp256k1
  const keyPair = ec.keyFromPrivate(privateKeyHex);
  const signature = keyPair.sign(hash);

  // DER encoding
  return signature.toDER('hex');
}

/**
 * Convert compressed public key to uncompressed format for backend.
 * Backend expects 65-byte uncompressed format (0x04 + 32 bytes X + 32 bytes Y).
 */
function publicKeyCompressedToUncompressed(compressedHex: string): string {
  const keyPair = ec.keyFromPublic(compressedHex, 'hex');
  return keyPair.getPublic('hex'); // Returns uncompressed (65 bytes)
}

/**
 * Sign a Thronos transaction with proper ECDSA/secp256k1.
 *
 * IMPORTANT: timestamp MUST be UNIX seconds (e.g. 1710000000), not milliseconds!
 */
export async function signThronosTransaction(params: {
  from: string;
  to: string;
  amount: number;
  token?: string;
  fee?: number;
  nonce: string;
  timestamp?: number; // UNIX seconds; if not provided, uses current time
}): Promise<SignedTransaction> {
  const mnemonic = await getMnemonic();
  if (!mnemonic) {
    throw new Error('Wallet not initialized. Please create or import a wallet first.');
  }

  const derived = await deriveHDWalletFromMnemonic(mnemonic);

  if (derived.address !== params.from) {
    throw new Error('Wallet address mismatch. Cannot sign for a different address.');
  }

  // Ensure timestamp is UNIX seconds, not milliseconds
  const timestampSeconds = params.timestamp || Math.floor(Date.now() / 1000);
  if (timestampSeconds > 1e10) {
    throw new Error(
      `Timestamp too large: ${timestampSeconds}. Use UNIX seconds (e.g. 1710000000), not milliseconds.`
    );
  }

  // Create canonical payload
  const payload = {
    from: params.from,
    to: params.to,
    amount: params.amount,
    token: params.token || 'THR',
    nonce: params.nonce,
    timestamp: timestampSeconds,
  };

  // Canonicalize for signing
  const canonical = canonicalPayloadString(payload);

  // Sign with ECDSA/secp256k1 (NOT HMAC-SHA256)
  const signature = signCanonicalPayload(canonical, derived.privateKey);

  // Get uncompressed public key for backend
  const publicKeyUncompressed = publicKeyCompressedToUncompressed(derived.publicKey);

  return {
    ...payload,
    signature,
    publicKey: publicKeyUncompressed,
    fee: params.fee || 0,
  };
}

/**
 * Sign a message with proper ECDSA/secp256k1.
 */
export async function signMessage(message: string): Promise<{
  message: string;
  signature: string;
  publicKey: string;
  timestamp: number;
}> {
  const mnemonic = await getMnemonic();
  if (!mnemonic) {
    throw new Error('Wallet not initialized.');
  }

  const derived = await deriveHDWalletFromMnemonic(mnemonic);

  // Hash message
  const messageHash = crypto.createHash('sha256').update(message).digest();

  // ECDSA sign
  const keyPair = ec.keyFromPrivate(derived.privateKey);
  const signature = keyPair.sign(messageHash);
  const signatureHex = signature.toDER('hex');

  const publicKeyUncompressed = publicKeyCompressedToUncompressed(derived.publicKey);

  return {
    message,
    signature: signatureHex,
    publicKey: publicKeyUncompressed,
    timestamp: Math.floor(Date.now() / 1000),
  };
}

/**
 * Verify a signature (for testing).
 */
export function verifySignature(
  message: string,
  signature: string,
  publicKey: string
): boolean {
  try {
    const messageHash = crypto.createHash('sha256').update(message).digest();
    const keyPair = ec.keyFromPublic(publicKey, 'hex');
    return keyPair.verify(messageHash, signature);
  } catch {
    return false;
  }
}
