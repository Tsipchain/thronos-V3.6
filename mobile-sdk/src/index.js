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
     * @returns {Promise<{address: string, secret: string}>}
     */
    async createWallet() {
        return await this.wallet.create();
    }

    /**
     * Import an existing wallet
     * @param {string} address - Wallet address
     * @param {string} secret - Wallet secret key
     * @returns {Promise<{address: string, secret: string}>}
     */
    async importWallet(address, secret) {
        return await this.wallet.import(address, secret);
    }

    /**
     * Get current wallet
     * @returns {Promise<{address: string, secret: string}|null>}
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
     * @returns {Promise<{success: boolean, transaction: object}>}
     */
    async sendTransaction(to, amount, token = 'THR') {
        const wallet = await this.wallet.get();
        if (!wallet) throw new Error('No wallet connected');

        return await this.api.sendTransaction({
            from: wallet.address,
            to,
            amount,
            token,
            secret: wallet.secret
        });
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

        return await this.wallet.signMessage(message, wallet.secret);
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
