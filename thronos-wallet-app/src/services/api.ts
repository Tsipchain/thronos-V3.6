// Thronos Wallet API Service
// Communicates with the Thronos blockchain backend
// Node 1 (master) primary, Node 2 (replica) fallback

import { CONFIG } from '../constants/config';

const BASE = CONFIG.API_URL;
const BASE_REPLICA = CONFIG.API_URL_REPLICA;

async function request<T = any>(endpoint: string, options?: RequestInit): Promise<T> {
  for (const baseUrl of [BASE, BASE_REPLICA]) {
    try {
      const url = `${baseUrl}${endpoint}`;
      const res = await fetch(url, {
        headers: { 'Content-Type': 'application/json', ...options?.headers },
        ...options,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: 'Request failed' }));
        throw new Error(err.error || `HTTP ${res.status}`);
      }
      return res.json();
    } catch (err) {
      if (baseUrl === BASE_REPLICA) throw err;
      continue;
    }
  }
  throw new Error('All nodes unreachable');
}

// NOTE: Wallet creation is now purely client-side.
// No server-side wallet creation or secret transmission.

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

export interface SignedTxEnvelope {
  nonce: number;
  timestamp: number;
  from: string;
  to: string;
  amount: number;
  token?: string;
  fee?: number;
  signature: string;
  publicKey: string;
}

export async function sendTHRSigned(params: {
  signedTx: SignedTxEnvelope;
  speed?: 'fast' | 'slow';
}): Promise<{ success: boolean; txHash?: string; error?: string }> {
  return request('/api/v1/tx/send', {
    method: 'POST',
    body: JSON.stringify({ tx: params.signedTx, speed: params.speed || 'fast' }),
  });
}

export async function sendTokenSigned(params: {
  signedTx: SignedTxEnvelope;
}): Promise<{ success: boolean; txHash?: string; error?: string }> {
  return request('/api/v1/tx/send', {
    method: 'POST',
    body: JSON.stringify({ tx: params.signedTx }),
  });
}

export async function getTransactionHistory(address: string, limit = 50, category?: string): Promise<any> {
  const params = new URLSearchParams({ address, limit: String(limit) });
  if (category && category !== 'all') params.set('category', category);
  return request(`/api/wallet/history?${params}`);
}

export async function getTransactionsByCategory(address: string, category = 'all', limit = 50): Promise<{ transactions: any[] }> {
  return request(`/api/v1/address/${address}/history?category=${category}&limit=${limit}`);
}

export async function getChainTokens(): Promise<{ tokens: any[] }> {
  return request('/api/tokens/list');
}

export async function getNetworkStatus(): Promise<{ block_height: number; tps: number; peers: number; mempool: number; total_supply: number; chain_height: number; [key: string]: any }> {
  const [status, peersRes, liveRes] = await Promise.allSettled([
    request<any>('/api/v1/status'),
    request<any>('/api/peers/list').catch(() => ({ peers: [] })),
    request<any>('/api/network_stats').catch(() => ({})),
  ]);
  const statusData = status.status === 'fulfilled' ? status.value : {};
  const peersData = peersRes.status === 'fulfilled' ? peersRes.value : {};
  const liveData = liveRes.status === 'fulfilled' ? liveRes.value : {};
  return {
    ...statusData,
    block_height: statusData.chain_height || statusData.block_count || statusData.height || 0,
    tps: statusData.tps || liveData.tps || 0,
    peers: Array.isArray(peersData.peers) ? peersData.peers.length : (peersData.active_peers?.length ?? 0),
    mempool: statusData.mempool || 0,
    total_supply: statusData.total_supply || 0,
    chain_height: statusData.chain_height || 0,
  };
}

export async function getTokenPrices(): Promise<any> {
  return request('/api/token/prices');
}

export async function getPledgeInfo(address: string): Promise<{ pledged_amount: number; rewards: number; apr: number }> {
  return request(`/api/pledge/info/${address}`);
}

