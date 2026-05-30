/**
 * Wallet V1 Authentication Helper
 *
 * Provides PIN-based unlock for wallet mutations while keeping plaintext
 * signing material in memory only for the page lifetime.
 */
(function(window) {
    'use strict';

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

    function logAuthDiagnostics(address) {
        try {
            if (window.walletSession && typeof window.walletSession.logWalletAuthDiagnostics === 'function') {
                window.walletSession.logWalletAuthDiagnostics(address);
                return;
            }
            console.info('[WalletAuth]', {
                active_wallet_address: address || '',
                credential_lookup_address: getCredentialLookupAddress(address) || '',
                migration_old_address: '',
                migration_new_v1_address: '',
                has_encrypted_send_seed: !!localStorage.getItem('encrypted_send_seed'),
                has_signing_material: !!getSigningMaterial(address)
            });
        } catch (_) {}
    }

    function missingSigningMaterialError() {
        const err = new Error('missing_wallet_signing_material');
        err.code = 'UNLOCK_FAILED';
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
            signTransaction: (txCore) => {
                if (!window.walletSession || typeof window.walletSession.signTransaction !== 'function') {
                    throw missingSigningMaterialError();
                }
                return window.walletSession.signTransaction(txCore);
            }
        };
    }

    let cachedAuthSecret = '';
    let cachedAuthAddress = '';

    const WalletAuth = {
        /**
         * Require unlocked wallet for mutations.
         * Throws error codes: WALLET_NOT_CONNECTED, WALLET_LOCKED, UNLOCK_FAILED.
         */
        async requireUnlockedWallet() {
            const address = getActiveWalletAddress();
            if (!address) {
                const err = new Error('Wallet not connected. Please connect your wallet first.');
                err.code = 'WALLET_NOT_CONNECTED';
                throw err;
            }

            const credentialLookupAddress = getCredentialLookupAddress(address);
            logAuthDiagnostics(address);

            // Check if wallet is already unlocked in this tab for this address
            if (window.walletSession && typeof window.walletSession.isUnlockedFor === 'function' && window.walletSession.isUnlockedFor(address)) {
                // Wallet is unlocked - return signing context without prompting
                const storedSecret = getSigningMaterial(address);
                if (storedSecret) {
                    cachedAuthSecret = storedSecret;
                    cachedAuthAddress = address;
                    return buildAuthResult(address, storedSecret, credentialLookupAddress);
                }
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

            const pin = prompt('🔐 PIN (unlock wallet):');
            if (!pin) {
                const err = new Error('Wallet is locked. Please unlock with your PIN.');
                err.code = 'WALLET_LOCKED';
                throw err;
            }

            if (window.walletSession && typeof window.walletSession.unlockWallet === 'function') {
                try {
                    const ok = await window.walletSession.unlockWallet({ pin, address });
                    if (!ok) throw missingSigningMaterialError();

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

                    const authSecret = getSigningMaterial(address);
                    cachedAuthSecret = authSecret;
                    cachedAuthAddress = address;
                    return buildAuthResult(address, authSecret, credentialLookupAddress);
                } catch (e) {
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
                    const authSecret = getSigningMaterial(address);
                    cachedAuthSecret = authSecret;
                    cachedAuthAddress = address;
                    return buildAuthResult(address, authSecret, credentialLookupAddress);
                } catch (e) {
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
            return !!(cachedAuthSecret || getSigningMaterial(address));
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
            sessionStorage.removeItem('thr_auth_secret');
            sessionStorage.removeItem('thr_auth_secret_address');
            if (window.walletSession && typeof window.walletSession.lockWallet === 'function') {
                window.walletSession.lockWallet();
            }
        }
    };

    window.WalletAuth = WalletAuth;

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
        WalletAuth.requireUnlockedWallet = async function() {
            const result = await originalRequire.call(this);
            WalletAuth.startAutoLock();
            return result;
        };

        console.log('[WalletAuth] Auto-lock initialized');
    }
})(window);