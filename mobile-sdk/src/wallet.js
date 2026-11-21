/**
 * Thronos Wallet Module (Secure)
 * Handles client-side wallet generation with BIP39/BIP32
 * Secrets are NEVER stored; keys derived on-demand for signing
 * Compatible with iOS, Android, and Web platforms
 *
 * @version 3.0.0 (Secure)
 * @platform iOS | Android | Web | APK
 */

// Platform-agnostic storage (falls back to localStorage for web/APK)
let AsyncStorage;
let CryptoJS;
let bip39;
let bip32;

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

try {
    bip39 = require('bip39');
    bip32 = require('bip32');
} catch (e) {
    console.warn('BIP39/BIP32 libraries not available');
}

// Import signing module for ECDSA secp256k1
let signingModule;
try {
    signingModule = require('./signing');
} catch (e) {
    console.warn('Signing module not available');
}

const STORAGE_KEY_ADDRESS = '@thronos_wallet_address';
const STORAGE_KEY_MNEMONIC_ENCRYPTED = '@thronos_wallet_mnemonic_encrypted';
const STORAGE_KEY_TOKENS_CACHE = '@thronos_wallet_tokens_cache';
const STORAGE_KEY_LAST_SYNC = '@thronos_wallet_last_sync';
const STORAGE_KEY_PUBKEY = '@thronos_wallet_pubkey';
const STORAGE_KEY_DERIVATION_VERSION = '@thronos_wallet_derivation_version';
const STORAGE_KEY_ENCRYPTION_VERSION = '@thronos_wallet_encryption_version';

export const ADDRESS_DERIVATION_LEGACY_V1 = 'mobile_sdk_hex_text_v1';
export const ADDRESS_DERIVATION_CANONICAL_V2 = 'wallet_v1_pubkey_hash160_v2';
export const MNEMONIC_ENCRYPTION_LEGACY_V1 = 'device_id_pbkdf2_v1';
export const MNEMONIC_ENCRYPTION_OS_KEYSTORE_V2 = 'os_keystore_key_v2';

export default class ThronosWallet {
    constructor(config) {
        this.config = config;
        this.apiUrl = config.apiUrl;
    }

    /** Return key material supplied by an OS Keychain/Keystore integration. */
    async getDeviceEncryptionKey() {
        if (typeof this.config.secureKeyProvider !== 'function') {
            throw new Error('os_keystore_key_provider_required');
        }
        const key = await this.config.secureKeyProvider();
        if (typeof key !== 'string' || key.length < 32 || key === 'default-device-key') {
            throw new Error('invalid_os_keystore_key');
        }
        return key;
    }

    /** Derive the historical v1 key only inside the explicit migration flow. */
    async getLegacyDeviceEncryptionKey() {
        let deviceId = this.config.legacyDeviceId;
        if (!deviceId && this.config.allowLegacyDefaultDeviceKeyMigration === true) {
            deviceId = 'default-device-key';
        }
        if (!deviceId) throw new Error('legacy_device_key_required');
        const key = CryptoJS.PBKDF2(deviceId, 'thronos-device-kdf-v1', {
            keySize: 256 / 32,
            iterations: 600000
        }).toString();

        return key;
    }

    /**
     * Create a new wallet with client-side BIP39/BIP32 generation
     * @returns {Promise<{address: string, mnemonic: string}>}
     */
    async create() {
        try {
            if (!bip39) {
                throw new Error('BIP39 library not available');
            }

            // Generate 12-word mnemonic (128-bit entropy)
            const mnemonic = bip39.generateMnemonic(128);

            if (!bip39.validateMnemonic(mnemonic)) {
                throw new Error('Invalid mnemonic generated');
            }

            // Derive address from mnemonic
            const address = await this.deriveAddressFromMnemonic(
                mnemonic,
                ADDRESS_DERIVATION_CANONICAL_V2
            );

            if (this.config.autoSave) {
                await this.saveMnemonic(mnemonic, address, ADDRESS_DERIVATION_CANONICAL_V2);
            }

            return {
                address,
                mnemonic // Return mnemonic to user for backup (one-time display only)
            };
        } catch (error) {
            throw new Error(`Wallet creation failed: ${error.message}`);
        }
    }

