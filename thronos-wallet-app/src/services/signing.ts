// Thronos Transaction Signing Service (Client-Side Only)
// All signing operations occur on-device. Private keys never leave the device.

import CryptoJS from 'crypto-js';
import { getMnemonic, deriveHDWalletFromMnemonic } from './wallet';

export interface SignedTransaction {
  nonce: number;
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

export async function signThronosTransaction(params: {
  from: string;
  to: string;
  amount: number;
  token?: string;
  fee?: number;
  nonce: number;
}): Promise<SignedTransaction> {
  const mnemonic = await getMnemonic();
  if (!mnemonic) {
    throw new Error('Wallet not initialized. Please create or import a wallet first.');
  }

  const derived = await deriveHDWalletFromMnemonic(mnemonic);

  if (derived.address !== params.from) {
    throw new Error('Wallet address mismatch. Cannot sign for a different address.');
  }

  const txObject = {
    nonce: params.nonce,
    timestamp: Math.floor(Date.now() / 1000),
    from: params.from,
    to: params.to,
    amount: params.amount,
    token: params.token || 'THR',
    fee: params.fee || 0,
  };

  const txString = JSON.stringify(txObject);
  const txHash = CryptoJS.SHA256(txString).toString();
  const signature = CryptoJS.HmacSHA256(txHash, derived.privateKey).toString();

  return { ...txObject, signature, publicKey: derived.publicKey };
}

export async function signMessage(message: string): Promise<SignedMessage> {
  const mnemonic = await getMnemonic();
  if (!mnemonic) {
    throw new Error('Wallet not initialized.');
  }

  const derived = await deriveHDWalletFromMnemonic(mnemonic);
  const messageHash = CryptoJS.SHA256(message).toString();
  const signature = CryptoJS.HmacSHA256(messageHash, derived.privateKey).toString();

  return { message, signature, publicKey: derived.publicKey, timestamp: Math.floor(Date.now() / 1000) };
}

export function verifySignature(message: string, signature: string, publicKey: string): boolean {
  const messageHash = CryptoJS.SHA256(message).toString();
  const expectedSignature = CryptoJS.HmacSHA256(messageHash, publicKey).toString();
  return signature === expectedSignature;
}
