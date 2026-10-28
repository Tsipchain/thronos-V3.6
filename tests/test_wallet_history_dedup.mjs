import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync('public/wallet-pwa/app.js', 'utf8');
const start = source.indexOf('  function _walletHistoryChain(value) {');
const end = source.indexOf('  async function loadHistory() {', start);
assert.ok(start >= 0 && end > start, 'history dedup helpers must exist before loadHistory');

const helperSource = source.slice(start, end);
const dedupeUnifiedWalletHistory = new Function(
  helperSource + '\nreturn _dedupeUnifiedWalletHistory;'
)();

const poolEvents = dedupeUnifiedWalletHistory([
  { id: 'thr-intent', original_event_type: 'pool_add_liquidity_intent_created', domain: 'liquidity', chain: 'thronos', pool_id: 'bsc-usdt', internal_txid: 'intent-1', status: 'pending' },
  { id: 'thr-confirmed', original_event_type: 'pool_add_liquidity_external_tx_confirmed', domain: 'liquidity', chain: 'thronos', pool_id: 'bsc-usdt', internal_txid: 'intent-1', status: 'confirmed' },
  { id: 'thr-lp', original_event_type: 'pool_add_liquidity_lp_minted', domain: 'liquidity', chain: 'thronos', pool_id: 'bsc-usdt', internal_txid: 'intent-1', status: 'confirmed', lp_shares: 12 },
  { id: 'bsc-intent', original_event_type: 'pool_add_liquidity_intent_created', domain: 'liquidity', chain: 'bsc', pool_id: 'bsc-usdt', internal_txid: 'intent-1', status: 'pending' },
  { id: 'bsc-confirmed', original_event_type: 'pool_add_liquidity_external_tx_confirmed', domain: 'liquidity', chain: 'bsc', pool_id: 'bsc-usdt', internal_txid: 'intent-1', external_txid: '0xsource', tx_hash: '0xsource', status: 'confirmed', asset: 'USDT' },
]);

assert.equal(poolEvents.length, 2, 'pool add should show once per chain');
assert.ok(poolEvents.some(e => e.chain === 'thronos' && e.event_type === 'pool_add_liquidity_lp_minted'), 'Thronos row should prefer LP minted');
assert.ok(poolEvents.some(e => e.chain === 'bsc' && e.event_type === 'pool_add_liquidity_external_tx_confirmed'), 'BSC row should prefer confirmed deposit');

const duplicates = dedupeUnifiedWalletHistory([
  { id: 'api-row-1', event_type: 'token_receive', domain: 'token', chain: 'bsc', tx_hash: '0xtoken', asset: 'USDT', direction: 'in', status: 'confirmed' },
  { id: 'api-row-2', event_type: 'token_receive', domain: 'token', chain: 'bnb', tx_hash: '0xTOKEN', asset: 'USDT', direction: 'in', status: 'confirmed' },
]);
assert.equal(duplicates.length, 1, 'same chain/hash/asset/direction from multiple feeds should collapse');

const sameTxDifferentLogs = dedupeUnifiedWalletHistory([
  { id: 'log-2', event_type: 'token_receive', domain: 'token', chain: 'bsc', tx_hash: '0xmulti', log_index: 2, asset: 'USDT', direction: 'in' },
  { id: 'log-3', event_type: 'token_receive', domain: 'token', chain: 'bsc', tx_hash: '0xmulti', log_index: 3, asset: 'USDT', direction: 'in' },
]);
assert.equal(sameTxDifferentLogs.length, 2, 'distinct log indices in one transaction must remain distinct');

const bridgeSides = dedupeUnifiedWalletHistory([
  { id: 'source', event_type: 'crosschain_transfer_sent', domain: 'gateway', chain: 'bsc', bridge_id: 'bridge-1', tx_hash: '0xbsc' },
  { id: 'destination', event_type: 'crosschain_transfer_received', domain: 'gateway', chain: 'arbitrum', bridge_id: 'bridge-1', tx_hash: '0xarb' },
]);
assert.equal(bridgeSides.length, 2, 'source and destination chain events must remain separately visible');

console.log('Wallet history dedup tests passed: pool lifecycle, same-hash duplicates, log index, cross-chain sides.');
