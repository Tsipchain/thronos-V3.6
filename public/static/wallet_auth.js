/** Wallet V1 Authentication Helper */
(function(window) {
  'use strict';

  const WalletAuth = {
    async requireUnlockedWallet() {
      if (!window.walletSession) {
        const err = new Error('wallet_session_missing'); err.code = 'WALLET_SESSION_MISSING'; throw err;
      }
      const address = window.walletSession.getAddress();
      if (!address) {
        const err = new Error('Wallet not connected.'); err.code = 'WALLET_NOT_CONNECTED'; throw err;
      }
      if (window.walletSession.isLocked && window.walletSession.isLocked()) {
        const pin = prompt('🔐 PIN (unlock Wallet V1):');
        if (!pin) { const err = new Error('Wallet locked'); err.code = 'WALLET_LOCKED'; throw err; }
        const ok = await window.walletSession.unlockWallet({ pin, prompt: false });
        if (!ok) { const err = new Error('Unlock failed'); err.code = 'UNLOCK_FAILED'; throw err; }
      }
      return {
        address,
        getPublicKey: () => window.walletSession.getPublicKey(),
        signTransaction: (txCore) => window.walletSession.signTransaction(txCore)
      };
    },
    isUnlocked() { return !!(window.walletSession && !window.walletSession.isLocked()); },
    getAddress() { return window.walletSession?.getAddress?.() || null; },
    lock() { if (window.walletSession?.lockWallet) window.walletSession.lockWallet(); },
    _autoLockTimer: null,
    _autoLockTimeout: 5 * 60 * 1000,
    startAutoLock(timeoutMs = null) { this.stopAutoLock(); const timeout = timeoutMs || this._autoLockTimeout; this._autoLockTimer = setTimeout(() => this.lock(), timeout); },
    stopAutoLock() { if (this._autoLockTimer) clearTimeout(this._autoLockTimer); this._autoLockTimer = null; },
    resetAutoLock() { if (this.isUnlocked()) this.startAutoLock(); }
  };

  window.WalletAuth = WalletAuth;
})(window);
