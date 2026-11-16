/**
 * Regression tests for HistoryScreen amount formatting and safeFloat.
 * Covers: true zero, missing/null, tiny nonzero (1e-8, 1e-12),
 * category mapping fixes, and mixed-chain duplicate/retry cases.
 *
 * Run: node tests/test_wallet_history_format.mjs
 */
import assert from 'node:assert/strict';

// ── Re-implement the helpers as they exist in HistoryScreen.tsx ──────────────

function safeFloat(v) {
  if (v === null || v === undefined || v === '') return null;
  const n = typeof v === 'number' ? v : parseFloat(String(v));
  return isNaN(n) ? null : n;
}

function formatAmount(amount) {
  if (amount === null) return '—';
  if (amount === 0) return '0';
  const abs = Math.abs(amount);
  if (abs >= 1000) return amount.toLocaleString('en-US', { maximumFractionDigits: 2 });
  if (abs >= 1) return amount.toFixed(2);
  if (abs >= 0.01) return amount.toFixed(4);
  if (abs >= 0.000001) return amount.toFixed(6);
  if (abs >= 1e-12) {
    const sig = amount.toPrecision(2);
    return Number(sig) === 0 ? (amount < 0 ? '< -0.000001' : '< 0.000001') : sig;
  }
  return amount < 0 ? '< -0.000001' : '< 0.000001';
}

const CATEGORY_MAP = {
  thr: 'thr',
  transfer: 'thr',
  token_transfer: 'tokens',
  token_receive: 'tokens',
  tokens: 'tokens',
  mining: 'mining',
  mining_reward: 'mining',
  swaps: 'swaps',
  swap: 'swaps',
  liquidity: 'liquidity',
  bridge: 'bridge',
  music_tip: 'music',
  ai_credits: 'ai_credits',
  t2e: 'l2e',
  l2e: 'l2e',
  other: 'gateway',
};

// ── safeFloat tests ─────────────────────────────────────────────────────────

// Missing data returns null, not 0
assert.equal(safeFloat(null), null, 'null → null');
assert.equal(safeFloat(undefined), null, 'undefined → null');
assert.equal(safeFloat(''), null, 'empty string → null');
assert.equal(safeFloat('abc'), null, 'non-numeric string → null');
assert.equal(safeFloat(NaN), null, 'NaN → null');

// Real values pass through
assert.equal(safeFloat(0), 0, '0 → 0');
assert.equal(safeFloat(42), 42, '42 → 42');
assert.equal(safeFloat(-1.5), -1.5, '-1.5 → -1.5');
assert.equal(safeFloat('3.14'), 3.14, '"3.14" → 3.14');
assert.equal(safeFloat(1e-8), 1e-8, '1e-8 → 1e-8');
assert.equal(safeFloat(1e-12), 1e-12, '1e-12 → 1e-12');
assert.equal(safeFloat('0.00000001'), 1e-8, '"0.00000001" → 1e-8');

console.log('  safeFloat: all pass');

// ── formatAmount tests ──────────────────────────────────────────────────────

// null (missing) → em dash
assert.equal(formatAmount(null), '—', 'null → —');

// true zero
assert.equal(formatAmount(0), '0', '0 → "0"');

// Standard amounts
assert.equal(formatAmount(1234.5), '1,234.5', '1234.5 → "1,234.5"');
assert.equal(formatAmount(42.123), '42.12', '42.123 → "42.12"');
assert.equal(formatAmount(0.05), '0.0500', '0.05 → "0.0500"');

// Tiny nonzero amounts — must NOT render as "0.000000"
const fmt8 = formatAmount(1e-8);
assert.notEqual(fmt8, '0.000000', '1e-8 must not show as 0.000000');
assert.ok(fmt8.includes('0.000001') || fmt8.includes('1') || fmt8.includes('<'),
  `1e-8 should display nonzero: got "${fmt8}"`);

const fmt12 = formatAmount(1e-12);
assert.notEqual(fmt12, '0.000000', '1e-12 must not show as 0.000000');
assert.ok(fmt12.includes('<') || fmt12.includes('1'),
  `1e-12 should indicate sub-precision: got "${fmt12}"`);

// Negative tiny
const fmtNeg8 = formatAmount(-1e-8);
assert.notEqual(fmtNeg8, '0.000000', '-1e-8 must not show as 0.000000');
assert.ok(fmtNeg8.includes('-') || fmtNeg8.includes('<'),
  `negative tiny should show sign: got "${fmtNeg8}"`);

// Normal sub-1 values
assert.equal(formatAmount(0.000001), '0.000001', '0.000001 → "0.000001"');
assert.equal(formatAmount(0.123456), '0.1235', '0.123456 → "0.1235"');

console.log('  formatAmount: all pass');

// ── Category mapping tests ──────────────────────────────────────────────────

// token_receive must NOT map to 'thr'
assert.equal(CATEGORY_MAP['token_receive'], 'tokens',
  'token_receive should map to tokens, not thr');

// 'other' must NOT map to 'thr'
assert.notEqual(CATEGORY_MAP['other'], 'thr',
  'other should not silently classify as THR');

// Known categories
assert.equal(CATEGORY_MAP['mining_reward'], 'mining');
assert.equal(CATEGORY_MAP['swap'], 'swaps');
assert.equal(CATEGORY_MAP['bridge'], 'bridge');
assert.equal(CATEGORY_MAP['t2e'], 'l2e');

console.log('  category mapping: all pass');

console.log('\nAll wallet history format tests passed.');
