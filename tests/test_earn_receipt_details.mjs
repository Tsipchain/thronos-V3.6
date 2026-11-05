import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const window = {};
vm.runInNewContext(readFileSync(new URL('../public/wallet-pwa/earn-receipt-details.js', import.meta.url), 'utf8'), { window });
const { countdown } = window.ThronosEarnReceipts;

test('absent or invalid provider ETA never invents a countdown', () => {
  for (const eta of [null, undefined, '', 0, -1, 'invalid', 1.5]) assert.equal(countdown(eta, 0), null);
});
test('countdown reflects an exact provider timestamp and updates with elapsed time', () => {
  assert.equal(countdown(90061, 0).text, '1d 01:01:01');
  assert.equal(countdown(90061, 1000).text, '1d 01:01:00');
});
test('elapsed estimate is marked expired rather than released', () => {
  assert.equal(countdown(1, 2000).expired, true);
  assert.equal(countdown(1, 2000).text, '0d 00:00:00');
});
