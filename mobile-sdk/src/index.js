/**
 * Thronos Mobile SDK
 * Main entry point for React Native applications
 */

import ThronosWallet from './wallet';
import ThronosAPI from './api';

export default class ThronosSDK {
    constructor(config = {}) {
        this.config = {
            apiUrl: config.apiUrl || 'http://localhost:5000',
            autoSave: config.autoSave !== false,
            network: config.network || 'mainnet',
            ...config
        };

        this.wallet = new ThronosWallet(this.config);
        this.api = new ThronosAPI(this.config);
    }

    /**
     * Create a new wallet
     * Requires secureKeyProvider backed by the OS Keychain/Keystore when
     * autoSave is enabled.
     * @returns {Promise<{address: string, mnemonic: string}>}
     */
    async createWallet() {
        return await this.wallet.create();
    }

    /**
     * Import or restore a BIP39 wallet. Historical stored addresses are
     * retained when they match an explicitly supported derivation version.
     * Raw address/secret import is intentionally not accepted here.
     * @param {string} mnemonic - BIP39 recovery phrase
     * @param {object} options - Optional authoritative identity validator
     * @returns {Promise<{address: string, derivationVersion: string}>}
     */
    async importWallet(mnemonic, options = {}) {
        return await this.wallet.import(mnemonic, options);
    }

    /**
     * Get current wallet
     * @returns {Promise<{address: string, derivationVersion: string|null}|null>}
     */
    async getWallet() {
        return await this.wallet.get();
    }

    /**
     * Check if wallet is connected
     * @returns {Promise<boolean>}
     */
    async isConnected() {
        return await this.wallet.isConnected();
    }

    /**
     * Get wallet address
     * @returns {Promise<string|null>}
     */
    async getAddress() {
        const wallet = await this.wallet.get();
        return wallet ? wallet.address : null;
    }

    /**
     * Get token balances
     * @param {string} address - Wallet address (optional, uses current wallet if not provided)
     * @param {boolean} showZero - Show tokens with zero balance
     * @returns {Promise<{address: string, tokens: Array, last_updated: string}>}
     */
    async getBalances(address = null, showZero = false) {
        if (!address) {
            const wallet = await this.wallet.get();
            if (!wallet) throw new Error('No wallet connected');
            address = wallet.address;
        }
        return await this.api.getTokens(address, showZero);
    }

    /**
     * Get balance for a specific token
     * @param {string} tokenSymbol - Token symbol (e.g., 'THR', 'WBTC')
     * @param {string} address - Wallet address (optional)
     * @returns {Promise<number>}
     */
    async getTokenBalance(tokenSymbol, address = null) {
        const data = await this.getBalances(address, true);
        const token = data.tokens.find(t => t.symbol === tokenSymbol);
        return token ? token.balance : 0;
    }

    /**
     * Send transaction
     * @param {string} to - Recipient address
     * @param {number} amount - Amount to send
     * @param {string} token - Token symbol (default: 'THR')
     * @param {object} options - Optional: { speed: 'slow'|'fast', nonce: string }
     * @returns {Promise<{success: boolean, transaction: object}>}
     */
    async sendTransaction(to, amount, token = 'THR', options = {}) {
        const wallet = await this.wallet.get();
        if (!wallet) throw new Error('No wallet connected');

        const signedTx = await this.wallet.signTransaction({
            from: wallet.address,
            to,
            amount,
            token,
            nonce: options.nonce
        });
        return await this.api.sendTransaction(signedTx);
    }

    /**
     * Send multiple tokens in a single batch
     * @param {Array<{to: string, amount: number, token: string}>} transfers - Array of transfers
     * @param {object} options - Optional: { speed: 'slow'|'fast', passphrase: string }
     * @returns {Promise<{success: boolean, results: Array}>}
     */
    async sendMultipleTokens(transfers, options = {}) {
        const wallet = await this.wallet.get();
        if (!wallet) throw new Error('No wallet connected');

        if (!Array.isArray(transfers) || transfers.length === 0) {
            throw new Error('Transfers must be a non-empty array');
        }

        const signedTransfers = [];
        for (const transfer of transfers) {
            const signedTx = await this.wallet.signTransaction({
                from: wallet.address,
                to: transfer.to,
                amount: transfer.amount,
                token: transfer.token || 'THR',
                nonce: transfer.nonce
            });
            signedTransfers.push({ ...transfer, signedTx });
        }
        return await this.api.sendMultipleTokens({ transfers: signedTransfers });
    }

    /**
     * Get all available tokens on the chain
     * @returns {Promise<{tokens: Array}>}
     */
    async getChainTokens() {
        return await this.api.getChainTokens();
    }

    /**
     * Get token info by symbol
     * @param {string} symbol - Token symbol
     * @returns {Promise<object>}
     */
    async getTokenInfo(symbol) {
        return await this.api.getTokenInfo(symbol);
    }

    /**
     * Get transaction history
     * @param {string} address - Wallet address (optional)
     * @param {number} limit - Number of transactions to retrieve
     * @returns {Promise<Array>}
     */
    async getTransactionHistory(address = null, limit = 50) {
        if (!address) {
            const wallet = await this.wallet.get();
            if (!wallet) throw new Error('No wallet connected');
            address = wallet.address;
        }
        return await this.api.getTransactionHistory(address, limit);
    }

    /**
     * Disconnect wallet
     * @returns {Promise<void>}
     */
    async disconnect() {
        return await this.wallet.disconnect();
    }

    /**
     * Sign message
     * @param {string} message - Message to sign
     * @returns {Promise<string>}
     */
    async signMessage(message) {
        const wallet = await this.wallet.get();
        if (!wallet) throw new Error('No wallet connected');

        throw new Error('Generic message signing is disabled until a domain-separated SDK contract is selected');
    }

    /**
     * Verify signature
     * @param {string} message - Original message
     * @param {string} signature - Signature to verify
     * @param {string} address - Address that signed the message
     * @returns {Promise<boolean>}
     */
    async verifySignature(message, signature, address) {
        return await this.wallet.verifySignature(message, signature, address);
    }
}

// Export individual modules
export { ThronosWallet, ThronosAPI };

// Export default instance
export const Thronos = ThronosSDK;
