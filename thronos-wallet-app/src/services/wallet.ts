// Thronos Wallet — Secure Storage & Crypto (pure JS, no Node built-ins)
// Uses @noble/ciphers for AES-GCM, @scure/bip32+bip39 for HD keys.
// Private keys never leave the device.

import * as SecureStore from 'expo-secure-store';
import * as LocalAuthentication from 'expo-local-authentication';
import { gcm } from '@noble/ciphers/aes';
import { pbkdf2 } from '@noble/hashes/pbkdf2';
import { sha256 } from '@noble/hashes/sha256';
import { ripemd160 } from '@noble/hashes/ripemd160';
import { secp256k1 } from '@noble/curves/secp256k1';
import { generateMnemonic as _genMnemonic, mnemonicToSeedSync, validateMnemonic as _validateMnemonic } from '@scure/bip39';
import { wordlist } from '@scure/bip39/wordlists/english';
import { HDKey } from '@scure/bip32';

const KEY_ADDRESS   = 'thr_address_v1';
const KEY_PRIV      = 'thr_private_key_v1';
const KEY_SECRET    = 'thr_auth_secret_v1';
const KEY_METHOD    = 'thr_wallet_method_v1';  // 'secret' | 'key' | 'mnemonic'
const KEY_MNEMONIC  = 'thr_mnemonic_enc_v1';
const KEY_BIOMETRIC = 'thr_biometric_v1';

export interface WalletCredentials {
  address: string;
  publicKey?: string;
  method?: 'secret' | 'key' | 'mnemonic';
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function hexToBytes(hex: string): Uint8Array {
  const b = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) b[i / 2] = parseInt(hex.substr(i, 2), 16);
  return b;
}

function bytesToHex(b: Uint8Array): string {
  return Array.from(b).map(x => x.toString(16).padStart(2, '0')).join('');
}

function thrAddressFromPubKey(pubKeyBytes: Uint8Array): string {
  const h1 = sha256(pubKeyBytes);
  const h2 = ripemd160(h1);
  return 'THR' + bytesToHex(h2).substring(0, 40).toUpperCase();
}

async function store(key: string, value: string): Promise<void> {
  await SecureStore.setItemAsync(key, value, {
    keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  });
}

// ─── Biometric ──────────────────────────────────────────────────────────────

export async function isBiometricAvailable(): Promise<boolean> {
  try {
    const [hw, enrolled] = await Promise.all([
      LocalAuthentication.hasHardwareAsync(),
      LocalAuthentication.isEnrolledAsync(),
    ]);
    return hw && enrolled;
  } catch {
    return false;
  }
}

export async function authenticateWithBiometrics(prompt = 'Unlock Thronos Wallet'): Promise<boolean> {
  try {
    const r = await LocalAuthentication.authenticateAsync({
      promptMessage: prompt,
      fallbackLabel: 'Use Passcode',
      disableDeviceFallback: false,
      cancelLabel: 'Cancel',
    });
    return r.success;
  } catch {
    return false;
  }
}

export async function isBiometricEnabled(): Promise<boolean> {
  return (await SecureStore.getItemAsync(KEY_BIOMETRIC)) === 'true';
}

export async function setBiometricEnabled(enabled: boolean): Promise<void> {
  await store(KEY_BIOMETRIC, enabled ? 'true' : 'false');
}

// ─── AES-GCM decrypt matching wallet_session.js (250k PBKDF2) ────────────────

async function decryptRecoveryBlob(blob: string, pin: string): Promise<string> {
  const p = typeof blob === 'string' ? JSON.parse(blob) : blob;
  if (!p.salt || !p.iv || !p.ct) throw new Error('invalid_encrypted_blob');

  const pinBytes  = new TextEncoder().encode(pin);
  const saltBytes = hexToBytes(p.salt);
  const ivBytes   = hexToBytes(p.iv);
  const ctBytes   = hexToBytes(p.ct);

  // PBKDF2-SHA256, 250 000 iterations — matches wallet_session.js aesKeyFromPin
  const key = pbkdf2(sha256, pinBytes, saltBytes, { c: 250000, dkLen: 32 });

  // AES-256-GCM decrypt (ctBytes includes 16-byte auth tag at end, as produced by WebCrypto)
  const clear = gcm(key, ivBytes).decrypt(ctBytes);
  return bytesToHex(clear);
}

// ─── Mnemonic / HD ──────────────────────────────────────────────────────────

export function generateMnemonic(strength: 128 | 256 = 128): string {
  return _genMnemonic(wordlist, strength);
}

export function validateMnemonic(mnemonic: string): boolean {
  return _validateMnemonic(mnemonic, wordlist);
}

export async function deriveHDWalletFromMnemonic(
  mnemonic: string,
  path = "m/44'/1'/0'/0/0",
): Promise<{ privateKey: string; publicKey: string; address: string }> {
  const seed  = mnemonicToSeedSync(mnemonic);
  const root  = HDKey.fromMasterSeed(seed);
  const child = root.derive(path);
  if (!child.privateKey) throw new Error('Failed to derive private key');
  const pub = secp256k1.getPublicKey(child.privateKey, true);
  return {
    privateKey: bytesToHex(child.privateKey),
    publicKey:  bytesToHex(pub),
    address:    thrAddressFromPubKey(pub),
  };
}

// ─── Public API ──────────────────────────────────────────────────────────────

