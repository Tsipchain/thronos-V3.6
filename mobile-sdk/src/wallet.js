/**
 * Thronos Wallet Module
 * Handles wallet creation, storage, and cryptographic operations
 * Compatible with iOS, Android, and Web platforms
 *
 * @version 2.0.0
 * @platform iOS | Android | Web | APK
 */

// Platform-agnostic storage (falls back to localStorage for web/APK)
let AsyncStorage;
let CryptoJS;

// Dynamic imports for platform compatibility
try {
    AsyncStorage = require('@react-native-async-storage/async-storage').default;
} catch (e) {
    // Fallback for web/APK builds
    AsyncStorage = {
        multiSet: async (pairs) => {
            pairs.forEach(([key, value]) => {
                if (typeof localStorage !== 'undefined') {
                    localStorage.setItem(key, value);
                }
            });
        },
        multiGet: async (keys) => {
            return keys.map(key => {
                const value = typeof localStorage !== 'undefined' ? localStorage.getItem(key) : null;
                return [key, value];
            });
        },
        multiRemove: async (keys) => {
            keys.forEach(key => {
                if (typeof localStorage !== 'undefined') {
                    localStorage.removeItem(key);
                }
            });
        }
    };
}

try {
    CryptoJS = require('react-native-crypto-js');
} catch (e) {
    // Fallback for web/APK builds
    CryptoJS = require('crypto-js');
}

const STORAGE_KEY_ADDRESS = '@thronos_wallet_address';
const STORAGE_KEY_SECRET = '@thronos_wallet_secret';
const STORAGE_KEY_TOKENS_CACHE = '@thronos_wallet_tokens_cache';
const STORAGE_KEY_LAST_SYNC = '@thronos_wallet_last_sync';

export default class ThronosWallet {
    constructor(config) {
        this.config = config;
        this.apiUrl = config.apiUrl;
    }

    /**
     * Create a new wallet
     * @returns {Promise<{address: string, secret: string}>}
     */
    async create() {
        try {
            const response = await fetch(`${this.apiUrl}/api/wallet/create`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) {
                throw new Error('Failed to create wallet');
            }

            const data = await response.json();

            if (this.config.autoSave) {
                await this.save(data.address, data.secret);
            }

            return {
                address: data.address,
                secret: data.secret
            };
        } catch (error) {
            throw new Error(`Wallet creation failed: ${error.message}`);
        }
    }

    /**
     * Import an existing wallet
     * @param {string} address - Wallet address
     * @param {string} secret - Wallet secret key
     * @returns {Promise<{address: string, secret: string}>}
     */
    async import(address, secret) {
        if (!address || !secret) {
            throw new Error('Address and secret are required');
        }

        if (!address.startsWith('THR')) {
            throw new Error('Invalid address format');
        }

        if (this.config.autoSave) {
            await this.save(address, secret);
        }

        return { address, secret };
    }

    /**
     * Save wallet to secure storage
     * @param {string} address - Wallet address
     * @param {string} secret - Wallet secret key
     * @returns {Promise<void>}
     */
    async save(address, secret) {
        try {
            // Encrypt secret before storing
            const encryptedSecret = CryptoJS.AES.encrypt(
                secret,
                this.getEncryptionKey()
            ).toString();

            await AsyncStorage.multiSet([
                [STORAGE_KEY_ADDRESS, address],
                [STORAGE_KEY_SECRET, encryptedSecret]
            ]);
        } catch (error) {
            throw new Error(`Failed to save wallet: ${error.message}`);
        }
    }

    /**
     * Get wallet from storage
     * @returns {Promise<{address: string, secret: string}|null>}
     */
    async get() {
        try {
            const [[, address], [, encryptedSecret]] = await AsyncStorage.multiGet([
                STORAGE_KEY_ADDRESS,
                STORAGE_KEY_SECRET
            ]);

            if (!address || !encryptedSecret) {
                return null;
            }

            // Decrypt secret
            const secret = CryptoJS.AES.decrypt(
                encryptedSecret,
                this.getEncryptionKey()
            ).toString(CryptoJS.enc.Utf8);

            return { address, secret };
        } catch (error) {
            console.error('Failed to get wallet:', error);
            return null;
        }
    }

    /**
     * Check if wallet is connected
     * @returns {Promise<boolean>}
     */
    async isConnected() {
        const wallet = await this.get();
        return wallet !== null;
    }

    /**
     * Disconnect wallet (remove from storage)
     * @returns {Promise<void>}
     */
    async disconnect() {
        try {
            await AsyncStorage.multiRemove([
                STORAGE_KEY_ADDRESS,
                STORAGE_KEY_SECRET
            ]);
        } catch (error) {
            throw new Error(`Failed to disconnect wallet: ${error.message}`);
        }
    }

    /**
     * Sign a message
     * @param {string} message - Message to sign
     * @param {string} secret - Wallet secret key
     * @returns {Promise<string>}
     */
    async signMessage(message, secret) {
        try {
            // Create HMAC signature
            const signature = CryptoJS.HmacSHA256(message, secret).toString();
            return signature;
        } catch (error) {
            throw new Error(`Failed to sign message: ${error.message}`);
        }
    }

