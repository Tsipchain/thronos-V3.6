import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync('thronos-wallet-app/src/screens/SwapScreen.tsx', 'utf8');
const signer = readFileSync('thronos-wallet-app/src/services/signing.ts', 'utf8');

assert.ok(
  source.includes("import { signWalletV1FullPayloadRequest } from '../services/signing';"),
  'Swap screen must use the centralized full-payload signer.',
);

const handleStart = source.indexOf('const handleSwap = async () =>');
const handleEnd = source.indexOf('\n  return (', handleStart);
assert.ok(handleStart >= 0 && handleEnd > handleStart, 'Swap handler must be present.');
const handler = source.slice(handleStart, handleEnd);

assert.ok(
  handler.includes("signWalletV1FullPayloadRequest('swap'"),
  'Swap must authorize the swap action through the V2 signer.',
);

const signerStart = signer.indexOf('export async function signWalletV1FullPayloadRequest(');
const signerEnd = signer.indexOf('\nfunction canonicalize(', signerStart);
assert.ok(signerStart >= 0 && signerEnd > signerStart, 'Centralized V2 signer must be present.');
const signerBody = signer.slice(signerStart, signerEnd);
const approval = signerBody.indexOf('authenticateWithBiometrics(');
const denial = signerBody.indexOf("if (!approved) throw new Error('signing_cancelled')");
const keyAccess = signerBody.indexOf('const privateKeyHex = await getPrivKeyHex()');
assert.ok(approval >= 0, 'Centralized signer must request device approval.');
assert.ok(denial > approval, 'Denied approval must fail closed.');
assert.ok(keyAccess > denial, 'Device approval must precede access to signing material.');

console.log('wallet mobile V2 approval gate verified');
