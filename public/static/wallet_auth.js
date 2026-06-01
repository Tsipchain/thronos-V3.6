/**
 * Wallet V1 Authentication Helper
 *
 * Provides PIN-based unlock for wallet mutations while keeping plaintext
 * signing material in memory only for the page lifetime.
 */
(function(window) {
    'use strict';

    const VERSION = 'wallet-v1-state-sync-2026-05-30';

    function getActiveWalletAddress() {
        if (window.walletSession && typeof window.walletSession.getActiveAddress === 'function') {
            return window.walletSession.getActiveAddress() || null;
        }
        if (window.walletSession && typeof window.walletSession.getAddress === 'function') {
            return window.walletSession.getAddress() || null;
        }
        return localStorage.getItem('thr_address') || null;
    }

    function getCredentialLookupAddress(address) {
        if (window.walletSession && typeof window.walletSession.getCredentialLookupAddress === 'function') {
            return window.walletSession.getCredentialLookupAddress(address) || address || null;
        }
        return address || null;
    }

    function getSigningMaterial(address) {
        if (window.walletSession && typeof window.walletSession.getSendSeed === 'function') {
            return window.walletSession.getSendSeed(address) || '';
        }
        return localStorage.getItem('send_secret') || localStorage.getItem('send_seed') || localStorage.getItem('thr_secret') || '';
    }

    function shortAddress(address) {
        return address ? address.substring(0, 10) + '...' : '';
    }

    function hasRuntimeSigningMaterial(address) {
        return !!(window.walletSession &&
                  typeof window.walletSession.hasRuntimeSigningMaterial === 'function' &&
                  window.walletSession.hasRuntimeSigningMaterial(address));
    }

    function hasEncryptedSeed() {
        return !!(window.walletSession &&
                  typeof window.walletSession.hasEncryptedPrivateKey === 'function' &&
                  window.walletSession.hasEncryptedPrivateKey()) ||
               !!localStorage.getItem('wallet_v1_encrypted_priv');
    }

    function logAuthDiagnostics(address, source = 'wallet_auth') {
        try {
            console.info('[WalletAuth]', {
                active_address_short: shortAddress(address),
                has_encrypted_seed: hasEncryptedSeed(),
                has_runtime_signing_material: hasRuntimeSigningMaterial(address),
                is_locked: !!(window.walletSession && typeof window.walletSession.isLocked === 'function' && window.walletSession.isLocked()),
                source: source
            });
        } catch (_) {}
    }

    function missingSigningMaterialError() {
        const err = new Error('missing_wallet_signing_material');
        err.code = 'UNLOCK_FAILED';
        return err;
    }

    function walletLockedRelockRequiredError() {
        const err = new Error('wallet_locked_reunlock_required');
        err.code = 'WALLET_LOCKED_REUNLOCK_REQUIRED';
        return err;
    }

    function hasV1SigningMaterial() {
        return !!(window.walletSession &&
                  typeof window.walletSession.isWalletV1 === 'function' &&
                  window.walletSession.isWalletV1());
    }

    function buildAuthResult(address, authSecret, credentialLookupAddress) {
        return {
            address,
            authSecret,
            credentialLookupAddress,
            getPublicKey: () => (
                window.walletSession && typeof window.walletSession.getPublicKey === 'function'
                    ? window.walletSession.getPublicKey()
                    : ''
            ),
            signTransaction: async (txCore) => {
                if (!window.walletSession || typeof window.walletSession.signTransaction !== 'function') {
                    throw missingSigningMaterialError();
                }
                try {
                    const signature = await window.walletSession.signTransaction(txCore);
                    if (!signature) throw walletLockedRelockRequiredError();
                    return signature;
                } catch (err) {
                    if (err && (err.message === 'wallet_locked' || err.code === 'WALLET_LOCKED_REUNLOCK_REQUIRED')) {
                        throw walletLockedRelockRequiredError();
                    }
                    throw err;
                }
            }
        };
    }

    let cachedAuthSecret = '';
    let cachedAuthAddress = '';
    let cachedRuntimeSigningAddress = '';

    const WalletAuth = {
        version: VERSION,
        /**
         * Require unlocked wallet for mutations.
         * Throws error codes: WALLET_NOT_CONNECTED, WALLET_LOCKED, UNLOCK_FAILED.
         */
        async requireUnlockedWallet(options = {}) {
            const address = getActiveWalletAddress();
            if (!address) {
                const err = new Error('Wallet not connected. Please connect your wallet first.');
                err.code = 'WALLET_NOT_CONNECTED';
                throw err;
            }

            const source = options.source || 'wallet_auth';
            const credentialLookupAddress = getCredentialLookupAddress(address);
            logAuthDiagnostics(address, source);

            // Check if Wallet V1 runtime signing material is already available in this tab.
            if (hasRuntimeSigningMaterial(address)) {
                cachedRuntimeSigningAddress = address;
                return buildAuthResult(address, '', credentialLookupAddress);
            }

            if (cachedRuntimeSigningAddress && cachedRuntimeSigningAddress === address && hasRuntimeSigningMaterial(address)) {
                return buildAuthResult(address, '', credentialLookupAddress);
            }

            // Do not persist plaintext signing material in localStorage/sessionStorage.
            if (cachedAuthSecret && (!cachedAuthAddress || cachedAuthAddress === address || cachedAuthAddress === credentialLookupAddress)) {
                return buildAuthResult(address, cachedAuthSecret, credentialLookupAddress);
            }

            const storedSecret = getSigningMaterial(address);
            if (storedSecret) {
                cachedAuthSecret = storedSecret;
                cachedAuthAddress = address;
                return buildAuthResult(address, storedSecret, credentialLookupAddress);
            }

            if (hasEncryptedSeed() && window.walletSession && typeof window.walletSession.isLocked === 'function' && !window.walletSession.isLocked() && !hasRuntimeSigningMaterial(address)) {
                if (typeof window.walletSession.lockWallet === 'function') window.walletSession.lockWallet();
                logAuthDiagnostics(address, source);
            }

            const pin = prompt('🔐 PIN (unlock wallet):');
            if (!pin) {
                throw walletLockedRelockRequiredError();
            }

            if (window.walletSession && typeof window.walletSession.unlockWallet === 'function') {
                try {
                    const ok = await window.walletSession.unlockWallet({ pin, address });
                    if (!ok) throw walletLockedRelockRequiredError();

                    if (!hasV1SigningMaterial()) {
                        if (typeof window.walletSession.enrollSigningMaterial === 'function') {
                            try {
                                await window.walletSession.enrollSigningMaterial({
                                    address: address,
                                    credentialLookupAddress: credentialLookupAddress,
                                    pin: pin
                                });
                            } catch (enrollErr) {
                                const err = new Error('Wallet V1 signing key is missing. Please unlock/migrate wallet to create signing material.');
                                err.code = 'UNLOCK_FAILED';
                                throw err;
                            }
                        }
                    }

                    if (hasRuntimeSigningMaterial(address)) {
                        cachedRuntimeSigningAddress = address;
                        return buildAuthResult(address, '', credentialLookupAddress);
                    }
                    const authSecret = getSigningMaterial(address);
                    if (authSecret) {
                        cachedAuthSecret = authSecret;
                        cachedAuthAddress = address;
                        return buildAuthResult(address, authSecret, credentialLookupAddress);
                    }
                    throw walletLockedRelockRequiredError();
                } catch (e) {
                    if (e && e.code === 'WALLET_LOCKED_REUNLOCK_REQUIRED') throw e;
                    if (e && (e.message || '').includes('wallet_signing_address_mismatch')) {
                        const err = new Error('Wallet signing key does not match the active wallet address. Please import or migrate the correct key for ' + shortAddress(address) + '.');
                        err.code = 'WALLET_SIGNING_ADDRESS_MISMATCH';
                        throw err;
                    }
                    const err = new Error(e && e.code === 'UNLOCK_FAILED'
                        ? e.message
                        : 'Failed to unlock wallet: ' + (e.message || e));
                    err.code = 'UNLOCK_FAILED';
                    throw err;
                }
            }

            const storedPin = localStorage.getItem('wallet_pin');
            if (storedPin === pin) {
                try {
                    if (!hasV1SigningMaterial()) {
                        if (typeof window.walletSession.enrollSigningMaterial === 'function') {
                            try {
                                await window.walletSession.enrollSigningMaterial({
                                    address: address,
                                    credentialLookupAddress: credentialLookupAddress,
                                    pin: pin
                                });
                            } catch (enrollErr) {
                                const err = new Error('Wallet V1 signing key is missing. Please unlock/migrate wallet to create signing material.');
                                err.code = 'UNLOCK_FAILED';
                                throw err;
                            }
                        }
                    }
                    if (hasRuntimeSigningMaterial(address)) {
                        cachedRuntimeSigningAddress = address;
                        return buildAuthResult(address, '', credentialLookupAddress);
                    }
                    const authSecret = getSigningMaterial(address);
                    if (authSecret) {
                        cachedAuthSecret = authSecret;
                        cachedAuthAddress = address;
                        return buildAuthResult(address, authSecret, credentialLookupAddress);
                    }
                    throw walletLockedRelockRequiredError();
                } catch (e) {
                    if (e && e.code === 'WALLET_LOCKED_REUNLOCK_REQUIRED') throw e;
                    const err = new Error(e && e.code === 'UNLOCK_FAILED'
                        ? e.message
                        : 'Failed to unlock wallet: ' + (e.message || e));
                    err.code = 'UNLOCK_FAILED';
                    throw err;
                }
            }

            const err = new Error('Invalid PIN. Please try again.');
            err.code = 'UNLOCK_FAILED';
            throw err;
        },

        isUnlocked() {
            const address = getActiveWalletAddress();
            return !!(hasRuntimeSigningMaterial(address) || cachedAuthSecret || getSigningMaterial(address));
        },

        hasRuntimeSigningMaterial(address = null) {
            const active = address || getActiveWalletAddress();
            return hasRuntimeSigningMaterial(active);
        },

        logDiagnostics(source = 'wallet_auth') {
            logAuthDiagnostics(getActiveWalletAddress(), source);
        },

        getAddress() {
            return getActiveWalletAddress();
        },

        _autoLockTimer: null,
        _autoLockTimeout: 5 * 60 * 1000,

        startAutoLock(timeoutMs = null) {
            this.stopAutoLock();
            const timeout = timeoutMs || this._autoLockTimeout;
            this._autoLockTimer = setTimeout(() => {
                console.log('[WalletAuth] Auto-locking wallet after inactivity');
                this.lock();
                if (typeof showToast === 'function') {
                    showToast('Wallet locked due to inactivity');
                }
            }, timeout);
            console.log(`[WalletAuth] Auto-lock timer started (${timeout / 1000}s)`);
        },

        stopAutoLock() {
            if (this._autoLockTimer) {
                clearTimeout(this._autoLockTimer);
                this._autoLockTimer = null;
            }
        },

        resetAutoLock() {
            if (this.isUnlocked()) {
                this.startAutoLock();
            }
        },

        lock() {
            cachedAuthSecret = '';
            cachedAuthAddress = '';
            cachedRuntimeSigningAddress = '';
            sessionStorage.removeItem('thr_auth_secret');
            sessionStorage.removeItem('thr_auth_secret_address');
            if (window.walletSession && typeof window.walletSession.lockWallet === 'function') {
                window.walletSession.lockWallet();
            }
        }
    };

    window.WalletAuth = WalletAuth;

    window.addEventListener('thronos:wallet:v1:unlocked', (event) => {
        const address = event && event.detail ? event.detail.address : getActiveWalletAddress();
        if (address && hasRuntimeSigningMaterial(address)) {
            cachedRuntimeSigningAddress = address;
        }
        logAuthDiagnostics(address, 'header');
    });

    window.addEventListener('thronos:wallet:state-changed', () => {
        const address = getActiveWalletAddress();
        if (!hasRuntimeSigningMaterial(address)) {
            cachedRuntimeSigningAddress = '';
        }
    });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAutoLock);
    } else {
        initAutoLock();
    }

    function initAutoLock() {
        if (WalletAuth.isUnlocked()) {
            WalletAuth.startAutoLock();
        }

        const activityEvents = ['mousedown', 'keypress', 'scroll', 'touchstart', 'click'];
        activityEvents.forEach(eventType => {
            document.addEventListener(eventType, () => {
                WalletAuth.resetAutoLock();
            }, { passive: true });
        });

        const originalRequire = WalletAuth.requireUnlockedWallet;
        WalletAuth.requireUnlockedWallet = async function(options = {}) {
            const result = await originalRequire.call(this, options);
            WalletAuth.startAutoLock();
            return result;
        };

        console.log('[WalletAuth] Auto-lock initialized');
    }
})(window);