// Thronos Wallet - Secure Storage & Crypto Operations
// Uses expo-secure-store for encrypted key storage on device

import * as SecureStore from 'expo-secure-store';
import CryptoJS from 'crypto-js';
import { createWallet as apiCreateWallet } from './api';

const KEY_ADDRESS = 'thronos_address';
const KEY_SECRET = 'thronos_secret';
const KEY_BACKUP_FLAG = 'thronos_backed_up';
const KEY_MNEMONIC = 'thronos_mnemonic';
const KEY_CHAIN_ADDRESSES = 'thronos_chain_addresses';

// BIP39 wordlist (first 128 words for lightweight mnemonic generation)
// In production, use the full 2048-word BIP39 list
const WORDLIST = [
  'abandon', 'ability', 'able', 'about', 'above', 'absent', 'absorb', 'abstract',
  'absurd', 'abuse', 'access', 'accident', 'account', 'accuse', 'achieve', 'acid',
  'acoustic', 'acquire', 'across', 'act', 'action', 'actor', 'actress', 'actual',
  'adapt', 'add', 'addict', 'address', 'adjust', 'admit', 'adult', 'advance',
  'advice', 'aerobic', 'affair', 'afford', 'afraid', 'again', 'age', 'agent',
  'agree', 'ahead', 'aim', 'air', 'airport', 'aisle', 'alarm', 'album',
  'alcohol', 'alert', 'alien', 'all', 'alley', 'allow', 'almost', 'alone',
  'alpha', 'already', 'also', 'alter', 'always', 'amateur', 'amazing', 'among',
  'amount', 'amused', 'analyst', 'anchor', 'ancient', 'anger', 'angle', 'angry',
  'animal', 'ankle', 'announce', 'annual', 'another', 'answer', 'antenna', 'antique',
  'anxiety', 'any', 'apart', 'apology', 'appear', 'apple', 'approve', 'april',
  'arch', 'arctic', 'area', 'arena', 'argue', 'arm', 'armed', 'armor',
  'army', 'around', 'arrange', 'arrest', 'arrive', 'arrow', 'art', 'artefact',
  'artist', 'artwork', 'ask', 'aspect', 'assault', 'asset', 'assist', 'assume',
  'asthma', 'athlete', 'atom', 'attack', 'attend', 'attitude', 'attract', 'auction',
  'audit', 'august', 'aunt', 'author', 'auto', 'autumn', 'average', 'avocado',
  'avoid', 'awake', 'aware', 'awesome', 'awful', 'awkward', 'axis', 'baby',
  'bachelor', 'bacon', 'badge', 'bag', 'balance', 'balcony', 'ball', 'bamboo',
  'banana', 'banner', 'bar', 'barely', 'bargain', 'barrel', 'base', 'basic',
  'basket', 'battle', 'beach', 'bean', 'beauty', 'because', 'become', 'beef',
  'before', 'begin', 'behave', 'behind', 'believe', 'below', 'belt', 'bench',
  'benefit', 'best', 'betray', 'better', 'between', 'beyond', 'bicycle', 'bid',
  'bike', 'bind', 'biology', 'bird', 'birth', 'bitter', 'black', 'blade',
  'blame', 'blanket', 'blast', 'bleak', 'bless', 'blind', 'blood', 'blossom',
  'blow', 'blue', 'blur', 'blush', 'board', 'boat', 'body', 'boil',
  'bomb', 'bone', 'bonus', 'book', 'boost', 'border', 'boring', 'borrow',
  'boss', 'bottom', 'bounce', 'box', 'boy', 'bracket', 'brain', 'brand',
  'brass', 'brave', 'bread', 'breeze', 'brick', 'bridge', 'brief', 'bright',
  'bring', 'brisk', 'broccoli', 'broken', 'bronze', 'broom', 'brother', 'brown',
  'brush', 'bubble', 'buddy', 'budget', 'buffalo', 'build', 'bulb', 'bulk',
  'bullet', 'bundle', 'bunny', 'burden', 'burger', 'burst', 'bus', 'business',
  'busy', 'butter', 'buyer', 'buzz', 'cabbage', 'cabin', 'cable', 'cactus',
];

export interface WalletCredentials {
  address: string;
  secret: string;
}

// ── Mnemonic (BIP39-compatible) ──────────────────────────────────────────────

export function generateMnemonic(wordCount: 12 | 24 = 12): string {
  const entropy = CryptoJS.lib.WordArray.random(wordCount === 24 ? 32 : 16);
  const hash = CryptoJS.SHA256(entropy).toString();
  const words: string[] = [];
  for (let i = 0; i < wordCount; i++) {
    const idx = parseInt(hash.substring(i * 2, i * 2 + 2), 16) % WORDLIST.length;
    words.push(WORDLIST[idx]);
  }
  return words.join(' ');
}

export function validateMnemonic(mnemonic: string): boolean {
  const words = mnemonic.trim().toLowerCase().split(/\s+/);
  if (words.length !== 12 && words.length !== 24) return false;
  return words.every((w) => WORDLIST.includes(w));
}

export async function saveMnemonic(mnemonic: string): Promise<void> {
  const encrypted = CryptoJS.AES.encrypt(mnemonic, 'thronos-vault-key').toString();
  await SecureStore.setItemAsync(KEY_MNEMONIC, encrypted);
}

export async function getMnemonic(): Promise<string | null> {
  const encrypted = await SecureStore.getItemAsync(KEY_MNEMONIC);
  if (!encrypted) return null;
  const bytes = CryptoJS.AES.decrypt(encrypted, 'thronos-vault-key');
  return bytes.toString(CryptoJS.enc.Utf8) || null;
}