    /**
     * Import an existing wallet using mnemonic
     * @param {string} mnemonic - BIP39 mnemonic (12 or 24 words)
     * @returns {Promise<{address: string}>}
     */
    async import(mnemonic, options = {}) {
        if (!mnemonic) {
            throw new Error('Mnemonic is required');
        }

        if (!bip39 || !bip39.validateMnemonic(mnemonic)) {
            throw new Error('Invalid BIP39 mnemonic');
        }

        const canonicalAddress = await this.deriveAddressFromMnemonic(
            mnemonic,
            ADDRESS_DERIVATION_CANONICAL_V2
        );
        const legacyAddress = await this.deriveAddressFromMnemonic(
            mnemonic,
            ADDRESS_DERIVATION_LEGACY_V1
        );
        const existing = await this.get();
        let address = canonicalAddress;
        let derivationVersion = ADDRESS_DERIVATION_CANONICAL_V2;

        // Never overwrite a registered/stored identity because a newer SDK
        // computes a different address. An existing address must match one of
        // the explicit historical algorithms or be independently validated.
        if (existing?.address) {
            if (existing.address === legacyAddress) {
                address = existing.address;
                derivationVersion = ADDRESS_DERIVATION_LEGACY_V1;
            } else if (existing.address === canonicalAddress) {
                address = existing.address;
            } else if (
                options.authoritativeAddress === existing.address &&
                typeof options.validateAuthoritativeIdentity === 'function' &&
                await options.validateAuthoritativeIdentity({
                    storedAddress: existing.address,
                    canonicalAddress,
                    legacyAddress,
                }) === true
            ) {
                address = existing.address;
                derivationVersion = existing.derivationVersion || 'authoritative_external_binding';
            } else {
                throw new Error('authoritative_identity_validation_required');
            }
        }

        if (this.config.autoSave) {
            await this.saveMnemonic(mnemonic, address, derivationVersion);
        }

        return { address, derivationVersion };
    }

    /**
     * Derive THR address from mnemonic using BIP44 path m/44'/1'/0'/0/0
     * Uses canonical Bitcoin-style address derivation: SHA256 → RIPEMD160 → first 40 chars uppercase
     * @param {string} mnemonic - BIP39 mnemonic
     * @returns {Promise<string>}
     * @private
     */
    async deriveAddressFromMnemonic(mnemonic, version = ADDRESS_DERIVATION_CANONICAL_V2) {
        if (!bip32) {
            throw new Error('BIP32 library not available');
        }

        try {
            // Convert mnemonic to seed (BIP39)
            const seed = await bip39.mnemonicToSeed(mnemonic);

            // Derive HD wallet from seed (BIP32)
            const root = bip32.fromSeed(Buffer.from(seed, 'hex'));

            // Use BIP44 path: m/44'/1'/0'/0/0 (testnet path)
            const path = "m/44'/1'/0'/0/0";
            const child = root.derivePath(path);

            const publicKeyHex = child.publicKey.toString('hex');
            let ripemd160Hash;
            if (version === ADDRESS_DERIVATION_LEGACY_V1) {
                // Historical Mobile SDK behavior. CryptoJS hashes the UTF-8
                // hexadecimal text twice; it is intentionally preserved only
                // for restoring already-created identities.
                const sha256HexText = CryptoJS.SHA256(publicKeyHex).toString();
                ripemd160Hash = CryptoJS.RIPEMD160(sha256HexText).toString();
            } else if (version === ADDRESS_DERIVATION_CANONICAL_V2) {
                const sha256Bytes = CryptoJS.SHA256(CryptoJS.enc.Hex.parse(publicKeyHex));
                ripemd160Hash = CryptoJS.RIPEMD160(sha256Bytes).toString();
            } else {
                throw new Error('unsupported_address_derivation_version');
            }

            // 3. Take first 40 chars (uppercase) and prepend THR
            const address = `THR${ripemd160Hash.substring(0, 40).toUpperCase()}`;

            return address;
        } catch (error) {
            throw new Error(`Failed to derive address: ${error.message}`);
        }
    }

    /**
     * Save encrypted mnemonic to storage (address only visible, mnemonic encrypted)
     * @param {string} mnemonic - BIP39 mnemonic
     * @param {string} address - Derived wallet address
     * @returns {Promise<void>}
     */
    async saveMnemonic(
        mnemonic,
        address,
        derivationVersion = ADDRESS_DERIVATION_CANONICAL_V2
    ) {
        try {
            if (derivationVersion !== 'authoritative_external_binding') {
                const derived = await this.deriveAddressFromMnemonic(mnemonic, derivationVersion);
                if (derived !== address) throw new Error('mnemonic_address_mismatch');
            }
            const encryptionKey = await this.getDeviceEncryptionKey();
            const encrypted = CryptoJS.AES.encrypt(mnemonic, encryptionKey).toString();

            await AsyncStorage.multiSet([
                [STORAGE_KEY_ADDRESS, address],
                [STORAGE_KEY_MNEMONIC_ENCRYPTED, encrypted],
                [STORAGE_KEY_DERIVATION_VERSION, derivationVersion],
                [STORAGE_KEY_ENCRYPTION_VERSION, MNEMONIC_ENCRYPTION_OS_KEYSTORE_V2]
            ]);
        } catch (error) {
            throw new Error(`Failed to save wallet: ${error.message}`);
        }
    }

