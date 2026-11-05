import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const window = {};
vm.runInNewContext(readFileSync(new URL('../public/wallet-pwa/earn-leaderboard.js', import.meta.url), 'utf8'), { window });
const { remaining, clock } = window.ThronosEarnLeaderboard;

test('countdown uses server time and elapsed time instead of the device wall clock', () => {
  assert.equal(remaining(30 * 86400, 0, 0), 2592000);
  assert.equal(remaining(30 * 86400, 0, 1000), 2591999);
  assert.equal(clock(2592000), '30d 00:00:00');
});
test('deadline reaches zero without automatically starting a new cycle', () => {
  assert.equal(remaining(100, 99, 1000), 0);
  assert.equal(remaining(100, 99, 100000), 0);
  assert.equal(clock(0), '0d 00:00:00');
});
test('invalid server times do not produce a fictional countdown', () => {
  assert.equal(remaining(NaN, 1), null);
  assert.equal(remaining(10, undefined), null);
  assert.equal(clock(null), '—');
});
