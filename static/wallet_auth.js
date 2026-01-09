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
            const storedSecret = localStorage.getItem('thr_secret');
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
            if (window.walletSession && typeof window.walletSession.unlockWithPin === 'function') {
                try {
                    const authSecret = await window.walletSession.unlockWithPin(pin);
                    if (!authSecret) throw new Error('Invalid PIN');

                    sessionStorage.setItem('thr_auth_secret', authSecret);
                    return { address, authSecret };
                } catch (e) {
                    const err = new Error('Failed to unlock wallet: ' + e.message);
                    err.code = 'UNLOCK_FAILED';
                    throw err;
                }
            }

            // Fallback: basic PIN verification (if walletSession not available)
            // This assumes PIN is stored as wallet_pin in localStorage
            const storedPin = localStorage.getItem('wallet_pin');
            if (storedPin === pin) {
                // In production, you'd decrypt the secret here
                // For now, we'll return an error asking to reconnect
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
                localStorage.getItem('thr_secret')
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
         * Lock wallet (clear session secret)
         */
        lock() {
            sessionStorage.removeItem('thr_auth_secret');
        }
    };

    // Export to window
    window.WalletAuth = WalletAuth;

})(window);
