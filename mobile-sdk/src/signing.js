/**
 * Thronos Mobile SDK - Transaction Signing Service
 *
 * ECDSA/secp256k1 + SHA256 signing to match backend verification.
 * Private keys never transmitted or stored persistently.
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
      `Invalid timestamp ${payload.timestamp}: must be UNIX seconds (e.g. 1710000000), not milliseconds`
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

  // ECDSA sign
  const keyPair = ec.keyFromPrivate(privateKeyHex);
  const signature = keyPair.sign(hash);

  // DER encoding
  return signature.toDER('hex');
}

/**
 * Sign a Thronos transaction with proper ECDSA/secp256k1.
 *
 * @param {object} params - Transaction parameters
 * @param {object} wallet - Wallet instance with privateKey and publicKey
 * @returns {Promise<object>} - Signed transaction envelope
 */
async function signThronosTransaction(params, wallet) {
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
    const timestampSeconds =
      params.timestamp || Math.floor(Date.now() / 1000);
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

    // Sign with ECDSA/secp256k1
    const signature = signCanonicalPayload(canonical, wallet.privateKey);

    // Use compressed public key for backend
    // Backend derives address from: RIPEMD160(SHA256(compressedPublicKey))
    return {
      ...payload,
      signature,
      publicKey: wallet.publicKey,  // Compressed key (66 hex chars, 02/03 prefix)
    };
  } catch (error) {
    throw new Error(`Failed to sign transaction: ${error.message}`);
  }
}

/**
 * Sign a message with proper ECDSA/secp256k1.
 */
async function signMessage(message, wallet) {
  try {
    if (!wallet) {
      throw new Error('Wallet required for signing');
    }

    // Hash message
    const messageHash = crypto
      .createHash('sha256')
      .update(message)
      .digest();

    // ECDSA sign
    const keyPair = ec.keyFromPrivate(wallet.privateKey);
    const signature = keyPair.sign(messageHash);
    const signatureHex = signature.toDER('hex');

    // Use compressed public key for backend
    return {
      message,
      signature: signatureHex,
      publicKey: wallet.publicKey,  // Compressed key (66 hex chars, 02/03 prefix)
      timestamp: Math.floor(Date.now() / 1000),
    };
  } catch (error) {
    throw new Error(`Failed to sign message: ${error.message}`);
  }
}

/**
 * Verify a signed transaction envelope structure.
 */
function verifyEnvelopeStructure(signedTx) {
  // Verify required fields
  const requiredFields = ['from', 'to', 'amount', 'signature', 'publicKey', 'nonce', 'timestamp'];
  const hasAllFields = requiredFields.every((field) => signedTx[field] !== undefined);

  if (!hasAllFields) {
    return false;
  }

  // Verify no secret fields present
  const forbiddenFields = ['secret', 'mnemonic', 'seed', 'privateKey', 'auth_secret'];
  const hasForbiddenFields = forbiddenFields.some((field) => signedTx[field] !== undefined);

  // Verify timestamp is in seconds, not milliseconds
  const isTimestampValid = signedTx.timestamp < 1e10;

  return !hasForbiddenFields && isTimestampValid;
}

/**
 * Verify a signature (for testing).
 */
function verifySignature(message, signature, publicKey) {
  try {
    const messageHash = crypto
      .createHash('sha256')
      .update(message)
      .digest();
    const keyPair = ec.keyFromPublic(publicKey, 'hex');
    return keyPair.verify(messageHash, signature);
  } catch {
    return false;
  }
}

module.exports = {
  signThronosTransaction,
  signMessage,
  verifyEnvelopeStructure,
  verifySignature,
};