export async function createNewWallet(): Promise<WalletCredentials & { mnemonic: string }> {
  const mnemonic = generateMnemonic(128);
  const d = await deriveHDWalletFromMnemonic(mnemonic);
  await store(KEY_ADDRESS,  d.address);
  await store(KEY_PRIV,     d.privateKey);
  await store(KEY_MNEMONIC, mnemonic);
  await store(KEY_METHOD,   'mnemonic');
  return { address: d.address, publicKey: d.publicKey, mnemonic, method: 'mnemonic' };
}

export async function importWalletFromMnemonic(mnemonic: string): Promise<WalletCredentials> {
  if (!validateMnemonic(mnemonic)) throw new Error('Invalid recovery phrase. Check your words.');
  const d = await deriveHDWalletFromMnemonic(mnemonic);
  await store(KEY_ADDRESS,  d.address);
  await store(KEY_PRIV,     d.privateKey);
  await store(KEY_MNEMONIC, mnemonic);
  await store(KEY_METHOD,   'mnemonic');
  return { address: d.address, publicKey: d.publicKey, method: 'mnemonic' };
}

export async function importWallet(address: string, secret: string): Promise<WalletCredentials> {
  if (!address.startsWith('THR') || address.length < 40) throw new Error('Invalid Thronos address');
  if (!secret || secret.length < 8) throw new Error('Invalid secret key');
  await store(KEY_ADDRESS, address);
  await store(KEY_SECRET,  secret);
  await store(KEY_METHOD,  'secret');
  return { address, method: 'secret' };
}

export async function importWalletFromRecoveryJson(
  jsonText: string,
  pin: string,
): Promise<WalletCredentials> {
  if (!pin || pin.length < 1) throw new Error('PIN is required');

  let kit: any;
  try { kit = JSON.parse(jsonText); } catch { throw new Error('Invalid JSON file'); }

  let blob: string | null = null;
  let kitAddress: string | null = null;

  if (kit.encrypted_private_key_backup) {
    blob       = kit.encrypted_private_key_backup;
    kitAddress = kit.canonical_v1_address || null;
  } else if (kit.wallet_v1_encrypted_priv) {
    blob       = kit.wallet_v1_encrypted_priv;
    kitAddress = kit.wallet_v1_canonical_address || kit.wallet_v1_address || null;
  } else if (kit.wallet_v1_encrypted_private_key) {
    blob       = kit.wallet_v1_encrypted_private_key;
    kitAddress = kit.wallet_v1_canonical_address || kit.wallet_v1_address || null;
  } else {
    throw new Error('Unrecognized recovery kit format');
  }

  if (!blob) throw new Error('No encrypted key in recovery kit');

  let privHex: string;
  try { privHex = await decryptRecoveryBlob(blob, pin); }
  catch { throw new Error('wrong_pin'); }

  if (!privHex || privHex.length !== 64) throw new Error('wrong_pin');

  const address = (kitAddress || '').toUpperCase();
  if (!address.startsWith('THR')) throw new Error('No valid address in recovery kit');

  await store(KEY_ADDRESS, address);
  await store(KEY_PRIV,    privHex);
  await store(KEY_METHOD,  'key');

  return { address, method: 'key' };
}

export async function getWallet(): Promise<WalletCredentials | null> {
  const address = await SecureStore.getItemAsync(KEY_ADDRESS);
  const method  = await SecureStore.getItemAsync(KEY_METHOD) as any;
  if (address && method) return { address, method };
  return null;
}

export async function getPrivateKey(): Promise<string | null> {
  return SecureStore.getItemAsync(KEY_PRIV);
}

export async function getAuthSecret(): Promise<string | null> {
  return SecureStore.getItemAsync(KEY_SECRET);
}

export async function getMnemonic(): Promise<string | null> {
  return SecureStore.getItemAsync(KEY_MNEMONIC);
}

export async function saveMnemonic(mnemonic: string): Promise<void> {
  await store(KEY_MNEMONIC, mnemonic);
}

export async function hasWallet(): Promise<boolean> {
  return !!(await SecureStore.getItemAsync(KEY_ADDRESS));
}

export async function deleteWallet(): Promise<void> {
  for (const k of [KEY_ADDRESS, KEY_PRIV, KEY_SECRET, KEY_MNEMONIC, KEY_METHOD, KEY_BIOMETRIC]) {
    await SecureStore.deleteItemAsync(k).catch(() => {});
  }
}

export async function isBackedUp(): Promise<boolean> { return false; }
export async function markBackedUp(): Promise<void> {}

export async function clearMnemonic(): Promise<void> {
  await SecureStore.deleteItemAsync(KEY_MNEMONIC).catch(() => {});
}

export function isValidAddress(address: string): boolean {
  return /^THR[0-9a-fA-F]{40}$/i.test(address);
}

export function shortenAddress(address: string): string {
  if (address.length <= 16) return address;
  return `${address.slice(0, 10)}...${address.slice(-6)}`;
}

export function generatePaymentUri(address: string, amount?: number, token = 'THR'): string {
  return amount ? `thronos:${address}?amount=${amount}&token=${token}` : `thronos:${address}`;
}

export function parsePaymentUri(uri: string): { address: string; amount: number | null; token: string } {
  if (!uri.startsWith('thronos:') && !uri.startsWith('THR')) throw new Error('Invalid payment URI');
  if (uri.startsWith('THR') && !uri.includes(':')) return { address: uri, amount: null, token: 'THR' };
  const [addr, qs] = uri.replace('thronos:', '').split('?');
  const out = { address: addr, amount: null as number | null, token: 'THR' };
  if (qs) {
    const p = new URLSearchParams(qs);
    const a = p.get('amount'); if (a) out.amount = parseFloat(a);
    const t = p.get('token');  if (t) out.token  = t.toUpperCase();
  }
  return out;
}