    /**
     * Get wallet address from storage (mnemonic NOT returned)
     * @returns {Promise<{address: string}|null>}
     */
    async get() {
        try {
            const [[, address], [, pubkey], [, derivationVersion]] = await AsyncStorage.multiGet([
                STORAGE_KEY_ADDRESS,
                STORAGE_KEY_PUBKEY,
                STORAGE_KEY_DERIVATION_VERSION
            ]);

            if (!address) {
                return null;
            }

            return {
                address,
                pubkey: pubkey || null,
                derivationVersion: derivationVersion || null
            };
        } catch (error) {
            console.error('Failed to get wallet:', error);
            return null;
        }
    }

    /**
     * Get mnemonic from encrypted storage (only for signing, never transmitted)
     * @returns {Promise<string|null>}
     * @private
     */
    async getMnemonicForSigning() {
        try {
            const [[, encrypted], [, encryptionVersion]] = await AsyncStorage.multiGet([
                STORAGE_KEY_MNEMONIC_ENCRYPTED,
                STORAGE_KEY_ENCRYPTION_VERSION
            ]);

            if (!encrypted) {
                return null;
            }

            if (encryptionVersion !== MNEMONIC_ENCRYPTION_OS_KEYSTORE_V2) {
                throw new Error('legacy_mnemonic_migration_required');
            }
            const encryptionKey = await this.getDeviceEncryptionKey();
            const decrypted = CryptoJS.AES.decrypt(encrypted, encryptionKey)
                .toString(CryptoJS.enc.Utf8);
            if (!bip39.validateMnemonic(decrypted)) throw new Error('mnemonic_decryption_failed');
            return decrypted;
        } catch (error) {
            console.error('Failed to decrypt mnemonic:', error);
            throw error;
        }
    }

    /**
     * Non-destructive transition for historical ciphertext. The old record is
     * read only after explicit opt-in, matched to its stored address, approved
     * by an authoritative recovery callback, and then atomically overwritten
     * with an OS-backed v2 key. Failure leaves every old value untouched.
     */
    async migrateLegacyMnemonicStorage(validateRecovery) {
        if (typeof validateRecovery !== 'function') {
            throw new Error('recovery_validation_required');
        }
        const rows = await AsyncStorage.multiGet([
            STORAGE_KEY_ADDRESS,
            STORAGE_KEY_MNEMONIC_ENCRYPTED,
            STORAGE_KEY_ENCRYPTION_VERSION
        ]);
        const address = rows[0][1];
        const encrypted = rows[1][1];
        const encryptionVersion = rows[2][1];
        if (!address || !encrypted) throw new Error('legacy_wallet_not_found');
        if (encryptionVersion === MNEMONIC_ENCRYPTION_OS_KEYSTORE_V2) {
            return { migrated: false, address, reason: 'already_current' };
        }

        const legacyKey = await this.getLegacyDeviceEncryptionKey();
        const mnemonic = CryptoJS.AES.decrypt(encrypted, legacyKey).toString(CryptoJS.enc.Utf8);
        if (!bip39.validateMnemonic(mnemonic)) throw new Error('legacy_mnemonic_unlock_failed');
        const canonicalAddress = await this.deriveAddressFromMnemonic(
            mnemonic,
            ADDRESS_DERIVATION_CANONICAL_V2
        );
        const legacyAddress = await this.deriveAddressFromMnemonic(
            mnemonic,
            ADDRESS_DERIVATION_LEGACY_V1
        );
        let derivationVersion;
        if (address === legacyAddress) derivationVersion = ADDRESS_DERIVATION_LEGACY_V1;
        else if (address === canonicalAddress) derivationVersion = ADDRESS_DERIVATION_CANONICAL_V2;
        else throw new Error('stored_address_derivation_mismatch');

        const verified = await validateRecovery({
            address,
            canonicalAddress,
            legacyAddress,
            derivationVersion,
        });
        if (verified !== true) throw new Error('recovery_validation_failed');
        await this.saveMnemonic(mnemonic, address, derivationVersion);
        return { migrated: true, address, derivationVersion };
    }

