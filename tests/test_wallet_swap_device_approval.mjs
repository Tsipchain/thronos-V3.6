import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync('thronos-wallet-app/src/screens/SwapScreen.tsx', 'utf8');

assert.match(
  source,
  /imports*{s*getWallet,s*authenticateWithBiometricss*}s*from '../services/wallet';/,
  'Swap screen must import the device-approval gate.',
);

const handleStart = source.indexOf('const handleSwap = async () =>');
const handleEnd = source.indexOf('\n  return (', handleStart);
assert.ok(handleStart >= 0 && handleEnd > handleStart, 'Swap handler must be present.');
const handler = source.slice(handleStart, handleEnd);

const approval = handler.indexOf("authenticateWithBiometrics('Approve Thronos swap')");
const signing = handler.indexOf('signThronosTransaction(');
assert.ok(approval >= 0, 'Swap must request device approval.');
assert.ok(signing >= 0, 'Swap handler must sign only after approval.');
assert.ok(approval < signing, 'Device approval must precede signing.');
assert.match(
  handler,
  /ifs*(!approved)s*{[\s\S]*?return;/,
  'Denied approval must stop the swap before signing.',
);

console.log('wallet mobile swap approval gate verified');
