/**
 * Thronos Transaction Signing Service (Client-Side Only)
 * ECDSA/secp256k1 signing with SHA256 hashing
 * Private keys never leave the device.
 */

import { ec as EC } from 'elliptic';
import * as crypto from 'crypto';
import { getMnemonic, deriveHDWalletFromMnemonic } from './wallet';

const ec = new EC('secp256k1');

export interface SignedTransaction {
  nonce: string;
  timestamp: number;
  from: string;
  to: string;
  amount: number;
  fee?: number;
  token?: string;
  signature: string;
  publicKey: string;
}

export interface SignedMessage {
  message: string;
  signature: string;
  publicKey: string;
  timestamp: number;
}

/**
 * Create canonical payload string for signing.
 * Must match backend's canonicalization exactly.
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
      `Invalid timestamp ${payload.timestamp}: must be UNIX seconds (e.g. 1710000000), not milliseconds`
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

  // ECDSA sign
  const keyPair = ec.keyFromPrivate(privateKeyHex);
  const signature = keyPair.sign(hash);

  // DER encoding
  return signature.toDER('hex');
}

/**
 * Sign a Thronos transaction with proper ECDSA/secp256k1.
 *
 * IMPORTANT: timestamp MUST be UNIX seconds, not milliseconds!
 */
export async function signThronosTransaction(params: {
  from: string;
  to: string;
  amount: number;
  token?: string;
  fee?: number;
  nonce: string;
  timestamp?: number;
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

  // Sign with ECDSA/secp256k1
  const signature = signCanonicalPayload(canonical, derived.privateKey);

  // Use compressed public key for backend
  // Backend derives address from: RIPEMD160(SHA256(compressedPublicKey))
  return {
    ...payload,
    signature,
    publicKey: derived.publicKey,  // Compressed key
    fee: params.fee || 0,
  };
}

/**
 * Sign a message with proper ECDSA/secp256k1.
 */
export async function signMessage(message: string): Promise<SignedMessage> {
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

  // Use compressed public key for backend
  return {
    message,
    signature: signatureHex,
    publicKey: derived.publicKey,  // Compressed key
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
