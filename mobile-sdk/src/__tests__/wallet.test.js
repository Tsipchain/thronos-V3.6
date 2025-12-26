/**
 * Comprehensive tests for ThronosWallet class
 * Tests wallet creation, import, storage, encryption, signing, and verification
 */

import ThronosWallet from '../wallet';

// Mock dependencies
jest.mock('@react-native-async-storage/async-storage', () => ({
    multiSet: jest.fn(() => Promise.resolve()),
    multiGet: jest.fn(() => Promise.resolve([['', null], ['', null]])),
    multiRemove: jest.fn(() => Promise.resolve())
}));

jest.mock('react-native-crypto-js', () => ({
    AES: {
        encrypt: jest.fn((data) => ({ toString: () => `encrypted_${data}` })),
        decrypt: jest.fn((data, key) => ({
            toString: jest.fn(() => data.replace('encrypted_', ''))
        }))
    },
    HmacSHA256: jest.fn((message, secret) => ({
        toString: () => `signature_${message}_${secret}`
    })),
    enc: {
        Utf8: 'utf8'
    }
}));

import AsyncStorage from '@react-native-async-storage/async-storage';
import CryptoJS from 'react-native-crypto-js';

// Mock fetch globally
global.fetch = jest.fn();

describe('ThronosWallet', () => {
    let wallet;
    let mockConfig;

    beforeEach(() => {
        // Reset all mocks before each test
        jest.clearAllMocks();

        mockConfig = {
            apiUrl: 'https://api.thronos.network',
            autoSave: true,
            network: 'mainnet'
        };

        wallet = new ThronosWallet(mockConfig);
    });

    describe('Constructor', () => {
        test('should initialize with config', () => {
            expect(wallet.config).toEqual(mockConfig);
            expect(wallet.apiUrl).toBe('https://api.thronos.network');
        });

        test('should accept custom apiUrl', () => {
            const customWallet = new ThronosWallet({ apiUrl: 'https://custom.api' });
            expect(customWallet.apiUrl).toBe('https://custom.api');
        });
    });

    describe('create()', () => {
        test('should create a new wallet successfully', async () => {
            const mockWalletData = {
                address: 'THR1234567890',
                secret: 'secret_key_123'
            };

            global.fetch.mockResolvedValueOnce({
                ok: true,
                json: async () => mockWalletData
            });

            const result = await wallet.create();

            expect(global.fetch).toHaveBeenCalledWith(
                'https://api.thronos.network/api/wallet/create',
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                }
            );

            expect(result).toEqual(mockWalletData);
            expect(AsyncStorage.multiSet).toHaveBeenCalled();
        });

        test('should not save wallet when autoSave is false', async () => {
            const noAutoSaveWallet = new ThronosWallet({ ...mockConfig, autoSave: false });
            const mockWalletData = {
                address: 'THR1234567890',
                secret: 'secret_key_123'
            };

            global.fetch.mockResolvedValueOnce({
                ok: true,
                json: async () => mockWalletData
            });

            await noAutoSaveWallet.create();

            expect(AsyncStorage.multiSet).not.toHaveBeenCalled();
        });

        test('should throw error when API request fails', async () => {
            global.fetch.mockResolvedValueOnce({
                ok: false,
                status: 500
            });

            await expect(wallet.create()).rejects.toThrow('Wallet creation failed');
        });

        test('should handle network errors', async () => {
            global.fetch.mockRejectedValueOnce(new Error('Network error'));

            await expect(wallet.create()).rejects.toThrow('Wallet creation failed: Network error');
        });
    });

    describe('import()', () => {
        test('should import wallet with valid address and secret', async () => {
            const address = 'THR1234567890';
            const secret = 'secret_key_123';

            const result = await wallet.import(address, secret);

            expect(result).toEqual({ address, secret });
            expect(AsyncStorage.multiSet).toHaveBeenCalled();
        });

        test('should throw error when address is missing', async () => {
            await expect(wallet.import('', 'secret')).rejects.toThrow(
                'Address and secret are required'
            );
        });

        test('should throw error when secret is missing', async () => {
            await expect(wallet.import('THR123', '')).rejects.toThrow(
                'Address and secret are required'
            );
        });

        test('should throw error for invalid address format', async () => {
            await expect(wallet.import('INVALID123', 'secret')).rejects.toThrow(
                'Invalid address format'
            );
        });

        test('should accept address starting with THR', async () => {
            const result = await wallet.import('THR9999', 'secret_key');
            expect(result.address).toBe('THR9999');
        });

        test('should not save when autoSave is false', async () => {
            const noAutoSaveWallet = new ThronosWallet({ ...mockConfig, autoSave: false });

            await noAutoSaveWallet.import('THR123', 'secret');

            expect(AsyncStorage.multiSet).not.toHaveBeenCalled();
        });
    });

    describe('save()', () => {
        test('should save wallet to secure storage with encryption', async () => {
            const address = 'THR1234567890';
            const secret = 'secret_key_123';

            await wallet.save(address, secret);

            expect(CryptoJS.AES.encrypt).toHaveBeenCalledWith(
                secret,
                'thronos_mainnet_encryption_key'
            );

            expect(AsyncStorage.multiSet).toHaveBeenCalledWith([
                ['@thronos_wallet_address', address],
                ['@thronos_wallet_secret', `encrypted_${secret}`]
            ]);
        });

        test('should throw error when storage fails', async () => {
            AsyncStorage.multiSet.mockRejectedValueOnce(new Error('Storage error'));

            await expect(wallet.save('THR123', 'secret')).rejects.toThrow(
                'Failed to save wallet: Storage error'
            );
        });

        test('should use network-specific encryption key', async () => {
            const testnetWallet = new ThronosWallet({ ...mockConfig, network: 'testnet' });

            await testnetWallet.save('THR123', 'secret');

            expect(CryptoJS.AES.encrypt).toHaveBeenCalledWith(
                'secret',
                'thronos_testnet_encryption_key'
            );
        });
    });

    describe('get()', () => {
        test('should retrieve and decrypt wallet from storage', async () => {
            AsyncStorage.multiGet.mockResolvedValueOnce([
                ['@thronos_wallet_address', 'THR1234567890'],
                ['@thronos_wallet_secret', 'encrypted_secret_key_123']
            ]);

            const result = await wallet.get();

            expect(AsyncStorage.multiGet).toHaveBeenCalledWith([
                '@thronos_wallet_address',
                '@thronos_wallet_secret'
            ]);

            expect(CryptoJS.AES.decrypt).toHaveBeenCalledWith(
                'encrypted_secret_key_123',
                'thronos_mainnet_encryption_key'
            );

            expect(result).toEqual({
                address: 'THR1234567890',
                secret: 'secret_key_123'
            });
        });

        test('should return null when no wallet is stored', async () => {
            AsyncStorage.multiGet.mockResolvedValueOnce([
                ['@thronos_wallet_address', null],
                ['@thronos_wallet_secret', null]
            ]);

            const result = await wallet.get();

            expect(result).toBeNull();
        });

        test('should return null when address is missing', async () => {
            AsyncStorage.multiGet.mockResolvedValueOnce([
                ['@thronos_wallet_address', null],
                ['@thronos_wallet_secret', 'encrypted_secret']
            ]);

            const result = await wallet.get();

            expect(result).toBeNull();
        });

        test('should return null when secret is missing', async () => {
            AsyncStorage.multiGet.mockResolvedValueOnce([
                ['@thronos_wallet_address', 'THR123'],
                ['@thronos_wallet_secret', null]
            ]);

            const result = await wallet.get();

            expect(result).toBeNull();
        });

        test('should handle storage errors gracefully', async () => {
            AsyncStorage.multiGet.mockRejectedValueOnce(new Error('Storage error'));

            const result = await wallet.get();

            expect(result).toBeNull();
        });
    });

    describe('isConnected()', () => {
        test('should return true when wallet exists', async () => {
            AsyncStorage.multiGet.mockResolvedValueOnce([
                ['@thronos_wallet_address', 'THR123'],
                ['@thronos_wallet_secret', 'encrypted_secret']
            ]);

            const result = await wallet.isConnected();

            expect(result).toBe(true);
        });

        test('should return false when wallet does not exist', async () => {
            AsyncStorage.multiGet.mockResolvedValueOnce([
                ['@thronos_wallet_address', null],
                ['@thronos_wallet_secret', null]
            ]);

            const result = await wallet.isConnected();

            expect(result).toBe(false);
        });

        test('should return false on storage error', async () => {
            AsyncStorage.multiGet.mockRejectedValueOnce(new Error('Storage error'));

            const result = await wallet.isConnected();

            expect(result).toBe(false);
        });
    });

    describe('disconnect()', () => {
        test('should remove wallet from storage', async () => {
            await wallet.disconnect();

            expect(AsyncStorage.multiRemove).toHaveBeenCalledWith([
                '@thronos_wallet_address',
                '@thronos_wallet_secret'
            ]);
        });

        test('should throw error when removal fails', async () => {
            AsyncStorage.multiRemove.mockRejectedValueOnce(new Error('Removal error'));

            await expect(wallet.disconnect()).rejects.toThrow(
                'Failed to disconnect wallet: Removal error'
            );
        });
    });

    describe('signMessage()', () => {
        test('should sign message with HMAC-SHA256', async () => {
            const message = 'Hello, Thronos!';
            const secret = 'secret_key_123';

            const signature = await wallet.signMessage(message, secret);

            expect(CryptoJS.HmacSHA256).toHaveBeenCalledWith(message, secret);
            expect(signature).toBe(`signature_${message}_${secret}`);
        });

        test('should handle signing errors', async () => {
            CryptoJS.HmacSHA256.mockImplementationOnce(() => {
                throw new Error('Signing error');
            });

            await expect(wallet.signMessage('message', 'secret')).rejects.toThrow(
                'Failed to sign message: Signing error'
            );
        });

        test('should sign different messages differently', async () => {
            const secret = 'secret_key';
            const message1 = 'Message 1';
            const message2 = 'Message 2';

            const sig1 = await wallet.signMessage(message1, secret);
            const sig2 = await wallet.signMessage(message2, secret);

            expect(sig1).not.toBe(sig2);
        });
    });

    describe('verifySignature()', () => {
        test('should verify valid signature', async () => {
            global.fetch.mockResolvedValueOnce({
                ok: true,
                json: async () => ({ valid: true })
            });

            const result = await wallet.verifySignature(
                'message',
                'signature',
                'THR123'
            );

            expect(global.fetch).toHaveBeenCalledWith(
                'https://api.thronos.network/api/wallet/verify',
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        message: 'message',
                        signature: 'signature',
                        address: 'THR123'
                    })
                }
            );

            expect(result).toBe(true);
        });

        test('should return false for invalid signature', async () => {
            global.fetch.mockResolvedValueOnce({
                ok: true,
                json: async () => ({ valid: false })
            });

            const result = await wallet.verifySignature('message', 'bad_sig', 'THR123');

            expect(result).toBe(false);
        });

        test('should return false when API request fails', async () => {
            global.fetch.mockResolvedValueOnce({
                ok: false,
                status: 400
            });

            const result = await wallet.verifySignature('message', 'signature', 'THR123');

            expect(result).toBe(false);
        });

        test('should return false on network error', async () => {
            global.fetch.mockRejectedValueOnce(new Error('Network error'));

            const result = await wallet.verifySignature('message', 'signature', 'THR123');

            expect(result).toBe(false);
        });
    });

    describe('export()', () => {
        test('should export wallet data', async () => {
            const mockWallet = {
                address: 'THR1234567890',
                secret: 'secret_key_123'
            };

            AsyncStorage.multiGet.mockResolvedValueOnce([
                ['@thronos_wallet_address', mockWallet.address],
                ['@thronos_wallet_secret', `encrypted_${mockWallet.secret}`]
            ]);

            const result = await wallet.export();

            expect(result).toEqual(mockWallet);
        });

        test('should throw error when no wallet exists', async () => {
            AsyncStorage.multiGet.mockResolvedValueOnce([
                ['@thronos_wallet_address', null],
                ['@thronos_wallet_secret', null]
            ]);

            await expect(wallet.export()).rejects.toThrow('No wallet to export');
        });
    });

    describe('getQRData()', () => {
        test('should return wallet address for QR code', async () => {
            const mockAddress = 'THR1234567890';

            AsyncStorage.multiGet.mockResolvedValueOnce([
                ['@thronos_wallet_address', mockAddress],
                ['@thronos_wallet_secret', 'encrypted_secret']
            ]);

            const result = await wallet.getQRData();

            expect(result).toBe(mockAddress);
        });

        test('should throw error when no wallet is connected', async () => {
            AsyncStorage.multiGet.mockResolvedValueOnce([
                ['@thronos_wallet_address', null],
                ['@thronos_wallet_secret', null]
            ]);

            await expect(wallet.getQRData()).rejects.toThrow('No wallet connected');
        });
    });

    describe('getEncryptionKey()', () => {
        test('should generate network-specific encryption key', () => {
            const key = wallet.getEncryptionKey();
            expect(key).toBe('thronos_mainnet_encryption_key');
        });

        test('should use testnet network in key', () => {
            const testnetWallet = new ThronosWallet({ ...mockConfig, network: 'testnet' });
            const key = testnetWallet.getEncryptionKey();
            expect(key).toBe('thronos_testnet_encryption_key');
        });

        test('should use devnet network in key', () => {
            const devnetWallet = new ThronosWallet({ ...mockConfig, network: 'devnet' });
            const key = devnetWallet.getEncryptionKey();
            expect(key).toBe('thronos_devnet_encryption_key');
        });
    });

    describe('Integration scenarios', () => {
        test('should complete full wallet lifecycle: create -> get -> disconnect', async () => {
            // Create wallet
            global.fetch.mockResolvedValueOnce({
                ok: true,
                json: async () => ({
                    address: 'THR1234567890',
                    secret: 'secret_key_123'
                })
            });

            const created = await wallet.create();
            expect(created.address).toBe('THR1234567890');

            // Get wallet
            AsyncStorage.multiGet.mockResolvedValueOnce([
                ['@thronos_wallet_address', 'THR1234567890'],
                ['@thronos_wallet_secret', 'encrypted_secret_key_123']
            ]);

            const retrieved = await wallet.get();
            expect(retrieved.address).toBe('THR1234567890');

            // Disconnect
            await wallet.disconnect();
            expect(AsyncStorage.multiRemove).toHaveBeenCalled();
        });

        test('should handle import -> sign -> verify workflow', async () => {
            // Import wallet
            await wallet.import('THR9999', 'my_secret');

            // Sign message
            const signature = await wallet.signMessage('Test message', 'my_secret');
            expect(signature).toContain('signature_');

            // Verify signature
            global.fetch.mockResolvedValueOnce({
                ok: true,
                json: async () => ({ valid: true })
            });

            const isValid = await wallet.verifySignature('Test message', signature, 'THR9999');
            expect(isValid).toBe(true);
        });

        test('should handle export after import', async () => {
            // Import
            await wallet.import('THR_EXPORT_TEST', 'export_secret');

            // Get for export
            AsyncStorage.multiGet.mockResolvedValueOnce([
                ['@thronos_wallet_address', 'THR_EXPORT_TEST'],
                ['@thronos_wallet_secret', 'encrypted_export_secret']
            ]);

            const exported = await wallet.export();
            expect(exported.address).toBe('THR_EXPORT_TEST');
        });
    });
});
