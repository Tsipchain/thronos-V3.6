// Thronos Wallet API Service
// Communicates with the Thronos blockchain backend
// Node 1 (master) primary, Node 2 (replica) fallback

import { CONFIG } from '../constants/config';

const BASE = CONFIG.API_URL;
const BASE_REPLICA = CONFIG.API_URL_REPLICA;

async function request<T = any>(endpoint: string, options?: RequestInit): Promise<T> {
  // Try Node 1 (master) first, fallback to Node 2 (replica)
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
      // Node 1 failed, try Node 2
      continue;
    }
  }
  throw new Error('All nodes unreachable');
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
  category?: string,
): Promise<any> {
  const params = new URLSearchParams({ address, limit: String(limit) });
  if (category && category !== 'all') params.set('category', category);
  return request(`/api/wallet/history?${params}`);
}

export async function getTransactionsByCategory(
  address: string,
  category = 'all',
  limit = 50,
): Promise<{ transactions: any[] }> {
  return request(`/api/v1/address/${address}/history?category=${category}&limit=${limit}`);
}

// ── Chain Info ─────────────────────────────────────────────────────────────────

export async function getChainTokens(): Promise<{ tokens: any[] }> {
  return request('/api/tokens/list');
}

export async function getNetworkStatus(): Promise<{
  block_height: number;
  tps: number;
  peers: number;
  mempool: number;
  total_supply: number;
  chain_height: number;
  [key: string]: any;
}> {
  // Fetch status and peers in parallel
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
  const data = await request(`/api/swap/quote?token_in=${from}&token_out=${to}&amount_in=${amount}`);
  // API returns amount_out but not rate — compute rate for display
  const amountOut = Number(data.amount_out) || 0;
  const fee = Number(data.fee) || 0;
  const rate = amount > 0 ? amountOut / amount : 0;
  return { rate, amount_out: amountOut, fee };
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
    body: JSON.stringify({
      token_in: params.from_token,
      token_out: params.to_token,
      amount_in: params.amount,
      trader_thr: params.address,
      auth_secret: params.secret,
    }),
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

// ── Music (Decent Music) ─────────────────────────────────────────────────────

export interface MusicTrack {
  id: string;
  title: string;
  artist_name?: string;
  artist_address?: string;
  genre?: string;
  description?: string;
  audio_url?: string;
  cover_url?: string;
  play_count?: number;
  tips_total?: number;
  uploaded_at?: string;
  published?: boolean;
}

export interface MusicPlaylist {
  id: string;
  name: string;
  track_count: number;
  total_duration: number;
  created_at: string;
}

export async function getMusicTracks(
  address?: string,
): Promise<{ tracks: MusicTrack[] }> {
  const q = address ? `?address=${address}` : '';
  return request(`/api/v1/music/tracks${q}`);
}

export async function recordPlay(
  trackId: string,
  address: string,
): Promise<{ success: boolean }> {
  return request(`/api/v1/music/play/${trackId}`, {
    method: 'POST',
    body: JSON.stringify({ address }),
  });
}

export async function tipArtist(params: {
  address: string;
  track_id: string;
  artist: string;
  amount: number;
}): Promise<{ success: boolean; tx_hash?: string }> {
  return request('/api/v1/music/tip', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

export async function getMusicPlaylists(
  address: string,
): Promise<{ playlists: MusicPlaylist[] }> {
  return request(`/api/music/playlists?address=${address}`);
}

export async function saveOfflineTrack(
  trackId: string,
  address: string,
): Promise<{ success: boolean }> {
  return request('/api/music/offline/save', {
    method: 'POST',
    body: JSON.stringify({ track_id: trackId, address }),
  });
}

export async function getOfflineTracks(
  address: string,
): Promise<{ tracks: MusicTrack[] }> {
  return request(`/api/music/offline/${address}`);
}

export async function startMusicSession(params: {
  address: string;
  latitude?: number;
  longitude?: number;
  carplay?: boolean;
  android_auto?: boolean;
}): Promise<{ session_id: string; success: boolean }> {
  return request('/api/music/session/start', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

export async function endMusicSession(
  sessionId: string,
  address: string,
): Promise<{ success: boolean; plays: number; rewards?: number }> {
  return request('/api/music/session/end', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, address }),
  });
}

export async function submitMusicGpsTelemetry(params: {
  address: string;
  session_id: string;
  latitude: number;
  longitude: number;
  speed?: number;
}): Promise<{ success: boolean }> {
  return request('/api/music/gps_telemetry', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

export async function getMusicEarnings(
  address: string,
): Promise<{
  stats: { total_tracks: number; total_plays: number; total_earnings_thr: number };
  artist?: { name: string; bio?: string };
  tracks?: any[];
}> {
  return request(`/api/v1/music/artist/${address}`);
}

export async function searchMusic(query: string): Promise<{ tracks: MusicTrack[] }> {
  return request(`/api/music/search?q=${encodeURIComponent(query)}`);
}

// ── Governance ──────────────────────────────────────────────────────────────

export async function getGovernanceProposals(): Promise<{ proposals: any[] }> {
  return request('/api/v1/governance/proposals');
}

export async function voteOnProposal(params: {
  address: string;
  proposal_id: string;
  vote: 'yes' | 'no' | 'abstain';
  secret: string;
}): Promise<{ success: boolean }> {
  return request('/api/v1/governance/vote', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

// ── AI Credits ──────────────────────────────────────────────────────────────

export async function getAiSessionHistory(address: string): Promise<{ sessions: any[] }> {
  return request(`/api/ai_session_history?address=${address}`);
}

// ── Gateway (Fiat On/Off Ramp) ─────────────────────────────────────────────

export async function getGatewayLimits(): Promise<any> {
  return request('/api/gateway/limits');
}

export async function createCheckout(params: {
  address: string;
  amount: number;
  currency: string;
}): Promise<{ checkout_url: string }> {
  return request('/api/gateway/create-checkout-session', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

// ── Cross-Chain / ACIC ───────────────────────────────────────────────────────

export interface ChainStatus {
  chain: string;
  block_height: number;
  tps: number;
  latency_ms: number;
  acic_enabled: boolean;
  peers: number;
  status: 'online' | 'degraded' | 'offline';
}

export async function getCrossChainStatus(): Promise<{ chains: ChainStatus[] }> {
  return request('/api/network/chains');
}

export async function getAcicMetrics(): Promise<{
  acic_tps: number;
  acic_latency_ms: number;
  acic_nodes: number;
  finality_seconds: number;
}> {
  return request('/api/network/acic');
}

// ── IoT / Telemetry ──────────────────────────────────────────────────────────

export async function submitGpsTelemetry(params: {
  address: string;
  latitude: number;
  longitude: number;
  speed?: number;
  heading?: number;
  altitude?: number;
}): Promise<{ success: boolean }> {
  return request('/api/iot/submit_gps', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

export async function getLiveTelemetry(
  address: string,
): Promise<{
  gps: { lat: number; lng: number; speed: number; heading: number };
  battery: number;
  lidar_distance?: number;
  lane_deviation?: number;
}> {
  return request(`/api/iot/telemetry/live?address=${address}`);
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

// ── Bridge Burn (THR → BTC) ──────────────────────────────────────────────────

export async function bridgeBurn(params: {
  wallet: string;
  amount: number;
  btc_destination: string;
  secret: string;
}): Promise<{ success: boolean; tx_hash?: string; btc_amount?: number; error?: string }> {
  return request('/api/bridge/burn', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

export async function getBridgeStats(): Promise<{
  total_burned_thr: number;
  total_locked_btc: number;
  transaction_count: number;
  exchange_rate: number;
}> {
  return request('/api/bridge/stats');
}

// ── Pledge System (BTC Entry Flow) ──────────────────────────────────────────

export async function submitPledge(params: {
  btc_address: string;
  pledge_text: string;
  recovery_phrase?: string;
}): Promise<{
  success: boolean;
  thr_address?: string;
  send_secret?: string;
  pledge_hash?: string;
  pdf_filename?: string;
  error?: string;
}> {
  return request('/api/pledge/submit', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

export async function verifyBtcPayment(
  btc_address: string,
): Promise<{
  verified: boolean;
  amount?: number;
  txid?: string;
}> {
  return request(`/api/pledge/verify_btc/${btc_address}`);
}

export async function downloadPledgePdf(
  thr_address: string,
): Promise<{ pdf_url: string }> {
  return request(`/api/pledge/pdf/${thr_address}`);
}

export async function recoverWallet(params: {
  pdf_filename?: string;
  recovery_phrase?: string;
}): Promise<{
  success: boolean;
  thr_address?: string;
  send_secret?: string;
  error?: string;
}> {
  return request('/recovery', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

// ── Phantom Network ──────────────────────────────────────────────────────────

export async function getPhantomTxChain(): Promise<{
  transactions: any[];
  chain_height: number;
}> {
  return request('/api/phantom/tx_chain');
}

export async function getPhantomNodeStatus(): Promise<{
  nodes_online: number;
  phantom_height: number;
  last_sync: string;
  consensus: string;
}> {
  return request('/api/phantom/status');
}

// ── Liquidity Pools ──────────────────────────────────────────────────────────

export async function getLiquidityPools(): Promise<{
  pools: Array<{
    id: string;
    token_a: string;
    token_b: string;
    total_liquidity: number;
    apy: number;
    volume_24h: number;
  }>;
}> {
  return request('/api/v1/pools');
}

export async function getLPPositions(address: string): Promise<{
  positions: Array<{
    pool_id: string;
    token_a: string;
    token_b: string;
    liquidity_share: number;
    value: number;
    pending_rewards: number;
  }>;
}> {
  return request(`/api/v1/pools/positions/${address}`);
}

export async function addLiquidity(params: {
  address: string;
  pool_id: string;
  amount_a: number;
  amount_b: number;
  secret: string;
}): Promise<{ success: boolean; shares?: number; error?: string }> {
  return request('/api/v1/pools/add_liquidity', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

export async function removeLiquidity(params: {
  address: string;
  pool_id: string;
  shares: number;
  secret: string;
}): Promise<{ success: boolean; amount_a?: number; amount_b?: number; error?: string }> {
  return request('/api/v1/pools/remove_liquidity', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

// ── Mining Rewards ───────────────────────────────────────────────────────────

export async function getMiningInfo(address: string): Promise<{
  hashrate: number;
  pending_reward: number;
  total_mined: number;
  blocks_found: number;
  last_payout: string;
}> {
  return request(`/api/mining/info?address=${address}`);
}

// ── Wallet Data (categorized history from mainchain) ─────────────────────────

export async function getWalletData(
  address: string,
  category = 'all',
  limit = 50,
): Promise<any> {
  return request(`/wallet_data/${address}?category=${category}&limit=${limit}`);
}
