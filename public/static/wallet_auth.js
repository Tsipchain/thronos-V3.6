/**
 * PR-5a: Wallet Authentication Helper
 *
 * Provides PIN-based unlock for music mutations (tips, playlists).
 * Never prompts for auth_secret - uses session-based unlock.
 */

(function(window) {
    'use strict';

    const WalletAuth = {
        /**
         * Require unlocked wallet for mutations.
         * Throws error codes: WALLET_NOT_CONNECTED, WALLET_LOCKED, UNLOCK_FAILED
         *
         * @returns {Promise<{address: string, authSecret: string}>}
         */
        async requireUnlockedWallet() {
            // Check if wallet is connected
            const address = localStorage.getItem('thr_address');
            if (!address) {
                const err = new Error('Wallet not connected. Please connect your wallet first.');
                err.code = 'WALLET_NOT_CONNECTED';
                throw err;
            }

            // Check if already unlocked this session
            const cachedSecret = sessionStorage.getItem('thr_auth_secret');
            if (cachedSecret) {
                return { address, authSecret: cachedSecret };
            }

            // Check if secret is in localStorage (wallet unlocked)
            // walletSession stores under send_secret / send_seed / thr_secret
            const storedSecret = (window.walletSession && typeof window.walletSession.getSendSeed === 'function')
                ? window.walletSession.getSendSeed()
                : (localStorage.getItem('send_secret') || localStorage.getItem('send_seed') || localStorage.getItem('thr_secret'));
            if (storedSecret) {
                // Cache in session for this tab
                sessionStorage.setItem('thr_auth_secret', storedSecret);
                return { address, authSecret: storedSecret };
            }

            // Wallet is locked - ask for PIN
            const pin = prompt('🔐 PIN (unlock wallet):');
            if (!pin) {
                const err = new Error('Wallet is locked. Please unlock with your PIN.');
                err.code = 'WALLET_LOCKED';
                throw err;
            }

            // Use existing walletSession unlock if available
            if (window.walletSession && typeof window.walletSession.unlockWallet === 'function') {
                try {
                    const ok = await window.walletSession.unlockWallet({ pin });
                    if (!ok) throw new Error('Invalid PIN');
                    // After unlock, retrieve the seed from walletSession
                    const authSecret = window.walletSession.getSendSeed();
                    if (!authSecret) throw new Error('No send seed found after unlock');

                    sessionStorage.setItem('thr_auth_secret', authSecret);
                    return { address, authSecret };
                } catch (e) {
                    const err = new Error('Failed to unlock wallet: ' + e.message);
                    err.code = 'UNLOCK_FAILED';
                    throw err;
                }
            }

            // Fallback: basic PIN verification (if walletSession not available)
            const storedPin = localStorage.getItem('wallet_pin');
            if (storedPin === pin) {
                // PIN matched - retrieve secret from all possible storage keys
                const authSecret = localStorage.getItem('send_secret')
                    || localStorage.getItem('send_seed')
                    || localStorage.getItem('thr_secret');
                if (authSecret) {
                    sessionStorage.setItem('thr_auth_secret', authSecret);
                    return { address, authSecret };
                }
                const err = new Error('Please reconnect your wallet with secret to enable mutations.');
                err.code = 'UNLOCK_FAILED';
                throw err;
            } else {
                const err = new Error('Invalid PIN. Please try again.');
                err.code = 'UNLOCK_FAILED';
                throw err;
            }
        },

        /**
         * Check if wallet is currently unlocked (without prompting)
         * @returns {boolean}
         */
        isUnlocked() {
            return !!(
                sessionStorage.getItem('thr_auth_secret') ||
                (window.walletSession && typeof window.walletSession.getSendSeed === 'function'
                    ? window.walletSession.getSendSeed()
                    : (localStorage.getItem('send_secret') || localStorage.getItem('send_seed') || localStorage.getItem('thr_secret')))
            );
        },

        /**
         * Get address if connected (without auth check)
         * @returns {string|null}
         */
        getAddress() {
            return localStorage.getItem('thr_address') || null;
        },

        /**
         * PR-5g: Auto-lock timer
         */
        _autoLockTimer: null,
        _autoLockTimeout: 5 * 60 * 1000, // 5 minutes default

        /**
         * Start auto-lock timer
         */
        startAutoLock(timeoutMs = null) {
            this.stopAutoLock(); // Clear any existing timer

            const timeout = timeoutMs || this._autoLockTimeout;

            this._autoLockTimer = setTimeout(() => {
                console.log('[WalletAuth] Auto-locking wallet after inactivity');
                this.lock();

                // Show notification if in browser
                if (typeof showToast === 'function') {
                    showToast('Wallet locked due to inactivity');
                }
            }, timeout);

            console.log(`[WalletAuth] Auto-lock timer started (${timeout / 1000}s)`);
        },

        /**
         * Stop auto-lock timer
         */
        stopAutoLock() {
            if (this._autoLockTimer) {
                clearTimeout(this._autoLockTimer);
                this._autoLockTimer = null;
            }
        },

        /**
         * Reset auto-lock timer (call on user activity)
         */
        resetAutoLock() {
            if (this.isUnlocked()) {
                this.startAutoLock();
            }
        },

        /**
         * Lock wallet (clear session secret)
         */
        lock() {
            sessionStorage.removeItem('thr_auth_secret');
        }
    };

    // Export to window
    window.WalletAuth = WalletAuth;

    // PR-5g: Setup auto-lock on page load
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAutoLock);
    } else {
        initAutoLock();
    }

    function initAutoLock() {
        // Start auto-lock if wallet is unlocked
        if (WalletAuth.isUnlocked()) {
            WalletAuth.startAutoLock();
        }

        // Reset timer on user activity
        const activityEvents = ['mousedown', 'keypress', 'scroll', 'touchstart', 'click'];
        activityEvents.forEach(eventType => {
            document.addEventListener(eventType, () => {
                WalletAuth.resetAutoLock();
            }, { passive: true });
        });

        // Also reset on wallet operations
        const originalRequire = WalletAuth.requireUnlockedWallet;
        WalletAuth.requireUnlockedWallet = async function() {
            const result = await originalRequire.call(this);
            // Start auto-lock after successful unlock
            WalletAuth.startAutoLock();
            return result;
        };

        console.log('[WalletAuth] Auto-lock initialized');
    }

})(window);
