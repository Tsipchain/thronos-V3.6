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
     * Make an API request
     * @param {string} endpoint - API endpoint
     * @param {object} options - Fetch options
     * @returns {Promise<any>}
     * @private
     */
    async request(endpoint, options = {}) {
        const url = `${this.apiUrl}${endpoint}`;

        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        };

        try {
            const response = await fetch(url, { ...defaultOptions, ...options });

            if (!response.ok) {
                const error = await response.json().catch(() => ({ error: 'Request failed' }));
                throw new Error(error.error || `Request failed with status ${response.status}`);
            }

            return await response.json();
        } catch (error) {
            throw new Error(`API request failed: ${error.message}`);
        }
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
        return await this.request('/api/wallet/send', {
            method: 'POST',
            body: JSON.stringify(transaction)
        });
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
}