export async function pledgeTokensSigned(params: { signedTx: SignedTxEnvelope }): Promise<{ success: boolean; txHash?: string }> {
  return request('/api/pledge/stake', { method: 'POST', body: JSON.stringify({ tx: params.signedTx }) });
}

export async function getSwapQuote(from: string, to: string, amount: number): Promise<{ rate: number; amount_out: number; fee: number }> {
  const data = await request(`/api/swap/quote?token_in=${from}&token_out=${to}&amount_in=${amount}`);
  const amountOut = Number(data.amount_out) || 0;
  const fee = Number(data.fee) || 0;
  const rate = amount > 0 ? amountOut / amount : 0;
  return { rate, amount_out: amountOut, fee };
}

export async function executeSwapSigned(params: { signedTx: SignedTxEnvelope }): Promise<{ success: boolean; txHash?: string }> {
  return request('/api/swap/execute', { method: 'POST', body: JSON.stringify({ tx: params.signedTx }) });
}

export async function verifySignature(message: string, signature: string, address: string): Promise<{ valid: boolean }> {
  return request('/api/wallet/verify', { method: 'POST', body: JSON.stringify({ message, signature, address }) });
}

export interface T2EBalance { balance: number; total_earned: number; multiplier: number; projects_completed: number; rank?: string; }
export interface T2EEarning { id: string; type: 'training' | 'rating' | 'contribution' | 'architect' | 'bonus'; amount: number; description: string; timestamp: string; }

export async function getT2EBalance(address: string): Promise<T2EBalance> {
  return request(`/api/t2e/balance/${address}`);
}

export async function getT2EHistory(address: string, limit = 20): Promise<{ earnings: T2EEarning[] }> {
  return request(`/api/architect_t2e_history/${address}?limit=${limit}`);
}

export interface MusicTrack { id: string; title: string; artist_name?: string; artist_address?: string; genre?: string; description?: string; audio_url?: string; cover_url?: string; play_count?: number; tips_total?: number; uploaded_at?: string; published?: boolean; }
export interface MusicPlaylist { id: string; name: string; track_count: number; total_duration: number; created_at: string; }

export async function getMusicTracks(address?: string): Promise<{ tracks: MusicTrack[] }> {
  const q = address ? `?address=${address}` : '';
  return request(`/api/v1/music/tracks${q}`);
}

export async function recordPlay(trackId: string, address: string): Promise<{ success: boolean }> {
  return request(`/api/v1/music/play/${trackId}`, { method: 'POST', body: JSON.stringify({ address }) });
}

export async function tipArtist(params: { address: string; track_id: string; artist: string; amount: number }): Promise<{ success: boolean; tx_hash?: string }> {
  return request('/api/v1/music/tip', { method: 'POST', body: JSON.stringify(params) });
}

export async function getMusicPlaylists(address: string): Promise<{ playlists: MusicPlaylist[] }> {
  return request(`/api/music/playlists?address=${address}`);
}

export async function saveOfflineTrack(trackId: string, address: string): Promise<{ success: boolean }> {
  return request('/api/music/offline/save', { method: 'POST', body: JSON.stringify({ track_id: trackId, address }) });
}

export async function getOfflineTracks(address: string): Promise<{ tracks: MusicTrack[] }> {
  return request(`/api/music/offline/${address}`);
}

export async function startMusicSession(params: { address: string; latitude?: number; longitude?: number; carplay?: boolean; android_auto?: boolean }): Promise<{ session_id: string; success: boolean }> {
  return request('/api/music/session/start', { method: 'POST', body: JSON.stringify(params) });
}

export async function endMusicSession(sessionId: string, address: string): Promise<{ success: boolean; plays: number; rewards?: number }> {
  return request('/api/music/session/end', { method: 'POST', body: JSON.stringify({ session_id: sessionId, address }) });
}

