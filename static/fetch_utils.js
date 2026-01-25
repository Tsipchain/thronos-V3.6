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

    function isVercelHost() {
        return window.location.hostname.endsWith('.vercel.app');
    }

    function isAssetPath(path) {
        if (!path) return false;
        const lowered = path.replace(/^\/+/, '').toLowerCase();
        return lowered.startsWith('static/')
            || lowered.startsWith('media/')
            || lowered.startsWith('img/')
            || lowered.startsWith('assets/')
            || lowered.startsWith('favicon')
            || lowered.startsWith('robots.txt');
    }

    function normalizeApiPath(path) {
        if (!path) return '';
        let p = String(path).trim();

        p = p.replace(/^https?:\/\/[^/]+/i, '');

        if (!p.startsWith('/')) p = `/${p}`;

        p = p.replace(/^\/api\/v1\/read\/api\/v1\/read\//, '/');
        p = p.replace(/^\/api\/v1\/read\/api\/v1\/write\//, '/');
        p = p.replace(/^\/api\/v1\/read\/api\/v1\/music\//, '/api/music/');

        p = p.replace(/^\/api\/v1\/read\//, '/');
        p = p.replace(/^\/api\/v1\/write\//, '/');
        p = p.replace(/^\/api\/v1\/music\//, '/api/music/');

        return p;
    }

    function buildApiUrl(path, method) {
        const p = normalizeApiPath(path);
        const host = (window.location.hostname || '').toLowerCase();
        const isVercel = host.endsWith('.vercel.app');

        if (!isVercel) return p;

        const m = (method || 'GET').toUpperCase();

        if (p.startsWith('/api/music/')) {
            return `/api/v1/music/${p.slice('/api/music/'.length)}`;
        }

        const prefix = (m === 'GET') ? '/api/v1/read' : '/api/v1/write';
        return `${prefix}${p}`;
    }

    function smartFetch(path, opts = {}) {
        if (typeof path === 'string') {
            const trimmed = path.trim();
            if (/^https?:\/\//i.test(trimmed) || isAssetPath(trimmed)) {
                return nativeFetch(trimmed, opts);
            }
        }

        const method = (opts.method || 'GET').toUpperCase();
        const url = buildApiUrl(path, method);

        return nativeFetch(url, {
            ...opts,
            method
        });
    }

    /**
     * Fetch JSON with automatic coalescing of identical requests
     * @param {string} url - The URL to fetch
     * @param {object} opts - Fetch options
     * @returns {Promise<any>}
     */
    async function fetchJSONOnce(url, opts = {}) {
        const method = (opts.method || 'GET').toUpperCase();
        const key = `${method}:${normalizeApiPath(url)}`;

        // Return existing in-flight request if any
        if (inflightRequests.has(key)) {
            return inflightRequests.get(key);
        }

        // Create new request
        const promise = smartFetch(url, { ...opts, method })
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
        smartFetchRaw,
        VisibilityGatedInterval,
        isPopupVisible
    };

    if (!window.__thronosSmartFetchInstalled) {
        window.fetch = smartFetchRaw;
        window.__thronosSmartFetchInstalled = true;
    }

})(window);
