import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync('thronos-wallet-app/src/screens/SwapScreen.tsx', 'utf8');
const signer = readFileSync('thronos-wallet-app/src/services/signing.ts', 'utf8');
const sendScreen = readFileSync('thronos-wallet-app/src/screens/SendScreen.tsx', 'utf8');

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
assert.ok(
  signerBody.includes('approveAndGetSigningKey('),
  'V2 signer must use the centralized approval/key-access boundary.',
);
assert.ok(!signer.includes('requireDeviceApproval'), 'Production signer must not expose an approval bypass.');

const approvalHelperStart = signer.indexOf('async function approveAndGetSigningKey(');
const approvalHelperEnd = signer.indexOf('\nfunction signHash(', approvalHelperStart);
assert.ok(approvalHelperStart >= 0 && approvalHelperEnd > approvalHelperStart,
  'Centralized approval/key-access helper must be present.');
const approvalHelper = signer.slice(approvalHelperStart, approvalHelperEnd);
const approval = approvalHelper.indexOf('authenticateWithBiometrics(');
const denial = approvalHelper.indexOf("if (!approved) throw new Error('signing_cancelled')");
const accountRecheck = approvalHelper.indexOf('const after = await getWallet()');
const keyAccess = approvalHelper.indexOf('return getPrivKeyHex()');
assert.ok(approval >= 0, 'Centralized signer must request device approval.');
assert.ok(denial > approval, 'Denied approval must fail closed.');
assert.ok(accountRecheck > denial, 'Account must be rechecked after approval.');
assert.ok(keyAccess > accountRecheck, 'Key access must follow approval and account recheck.');

for (const entryPoint of ['signThronosTransaction', 'signMessage']) {
  const start = signer.indexOf(`export async function ${entryPoint}(`);
  const end = signer.indexOf('\nexport ', start + 1);
  const body = signer.slice(start, end >= 0 ? end : signer.length);
  assert.ok(start >= 0 && body.includes('approveAndGetSigningKey('),
    `${entryPoint} must use centralized device approval.`);
  assert.ok(!body.includes('getPrivKeyHex()'),
    `${entryPoint} must not retrieve a key outside the approval helper.`);
}

const sendSign = sendScreen.indexOf('const signedTx = await signThronosTransaction(');
const sendNetwork = sendScreen.indexOf('await sendTHRSigned(', sendSign);
const tokenNetwork = sendScreen.indexOf('await sendTokenSigned(', sendSign);
assert.ok(sendSign >= 0, 'Native Send must sign locally.');
assert.ok(sendNetwork > sendSign && tokenNetwork > sendSign,
  'Native Send must not make a network request before approved local signing succeeds.');

console.log('wallet mobile signing approval gates verified');
