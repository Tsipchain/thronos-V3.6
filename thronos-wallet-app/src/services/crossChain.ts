// Cross-chain address + balance lookups for the home-screen network switcher.
// Mirrors public/wallet-pwa/app.js's _fetchBtcAddress / _fetchAllChainBalances
// so the mobile and PWA wallets show identical per-network data.

import { CONFIG } from '../constants/config';

const USDT_BNB = '0x55d398326f99059fF775485246999027B3197955';   // 18 dec
const USDT_ARB = '0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9';   // 6 dec
const USDC_BASE = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913';  // 6 dec

export async function fetchBtcAddress(privateKeyHex: string): Promise<string> {
  try {
    const r = await fetch(`${CONFIG.API_URL}/api/wallet/v1/btc-address-from-key`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ private_key_hex: privateKeyHex }),
    });
    const d = await r.json();
    return d.ok && d.btc_address ? d.btc_address : '';
  } catch {
    return '';
  }
}

async function fetchBtcBalance(btcAddr: string): Promise<number | null> {
  if (!btcAddr) return null;
  try {
    const r = await fetch(`https://blockstream.info/api/address/${encodeURIComponent(btcAddr)}`);
    if (!r.ok) return null;
    const d = await r.json();
    const sats = (d.chain_stats?.funded_txo_sum || 0) - (d.chain_stats?.spent_txo_sum || 0);
    return sats / 1e8;
  } catch {
    return null;
  }
}

async function fetchEvmNative(evmAddr: string, rpcUrl: string): Promise<number | null> {
  if (!evmAddr || !rpcUrl) return null;
  try {
    const r = await fetch(rpcUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jsonrpc: '2.0', method: 'eth_getBalance', params: [evmAddr, 'latest'], id: 1 }),
    });
    const d = await r.json();
    if (d.error || !d.result) return null;
    return parseInt(d.result, 16) / 1e18;
  } catch {
    return null;
  }
}

async function fetchErc20(evmAddr: string, tokenContract: string, rpcUrl: string, decimals: number): Promise<number | null> {
  if (!evmAddr || !tokenContract || !rpcUrl) return null;
  try {
    const data = '0x70a08231' + evmAddr.replace(/^0x/, '').padStart(64, '0');
    const r = await fetch(rpcUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jsonrpc: '2.0', method: 'eth_call', params: [{ to: tokenContract, data }, 'latest'], id: 1 }),
    });
    const d = await r.json();
    if (d.error || !d.result || d.result === '0x') return null;
    return parseInt(d.result, 16) / Math.pow(10, decimals);
  } catch {
    return null;
  }
}

export interface ChainBalances {
  btc: number | null;
  eth: number | null;
  bnb: number | null;
  arb: number | null;
  base: number | null;
  usdtBnb: number | null;
  usdtArb: number | null;
  usdcBase: number | null;
}

export async function fetchAllChainBalances(evmAddr: string, btcAddr: string): Promise<ChainBalances> {
  const [btc, eth, bnb, arb, base, usdtBnb, usdtArb, usdcBase] = await Promise.allSettled([
    fetchBtcBalance(btcAddr),
    fetchEvmNative(evmAddr, CONFIG.RPC.ETH),
    fetchEvmNative(evmAddr, CONFIG.RPC.BSC),
    fetchEvmNative(evmAddr, CONFIG.RPC.ARBITRUM),
    fetchEvmNative(evmAddr, 'https://mainnet.base.org'),
    fetchErc20(evmAddr, USDT_BNB, CONFIG.RPC.BSC, 18),
    fetchErc20(evmAddr, USDT_ARB, CONFIG.RPC.ARBITRUM, 6),
    fetchErc20(evmAddr, USDC_BASE, 'https://mainnet.base.org', 6),
  ]);
  const v = (r: PromiseSettledResult<number | null>) => r.status === 'fulfilled' ? r.value : null;
  return {
    btc: v(btc), eth: v(eth), bnb: v(bnb), arb: v(arb), base: v(base),
    usdtBnb: v(usdtBnb), usdtArb: v(usdtArb), usdcBase: v(usdcBase),
  };
}
