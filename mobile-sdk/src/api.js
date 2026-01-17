/**
 * Thronos API Client Module
 * Handles all API communication with Thronos Network
 */

export default class ThronosAPI {
    constructor(config) {
        this.config = config;
        this.apiUrl = config.apiUrl;
    }

    /**
     * Make an API request with retry logic
     * @param {string} endpoint - API endpoint
     * @param {object} options - Fetch options
     * @param {number} retries - Number of retry attempts
     * @returns {Promise<any>}
     * @private
     */
    async request(endpoint, options = {}, retries = 3) {
        const url = `${this.apiUrl}${endpoint}`;

        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        };

        let lastError;
        for (let attempt = 0; attempt <= retries; attempt++) {
            try {
                const response = await fetch(url, { ...defaultOptions, ...options });

                if (!response.ok) {
                    const error = await response.json().catch(() => ({ error: 'Request failed' }));
                    throw new Error(error.error || `Request failed with status ${response.status}`);
                }

                return await response.json();
            } catch (error) {
                lastError = error;
                // Only retry on network errors, not on API errors
                if (attempt < retries && error.message.includes('fetch')) {
                    // Exponential backoff: 1s, 2s, 4s
                    await new Promise(resolve => setTimeout(resolve, Math.pow(2, attempt) * 1000));
                    continue;
                }
                break;
            }
        }
        throw new Error(`API request failed: ${lastError.message}`);
    }

    /**
     * Get token balances for an address
     * @param {string} address - Wallet address
     * @param {boolean} showZero - Show tokens with zero balance
     * @returns {Promise<{address: string, tokens: Array, last_updated: string}>}
     */
    async getTokens(address, showZero = false) {
        return await this.request(`/api/wallet/tokens/${address}?show_zero=${showZero}`);
    }

    /**
     * Send a transaction
     * @param {object} transaction - Transaction details
     * @returns {Promise<{success: boolean, transaction: object}>}
     */
    async sendTransaction(transaction) {
        // Route based on token type
        const token = (transaction.token || 'THR').toUpperCase();

        if (token === 'THR') {
            // Native THR send
            return await this.request('/send_thr', {
                method: 'POST',
                body: JSON.stringify({
                    from_thr: transaction.from,
                    to_thr: transaction.to,
                    amount: transaction.amount,
                    auth_secret: transaction.secret,
                    speed: transaction.speed || 'fast',
                    passphrase: transaction.passphrase
                })
            });
        } else {
            // Custom token transfer (fee paid in THR)
            return await this.request('/api/tokens/transfer', {
                method: 'POST',
                body: JSON.stringify({
                    symbol: token,
                    from_thr: transaction.from,
                    to_thr: transaction.to,
                    amount: transaction.amount,
                    auth_secret: transaction.secret,
                    speed: transaction.speed || 'fast',
                    passphrase: transaction.passphrase
                })
            });
        }
    }

    /**
     * Send multiple tokens in batch
     * @param {object} batchDetails - Batch transfer details
     * @returns {Promise<{success: boolean, results: Array}>}
     */
    async sendMultipleTokens(batchDetails) {
        const results = [];
        const { from, transfers, secret, speed, passphrase } = batchDetails;

        for (const transfer of transfers) {
            try {
                const result = await this.sendTransaction({
                    from,
                    to: transfer.to,
                    amount: transfer.amount,
                    token: transfer.token || 'THR',
                    secret,
                    speed,
                    passphrase
                });
                results.push({ ...transfer, success: true, result });
            } catch (error) {
                results.push({ ...transfer, success: false, error: error.message });
            }
        }

        const allSuccess = results.every(r => r.success);
        return { success: allSuccess, results };
    }

    /**
     * Get all chain tokens
     * @returns {Promise<{tokens: Array}>}
     */
    async getChainTokens() {
        return await this.request('/api/tokens/list');
    }

    /**
     * Get token info by symbol
     * @param {string} symbol - Token symbol
     * @returns {Promise<object>}
     */
    async getTokenInfo(symbol) {
        const tokens = await this.getChainTokens();
        const token = tokens.tokens?.find(t => t.symbol.toUpperCase() === symbol.toUpperCase());
        if (!token) throw new Error(`Token ${symbol} not found`);
        return token;
    }

    /**
     * Get transaction history
     * @param {string} address - Wallet address
     * @param {number} limit - Number of transactions
     * @returns {Promise<Array>}
     */
    async getTransactionHistory(address, limit = 50) {
        return await this.request(`/api/transactions/${address}?limit=${limit}`);
    }

    /**
     * Get network status
     * @returns {Promise<object>}
     */
    async getNetworkStatus() {
        return await this.request('/api/network/status');
    }

    /**
     * Get token price
     * @param {string} symbol - Token symbol
     * @returns {Promise<{symbol: string, price: number, change_24h: number}>}
     */
    async getTokenPrice(symbol) {
        return await this.request(`/api/token/price/${symbol}`);
    }

    /**
     * Get swap quote
     * @param {string} fromToken - Source token symbol
     * @param {string} toToken - Destination token symbol
     * @param {number} amount - Amount to swap
     * @returns {Promise<{rate: number, amount_out: number, fee: number}>}
     */
    async getSwapQuote(fromToken, toToken, amount) {
        return await this.request(`/api/swap/quote?from=${fromToken}&to=${toToken}&amount=${amount}`);
    }

    /**
     * Execute a swap
     * @param {object} swapDetails - Swap details
     * @returns {Promise<{success: boolean, transaction: object}>}
     */
    async executeSwap(swapDetails) {
        return await this.request('/api/swap/execute', {
            method: 'POST',
            body: JSON.stringify(swapDetails)
        });
    }

    /**
     * Get pledge information
     * @param {string} address - Wallet address
     * @returns {Promise<{pledged_amount: number, rewards: number, apr: number}>}
     */
    async getPledgeInfo(address) {
        return await this.request(`/api/pledge/info/${address}`);
    }

    /**
     * Pledge tokens
     * @param {object} pledgeDetails - Pledge details
     * @returns {Promise<{success: boolean, transaction: object}>}
     */
    async pledgeTokens(pledgeDetails) {
        return await this.request('/api/pledge/stake', {
            method: 'POST',
            body: JSON.stringify(pledgeDetails)
        });
    }

    /**
     * Unpledge tokens
     * @param {object} unpledgeDetails - Unpledge details
     * @returns {Promise<{success: boolean, transaction: object}>}
     */
    async unpledgeTokens(unpledgeDetails) {
        return await this.request('/api/pledge/unstake', {
            method: 'POST',
            body: JSON.stringify(unpledgeDetails)
        });
    }

    /**
     * Get AI chat credits
     * @param {string} address - Wallet address
     * @returns {Promise<{credits: number, used: number, remaining: number}>}
     */
    async getAICredits(address) {
        return await this.request(`/api/ai/credits/${address}`);
    }

    /**
     * Send AI chat message
     * @param {object} messageDetails - Message details
     * @returns {Promise<{response: string, credits_used: number}>}
     */
    async sendAIMessage(messageDetails) {
        return await this.request('/api/ai/chat', {
            method: 'POST',
            body: JSON.stringify(messageDetails)
        });
    }

    /**
     * Get IoT node status
     * @param {string} nodeId - Node ID
     * @returns {Promise<object>}
     */
    async getIoTNodeStatus(nodeId) {
        return await this.request(`/api/iot/node/${nodeId}`);
    }

    /**
     * Register IoT node
     * @param {object} nodeDetails - Node details
     * @returns {Promise<{success: boolean, node_id: string}>}
     */
    async registerIoTNode(nodeDetails) {
        return await this.request('/api/iot/register', {
            method: 'POST',
            body: JSON.stringify(nodeDetails)
        });
    }

    /**
     * Get BTC bridge status
     * @returns {Promise<object>}
     */
    async getBridgeStatus() {
        return await this.request('/api/bridge/status');
    }

    /**
     * Bridge BTC to WBTC
     * @param {object} bridgeDetails - Bridge details
     * @returns {Promise<{success: boolean, transaction: object}>}
     */
    async bridgeBTC(bridgeDetails) {
        return await this.request('/api/bridge/btc-to-wbtc', {
            method: 'POST',
            body: JSON.stringify(bridgeDetails)
        });
    }

    /**
     * Bridge WBTC to BTC
     * @param {object} bridgeDetails - Bridge details
     * @returns {Promise<{success: boolean, transaction: object}>}
     */
    async bridgeWBTC(bridgeDetails) {
        return await this.request('/api/bridge/wbtc-to-btc', {
            method: 'POST',
            body: JSON.stringify(bridgeDetails)
        });
    }

    /**
     * Get smart contract details
     * @param {string} contractAddress - Contract address
     * @returns {Promise<object>}
     */
    async getContract(contractAddress) {
        return await this.request(`/api/evm/contract/${contractAddress}`);
    }

    /**
     * Deploy smart contract
     * @param {object} contractDetails - Contract details
     * @returns {Promise<{success: boolean, contract_address: string}>}
     */
    async deployContract(contractDetails) {
        return await this.request('/api/evm/deploy', {
            method: 'POST',
            body: JSON.stringify(contractDetails)
        });
    }

    /**
     * Call smart contract method
     * @param {object} callDetails - Call details
     * @returns {Promise<{success: boolean, result: any}>}
     */
    async callContract(callDetails) {
        return await this.request('/api/evm/call', {
            method: 'POST',
            body: JSON.stringify(callDetails)
        });
    }

    /**
     * Get music tracks
     * @param {object} filters - Optional filters (genre, artist, etc.)
     * @returns {Promise<{tracks: Array}>}
     */
    async getMusicTracks(filters = {}) {
        const params = new URLSearchParams(filters).toString();
        return await this.request(`/api/music/tracks${params ? '?' + params : ''}`);
    }

    /**
     * Send music tip to artist
     * @param {string} artistAddress - Artist's THR address
     * @param {number} amount - Tip amount in THR
     * @param {string} trackId - Track ID
     * @returns {Promise<{success: boolean, transaction: object}>}
     */
    async sendMusicTip(artistAddress, amount, trackId) {
        return await this.request('/api/music/tip', {
            method: 'POST',
            body: JSON.stringify({
                artist: artistAddress,
                amount: amount,
                track_id: trackId
            })
        });
    }

    /**
     * Record music stream telemetry
     * @param {object} telemetryData - Stream data (track_id, duration, location, etc.)
     * @returns {Promise<{success: boolean}>}
     */
    async recordMusicTelemetry(telemetryData) {
        return await this.request('/api/music/telemetry', {
            method: 'POST',
            body: JSON.stringify(telemetryData)
        });
    }

    /**
     * Generate WhisperNote audio from transaction data
     * @param {object} txData - Transaction data to encode
     * @param {number} frequency - Audio frequency (1000-4000 Hz)
     * @returns {Promise<{success: boolean, audio_url: string}>}
     */
    async generateWhisperNote(txData, frequency = 2000) {
        return await this.request('/api/music/whispernote', {
            method: 'POST',
            body: JSON.stringify({
                data: txData,
                frequency: frequency
            })
        });
    }

    /**
     * Get GPS telemetry data
     * @param {object} location - GPS coordinates {lat, lng, speed, heading}
     * @returns {Promise<{success: boolean}>}
     */
    async sendGPSTelemetry(location) {
        return await this.request('/api/iot/telemetry', {
            method: 'POST',
            body: JSON.stringify({
                type: 'gps',
                lat: location.lat,
                lng: location.lng,
                speed: location.speed || 0,
                heading: location.heading || 0,
                timestamp: new Date().toISOString()
            })
        });
    }

    /**
     * Get transaction history with category filtering
     * @param {string} address - Wallet address
     * @param {string} category - Category filter (mining, liquidity, gateway, music, etc.)
     * @param {number} limit - Number of transactions
     * @returns {Promise<{transactions: Array}>}
     */
    async getTransactionsByCategory(address, category = 'all', limit = 50) {
        return await this.request(`/wallet_data/${address}?category=${category}&limit=${limit}`);
    }
}
