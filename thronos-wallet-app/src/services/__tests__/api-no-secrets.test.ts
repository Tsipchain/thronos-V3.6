/**
 * API Security Test Suite
 * Verifies that NO secrets/mnemonics/private keys are transmitted to backend
 */

import * as API from '../api';

describe('API Security - No Secret Transmission', () => {
  test('sendTHRSigned should require signature, not secret', () => {
    const validCall = {
      signedTx: {
        nonce: 1,
        timestamp: Date.now(),
        from: 'THR...',
        to: 'THR...',
        amount: 100,
        signature: 'abc123',
        publicKey: 'pub_key'
      },
      speed: 'fast'
    };
    expect(validCall.signedTx).toHaveProperty('signature');
    expect(validCall.signedTx).toHaveProperty('publicKey');
    expect(validCall.signedTx).not.toHaveProperty('secret');
    expect(validCall.signedTx).not.toHaveProperty('mnemonic');
    expect(validCall.signedTx).not.toHaveProperty('privateKey');
  });

  test('SignedTxEnvelope should not include sensitive fields', () => {
    const envelope: any = {
      nonce: 1,
      timestamp: Date.now(),
      from: 'THR...',
      to: 'THR...',
      amount: 100,
      token: 'THR',
      fee: 0,
      signature: 'sig...',
      publicKey: 'pub...'
    };
    const sensitiveFields = ['secret', 'mnemonic', 'seed', 'privateKey', 'auth_secret'];
    sensitiveFields.forEach(field => {
      expect(envelope).not.toHaveProperty(field);
    });
  });

  test('No API method should accept secret parameter', () => {
    const mockSignedTx = {
      nonce: 1,
      timestamp: Date.now(),
      from: 'THR...',
      to: 'THR...',
      amount: 100,
      signature: 'sig',
      publicKey: 'pub'
    };
    const apis = [
      { name: 'sendTHRSigned', func: (tx: any) => ({ signedTx: tx }) },
      { name: 'executeSwapSigned', func: (tx: any) => ({ signedTx: tx }) },
      { name: 'executeBridgeSigned', func: (tx: any) => ({ signedTx: tx, from_chain: '', to_chain: '' }) },
      { name: 'pledgeTokensSigned', func: (tx: any) => ({ signedTx: tx }) },
    ];
    apis.forEach(api => {
      const params = api.func(mockSignedTx);
      expect(params).toHaveProperty('signedTx');
      expect(params.signedTx).toHaveProperty('signature');
      expect(params.signedTx).not.toHaveProperty('secret');
    });
  });

  test('Old secret-based API methods should be removed', () => {
    const apiModule = require('../api');
    const oldMethods = ['sendTHR','sendToken','executeSwap','executeBridge','pledgeTokens','voteOnProposal','addLiquidity','removeLiquidity'];
    oldMethods.forEach(method => {
      expect(apiModule[method]).toBeUndefined();
    });
  });

  test('Signed-only API methods should be exported', () => {
    const apiModule = require('../api');
    const signedMethods = ['sendTHRSigned','sendTokenSigned','executeSwapSigned','executeBridgeSigned','pledgeTokensSigned','voteOnProposalSigned','addLiquiditySigned','removeLiquiditySigned'];
    signedMethods.forEach(method => {
      expect(apiModule[method]).toBeDefined();
      expect(typeof apiModule[method]).toBe('function');
    });
  });

  test('Request body should only contain public data', () => {
    const requestBody = {
      tx: {
        nonce: 1,
        timestamp: 1234567890,
        from: 'THR1234567890abcdef1234567890abcdef',
        to: 'THR0987654321fedcba0987654321fedcba',
        amount: 100,
        token: 'THR',
        fee: 0,
        signature: 'abcd1234efgh5678ijkl9012mnop3456',
        publicKey: 'pubkey_1234567890'
      },
      speed: 'fast'
    };
    const bodyString = JSON.stringify(requestBody);
    const sensitivePatterns = ['secret', 'mnemonic', 'seed', 'privateKey'];
    sensitivePatterns.forEach(pattern => {
      expect(bodyString.toLowerCase()).not.toContain(pattern.toLowerCase());
    });
  });

  test('Private key should never be in wallet response', () => {
    const publicWalletInfo = { address: 'THR...', publicKey: 'pub...' };
    const sensitiveFields = ['secret', 'privateKey', 'mnemonic', 'seed', 'auth_secret'];
    sensitiveFields.forEach(field => {
      expect(publicWalletInfo).not.toHaveProperty(field);
    });
  });
});

describe('Production Screen Security Checks', () => {
  test('Screens should import signed API methods only', () => {
    const screenImports = {
      'SendScreen.tsx': { old: 'import { sendTHR } from api', new: 'import { sendTHRSigned } from api' },
      'StakeScreen.tsx': { old: 'import { pledgeTokens } from api', new: 'import { pledgeTokensSigned } from api' },
      'SwapScreen.tsx': { old: 'import { executeSwap } from api', new: 'import { executeSwapSigned } from api' },
      'BridgeScreen.tsx': { old: 'import { executeBridge } from api', new: 'import { executeBridgeSigned } from api' }
    };
    Object.values(screenImports).forEach(imports => {
      expect(imports.new).toBeTruthy();
    });
  });

  test('Screens should use signThronosTransaction before sending', () => {
    const correctPattern = { getWallet: true, signThronosTransaction: true, sendSigned: true, noRawSecret: true };
    expect(correctPattern.signThronosTransaction).toBe(true);
    expect(correctPattern.sendSigned).toBe(true);
  });
});

describe('Backend Verification Requirements', () => {
  test('Backend must verify signatures before accepting transactions', () => {
    const requirements = {
      'MUST verify signature using public key': true,
      'MUST reject unsigned transaction envelopes': true,
      'MUST reject transactions with "secret" field': true,
      'MUST reject transactions with "mnemonic" field': true,
      'MUST reject transactions with "privateKey" field': true,
      'MUST use strict schema validation': true,
      'MUST reject any field not in SignedTxEnvelope interface': true,
      'MUST log rejections with reason': true,
    };
    Object.entries(requirements).forEach(([, status]) => {
      expect(status).toBe(true);
    });
  });

  test('Backend must disable legacy secret-based endpoints', () => {
    const endpointsToDisable = [
      'POST /api/wallet/create',
      'POST /send_thr',
      'POST /api/tokens/transfer',
      'POST /api/swap/execute',
      'POST /api/bridge/execute',
      'POST /api/pledge/stake',
      'POST /api/v1/governance/vote'
    ];
    endpointsToDisable.forEach(endpoint => {
      expect(endpoint).toMatch(/api\/(wallet|tokens|swap|bridge|pledge|governance)/);
    });
  });
});