export async function submitMusicGpsTelemetry(params: { address: string; session_id: string; latitude: number; longitude: number; speed?: number }): Promise<{ success: boolean }> {
  return request('/api/music/gps_telemetry', { method: 'POST', body: JSON.stringify(params) });
}

export async function getMusicEarnings(address: string): Promise<{ stats: { total_tracks: number; total_plays: number; total_earnings_thr: number }; artist?: { name: string; bio?: string }; tracks?: any[] }> {
  return request(`/api/v1/music/artist/${address}`);
}

export async function searchMusic(query: string): Promise<{ tracks: MusicTrack[] }> {
  return request(`/api/music/search?q=${encodeURIComponent(query)}`);
}

export async function getGovernanceProposals(): Promise<{ proposals: any[] }> {
  return request('/api/v1/governance/proposals');
}

export async function voteOnProposalSigned(params: { proposal_id: string; vote: 'yes' | 'no' | 'abstain'; signedVote: SignedTxEnvelope }): Promise<{ success: boolean }> {
  return request('/api/v1/governance/vote', { method: 'POST', body: JSON.stringify({ proposal_id: params.proposal_id, vote: params.vote, tx: params.signedVote }) });
}

export async function getAiSessionHistory(address: string): Promise<{ sessions: any[] }> {
  return request(`/api/ai_session_history?address=${address}`);
}

export async function getGatewayLimits(): Promise<any> {
  return request('/api/gateway/limits');
}

export async function createCheckout(params: { address: string; amount: number; currency: string }): Promise<{ checkout_url: string }> {
  return request('/api/gateway/create-checkout-session', { method: 'POST', body: JSON.stringify(params) });
}

export interface ChainStatus { chain: string; block_height: number; tps: number; latency_ms: number; acic_enabled: boolean; peers: number; status: 'online' | 'degraded' | 'offline'; }

export async function getCrossChainStatus(): Promise<{ chains: ChainStatus[] }> {
  return request('/api/network/chains');
}

export async function getAcicMetrics(): Promise<{ acic_tps: number; acic_latency_ms: number; acic_nodes: number; finality_seconds: number }> {
  return request('/api/network/acic');
}

export async function submitGpsTelemetry(params: { address: string; latitude: number; longitude: number; speed?: number; heading?: number; altitude?: number }): Promise<{ success: boolean }> {
  return request('/api/iot/submit_gps', { method: 'POST', body: JSON.stringify(params) });
}

export async function getLiveTelemetry(address: string): Promise<{ gps: { lat: number; lng: number; speed: number; heading: number }; battery: number; lidar_distance?: number; lane_deviation?: number }> {
  return request(`/api/iot/telemetry/live?address=${address}`);
}

export interface BridgeQuote { from_chain: string; to_chain: string; from_token: string; to_token: string; amount_in: number; amount_out: number; fee: number; estimated_time_min: number; }
export interface BridgeTransfer { id: string; from_chain: string; to_chain: string; from_token: string; to_token: string; amount: number; status: 'pending' | 'processing' | 'completed' | 'failed'; created_at: string; tx_hash?: string; }

export async function getBridgeQuote(params: { from_chain: string; to_chain: string; token: string; amount: number }): Promise<BridgeQuote> {
  const q = new URLSearchParams({ from: params.from_chain, to: params.to_chain, token: params.token, amount: String(params.amount) });
  return request(`/api/bridge/quote?${q}`);
}

export async function executeBridgeSigned(params: { from_chain: string; to_chain: string; signedTx: SignedTxEnvelope }): Promise<{ success: boolean; transfer?: BridgeTransfer; error?: string }> {
  return request('/api/bridge/execute', { method: 'POST', body: JSON.stringify({ from_chain: params.from_chain, to_chain: params.to_chain, tx: params.signedTx }) });
}

export async function getBridgeHistory(address: string): Promise<{ transfers: BridgeTransfer[] }> {
  return request(`/api/bridge/history/${address}`);
}

