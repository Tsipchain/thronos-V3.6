/** Wallet V1 Authentication Helper */
(function(window) {
  'use strict';

  function fail(code) {
    const err = new Error(code);
    err.code = code.toUpperCase();
    throw err;
  }

  function getMigrationInfo() {
    try {
      return window.walletSession && typeof window.walletSession.getMigrationInfo === 'function'
        ? (window.walletSession.getMigrationInfo() || {})
        : {};
    } catch (_) {
      return {};
    }
  }

  function resolveActiveWalletAddress() {
    if (typeof window.getActiveWalletAddress === 'function') {
      const active = window.getActiveWalletAddress();
      if (active) return active;
    }
    if (window.walletSession && typeof window.walletSession.getActiveAddress === 'function') {
      const active = window.walletSession.getActiveAddress();
      if (active) return active;
    }
    if (window.walletSession && typeof window.walletSession.getAddress === 'function') {
      const active = window.walletSession.getAddress();
      if (active) return active;
    }
    return localStorage.getItem('thr_address') || '';
  }

  function resolveCredentialLookupAddress(activeAddress) {
    if (window.walletSession && typeof window.walletSession.getCredentialLookupAddress === 'function') {
      try {
        const lookup = window.walletSession.getCredentialLookupAddress(activeAddress);
        if (lookup) return lookup;
      } catch (_) {}
    }
    const info = getMigrationInfo();
    return activeAddress || info.new_v1_address || info.old_address || '';
  }

  function resolveAuthSecret(lookupAddress, activeAddress) {
    if (!window.walletSession || typeof window.walletSession.getSendSeed !== 'function') return '';
    return window.walletSession.getSendSeed(lookupAddress)
      || window.walletSession.getSendSeed(activeAddress)
      || '';
  }

  function hasSigningMaterial() {
    if (!window.walletSession) return false;
    if (typeof window.walletSession.hasV1SigningMaterial === 'function') {
      return !!window.walletSession.hasV1SigningMaterial();
    }
    const publicKey = window.walletSession.getPublicKey && window.walletSession.getPublicKey();
    const hasEncryptedKey = typeof window.walletSession.hasEncryptedPrivateKey !== 'function' || window.walletSession.hasEncryptedPrivateKey();
    return !!(publicKey && hasEncryptedKey && typeof window.walletSession.signTransaction === 'function');
  }

  async function ensureSigningMaterial(address, credentialLookupAddress, authSecret) {
    if (hasSigningMaterial()) return;
    if (!authSecret || !window.walletSession || typeof window.walletSession.enrollSigningMaterial !== 'function') {
      fail('missing_wallet_signing_material');
    }
    alert('Wallet V1 signing upgrade required. Unlock with PIN to create encrypted V1 signing key.');
    await window.walletSession.enrollSigningMaterial({ address, credentialLookupAddress, authSecret });
    if (!hasSigningMaterial()) fail('missing_wallet_signing_material');
  }

  const WalletAuth = {
    resolveActiveWalletAddress,
    resolveCredentialLookupAddress,

    async requireUnlockedWallet() {
      if (!window.walletSession) fail('wallet_session_missing');

      let address = resolveActiveWalletAddress();
      if (!address) {
        const err = new Error('Wallet not connected.');
        err.code = 'WALLET_NOT_CONNECTED';
        throw err;
      }

      if (window.walletSession.isLocked && window.walletSession.isLocked()) {
        const pin = prompt('🔐 PIN (unlock Wallet V1):');
        if (!pin) {
          const err = new Error('Wallet locked');
          err.code = 'WALLET_LOCKED';
          throw err;
        }
        const ok = await window.walletSession.unlockWallet({ pin, prompt: false });
        if (!ok) {
          const err = new Error('Unlock failed');
          err.code = 'UNLOCK_FAILED';
          throw err;
        }
        address = resolveActiveWalletAddress() || address;
      }

      const credentialLookupAddress = resolveCredentialLookupAddress(address);
      const authSecret = resolveAuthSecret(credentialLookupAddress, address);
      await ensureSigningMaterial(address, credentialLookupAddress, authSecret);
      const publicKey = window.walletSession.getPublicKey && window.walletSession.getPublicKey();
      if (!publicKey || typeof window.walletSession.signTransaction !== 'function') {
        fail('missing_wallet_signing_material');
      }

      return {
        address,
        authSecret,
        credentialLookupAddress,
        getPublicKey: () => publicKey,
        signTransaction: async (txCore) => {
          if (!txCore || typeof txCore !== 'object') fail('missing_wallet_signing_material');
          try {
            return await window.walletSession.signTransaction(txCore);
          } catch (err) {
            if (err && err.message === 'wallet_locked') throw err;
            fail('missing_wallet_signing_material');
          }
        }
      };
    },
    isUnlocked() { return !!(window.walletSession && !window.walletSession.isLocked()); },
    getAddress() { return resolveActiveWalletAddress() || null; },
    lock() { if (window.walletSession?.lockWallet) window.walletSession.lockWallet(); },
    _autoLockTimer: null,
    _autoLockTimeout: 5 * 60 * 1000,
    startAutoLock(timeoutMs = null) { this.stopAutoLock(); const timeout = timeoutMs || this._autoLockTimeout; this._autoLockTimer = setTimeout(() => this.lock(), timeout); },
    stopAutoLock() { if (this._autoLockTimer) clearTimeout(this._autoLockTimer); this._autoLockTimer = null; },
    resetAutoLock() { if (this.isUnlocked()) this.startAutoLock(); }
  };

  window.WalletAuth = WalletAuth;
})(window);