    /**
     * Verify a signature
     * @param {string} message - Original message
     * @param {string} signature - Signature to verify
     * @param {string} address - Address that signed the message
     * @returns {Promise<boolean>}
     */
    async verifySignature(message, signature, address) {
        try {
            const response = await fetch(`${this.apiUrl}/api/wallet/verify`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    message,
                    signature,
                    address
                })
            });

            if (!response.ok) {
                return false;
            }

            const data = await response.json();
            return data.valid === true;
        } catch (error) {
            console.error('Failed to verify signature:', error);
            return false;
        }
    }

    /**
     * Get encryption key for secure storage
     * @returns {string}
     * @private
     */
    getEncryptionKey() {
        // In production, this should be derived from device-specific credentials
        // or use a more secure key management system
        return `thronos_${this.config.network}_encryption_key`;
    }

    /**
     * Export wallet (for backup)
     * @returns {Promise<{address: string, secret: string}>}
     */
    async export() {
        const wallet = await this.get();
        if (!wallet) {
            throw new Error('No wallet to export');
        }
        return wallet;
    }

    /**
     * Generate a QR code data for the wallet address
     * @returns {Promise<string>}
     */
    async getQRData() {
        const wallet = await this.get();
        if (!wallet) {
            throw new Error('No wallet connected');
        }
        return wallet.address;
    }

    /**
     * Get all token balances for the wallet
     * @param {boolean} forceRefresh - Force fetch from server even if cached
     * @returns {Promise<{tokens: Array, fromCache: boolean}>}
     */
    async getAllTokenBalances(forceRefresh = false) {
        const wallet = await this.get();
        if (!wallet) {
            throw new Error('No wallet connected');
        }

        // Check cache first
        if (!forceRefresh) {
            const cached = await this.getCachedTokens();
            if (cached && Date.now() - cached.timestamp < 60000) { // 1 minute cache
                return { tokens: cached.tokens, fromCache: true };
            }
        }

        // Fetch from server
        try {
            const response = await fetch(`${this.apiUrl}/api/wallet/tokens/${wallet.address}?show_zero=true`);
            if (!response.ok) throw new Error('Failed to fetch tokens');

            const data = await response.json();

            // Cache the result
            await this.cacheTokens(data.tokens);

            return { tokens: data.tokens, fromCache: false };
        } catch (error) {
            // Return cached data if available on error
            const cached = await this.getCachedTokens();
            if (cached) {
                return { tokens: cached.tokens, fromCache: true, error: error.message };
            }
            throw error;
        }
    }

    /**
     * Cache tokens for offline access
     * @param {Array} tokens - Token balances to cache
     * @private
     */
    async cacheTokens(tokens) {
        try {
            const cacheData = JSON.stringify({
                tokens,
                timestamp: Date.now()
            });
            await AsyncStorage.multiSet([[STORAGE_KEY_TOKENS_CACHE, cacheData]]);
        } catch (e) {
            console.warn('Failed to cache tokens:', e);
        }
    }

    /**
     * Get cached tokens
     * @returns {Promise<{tokens: Array, timestamp: number}|null>}
     * @private
     */
    async getCachedTokens() {
        try {
            const [[, cached]] = await AsyncStorage.multiGet([STORAGE_KEY_TOKENS_CACHE]);
            return cached ? JSON.parse(cached) : null;
        } catch (e) {
            return null;
        }
    }

    /**
     * Get balance for a specific token
     * @param {string} symbol - Token symbol (e.g., 'THR', 'WBTC', 'L2E')
     * @returns {Promise<number>}
     */
    async getTokenBalance(symbol) {
        const { tokens } = await this.getAllTokenBalances();
        const token = tokens.find(t => t.symbol.toUpperCase() === symbol.toUpperCase());
        return token ? token.balance : 0;
    }

    /**
     * Check if device is online
     * @returns {boolean}
     */
    isOnline() {
        if (typeof navigator !== 'undefined' && navigator.onLine !== undefined) {
            return navigator.onLine;
        }
        return true; // Assume online if we can't detect
    }

    /**
     * Generate receive address with optional amount (for QR codes)
     * @param {number} amount - Optional amount to request
     * @param {string} token - Token symbol (default: 'THR')
     * @returns {Promise<string>}
     */
    async generatePaymentRequest(amount = null, token = 'THR') {
        const wallet = await this.get();
        if (!wallet) throw new Error('No wallet connected');

        let request = `thronos:${wallet.address}`;
        if (amount) {
            request += `?amount=${amount}&token=${token}`;
        }
        return request;
    }

    /**
     * Parse a payment request string
     * @param {string} request - Payment request (e.g., "thronos:THRxxx?amount=10&token=THR")
     * @returns {{address: string, amount: number|null, token: string}}
     */
    parsePaymentRequest(request) {
        if (!request.startsWith('thronos:')) {
            // Try to parse as plain address
            if (request.startsWith('THR')) {
                return { address: request, amount: null, token: 'THR' };
            }
            throw new Error('Invalid payment request format');
        }

        const [addressPart, queryString] = request.replace('thronos:', '').split('?');
        const result = { address: addressPart, amount: null, token: 'THR' };

        if (queryString) {
            const params = new URLSearchParams(queryString);
            if (params.get('amount')) {
                result.amount = parseFloat(params.get('amount'));
            }
            if (params.get('token')) {
                result.token = params.get('token').toUpperCase();
            }
        }

        return result;
    }

    /**
     * Get wallet info for display (masked secret)
     * @returns {Promise<{address: string, shortAddress: string, hasSecret: boolean}>}
     */
    async getWalletInfo() {
        const wallet = await this.get();
        if (!wallet) return null;

        return {
            address: wallet.address,
            shortAddress: `${wallet.address.slice(0, 8)}...${wallet.address.slice(-6)}`,
            hasSecret: !!wallet.secret
        };
    }
}