export async function bridgeBurnSigned(params: { btc_destination: string; signedTx: SignedTxEnvelope }): Promise<{ success: boolean; tx_hash?: string; btc_amount?: number; error?: string }> {
  return request('/api/bridge/burn', { method: 'POST', body: JSON.stringify({ btc_destination: params.btc_destination, tx: params.signedTx }) });
}

export async function getBridgeStats(): Promise<{ total_burned_thr: number; total_locked_btc: number; transaction_count: number; exchange_rate: number }> {
  return request('/api/bridge/stats');
}

export async function submitPledge(params: { btc_address: string; pledge_text: string }): Promise<{ ok: boolean; status?: string; thr_address?: string; secret_seed?: string; pledge_hash?: string; pending_confirmation?: boolean; error?: string }> {
  return request('/api/pledge', { method: 'POST', body: JSON.stringify({ btc_address: params.btc_address, pledge_text: params.pledge_text }) });
}

export async function getPledgeStatus(btc_address: string): Promise<{ ok: boolean; status?: string; thr_address?: string; pledge_hash?: string; pdf_filename?: string; send_secret?: string; pending_confirmation?: boolean }> {
  return request(`/api/pledge/status?btc=${encodeURIComponent(btc_address)}`);
}

export async function getBnbPledgeStatus(bnb_address: string): Promise<{ ok: boolean; status?: string; thr_address?: string; send_secret?: string; pdf_filename?: string; pending_confirmation?: boolean; error?: string }> {
  return request(`/api/pledge/bnb/status?bnb=${encodeURIComponent(bnb_address)}`);
}

export async function pledgeMigrate(params: { send_secret: string; pin: string }): Promise<{ ok: boolean; canonical_v1_address?: string; recovery_kit?: string; pdf_url?: string; error?: string }> {
  return request('/api/wallet/v1/pledge-migrate', { method: 'POST', body: JSON.stringify(params) });
}

export async function getBnbPledgeQuote(): Promise<{ ok: boolean; vault_address?: string; token_contract?: string; chain?: string; min_usdt?: number; usdt_thr_rate?: number }> {
  return request('/api/pledge/bnb/quote');
}

export async function registerBnbAddress(params: { thr_address?: string; bnb_address: string; passphrase?: string }): Promise<{ ok: boolean; thr_address?: string; vault_address?: string; error?: string }> {
  return request('/api/pledge/bnb/register', { method: 'POST', body: JSON.stringify(params) });
}

export async function recoverWallet(params: { pdf_filename?: string; recovery_phrase?: string }): Promise<{ success: boolean; thr_address?: string; send_secret?: string; error?: string }> {
  return request('/recovery', { method: 'POST', body: JSON.stringify(params) });
}

export async function getPhantomTxChain(): Promise<{ transactions: any[]; chain_height: number }> {
  return request('/api/phantom/tx_chain');
}

export async function getPhantomNodeStatus(): Promise<{ nodes_online: number; phantom_height: number; last_sync: string; consensus: string }> {
  return request('/api/phantom/status');
}

export async function getLiquidityPools(): Promise<{ pools: Array<{ id: string; token_a: string; token_b: string; total_liquidity: number; apy: number; volume_24h: number }> }> {
  return request('/api/v1/pools');
}

export interface ThrUsdtPoolInfo {
  ok: boolean;
  pool_exists: boolean;
  pool_id?: string;
  thr_reserve: number;
  usdt_reserve: number;
  thr_price_usd: number;
  usdt_thr_rate: number;
  pledge_count: number;
  next_level_at: number;
  next_price_usd: number;
  max_withdraw_usdt: number;
}

export async function getThrUsdtPoolInfo(): Promise<ThrUsdtPoolInfo> {
  return request('/api/v1/pool/thr-usdt');
}

