/**
 * Thronos Wallet Module
 * Handles wallet creation, storage, and cryptographic operations
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import CryptoJS from 'react-native-crypto-js';

const STORAGE_KEY_ADDRESS = '@thronos_wallet_address';
const STORAGE_KEY_SECRET = '@thronos_wallet_secret';

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
}
