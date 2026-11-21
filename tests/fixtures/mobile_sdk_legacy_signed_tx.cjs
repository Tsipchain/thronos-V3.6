'use strict';

// Synthetic historical Mobile SDK vector. Never use production mnemonic data.
const path = require('path');
const sdkModules = path.resolve(__dirname, '../../mobile-sdk/node_modules');
const bip39 = require(path.join(sdkModules, 'bip39'));
const bip32 = require(path.join(sdkModules, 'bip32'));
const CryptoJS = require(path.join(sdkModules, 'crypto-js'));
const elliptic = require(path.join(sdkModules, 'elliptic'));

const mnemonic = 'abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about';
const seed = bip39.mnemonicToSeedSync(mnemonic);
const child = bip32.fromSeed(seed).derivePath("m/44'/1'/0'/0/0");
const publicKey = child.publicKey.toString('hex');
const privateKey = child.privateKey.toString('hex');
const legacyHash = CryptoJS.RIPEMD160(CryptoJS.SHA256(publicKey).toString()).toString();
const canonicalHash = CryptoJS.RIPEMD160(CryptoJS.SHA256(CryptoJS.enc.Hex.parse(publicKey))).toString();
const legacyAddress = `THR${legacyHash.toUpperCase()}`;
const canonicalAddress = `THR${canonicalHash.toUpperCase()}`;

const payload = {
  from: process.argv[3] || legacyAddress,
  to: `THR${'C'.repeat(40)}`,
  amount: 7,
  token: 'THR',
  nonce: process.argv[2] || `legacy-roundtrip-${Date.now()}`,
  timestamp: Math.floor(Date.now() / 1000),
};
const canonical = JSON.stringify(payload, Object.keys(payload).sort());
const digest = require('crypto').createHash('sha256').update(Buffer.from(canonical, 'utf8')).digest();
const signature = new elliptic.ec('secp256k1').keyFromPrivate(privateKey).sign(digest).toDER('hex');

process.stdout.write(JSON.stringify({
  signedTx: { ...payload, signature, publicKey },
  legacyAddress,
  canonicalAddress,
  publicKey,
}));
