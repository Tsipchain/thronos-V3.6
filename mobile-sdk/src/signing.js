/**
 * Thronos Transaction Signing Service (Mobile SDK)
 * Handles client-side signing of transactions
 * Private keys never transmitted or stored persistently
 */

let CryptoJS;

try {
    CryptoJS = require('react-native-crypto-js');
} catch (e) {
    CryptoJS = require('crypto-js');
}

/**
 * Sign a transaction with wallet's private key
 * @param {object} params - Transaction parameters
 * @param {object} wallet - Wallet instance
 * @returns {Promise<object>} - Signed transaction envelope
 */
export async function signThronosTransaction(params, wallet) {
    try {
        if (!wallet) {
            throw new Error('Wallet required for signing');
        }

        // Create normalized payload
        const txPayload = {
            from: params.from,
            to: params.to,
            amount: params.amount,
            token: params.token || 'THR',
            nonce: params.nonce || Math.floor(Date.now() / 1000),
            timestamp: Date.now()
        };

        // Sign using wallet's internal signing method
        const signedTx = await wallet.signTransaction(txPayload);

        if (!signedTx.signature || !signedTx.publicKey) {
            throw new Error('Signature generation failed');
        }

        return signedTx;
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

        // Use wallet's signing capability
        const signature = await wallet.signTransaction({
            from: '',
            to: '',
            amount: 0,
            message: message
        });

        return signature.signature;
    } catch (error) {
        throw new Error(`Failed to sign message: ${error.message}`);
    }
}

/**
 * Verify a signed transaction envelope structure
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

    return !hasForbiddenFields;
}

export default {
    signThronosTransaction,
    signMessage,
    verifyEnvelopeStructure
};
