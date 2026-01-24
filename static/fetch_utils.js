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
        return window.location.hostname.endsWith('vercel.app');
    }

    function normalizeApiPath(path) {
        if (!path) return '/api/health';
        let p = String(path).trim();

        try {
            if (/^https?:\/\//i.test(p)) {
                const url = new URL(p);
                p = url.pathname + (url.search || '');
            }
        } catch (_) {
            // Ignore URL parsing failures.
        }

        if (!p.startsWith('/')) p = `/${p}`;

        while (/^\/(api\/v1\/(read|write)|v1\/(read|write))\//.test(p)) {
            p = p.replace(/^\/api\/v1\/(read|write)\//, '/');
            p = p.replace(/^\/v1\/(read|write)\//, '/');
        }
        p = p.replace(/\/{2,}/g, '/');

        if (!p.startsWith('/api/')) {
            p = `/api${p}`;
        }

        p = p.replace(/^\/api\/api\//, '/api/');

        return p;
    }

    function getReadBase() {
        return isVercelHost() ? '/api/v1/read' : '';
    }

    function getWriteBase() {
        return isVercelHost() ? '/api/v1/write' : '';
    }

    function smartFetchRaw(path, opts = {}) {
        if (typeof path === 'string') {
            const trimmed = path.trim();
            if (/^https?:\/\//i.test(trimmed)) {
                return nativeFetch(trimmed, opts);
            }
            const lowered = trimmed.replace(/^\/+/, '').toLowerCase();
            if (lowered.startsWith('static/')
                || lowered.startsWith('media/')
                || lowered.startsWith('img/')
                || lowered.startsWith('assets/')
                || lowered.startsWith('favicon')
                || lowered.startsWith('robots.txt')) {
                return nativeFetch(trimmed, opts);
            }
        }
        const method = (opts.method || 'GET').toUpperCase();
        const apiPath = normalizeApiPath(path);
        const base = method === 'GET' ? getReadBase() : getWriteBase();
        const url = `${base}${apiPath}`;

        return nativeFetch(url, {
            credentials: 'include',
            ...opts,
            headers: {
                'Content-Type': 'application/json',
                ...(opts.headers || {})
            }
        });
    }

    async function smartFetch(path, opts = {}) {
        const res = await smartFetchRaw(path, opts);

        const text = await res.text();
        let data = null;
        try {
            data = text ? JSON.parse(text) : null;
        } catch (_) {
            data = null;
        }

        if (!res.ok) {
            const err = (data && (data.error || data.message)) || `http_${res.status}`;
            const error = new Error(err);
            error.status = res.status;
            error.data = data;
            throw error;
        }

        return data;
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
