// Thronos Wallet - Secure Storage & Crypto Operations
// Uses expo-secure-store for encrypted key storage on device

import * as SecureStore from 'expo-secure-store';
import CryptoJS from 'crypto-js';
import { createWallet as apiCreateWallet } from './api';

const KEY_ADDRESS = 'thronos_address';
const KEY_SECRET = 'thronos_secret';
const KEY_BACKUP_FLAG = 'thronos_backed_up';

export interface WalletCredentials {
  address: string;
  secret: string;
}

// ── Create / Import ───────────────────────────────────────────────────────────

export async function createNewWallet(): Promise<WalletCredentials> {
  const data = await apiCreateWallet();
  await saveWallet(data.address, data.secret);
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
