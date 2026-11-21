// Thronos Transaction Signing — pure JS via @noble/curves + @noble/hashes
// No Node.js built-ins. Private keys never leave the device.

import { secp256k1 } from '@noble/curves/secp256k1';
import { sha256 } from '@noble/hashes/sha256';
import { ripemd160 } from '@noble/hashes/ripemd160';
import {
  authenticateWithBiometrics,
  deriveHDWalletFromMnemonic,
  getMnemonic,
  getPrivateKey,
  getWallet,
} from './wallet';

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

export const WALLET_V1_V2_DOMAIN = 'thronos.wallet.service_request';
export const WALLET_V1_V2_PROTOCOL_VERSION = '2';
export const WALLET_V1_V2_CHAIN_ID = 'thronos-mainnet';
export const WALLET_V1_V2_SIGNATURE_FORMAT = 'wallet_v1_full_payload_v2';

type CanonicalPayload = null | boolean | string | CanonicalPayload[] | { [key: string]: CanonicalPayload };

export interface WalletV1FullPayloadRequest {
  action: string;
  canonical_v1_address: string;
  chain_id: typeof WALLET_V1_V2_CHAIN_ID;
  domain: typeof WALLET_V1_V2_DOMAIN;
  expires_at: string;
  issued_at: string;
  nonce: string;
  payload: { [key: string]: CanonicalPayload };
  protocol_version: typeof WALLET_V1_V2_PROTOCOL_VERSION;
  signer_address: string;
  from: string;
  public_key: string;
  signature: string;
  signature_format: typeof WALLET_V1_V2_SIGNATURE_FORMAT;
  signing_payload_hash: string;
  bound_key_address?: string;
}

function hexToBytes(hex: string): Uint8Array {
  const b = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) b[i / 2] = parseInt(hex.substr(i, 2), 16);
  return b;
}

function bytesToHex(b: Uint8Array): string {
  return Array.from(b).map(x => x.toString(16).padStart(2, '0')).join('');
}

function thrAddressFromPublicKey(publicKey: Uint8Array): string {
  // Keep byte-for-byte compatibility with Wallet V1 address derivation.
  return 'THR' + bytesToHex(ripemd160(sha256(publicKey))).slice(0, 40).toUpperCase();
}

export function normalizeWalletV1Payload(value: any, depth = 0): CanonicalPayload {
  if (depth > 32) throw new Error('payload_too_deep');
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error('payload_number_not_finite');
    return String(value);
  }
  if (Array.isArray(value)) return value.map(item => normalizeWalletV1Payload(item, depth + 1));
  if (value && Object.getPrototypeOf(value) === Object.prototype) {
    const result: { [key: string]: CanonicalPayload } = {};
    Object.keys(value).sort().forEach(key => {
      const item = value[key];
      if (item === undefined || typeof item === 'function' || typeof item === 'symbol') {
        throw new Error('unsupported_payload_value');
      }
      result[key] = normalizeWalletV1Payload(item, depth + 1);
    });
    return result;
  }
  throw new Error('unsupported_payload_value');
}

export function canonicalWalletV1Json(value: CanonicalPayload): string {
  if (Array.isArray(value)) return '[' + value.map(canonicalWalletV1Json).join(',') + ']';
  if (value && typeof value === 'object') {
    return '{' + Object.keys(value).sort().map(
      key => JSON.stringify(key) + ':' + canonicalWalletV1Json((value as any)[key]),
    ).join(',') + '}';
  }
  return JSON.stringify(value);
}

