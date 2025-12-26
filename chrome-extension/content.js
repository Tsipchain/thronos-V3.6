// Content script for Thronos Wallet Extension
// Injects wallet functionality into web pages

(function() {
    'use strict';

    // Inject Thronos provider into page
    const script = document.createElement('script');
    script.textContent = `
        (function() {
            // Thronos Wallet Provider
            window.thronos = {
                version: '1.0.0',
                isThronos: true,
                isConnected: false,
                address: null,

                // Request wallet connection
                async connect() {
                    return new Promise((resolve, reject) => {
                        window.postMessage({
                            type: 'THRONOS_CONNECT_REQUEST',
                            source: 'thronos-page'
                        }, '*');

                        const handleResponse = (event) => {
                            if (event.data.type === 'THRONOS_CONNECT_RESPONSE') {
                                window.removeEventListener('message', handleResponse);
                                if (event.data.success) {
                                    this.isConnected = true;
                                    this.address = event.data.address;
                                    resolve(event.data);
                                } else {
                                    reject(new Error('Connection failed'));
                                }
                            }
                        };

                        window.addEventListener('message', handleResponse);

                        // Timeout after 10 seconds
                        setTimeout(() => {
                            window.removeEventListener('message', handleResponse);
                            reject(new Error('Connection timeout'));
                        }, 10000);
                    });
                },

                // Disconnect wallet
                async disconnect() {
                    return new Promise((resolve) => {
                        window.postMessage({
                            type: 'THRONOS_DISCONNECT_REQUEST',
                            source: 'thronos-page'
                        }, '*');

                        this.isConnected = false;
                        this.address = null;
                        resolve({ success: true });
                    });
                },

                // Get wallet address
                async getAddress() {
                    if (!this.isConnected) {
                        throw new Error('Wallet not connected');
                    }
                    return this.address;
                },

                // Sign transaction
                async signTransaction(transaction) {
                    if (!this.isConnected) {
                        throw new Error('Wallet not connected');
                    }

                    return new Promise((resolve, reject) => {
                        window.postMessage({
                            type: 'THRONOS_SIGN_REQUEST',
                            source: 'thronos-page',
                            transaction: transaction
                        }, '*');

                        const handleResponse = (event) => {
                            if (event.data.type === 'THRONOS_SIGN_RESPONSE') {
                                window.removeEventListener('message', handleResponse);
                                if (event.data.success) {
                                    resolve(event.data.signature);
                                } else {
                                    reject(new Error('Signature rejected'));
                                }
                            }
                        };

                        window.addEventListener('message', handleResponse);

                        setTimeout(() => {
                            window.removeEventListener('message', handleResponse);
                            reject(new Error('Signature timeout'));
                        }, 30000);
                    });
                },

                // Send transaction
                async sendTransaction(to, amount, token = 'THR') {
                    if (!this.isConnected) {
                        throw new Error('Wallet not connected');
                    }

                    return new Promise((resolve, reject) => {
                        window.postMessage({
                            type: 'THRONOS_SEND_REQUEST',
                            source: 'thronos-page',
                            to: to,
                            amount: amount,
                            token: token
                        }, '*');

                        const handleResponse = (event) => {
                            if (event.data.type === 'THRONOS_SEND_RESPONSE') {
                                window.removeEventListener('message', handleResponse);
                                if (event.data.success) {
                                    resolve(event.data);
                                } else {
                                    reject(new Error(event.data.error || 'Transaction failed'));
                                }
                            }
                        };

                        window.addEventListener('message', handleResponse);

                        setTimeout(() => {
                            window.removeEventListener('message', handleResponse);
                            reject(new Error('Transaction timeout'));
                        }, 30000);
                    });
                },

                // Get balance
                async getBalance(token = 'THR') {
                    if (!this.isConnected) {
                        throw new Error('Wallet not connected');
                    }

                    return new Promise((resolve, reject) => {
                        window.postMessage({
                            type: 'THRONOS_BALANCE_REQUEST',
                            source: 'thronos-page',
                            token: token
                        }, '*');

                        const handleResponse = (event) => {
                            if (event.data.type === 'THRONOS_BALANCE_RESPONSE') {
                                window.removeEventListener('message', handleResponse);
                                if (event.data.success) {
                                    resolve(event.data.balance);
                                } else {
                                    reject(new Error('Failed to get balance'));
                                }
                            }
                        };

                        window.addEventListener('message', handleResponse);

                        setTimeout(() => {
                            window.removeEventListener('message', handleResponse);
                            reject(new Error('Balance request timeout'));
                        }, 10000);
                    });
                }
            };

            // Dispatch ready event
            window.dispatchEvent(new Event('thronos#initialized'));

            console.log('Thronos Wallet Provider initialized');
        })();
    `;

    (document.head || document.documentElement).appendChild(script);
    script.remove();

    // Listen for messages from page
    window.addEventListener('message', async (event) => {
        if (event.source !== window || !event.data.source === 'thronos-page') {
            return;
        }

        const { type } = event.data;

        if (type === 'THRONOS_CONNECT_REQUEST') {
            // Request wallet info from extension
            chrome.runtime.sendMessage({ action: 'getWallet' }, (response) => {
                window.postMessage({
                    type: 'THRONOS_CONNECT_RESPONSE',
                    success: response.connected,
                    address: response.address
                }, '*');
            });
        }

        if (type === 'THRONOS_DISCONNECT_REQUEST') {
            chrome.runtime.sendMessage({ action: 'disconnect' }, (response) => {
                window.postMessage({
                    type: 'THRONOS_DISCONNECT_RESPONSE',
                    success: true
                }, '*');
            });
        }

        if (type === 'THRONOS_SEND_REQUEST') {
            const { to, amount, token } = event.data;

            // Get wallet credentials
            chrome.runtime.sendMessage({ action: 'getWallet' }, async (wallet) => {
                if (!wallet.connected) {
                    window.postMessage({
                        type: 'THRONOS_SEND_RESPONSE',
                        success: false,
                        error: 'Wallet not connected'
                    }, '*');
                    return;
                }

                try {
                    const response = await fetch('http://localhost:5000/api/wallet/send', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            from: wallet.address,
                            to: to,
                            amount: amount,
                            token: token,
                            secret: wallet.secret
                        })
                    });

                    if (!response.ok) throw new Error('Transaction failed');

                    const result = await response.json();

                    window.postMessage({
                        type: 'THRONOS_SEND_RESPONSE',
                        success: true,
                        transaction: result
                    }, '*');
                } catch (error) {
                    window.postMessage({
                        type: 'THRONOS_SEND_RESPONSE',
                        success: false,
                        error: error.message
                    }, '*');
                }
            });
        }

        if (type === 'THRONOS_BALANCE_REQUEST') {
            const { token } = event.data;

            chrome.runtime.sendMessage({ action: 'getWallet' }, async (wallet) => {
                if (!wallet.connected) {
                    window.postMessage({
                        type: 'THRONOS_BALANCE_RESPONSE',
                        success: false
                    }, '*');
                    return;
                }

                try {
                    const response = await fetch(`http://localhost:5000/api/wallet/tokens/${wallet.address}?show_zero=false`);
                    if (!response.ok) throw new Error('Failed to get balance');

                    const data = await response.json();
                    const tokenData = data.tokens.find(t => t.symbol === token);

                    window.postMessage({
                        type: 'THRONOS_BALANCE_RESPONSE',
                        success: true,
                        balance: tokenData ? tokenData.balance : 0
                    }, '*');
                } catch (error) {
                    window.postMessage({
                        type: 'THRONOS_BALANCE_RESPONSE',
                        success: false
                    }, '*');
                }
            });
        }
    });

    console.log('Thronos Wallet content script loaded');
})();
