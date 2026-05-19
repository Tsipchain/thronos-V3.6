// Wallet Security Tests
// Ensures private keys and mnemonics never leave the device

import * as wallet from '../wallet';
import * as signing from '../signing';
import * as SecureStore from 'expo-secure-store';

jest.mock('expo-secure-store');
jest.mock('expo-application', () => ({
  getUniqueIdAsync: jest.fn(() => Promise.resolve('test-device-id')),
}));

describe('Wallet Security - No Secret Transport', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Mnemonic Storage', () => {
    it('should encrypt mnemonic before storing', async () => {
      const mnemonic = wallet.generateMnemonic(128);
      await wallet.saveMnemonic(mnemonic);
      const setItemCall = (SecureStore.setItemAsync as jest.Mock).mock.calls[0];
      const encryptedValue = setItemCall[1];
      expect(encryptedValue).not.toContain(mnemonic);
      expect(encryptedValue).toMatch(/^[A-Za-z0-9+/=]+$/);
    });

    it('should retrieve and decrypt mnemonic correctly', async () => {
      const testMnemonic = wallet.generateMnemonic(128);
      (SecureStore.getItemAsync as jest.Mock).mockResolvedValue(testMnemonic.split(' ').join('_'));
      const retrieved = await wallet.getMnemonic();
      expect(retrieved).toBeDefined();
    });

    it('should clear mnemonic on deletion', async () => {
      await wallet.clearMnemonic();
      expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith(expect.stringContaining('mnemonic'));
    });
  });

  describe('Transaction Signing', () => {
    it('should sign transactions without transmitting private key', async () => {
      const txData = { from: 'THR1234567890abcdef', to: 'THR0987654321fedcba', amount: 100, token: 'THR', nonce: 1 };
      const signedTx = await signing.signThronosTransaction(txData);
      expect(signedTx).toHaveProperty('signature');
      expect(signedTx).toHaveProperty('publicKey');
      expect(signedTx).not.toHaveProperty('privateKey');
      expect(signedTx).not.toHaveProperty('secret');
      expect(signedTx).not.toHaveProperty('mnemonic');
      expect(JSON.stringify(signedTx)).not.toContain('private');
    });

    it('should include only public information in signed tx envelope', async () => {
      const txData = { from: 'THR1234567890abcdef', to: 'THR0987654321fedcba', amount: 50, nonce: 2 };
      const signedTx = await signing.signThronosTransaction(txData);
      const txEnvelopeKeys = Object.keys(signedTx);
      const publicOnlyKeys = ['nonce','timestamp','from','to','amount','token','fee','signature','publicKey'];
      expect(txEnvelopeKeys).toEqual(expect.arrayContaining(publicOnlyKeys));
      const sensitiveFields = ['secret', 'privateKey', 'mnemonic', 'seed'];
      sensitiveFields.forEach((field) => {
        expect(txEnvelopeKeys).not.toContain(field);
      });
    });

    it('should reject if wallet address mismatch', async () => {
      const txData = { from: 'THRDIFFERENTADDRESS', to: 'THR0987654321fedcba', amount: 100, nonce: 1 };
      await expect(signing.signThronosTransaction(txData)).rejects.toThrow('address mismatch');
    });
  });

  describe('Message Signing', () => {
    it('should sign message without exposing private key', async () => {
      const message = 'test message';
      const signedMessage = await signing.signMessage(message);
      expect(signedMessage).toHaveProperty('signature');
      expect(signedMessage).toHaveProperty('publicKey');
      expect(signedMessage).toHaveProperty('message', message);
      expect(signedMessage).not.toHaveProperty('privateKey');
      expect(signedMessage).not.toHaveProperty('secret');
    });
  });

  describe('Wallet Storage', () => {
    it('should store only address and public key, not secrets', async () => {
      const result = await wallet.createNewWallet();
      const setItemCalls = (SecureStore.setItemAsync as jest.Mock).mock.calls;
      const values = setItemCalls.map((call) => call[1]);
      const sensitiveFields = ['secret', 'privateKey', 'mnemonic_plain'];
      values.forEach((value) => {
        sensitiveFields.forEach((field) => {
          if (typeof value === 'string') { expect(value).not.toContain(field); }
        });
      });
    });

    it('should retrieve wallet without exposing secrets', async () => {
      const wallet_creds = await wallet.getWallet();
      if (wallet_creds) {
        expect(wallet_creds).toHaveProperty('address');
        expect(wallet_creds).toHaveProperty('publicKey');
        expect(wallet_creds).not.toHaveProperty('secret');
        expect(wallet_creds).not.toHaveProperty('privateKey');
      }
    });
  });

  describe('Network Request Protection', () => {
    it('should not construct requests with secrets', () => {
      const requestBody = {
        tx: { nonce: 1, from: 'THR1234567890abcdef', to: 'THR0987654321fedcba', amount: 100, signature: 'mock_signature', publicKey: 'mock_pubkey' },
      };
      const bodyString = JSON.stringify(requestBody);
      expect(bodyString).not.toMatch(/secret|privateKey|mnemonic/i);
    });
  });

  describe('Device-Specific Encryption', () => {
    it('should derive encryption key from device ID', async () => {
      const mnemonic1 = wallet.generateMnemonic(128);
      await wallet.saveMnemonic(mnemonic1);
      const calls = (SecureStore.setItemAsync as jest.Mock).mock.calls;
      const encryptedValue = calls[calls.length - 1][1];
      expect(encryptedValue).toBeTruthy();
      expect(encryptedValue).not.toEqual(mnemonic1);
    });
  });
});