export interface WithdrawResult {
  ok: boolean;
  withdrawal_id?: string;
  token?: string;
  amount?: number;
  amount_net?: number;
  fee_thr?: number;
  fee_pool_usdt?: number;
  dest_chain?: string;
  dest_address?: string;
  status?: string;
  estimated_minutes?: number;
  error?: string;
  available_usdt?: number;
  required_thr?: number;
  thr_balance?: number;
}

export async function requestWithdrawal(params: {
  address: string;
  send_secret: string;
  amount: number;
  token: 'USDT' | 'USDC';
  dest_chain: string;
  dest_address: string;
}): Promise<WithdrawResult> {
  return request('/api/v1/withdraw', { method: 'POST', body: JSON.stringify(params) });
}

export interface WithdrawChain {
  chain: string;
  label: string;
  tokens: string[];
}

export async function getWithdrawChains(): Promise<{ ok: boolean; chains: WithdrawChain[] }> {
  return request('/api/v1/withdraw/chains');
}

export interface EvmTokenBalanceResult {
  ok: boolean;
  chain?: string;
  address?: string;
  token_contract?: string;
  balance?: number;
  balance_raw?: string;
  error?: string;
  details?: string;
}

export async function getEvmTokenBalance(
  chain: 'bsc' | 'arbitrum' | 'base',
  address: string,
  tokenContract: string,
  decimals: number
): Promise<EvmTokenBalanceResult> {
  try {
    return await request('/api/evm/token-balance', {
      method: 'POST',
      body: JSON.stringify({ chain, address, token_contract: tokenContract, decimals }),
    });
  } catch (err: any) {
    return { ok: false, error: 'request_failed', details: err.message };
  }
}

export async function getLPPositions(address: string): Promise<{ positions: Array<{ pool_id: string; token_a: string; token_b: string; liquidity_share: number; value: number; pending_rewards: number }> }> {
  return request(`/api/v1/pools/positions/${address}`);
}

export async function addLiquidity(params: { from: string; pool_id: string; amount_a: number; amount_b: number; private_key_hex: string }): Promise<{ ok: boolean; status?: string; shares_minted?: number; error?: string }> {
  return request('/api/wallet/v1/add_liquidity', { method: 'POST', body: JSON.stringify({ from: params.from, pool_id: params.pool_id, amount_a: params.amount_a, amount_b: params.amount_b, private_key_hex: params.private_key_hex }) });
}

export interface ExternalChainInfo {
  chain: string;
  label: string;
  token_contract: string;
  decimals: number;
  token_standard: string;
}

export interface AvailablePool {
  pool_id: string;
  name: string;
  token_a: string;
  token_b: string;
  reserves_a: number;
  reserves_b: number;
  total_shares: number;
  pool_ratio: number | null;
  fee_bps: number;
  lp_symbol: string;
  external_chains: ExternalChainInfo[];
}

export async function getAvailablePools(): Promise<{ ok: boolean; pools: AvailablePool[] }> {
  return request('/api/v1/pools/available');
}

export interface AddLiquidityQuote {
  ok: boolean;
  pool_id?: string;
  token_a?: string;
  token_b?: string;
  amount_a?: number;
  amount_b?: number;
  pool_ratio?: number;
  lp_shares_estimate?: number;
  share_pct?: number;
  fee_bps?: number;
  chain_info?: ExternalChainInfo | null;
  gas_warning?: string;
  slippage_tolerance_pct?: number;
  error?: string;
}

export async function quoteAddLiquidity(poolId: string, amountA: number, chain?: string): Promise<AddLiquidityQuote> {
  const params = new URLSearchParams({ pool_id: poolId, amount_a: String(amountA) });
  if (chain) params.set('chain', chain);
  return request(`/api/v1/pools/quote-add-liquidity?${params}`);
}

export interface CrossChainAddLiquidityResult {
  ok: boolean;
  tx_id?: string;
  pool_id?: string;
  lp_shares_minted?: number;
  reserves_a?: number;
  reserves_b?: number;
  external_chain?: string;
  status?: string;
  message?: string;
  gas_warning?: string;
  error?: string;
}