    async requireDeviceAuthentication(reason) {
        if (typeof this.config.deviceAuthenticator !== 'function') {
            throw new Error('device_authenticator_required');
        }
        const result = await this.config.deviceAuthenticator({ reason, allowDevicePasscode: true });
        const approved = result === true || result?.success === true;
        if (!approved) throw new Error('device_authentication_cancelled');
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
                STORAGE_KEY_MNEMONIC_ENCRYPTED,
                STORAGE_KEY_PUBKEY,
                STORAGE_KEY_DERIVATION_VERSION,
                STORAGE_KEY_ENCRYPTION_VERSION
            ]);
        } catch (error) {
            throw new Error(`Failed to disconnect wallet: ${error.message}`);
        }
    }

    /**
     * Sign a transaction on the device using ECDSA/secp256k1
     * Mnemonic retrieved on-demand, key never stored
     * @param {object} txParams - Transaction parameters
     * @returns {Promise<object>} - Signed transaction envelope
     */
    async signTransaction(txParams) {
        try {
            const beforeApproval = await this.get();
            if (!beforeApproval?.address || beforeApproval.address !== txParams.from) {
                throw new Error('wallet_address_mismatch');
            }
            await this.requireDeviceAuthentication('Approve Thronos transaction');
            const afterApproval = await this.get();
            if (!afterApproval?.address || afterApproval.address !== beforeApproval.address) {
                throw new Error('wallet_changed_during_approval');
            }
            const mnemonic = await this.getMnemonicForSigning();
            if (!mnemonic) {
                throw new Error('Wallet not found or mnemonic not available');
            }

            if (!bip32 || !signingModule) {
                throw new Error('BIP32 or signing module not available');
            }

            // Derive private key and public key from mnemonic
            const seed = await bip39.mnemonicToSeed(mnemonic);
            const root = bip32.fromSeed(Buffer.from(seed, 'hex'));
            const child = root.derivePath("m/44'/1'/0'/0/0");

            if (!child.privateKey) {
                throw new Error('Failed to derive private key');
            }

            const wallet = {
                privateKey: child.privateKey.toString('hex'),
                publicKey: child.publicKey.toString('hex')
            };

            // Create transaction payload with UNIX seconds timestamp
            const txPayload = {
                from: txParams.from,
                to: txParams.to,
                amount: txParams.amount,
                token: txParams.token || 'THR',
                nonce: txParams.nonce || `tx_${Date.now()}`,
                timestamp: Math.floor(Date.now() / 1000)  // UNIX seconds, not milliseconds
            };

            // Sign using ECDSA/secp256k1 from signing module
            const signedTx = await signingModule.signThronosTransaction(txPayload, wallet);

            // Verify envelope structure (no forbidden fields)
            if (!signingModule.verifyEnvelopeStructure(signedTx)) {
                throw new Error('Invalid transaction envelope');
            }

            return signedTx;
        } catch (error) {
            throw new Error(`Failed to sign transaction: ${error.message}`);
        }
    }

    /**
     * Export wallet (backup mnemonic only - NOT secret)
     * Returns mnemonic for user to write down securely
     * @returns {Promise<{address: string, mnemonic: string}>}
     */
    async export() {
        const wallet = await this.get();
        if (!wallet) {
            throw new Error('No wallet to export');
        }

        await this.requireDeviceAuthentication('Export Thronos recovery phrase');
        const afterApproval = await this.get();
        if (!afterApproval?.address || afterApproval.address !== wallet.address) {
            throw new Error('wallet_changed_during_approval');
        }

        const mnemonic = await this.getMnemonicForSigning();
        if (!mnemonic) {
            throw new Error('Mnemonic not available for export');
        }

        return {
            address: wallet.address,
            mnemonic: mnemonic // User should store securely (NOT in clipboard)
        };
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
     * Get wallet info for display (address only - no secrets)
     * @returns {Promise<{address: string, shortAddress: string, isConnected: boolean}>}
     */
    async getWalletInfo() {
        const wallet = await this.get();
        if (!wallet) return null;

        return {
            address: wallet.address,
            shortAddress: `${wallet.address.slice(0, 8)}...${wallet.address.slice(-6)}`,
            isConnected: true
        };
    }
}
