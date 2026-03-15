// Thronos Wallet API Service
// Communicates with the Thronos blockchain backend

import { CONFIG } from '../constants/config';

const BASE = CONFIG.API_URL;

async function request<T = any>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${BASE}${endpoint}`;
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: 'Request failed' }));
    throw new Error(err.error || `HTTP ${res.status}`);
  }
  return res.json();
}

// ── Wallet ────────────────────────────────────────────────────────────────────

export async function createWallet(): Promise<{ address: string; secret: string }> {
  return request('/api/wallet/create', { method: 'POST' });
}

export async function getTokenBalances(
  address: string,
  showZero = true,
): Promise<{ address: string; tokens: TokenBalance[]; last_updated: string }> {
  return request(`/api/wallet/tokens/${address}?show_zero=${showZero}`);
}

export interface TokenBalance {
  symbol: string;
  name: string;
  balance: number;
  category?: string;
}

// ── Transactions ──────────────────────────────────────────────────────────────

export async function sendTHR(params: {
  from: string;
  to: string;
  amount: number;
  secret: string;
  speed?: 'fast' | 'slow';
}): Promise<{ success: boolean; transaction?: any; error?: string }> {
  return request('/send_thr', {
    method: 'POST',
    body: JSON.stringify({
      from_thr: params.from,
      to_thr: params.to,
      amount: params.amount,
      auth_secret: params.secret,
      speed: params.speed || 'fast',
    }),
  });
}

export async function sendToken(params: {
  symbol: string;
  from: string;
  to: string;
  amount: number;
  secret: string;
}): Promise<{ success: boolean; transaction?: any; error?: string }> {
  return request('/api/tokens/transfer', {
    method: 'POST',
    body: JSON.stringify({
      symbol: params.symbol,
      from_thr: params.from,
      to_thr: params.to,
      amount: params.amount,
      auth_secret: params.secret,
      speed: 'fast',
    }),
  });
}

export async function getTransactionHistory(
  address: string,
  limit = 50,
): Promise<any[]> {
  return request(`/api/transactions/${address}?limit=${limit}`);
}

export async function getTransactionsByCategory(
  address: string,
  category = 'all',
  limit = 50,
): Promise<{ transactions: any[] }> {
  return request(`/wallet_data/${address}?category=${category}&limit=${limit}`);
}

// ── Chain Info ─────────────────────────────────────────────────────────────────

export async function getChainTokens(): Promise<{ tokens: any[] }> {
  return request('/api/tokens/list');
}

export async function getNetworkStatus(): Promise<any> {
  return request('/api/network/status');
}

// ── Staking / Pledge ──────────────────────────────────────────────────────────

export async function getPledgeInfo(address: string): Promise<{
  pledged_amount: number;
  rewards: number;
  apr: number;
}> {
  return request(`/api/pledge/info/${address}`);
}

export async function pledgeTokens(params: {
  address: string;
  amount: number;
  secret: string;
}): Promise<{ success: boolean }> {
  return request('/api/pledge/stake', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

// ── Swap ──────────────────────────────────────────────────────────────────────

export async function getSwapQuote(
  from: string,
  to: string,
  amount: number,
): Promise<{ rate: number; amount_out: number; fee: number }> {
  return request(`/api/swap/quote?from=${from}&to=${to}&amount=${amount}`);
}

export async function executeSwap(params: {
  from_token: string;
  to_token: string;
  amount: number;
  address: string;
  secret: string;
}): Promise<{ success: boolean; transaction?: any }> {
  return request('/api/swap/execute', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

// ── Wallet Verify ────────────────────────────────────────────────────────────

export async function verifySignature(
  message: string,
  signature: string,
  address: string,
): Promise<{ valid: boolean }> {
  return request('/api/wallet/verify', {
    method: 'POST',
    body: JSON.stringify({ message, signature, address }),
  });
}

// ── T2E (Train to Earn) ─────────────────────────────────────────────────────

export interface T2EBalance {
  balance: number;
  total_earned: number;
  multiplier: number;
  projects_completed: number;
  rank?: string;
}

export interface T2EEarning {
  id: string;
  type: 'training' | 'rating' | 'contribution' | 'architect' | 'bonus';
  amount: number;
  description: string;
  timestamp: string;
}

export async function getT2EBalance(address: string): Promise<T2EBalance> {
  return request(`/api/t2e/balance/${address}`);
}

export async function getT2EHistory(
  address: string,
  limit = 20,
): Promise<{ earnings: T2EEarning[] }> {
  return request(`/api/architect_t2e_history/${address}?limit=${limit}`);
}

// ── Bridge ──────────────────────────────────────────────────────────────────

export interface BridgeQuote {
  from_chain: string;
  to_chain: string;
  from_token: string;
  to_token: string;
  amount_in: number;
  amount_out: number;
  fee: number;
  estimated_time_min: number;
}

export interface BridgeTransfer {
  id: string;
  from_chain: string;
  to_chain: string;
  from_token: string;
  to_token: string;
  amount: number;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  created_at: string;
  tx_hash?: string;
}

export async function getBridgeQuote(params: {
  from_chain: string;
  to_chain: string;
  token: string;
  amount: number;
}): Promise<BridgeQuote> {
  const q = new URLSearchParams({
    from: params.from_chain,
    to: params.to_chain,
    token: params.token,
    amount: String(params.amount),
  });
  return request(`/api/bridge/quote?${q}`);
}

export async function executeBridge(params: {
  from_chain: string;
  to_chain: string;
  token: string;
  amount: number;
  from_address: string;
  to_address: string;
  secret: string;
}): Promise<{ success: boolean; transfer?: BridgeTransfer; error?: string }> {
  return request('/api/bridge/execute', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

export async function getBridgeHistory(
  address: string,
): Promise<{ transfers: BridgeTransfer[] }> {
  return request(`/api/bridge/history/${address}`);
}