export async function addLiquidityCrossChain(params: {
  pool_id: string;
  amount_a: number;
  amount_b: number;
  chain: string;
  token_contract: string;
  decimals: number;
  provider_thr: string;
  evm_address: string;
  auth_secret: string;
  passphrase?: string;
}): Promise<CrossChainAddLiquidityResult> {
  return request('/api/v1/pools/add-liquidity', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

export async function removeLiquiditySigned(params: { pool_id: string; shares: number; signedTx: SignedTxEnvelope }): Promise<{ success: boolean; amount_a?: number; amount_b?: number; error?: string }> {
  return request('/api/v1/pools/remove_liquidity', { method: 'POST', body: JSON.stringify({ pool_id: params.pool_id, shares: params.shares, tx: params.signedTx }) });
}

export interface HalvingEntry {
  epoch: number;
  halving_date: string;
  block_height: number;
  reward_before: number;
  reward_after: number;
  supply_at_halving: number;
  epoch_duration_hours: number;
  blocks_until_halving: number;
}

export async function getHalvingSchedule(): Promise<{ total_supply: number; block_time_minutes: number; halving_interval_blocks: number; halvings: HalvingEntry[] }> {
  return request('/api/mining/halving-schedule');
}

export interface CurrentEpochInfo {
  epoch: number;
  block_range: string;
  current_block: number;
  blocks_until_halving: number;
  halving_date_estimate: string;
  current_reward: number;
  reward_distribution: Record<string, number>;
  supply_circulating: number;
  supply_max: number;
}

export async function getCurrentEpoch(blockHeight?: number): Promise<CurrentEpochInfo> {
  return request(`/api/mining/current-epoch${blockHeight ? `?block_height=${blockHeight}` : ''}`);
}

export async function getMiningEcosystemStats(): Promise<{
  total_supply_max: number;
  initial_reward: number;
  block_time_minutes: number;
  halving_interval_blocks: number;
  halving_interval_months: number;
  estimated_full_circulation_years: number;
}> {
  return request('/api/mining/ecosystem-stats');
}

export interface ThronosToken {
  id?: string;
  symbol: string;
  name: string;
  decimals: number;
  owner: string;
  total_supply: number;
}

export async function createToken(params: { from: string; name: string; symbol: string; total_supply: number; decimals: number; private_key_hex: string }): Promise<{ ok: boolean; status?: string; token?: ThronosToken; error?: string }> {
  return request('/api/wallet/v1/create_token', { method: 'POST', body: JSON.stringify(params) });
}

export interface ThronosNft {
  id: string;
  name: string;
  description?: string;
  category?: string;
  price: number;
  royalties: number;
  creator: string;
  owner: string;
  image_url?: string;
  for_sale: boolean;
  created_at?: string;
}

export async function getNfts(): Promise<{ nfts: ThronosNft[] }> {
  return request('/api/v1/nfts');
}

export async function mintNft(params: { from: string; name: string; description?: string; category?: string; price?: number; royalties?: number; image_data_url?: string; private_key_hex: string }): Promise<{ ok: boolean; status?: string; nft?: ThronosNft; error?: string }> {
  return request('/api/wallet/v1/nfts/mint', { method: 'POST', body: JSON.stringify(params) });
}

export async function buyNft(params: { from: string; nft_id: string; private_key_hex: string }): Promise<{ ok: boolean; status?: string; nft?: ThronosNft; error?: string }> {
  return request('/api/wallet/v1/nfts/buy', { method: 'POST', body: JSON.stringify(params) });
}

export async function getMiningInfo(address: string): Promise<{ hashrate: number; pending_reward: number; total_mined: number; blocks_found: number; last_payout: string }> {
  return request(`/api/mining/info?address=${address}`);
}

export async function getWalletData(address: string, category = 'all', limit = 50): Promise<any> {
  return request(`/wallet_data/${address}?category=${category}&limit=${limit}`);
}
