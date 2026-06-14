// Thronos Transaction Signing — pure JS via @noble/curves + @noble/hashes
// No Node.js built-ins. Private keys never leave the device.

import { secp256k1 } from '@noble/curves/secp256k1';
import { sha256 } from '@noble/hashes/sha256';
import { getMnemonic, getPrivateKey, deriveHDWalletFromMnemonic } from './wallet';

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

function hexToBytes(hex: string): Uint8Array {
  const b = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) b[i / 2] = parseInt(hex.substr(i, 2), 16);
  return b;
}

function bytesToHex(b: Uint8Array): string {
  return Array.from(b).map(x => x.toString(16).padStart(2, '0')).join('');
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
  fee?: number; nonce: string; timestamp?: number;
}): Promise<SignedTransaction> {
  const ts = params.timestamp || Math.floor(Date.now() / 1000);
  if (ts > 1e10) throw new Error('Use UNIX seconds for timestamp');

  const payload = {
    from: params.from, to: params.to, amount: params.amount,
    token: params.token || 'THR', nonce: params.nonce, timestamp: ts,
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
    return secp256k1.verify(signature, hash, hexToBytes(publicKey));
  } catch {
    return false;
  }
}
