/** Current Mobile SDK security and historical-compatibility contract. */
jest.mock('@react-native-async-storage/async-storage', () => ({
  __esModule: true,
  default: {
    multiSet: jest.fn(),
    multiGet: jest.fn(),
    multiRemove: jest.fn(),
  },
}));
jest.mock('react-native-crypto-js', () => require('crypto-js'));

import CryptoJS from 'react-native-crypto-js';
import AsyncStorage from '@react-native-async-storage/async-storage';
import ThronosSDK from '../index';
import ThronosWallet, {
  ADDRESS_DERIVATION_CANONICAL_V2,
  ADDRESS_DERIVATION_LEGACY_V1,
  MNEMONIC_ENCRYPTION_OS_KEYSTORE_V2,
} from '../wallet';

const MNEMONIC = 'abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about';
const LEGACY_ADDRESS = 'THR7BBE7B233ED012758E8C1A7281AA805D26177F66';
const CANONICAL_ADDRESS = 'THR3A2D4145A4F098523B3E8127F1DA87CFC55B8E79';
const SECURE_KEY = 'synthetic-os-keystore-key-material-32-bytes';

describe('ThronosWallet current security and compatibility contract', () => {
  let storage;
  let authenticate;
  let wallet;

  beforeEach(() => {
    storage = new Map();
    authenticate = jest.fn().mockResolvedValue(true);
    AsyncStorage.multiSet.mockReset().mockImplementation(async pairs => {
      pairs.forEach(([key, value]) => storage.set(key, value));
    });
    AsyncStorage.multiGet.mockReset().mockImplementation(async keys => (
      keys.map(key => [key, storage.has(key) ? storage.get(key) : null])
    ));
    AsyncStorage.multiRemove.mockReset().mockImplementation(async keys => {
      keys.forEach(key => storage.delete(key));
    });
    global.fetch = jest.fn();
    wallet = new ThronosWallet({
      apiUrl: 'https://api.invalid.test',
      autoSave: true,
      network: 'mainnet',
      secureKeyProvider: jest.fn().mockResolvedValue(SECURE_KEY),
      deviceAuthenticator: authenticate,
    });
  });

  describe('address derivation golden vectors', () => {
    test('preserves the pre-#968 hexadecimal-text derivation', async () => {
      await expect(wallet.deriveAddressFromMnemonic(MNEMONIC, ADDRESS_DERIVATION_LEGACY_V1))
        .resolves.toBe(LEGACY_ADDRESS);
    });

    test('uses canonical byte HASH160 for newly enrolled identities', async () => {
      await expect(wallet.deriveAddressFromMnemonic(MNEMONIC, ADDRESS_DERIVATION_CANONICAL_V2))
        .resolves.toBe(CANONICAL_ADDRESS);
    });

    test('rejects unknown derivation versions', async () => {
      await expect(wallet.deriveAddressFromMnemonic(MNEMONIC, 'implicit-latest'))
        .rejects.toThrow('unsupported_address_derivation_version');
    });

    test('legacy and canonical vectors remain intentionally distinct', async () => {
      const legacy = await wallet.deriveAddressFromMnemonic(MNEMONIC, ADDRESS_DERIVATION_LEGACY_V1);
      const canonical = await wallet.deriveAddressFromMnemonic(MNEMONIC, ADDRESS_DERIVATION_CANONICAL_V2);
      expect(legacy).not.toBe(canonical);
    });
  });

  describe('create and import identity persistence', () => {
    test('creates a mnemonic locally without a server request', async () => {
      const result = await wallet.create();
      expect(result.address).toMatch(/^THR[0-9A-F]{40}$/);
      expect(result.mnemonic.split(' ')).toHaveLength(12);
      expect(global.fetch).not.toHaveBeenCalled();
    });

    test('new mnemonic import selects canonical v2', async () => {
      const result = await wallet.import(MNEMONIC);
      expect(result).toEqual({
        address: CANONICAL_ADDRESS,
        derivationVersion: ADDRESS_DERIVATION_CANONICAL_V2,
      });
      expect(storage.get('@thronos_wallet_address')).toBe(CANONICAL_ADDRESS);
      expect(storage.get('@thronos_wallet_derivation_version')).toBe(ADDRESS_DERIVATION_CANONICAL_V2);
    });

    test('existing historical address survives mnemonic restore', async () => {
      storage.set('@thronos_wallet_address', LEGACY_ADDRESS);
      const result = await wallet.import(MNEMONIC);
      expect(result.address).toBe(LEGACY_ADDRESS);
      expect(result.derivationVersion).toBe(ADDRESS_DERIVATION_LEGACY_V1);
      expect(storage.get('@thronos_wallet_address')).toBe(LEGACY_ADDRESS);
    });

    test('existing canonical address survives storage upgrade', async () => {
      storage.set('@thronos_wallet_address', CANONICAL_ADDRESS);
      const result = await wallet.import(MNEMONIC);
      expect(result.address).toBe(CANONICAL_ADDRESS);
      expect(storage.get('@thronos_wallet_address')).toBe(CANONICAL_ADDRESS);
    });

    test('mismatched stored address is never overwritten implicitly', async () => {
      const unrelated = `THR${'A'.repeat(40)}`;
      storage.set('@thronos_wallet_address', unrelated);
      await expect(wallet.import(MNEMONIC)).rejects
        .toThrow('authoritative_identity_validation_required');
      expect(storage.get('@thronos_wallet_address')).toBe(unrelated);
      expect(storage.has('@thronos_wallet_mnemonic_encrypted')).toBe(false);
    });

    test('authoritative external binding requires a positive validator', async () => {
      const authoritative = `THR${'B'.repeat(40)}`;
      storage.set('@thronos_wallet_address', authoritative);
      const validator = jest.fn().mockResolvedValue(true);
      const result = await wallet.import(MNEMONIC, {
        authoritativeAddress: authoritative,
        validateAuthoritativeIdentity: validator,
      });
      expect(result.address).toBe(authoritative);
      expect(validator).toHaveBeenCalledWith(expect.objectContaining({ storedAddress: authoritative }));
    });

    test('invalid mnemonic is rejected without storage writes', async () => {
      await expect(wallet.import('not a recovery phrase')).rejects.toThrow('Invalid BIP39 mnemonic');
      expect(AsyncStorage.multiSet).not.toHaveBeenCalled();
    });

    test('autoSave false derives without persistent writes', async () => {
      const transient = new ThronosWallet({
        apiUrl: 'https://api.invalid.test', autoSave: false,
      });
      const result = await transient.import(MNEMONIC);
      expect(result.address).toBe(CANONICAL_ADDRESS);
      expect(AsyncStorage.multiSet).not.toHaveBeenCalled();
    });
  });

  describe('versioned mnemonic encryption and migration', () => {
    test('new persistent storage requires an OS-backed key provider', async () => {
      const insecure = new ThronosWallet({ apiUrl: 'https://api.invalid.test', autoSave: true });
      await expect(insecure.import(MNEMONIC)).rejects.toThrow('os_keystore_key_provider_required');
      expect(storage.has('@thronos_wallet_mnemonic_encrypted')).toBe(false);
    });

    test('rejects the historical predictable value as a new storage key', async () => {
      const insecure = new ThronosWallet({
        apiUrl: 'https://api.invalid.test', autoSave: true,
        secureKeyProvider: async () => 'default-device-key',
      });
      await expect(insecure.import(MNEMONIC)).rejects.toThrow('invalid_os_keystore_key');
    });

    test('writes explicit encryption and derivation versions', async () => {
      await wallet.import(MNEMONIC);
      expect(storage.get('@thronos_wallet_encryption_version')).toBe(MNEMONIC_ENCRYPTION_OS_KEYSTORE_V2);
      expect(storage.get('@thronos_wallet_derivation_version')).toBe(ADDRESS_DERIVATION_CANONICAL_V2);
      expect(storage.get('@thronos_wallet_mnemonic_encrypted')).not.toContain(MNEMONIC);
    });

    test('ordinary unlock refuses unversioned legacy ciphertext', async () => {
      storage.set('@thronos_wallet_mnemonic_encrypted', 'legacy-ciphertext');
      await expect(wallet.getMnemonicForSigning()).rejects
        .toThrow('legacy_mnemonic_migration_required');
    });

    test('legacy migration is opt-in and recovery-validated', async () => {
      const legacyKey = 'synthetic-legacy-unlock-key';
      storage.set('@thronos_wallet_address', LEGACY_ADDRESS);
      storage.set('@thronos_wallet_mnemonic_encrypted', CryptoJS.AES.encrypt(MNEMONIC, legacyKey).toString());
      jest.spyOn(wallet, 'getLegacyDeviceEncryptionKey').mockResolvedValue(legacyKey);
      const validate = jest.fn().mockResolvedValue(true);
      const result = await wallet.migrateLegacyMnemonicStorage(validate);
      expect(result).toEqual({
        migrated: true,
        address: LEGACY_ADDRESS,
        derivationVersion: ADDRESS_DERIVATION_LEGACY_V1,
      });
      expect(validate).toHaveBeenCalledWith(expect.objectContaining({
        address: LEGACY_ADDRESS,
        legacyAddress: LEGACY_ADDRESS,
        canonicalAddress: CANONICAL_ADDRESS,
      }));
      expect(storage.get('@thronos_wallet_address')).toBe(LEGACY_ADDRESS);
      expect(storage.get('@thronos_wallet_encryption_version')).toBe(MNEMONIC_ENCRYPTION_OS_KEYSTORE_V2);
    });

    test('failed validation leaves legacy values byte-for-byte intact', async () => {
      const legacyKey = 'synthetic-legacy-unlock-key';
      const ciphertext = CryptoJS.AES.encrypt(MNEMONIC, legacyKey).toString();
      storage.set('@thronos_wallet_address', LEGACY_ADDRESS);
      storage.set('@thronos_wallet_mnemonic_encrypted', ciphertext);
      jest.spyOn(wallet, 'getLegacyDeviceEncryptionKey').mockResolvedValue(legacyKey);
      await expect(wallet.migrateLegacyMnemonicStorage(async () => false))
        .rejects.toThrow('recovery_validation_failed');
      expect(storage.get('@thronos_wallet_address')).toBe(LEGACY_ADDRESS);
      expect(storage.get('@thronos_wallet_mnemonic_encrypted')).toBe(ciphertext);
      expect(storage.has('@thronos_wallet_encryption_version')).toBe(false);
    });

    test('legacy default key requires explicit migration opt-in', async () => {
      await expect(wallet.getLegacyDeviceEncryptionKey()).rejects.toThrow('legacy_device_key_required');
    });
  });

  describe('device-approved signing', () => {
    beforeEach(async () => {
      await wallet.import(MNEMONIC);
      AsyncStorage.multiGet.mockClear();
    });

    test('approved signing preserves the SignedTxEnvelope format', async () => {
      const signed = await wallet.signTransaction({
        from: CANONICAL_ADDRESS,
        to: `THR${'C'.repeat(40)}`,
        amount: 7,
        token: 'THR',
        nonce: 'approved-1',
      });
      expect(authenticate).toHaveBeenCalledTimes(1);
      expect(signed).toEqual(expect.objectContaining({
        from: CANONICAL_ADDRESS,
        amount: 7,
        nonce: 'approved-1',
        signature: expect.any(String),
        publicKey: expect.stringMatching(/^(02|03)[0-9a-f]{64}$/),
      }));
      expect(signed).not.toHaveProperty('privateKey');
      expect(signed).not.toHaveProperty('mnemonic');
    });

    test.each([
      ['biometric cancellation', false],
      ['explicit denial', { success: false, error: 'denied' }],
      ['session expiry', { success: false, error: 'expired' }],
      ['locked device', { success: false, error: 'lockout' }],
    ])('%s prevents key access', async (_label, result) => {
      authenticate.mockResolvedValueOnce(result);
      await expect(wallet.signTransaction({
        from: CANONICAL_ADDRESS, to: `THR${'D'.repeat(40)}`, amount: 1, nonce: 'deny-1',
      })).rejects.toThrow('device_authentication_cancelled');
      const requestedKeys = AsyncStorage.multiGet.mock.calls.flatMap(call => call[0]);
      expect(requestedKeys).not.toContain('@thronos_wallet_mnemonic_encrypted');
    });

    test('account switch during approval prevents key access', async () => {
      authenticate.mockImplementationOnce(async () => {
        storage.set('@thronos_wallet_address', `THR${'E'.repeat(40)}`);
        return true;
      });
      await expect(wallet.signTransaction({
        from: CANONICAL_ADDRESS, to: `THR${'F'.repeat(40)}`, amount: 1, nonce: 'switch-1',
      })).rejects.toThrow('wallet_changed_during_approval');
      const requestedKeys = AsyncStorage.multiGet.mock.calls.flatMap(call => call[0]);
      expect(requestedKeys).not.toContain('@thronos_wallet_mnemonic_encrypted');
    });

    test('wrong sender is rejected before device approval', async () => {
      await expect(wallet.signTransaction({
        from: `THR${'0'.repeat(40)}`, to: `THR${'1'.repeat(40)}`, amount: 1,
      })).rejects.toThrow('wallet_address_mismatch');
      expect(authenticate).not.toHaveBeenCalled();
    });

    test('missing authenticator fails before mnemonic access', async () => {
      const noAuth = new ThronosWallet({
        apiUrl: 'https://api.invalid.test', autoSave: false,
        secureKeyProvider: async () => SECURE_KEY,
      });
      await expect(noAuth.signTransaction({
        from: CANONICAL_ADDRESS, to: `THR${'2'.repeat(40)}`, amount: 1,
      })).rejects.toThrow('device_authenticator_required');
    });

    test('recovery export also requires approval', async () => {
      authenticate.mockResolvedValueOnce(false);
      await expect(wallet.export()).rejects.toThrow('device_authentication_cancelled');
      const requestedKeys = AsyncStorage.multiGet.mock.calls.flatMap(call => call[0]);
      expect(requestedKeys).not.toContain('@thronos_wallet_mnemonic_encrypted');
    });

    test('SDK cancellation produces no transaction network request', async () => {
      const denied = jest.fn().mockResolvedValue(false);
      const sdk = new ThronosSDK({
        apiUrl: 'https://api.invalid.test',
        autoSave: true,
        secureKeyProvider: async () => SECURE_KEY,
        deviceAuthenticator: denied,
      });
      global.fetch.mockClear();
      await expect(sdk.sendTransaction(`THR${'9'.repeat(40)}`, 1, 'THR'))
        .rejects.toThrow('device_authentication_cancelled');
      expect(global.fetch).not.toHaveBeenCalled();
    });
  });

  describe('read-only and lifecycle behavior', () => {
    test('get returns stored address without exposing mnemonic', async () => {
      storage.set('@thronos_wallet_address', LEGACY_ADDRESS);
      storage.set('@thronos_wallet_derivation_version', ADDRESS_DERIVATION_LEGACY_V1);
      const result = await wallet.get();
      expect(result).toEqual({
        address: LEGACY_ADDRESS,
        pubkey: null,
        derivationVersion: ADDRESS_DERIVATION_LEGACY_V1,
      });
      expect(result).not.toHaveProperty('mnemonic');
    });

    test('isConnected depends only on persisted public identity', async () => {
      expect(await wallet.isConnected()).toBe(false);
      storage.set('@thronos_wallet_address', CANONICAL_ADDRESS);
      expect(await wallet.isConnected()).toBe(true);
    });

    test('disconnect removes wallet metadata and encrypted mnemonic', async () => {
      await wallet.import(MNEMONIC);
      await wallet.disconnect();
      expect(await wallet.get()).toBeNull();
      expect(storage.has('@thronos_wallet_mnemonic_encrypted')).toBe(false);
      expect(storage.has('@thronos_wallet_derivation_version')).toBe(false);
    });

    test('QR output contains only the stored address', async () => {
      storage.set('@thronos_wallet_address', CANONICAL_ADDRESS);
      await expect(wallet.getQRData()).resolves.toBe(CANONICAL_ADDRESS);
    });

    test('payment request round-trips address, amount, and token', async () => {
      storage.set('@thronos_wallet_address', CANONICAL_ADDRESS);
      const request = await wallet.generatePaymentRequest(12.5, 'L2E');
      expect(wallet.parsePaymentRequest(request)).toEqual({
        address: CANONICAL_ADDRESS,
        amount: 12.5,
        token: 'L2E',
      });
    });

    test('invalid payment request is rejected', () => {
      expect(() => wallet.parsePaymentRequest('https://invalid.test')).toThrow('Invalid payment request format');
    });

    test('wallet info shortens only public identity data', async () => {
      storage.set('@thronos_wallet_address', CANONICAL_ADDRESS);
      const info = await wallet.getWalletInfo();
      expect(info.address).toBe(CANONICAL_ADDRESS);
      expect(info.shortAddress).toContain('...');
      expect(info).not.toHaveProperty('mnemonic');
    });
  });
});