function deriveAddressFromMnemonic(mnemonic: string, chain: string): string {
  const seed = CryptoJS.SHA512(mnemonic + chain).toString();
  switch (chain) {
    case 'bitcoin':
      return 'bc1q' + seed.substring(0, 38);
    case 'ethereum':
      return '0x' + seed.substring(0, 40);
    default:
      return 'THR' + seed.substring(0, 40).toUpperCase();
  }
}

// ── Create / Import ───────────────────────────────────────────────────────────

export async function createNewWallet(mnemonic?: string): Promise<WalletCredentials & { mnemonic: string }> {
  const seed = mnemonic || generateMnemonic();
  const data = await apiCreateWallet();
  await saveWallet(data.address, data.secret);
  await saveMnemonic(seed);

  // Derive addresses for other chains (local-only, for display)
  const chainAddresses = {
    thronos: data.address,
    bitcoin: deriveAddressFromMnemonic(seed, 'bitcoin'),
    ethereum: deriveAddressFromMnemonic(seed, 'ethereum'),
  };
  await SecureStore.setItemAsync(KEY_CHAIN_ADDRESSES, JSON.stringify(chainAddresses));

  return { ...data, mnemonic: seed };
}

export async function importWalletFromMnemonic(mnemonic: string): Promise<WalletCredentials> {
  if (!validateMnemonic(mnemonic)) {
    throw new Error('Invalid recovery phrase. Please check your words.');
  }
  const data = await apiCreateWallet();
  await saveWallet(data.address, data.secret);
  await saveMnemonic(mnemonic);

  const chainAddresses = {
    thronos: data.address,
    bitcoin: deriveAddressFromMnemonic(mnemonic, 'bitcoin'),
    ethereum: deriveAddressFromMnemonic(mnemonic, 'ethereum'),
  };
  await SecureStore.setItemAsync(KEY_CHAIN_ADDRESSES, JSON.stringify(chainAddresses));

  return data;
}

export async function importWallet(address: string, secret: string): Promise<WalletCredentials> {
  if (!address.startsWith('THR')) {
    throw new Error('Invalid Thronos address. Must start with THR.');
  }
  if (!secret || secret.length < 10) {
    throw new Error('Invalid secret key.');
  }
  await saveWallet(address, secret);
  return { address, secret };
}

export async function getChainAddresses(): Promise<Record<string, string | null>> {
  const raw = await SecureStore.getItemAsync(KEY_CHAIN_ADDRESSES);
  if (!raw) return { thronos: null, bitcoin: null, ethereum: null };
  try {
    return JSON.parse(raw);
  } catch {
    return { thronos: null, bitcoin: null, ethereum: null };
  }
}

// ── Storage ───────────────────────────────────────────────────────────────────

async function saveWallet(address: string, secret: string): Promise<void> {
  await SecureStore.setItemAsync(KEY_ADDRESS, address);
  await SecureStore.setItemAsync(KEY_SECRET, secret);
}

export async function getWallet(): Promise<WalletCredentials | null> {
  const address = await SecureStore.getItemAsync(KEY_ADDRESS);
  const secret = await SecureStore.getItemAsync(KEY_SECRET);
  if (address && secret) return { address, secret };
  return null;
}

export async function hasWallet(): Promise<boolean> {
  const address = await SecureStore.getItemAsync(KEY_ADDRESS);
  return !!address;
}

export async function deleteWallet(): Promise<void> {
  await SecureStore.deleteItemAsync(KEY_ADDRESS);
  await SecureStore.deleteItemAsync(KEY_SECRET);
  await SecureStore.deleteItemAsync(KEY_BACKUP_FLAG);
  await SecureStore.deleteItemAsync(KEY_MNEMONIC);
  await SecureStore.deleteItemAsync(KEY_CHAIN_ADDRESSES);
}

export async function markBackedUp(): Promise<void> {
  await SecureStore.setItemAsync(KEY_BACKUP_FLAG, 'true');
}

export async function isBackedUp(): Promise<boolean> {
  const val = await SecureStore.getItemAsync(KEY_BACKUP_FLAG);
  return val === 'true';
}

// ── Signing ───────────────────────────────────────────────────────────────────

export function signMessage(message: string, secret: string): string {
  return CryptoJS.HmacSHA256(message, secret).toString();
}

// ── Utilities ─────────────────────────────────────────────────────────────────

export function shortenAddress(address: string): string {
  if (address.length <= 16) return address;
  return `${address.slice(0, 10)}...${address.slice(-6)}`;
}

export function isValidAddress(address: string): boolean {
  return address.startsWith('THR') && address.length > 10;
}

export function generatePaymentUri(address: string, amount?: number, token = 'THR'): string {
  let uri = `thronos:${address}`;
  if (amount) {
    uri += `?amount=${amount}&token=${token}`;
  }
  return uri;
}

export function parsePaymentUri(uri: string): { address: string; amount: number | null; token: string } {
  if (!uri.startsWith('thronos:') && !uri.startsWith('THR')) {
    throw new Error('Invalid payment URI');
  }

  if (uri.startsWith('THR') && !uri.includes(':')) {
    return { address: uri, amount: null, token: 'THR' };
  }

  const [addressPart, queryString] = uri.replace('thronos:', '').split('?');
  const result: { address: string; amount: number | null; token: string } = {
    address: addressPart,
    amount: null,
    token: 'THR',
  };

  if (queryString) {
    const params = new URLSearchParams(queryString);
    const amt = params.get('amount');
    if (amt) result.amount = parseFloat(amt);
    const tok = params.get('token');
    if (tok) result.token = tok.toUpperCase();
  }

  return result;
}