export async function signWalletV1FullPayloadRequest(
  action: string,
  payload: Record<string, any>,
  options: { now?: number; ttlSeconds?: number; nonce?: string; requireDeviceApproval?: boolean } = {},
): Promise<WalletV1FullPayloadRequest> {
  const wallet = await getWallet();
  if (!wallet?.address) throw new Error('Wallet not initialized');
  const privateKeyHex = await getPrivKeyHex();
  const privateKey = hexToBytes(privateKeyHex);
  const publicKey = secp256k1.getPublicKey(privateKey, true);
  const signerAddress = thrAddressFromPublicKey(publicKey);

  if (options.requireDeviceApproval !== false) {
    const approved = await authenticateWithBiometrics(`Approve ${action.replace(/_/g, ' ')}`);
    if (!approved) throw new Error('signing_cancelled');
  }

  const issuedAt = Math.floor(options.now ?? Date.now() / 1000);
  const ttl = Math.max(1, Math.min(300, options.ttlSeconds ?? 120));
  const randomNonce = bytesToHex(secp256k1.utils.randomPrivateKey());
  const normalizedPayload = normalizeWalletV1Payload(payload);
  if (!normalizedPayload || Array.isArray(normalizedPayload) || typeof normalizedPayload !== 'object') {
    throw new Error('payload_must_be_object');
  }
  const envelope = {
    action: String(action || '').trim().toLowerCase(),
    canonical_v1_address: wallet.address,
    chain_id: WALLET_V1_V2_CHAIN_ID,
    domain: WALLET_V1_V2_DOMAIN,
    expires_at: String(issuedAt + ttl),
    issued_at: String(issuedAt),
    nonce: options.nonce || randomNonce,
    payload: normalizedPayload,
    protocol_version: WALLET_V1_V2_PROTOCOL_VERSION,
    signer_address: signerAddress,
  } as const;
  const signingJson = canonicalWalletV1Json(envelope as any);
  const signingHash = sha256(new TextEncoder().encode(signingJson));
  const signature = secp256k1.sign(signingHash, privateKey).toCompactHex();

  return {
    ...envelope,
    from: wallet.address,
    public_key: bytesToHex(publicKey),
    signature,
    signature_format: WALLET_V1_V2_SIGNATURE_FORMAT,
    signing_payload_hash: bytesToHex(signingHash),
    ...(signerAddress !== wallet.address ? { bound_key_address: signerAddress } : {}),
  };
}

function canonicalize(payload: {
  from: string; to: string; amount: number; token: string; nonce: string; timestamp: number;
}): string {
  if (payload.timestamp > 1e10) throw new Error('timestamp must be UNIX seconds, not milliseconds');
  const obj = {
    amount: payload.amount, from: payload.from, nonce: payload.nonce,
    timestamp: payload.timestamp, to: payload.to, token: payload.token,
  };
  return JSON.stringify(obj, Object.keys(obj).sort());
}

async function getPrivKeyHex(): Promise<string> {
  const priv = await getPrivateKey();
  if (priv) return priv;
  const mnemonic = await getMnemonic();
  if (!mnemonic) throw new Error('Wallet not initialized. Please import or create a wallet first.');
  const d = await deriveHDWalletFromMnemonic(mnemonic);
  return d.privateKey;
}

function signHash(hash: Uint8Array, privHex: string): { signature: string; publicKey: string } {
  const privBytes = hexToBytes(privHex);
  const sig       = secp256k1.sign(hash, privBytes);
  const pub       = secp256k1.getPublicKey(privBytes, true);
  return { signature: sig.toDERHex(), publicKey: bytesToHex(pub) };
}

export async function signThronosTransaction(params: {
  from: string; to: string; amount: number; token?: string;
  fee?: number; nonce: string | number; timestamp?: number;
}): Promise<SignedTransaction> {
  const ts = params.timestamp || Math.floor(Date.now() / 1000);
  if (ts > 1e10) throw new Error('Use UNIX seconds for timestamp');

  const payload = {
    from: params.from, to: params.to, amount: params.amount,
    token: params.token || 'THR', nonce: String(params.nonce), timestamp: ts,
  };

  const hash            = sha256(new TextEncoder().encode(canonicalize(payload)));
  const privHex         = await getPrivKeyHex();
  const { signature, publicKey } = signHash(hash, privHex);

  return { ...payload, signature, publicKey, fee: params.fee || 0 };
}

export async function signMessage(message: string): Promise<SignedMessage> {
  const hash            = sha256(new TextEncoder().encode(message));
  const privHex         = await getPrivKeyHex();
  const { signature, publicKey } = signHash(hash, privHex);
  return { message, signature, publicKey, timestamp: Math.floor(Date.now() / 1000) };
}

export function verifySignature(message: string, signature: string, publicKey: string): boolean {
  try {
    const hash = sha256(new TextEncoder().encode(message));
    return secp256k1.verify(hexToBytes(signature), hash, hexToBytes(publicKey));
  } catch {
    return false;
  }
}
