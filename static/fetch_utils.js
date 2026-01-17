/**
 * PR-5a: Fetch Utilities - Request coalescing and visibility gating
 *
 * Prevents duplicate in-flight requests and manages polling lifecycle
 */

(function(window) {
    'use strict';

    // In-flight request tracking
    const inflightRequests = new Map();

    const nativeFetch = window.fetch.bind(window);
    const node1Base = (window.TH_NODE1_RPC_URL || window.location.origin || '').replace(/\/$/, '');
    const node2Base = (window.TH_NODE2_RPC_URL || node1Base || window.location.origin || '').replace(/\/$/, '');

    function shouldRouteRpc(url) {
        if (typeof url !== 'string') return false;
        if (!url.startsWith('/api/')) return false;
        return true;
    }

    function resolveRpcUrl(url, method) {
        if (!shouldRouteRpc(url)) return url;
        const upper = (method || 'GET').toUpperCase();
        const base = (upper === 'GET' || upper === 'HEAD') ? node2Base : node1Base;
        if (!base) return url;
        return `${base}${url}`;
    }

    function smartFetch(url, opts = {}) {
        if (typeof url === 'string') {
            const resolved = resolveRpcUrl(url, opts.method);
            return nativeFetch(resolved, opts);
        }
        return nativeFetch(url, opts);
    }

    /**
     * Fetch JSON with automatic coalescing of identical requests
     * @param {string} url - The URL to fetch
     * @param {object} opts - Fetch options
     * @returns {Promise<any>}
     */
    async function fetchJSONOnce(url, opts = {}) {
        const method = opts.method || 'GET';
        const resolvedUrl = resolveRpcUrl(url, method);
        const key = `${method}:${resolvedUrl}`;

        // Return existing in-flight request if any
        if (inflightRequests.has(key)) {
            return inflightRequests.get(key);
        }

        // Create new request
        const promise = smartFetch(resolvedUrl, opts)
            .then(response => response.json())
            .finally(() => {
                // Clean up after request completes
                inflightRequests.delete(key);
            });

        inflightRequests.set(key, promise);
        return promise;
    }

    /**
     * Visibility-gated interval manager
     * Runs callback only when page is visible
     */
    class VisibilityGatedInterval {
        constructor(callback, interval) {
            this.callback = callback;
            this.interval = interval;
            this.intervalId = null;
            this.isRunning = false;

            // Bind visibility change handler
            this.handleVisibilityChange = this.handleVisibilityChange.bind(this);
        }

        start() {
            if (this.isRunning) return;
            this.isRunning = true;

            // Add visibility change listener
            document.addEventListener('visibilitychange', this.handleVisibilityChange);

            // Start interval if page is visible
            if (!document.hidden) {
                this.startInterval();
            }
        }

        stop() {
            this.isRunning = false;
            this.stopInterval();
            document.removeEventListener('visibilitychange', this.handleVisibilityChange);
        }

        handleVisibilityChange() {
            if (document.hidden) {
                this.stopInterval();
            } else if (this.isRunning) {
                this.startInterval();
            }
        }

        startInterval() {
            if (this.intervalId) return;
            this.intervalId = setInterval(this.callback, this.interval);
        }

        stopInterval() {
            if (this.intervalId) {
                clearInterval(this.intervalId);
                this.intervalId = null;
            }
        }
    }

    /**
     * Check if popup/modal is currently visible
     * @param {string} elementId - ID of the popup element
     * @returns {boolean}
     */
    function isPopupVisible(elementId) {
        const el = document.getElementById(elementId);
        if (!el) return false;

        // Check if element is visible
        const style = window.getComputedStyle(el);
        if (style.display === 'none') return false;
        if (style.visibility === 'hidden') return false;
        if (style.opacity === '0') return false;

        // Check if element has 'active' class (common pattern)
        if (el.classList.contains('active')) return true;

        // Check if element has actual dimensions
        return el.offsetWidth > 0 && el.offsetHeight > 0;
    }

    // Export to window
    window.FetchUtils = {
        fetchJSONOnce,
        smartFetch,
        VisibilityGatedInterval,
        isPopupVisible
    };

    if (!window.__thronosSmartFetchInstalled) {
        window.fetch = smartFetch;
        window.__thronosSmartFetchInstalled = true;
    }

})(window);
