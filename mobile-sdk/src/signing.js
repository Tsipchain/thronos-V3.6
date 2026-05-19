/**
 * Thronos Mobile SDK - Transaction Signing Service (FIXED - ECDSA/secp256k1)
 * Handles client-side signing of transactions with real secp256k1 ECDSA
 * Private keys never transmitted or stored persistently
 */

const elliptic = require('elliptic');
const crypto = require('crypto');

const ec = new elliptic.ec('secp256k1');

/**
 * Create canonical payload string for signing.
 * Must match backend's canonicalization exactly.
 */
function canonicalPayloadString(payload) {
  // Verify timestamp is in seconds, not milliseconds
  if (payload.timestamp > 1e10) {
    throw new Error(
      `Invalid timestamp ${payload.timestamp}: must be UNIX seconds (< 1e10), not milliseconds`
    );
  }

  const obj = {
    amount: payload.amount,
    from: payload.from,
    nonce: payload.nonce,
    timestamp: payload.timestamp,
    to: payload.to,
    token: payload.token,
  };

  // Compact JSON with sorted keys - must match backend exactly
  return JSON.stringify(obj, Object.keys(obj).sort());
}

/**
 * Sign canonical payload with ECDSA/secp256k1 + SHA256.
 */
function signCanonicalPayload(canonical, privateKeyHex) {
  const canonicalBytes = Buffer.from(canonical, 'utf8');

  // Hash with SHA256
  const hash = crypto.createHash('sha256').update(canonicalBytes).digest();

  // ECDSA sign using secp256k1
  const keyPair = ec.keyFromPrivate(privateKeyHex);
  const signature = keyPair.sign(hash);

  // DER encoding
  return signature.toDER('hex');
}

/**
 * Convert compressed public key to uncompressed format for backend.
 */
function publicKeyCompressedToUncompressed(compressedHex) {
  const keyPair = ec.keyFromPublic(compressedHex, 'hex');
  return keyPair.getPublic('hex'); // Returns uncompressed (65 bytes)
}

/**
 * Sign a transaction with wallet's private key
 * @param {object} params - Transaction parameters
 * @param {object} wallet - Wallet instance with privateKey and publicKey
 * @returns {Promise<object>} - Signed transaction envelope
 */
export async function signThronosTransaction(params, wallet) {
  try {
    if (!wallet) {
      throw new Error('Wallet required for signing');
    }

    if (!wallet.privateKey || !wallet.publicKey) {
      throw new Error(
        'Wallet missing privateKey or publicKey. Ensure wallet is properly initialized.'
      );
    }

    // Ensure timestamp is UNIX seconds, not milliseconds
    const timestampSeconds = params.timestamp || Math.floor(Date.now() / 1000);
    if (timestampSeconds > 1e10) {
      throw new Error(
        `Timestamp too large: ${timestampSeconds}. Use UNIX seconds (e.g. 1710000000), not milliseconds.`
      );
    }

    // Create canonical payload
    const payload = {
      from: params.from,
      to: params.to,
      amount: params.amount,
      token: params.token || 'THR',
      nonce: params.nonce || `tx_${Date.now()}`,
      timestamp: timestampSeconds,
    };

    // Canonicalize for signing
    const canonical = canonicalPayloadString(payload);

    // Sign with ECDSA/secp256k1 (NOT HMAC-SHA256)
    const signature = signCanonicalPayload(canonical, wallet.privateKey);

    // Get uncompressed public key for backend
    const publicKeyUncompressed = publicKeyCompressedToUncompressed(wallet.publicKey);

    return {
      ...payload,
      signature,
      publicKey: publicKeyUncompressed,
    };
  } catch (error) {
    throw new Error(`Failed to sign transaction: ${error.message}`);
  }
}

/**
 * Sign a message with wallet's private key
 * @param {string} message - Message to sign
 * @param {object} wallet - Wallet instance
 * @returns {Promise<string>} - Message signature
 */
export async function signMessage(message, wallet) {
  try {
    if (!wallet) {
      throw new Error('Wallet required for signing');
    }

    // Hash message
    const messageHash = crypto.createHash('sha256').update(message).digest();

    // ECDSA sign
    const keyPair = ec.keyFromPrivate(wallet.privateKey);
    const signature = keyPair.sign(messageHash);
    const signatureHex = signature.toDER('hex');

    const publicKeyUncompressed = publicKeyCompressedToUncompressed(wallet.publicKey);

    return {
      message,
      signature: signatureHex,
      publicKey: publicKeyUncompressed,
      timestamp: Math.floor(Date.now() / 1000),
    };
  } catch (error) {
    throw new Error(`Failed to sign message: ${error.message}`);
  }
}

/**
 * Verify a signed transaction envelope structure.
 * @param {object} signedTx - Signed transaction to verify
 * @returns {boolean}
 */
export function verifyEnvelopeStructure(signedTx) {
  // Verify required fields
  const requiredFields = ['from', 'to', 'amount', 'signature', 'publicKey', 'nonce', 'timestamp'];
  const hasAllFields = requiredFields.every(field => signedTx[field] !== undefined);

  if (!hasAllFields) {
    return false;
  }

  // Verify no secret fields present
  const forbiddenFields = ['secret', 'mnemonic', 'seed', 'privateKey', 'auth_secret'];
  const hasForbiddenFields = forbiddenFields.some(field => signedTx[field] !== undefined);

  // Verify timestamp is in seconds, not milliseconds
  const isTimestampValid = signedTx.timestamp < 1e10;

  return !hasForbiddenFields && isTimestampValid;
}

/**
 * Verify a signature (for testing).
 */
export function verifySignature(message, signature, publicKey) {
  try {
    const messageHash = crypto.createHash('sha256').update(message).digest();
    const keyPair = ec.keyFromPublic(publicKey, 'hex');
    return keyPair.verify(messageHash, signature);
  } catch {
    return false;
  }
}

export default {
  signThronosTransaction,
  signMessage,
  verifyEnvelopeStructure,
  verifySignature,
};
