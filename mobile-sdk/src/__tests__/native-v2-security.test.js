jest.mock('react-native-crypto-js', () => require('crypto-js'));

import ThronosWallet from '../wallet';
import ThronosAPI from '../api';

describe('native SDK security contract', () => {
  test('canonical mnemonic preserves the established THR address', async () => {
    const wallet = new ThronosWallet({ apiUrl: 'https://invalid.test', autoSave: false });
    const address = await wallet.deriveAddressFromMnemonic(
      'abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about'
    );
    expect(address).toBe('THR3A2D4145A4F098523B3E8127F1DA87CFC55B8E79');
  });

  test('API sends only a signed transaction envelope', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true }),
    });
    global.fetch = fetchMock;
    const api = new ThronosAPI({ apiUrl: 'https://api.example' });
    const signed = {
      from: 'THR' + 'A'.repeat(40),
      to: 'THR' + 'B'.repeat(40),
      amount: 1,
      token: 'THR',
      nonce: 'synthetic-nonce',
      timestamp: 1800000000,
      signature: '30'.repeat(64),
      publicKey: '02' + '11'.repeat(32),
    };
    await api.sendTransaction(signed);
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body).toEqual({ tx: signed });
    expect(JSON.stringify(body)).not.toMatch(/private_key|send_secret|auth_secret|mnemonic|seed|pin/i);
  });

  test('unsigned swap and raw signing material fail before fetch', async () => {
    global.fetch = jest.fn();
    const api = new ThronosAPI({ apiUrl: 'https://api.example' });
    await expect(api.executeSwap({ amount: 1 })).rejects.toThrow('full-payload signature required');
    await expect(api.executeSwap({
      signature_format: 'wallet_v1_full_payload_v2',
      secret: 'forbidden',
    })).rejects.toThrow('Raw signing material is forbidden');
    expect(global.fetch).not.toHaveBeenCalled();
  });
});
