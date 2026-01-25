/* Thronos Fetch Utils - API path normalizer + safe fetch wrapper */
(function () {
  // Keep native fetch safe (avoid recursion)
  const NATIVE_FETCH = window.fetch ? window.fetch.bind(window) : null;
  if (!NATIVE_FETCH) {
    console.error("[fetch_utils] Native fetch missing");
    return;
  }

  // Optional: force API base (useful if frontend is on Vercel and API on Railway)
  // Example: window.THRONOS_API_BASE = "https://thrchain.up.railway.app";
  function getApiBase() {
    const base = window.THRONOS_API_BASE || "";
    return String(base).replace(/\/+$/, "");
  }

  function isProbablyApiPath(p) {
    if (!p) return false;
    return (
      p.startsWith("/api/") ||
      p.startsWith("api/") ||
      p.includes("/api/v1/") ||
      p.includes("/api/v1/read/") ||
      p.includes("/api/v1/write/")
    );
  }

  function extractPathQuery(u) {
    if (typeof u !== "string") return u;
    const s = u.trim();

    // If absolute URL, normalize only if it looks like Thronos API URL
    if (/^https?:\/\//i.test(s)) {
      try {
        const url = new URL(s);
        const pq = url.pathname + url.search;
        return isProbablyApiPath(url.pathname) ? pq : s;
      } catch {
        return s;
      }
    }

    return s;
  }

  // Normalize all legacy prefixes -> canonical /api/...
  function normalizeApiPath(input) {
    if (!input) return input;

    let p = extractPathQuery(input);
    if (typeof p !== "string") return p;

    // allow "api/..." without leading slash
    if (p.startsWith("api/")) p = "/" + p;

    if (!isProbablyApiPath(p)) return p;

    // Hard normalize multiple nested prefixes
    // Examples fixed:
    // /api/v1/read/api/dashboard  -> /api/dashboard
    // /api/v1/write/api/music/... -> /api/music/...
    // /api/v1/read/api/v1/read/api/balances -> /api/balances
    // /api/api/token/prices -> /api/token/prices
    const rules = [
      [/^\/api\/v1\/read\/api\//, "/api/"],
      [/^\/api\/v1\/write\/api\//, "/api/"],
      [/^\/api\/v1\/read\//, "/"],
      [/^\/api\/v1\/write\//, "/"],
      [/^\/api\/api\//, "/api/"],
    ];

    // Apply repeatedly until stable
    let changed = true;
    while (changed) {
      changed = false;
      for (const [re, rep] of rules) {
        if (re.test(p)) {
          p = p.replace(re, rep);
          changed = true;
        }
      }
      // If someone accidentally produced .../api/v1/read/api/... inside again
      p = p.replace(/\/api\/v1\/read\/api\//g, "/api/");
      p = p.replace(/\/api\/v1\/write\/api\//g, "/api/");
      p = p.replace(/\/api\/api\//g, "/api/");
    }

    return p;
  }

  function buildApiUrl(urlLike) {
    if (typeof urlLike !== "string") return urlLike;

    const normalized = normalizeApiPath(urlLike);

    // If normalized is still absolute url, keep it
    if (/^https?:\/\//i.test(normalized)) return normalized;

    const base = getApiBase();
    if (!base) return normalized; // same-origin

    // If base exists, always target it (cross-domain safe)
    if (normalized.startsWith("/")) return base + normalized;
    return base + "/" + normalized;
  }

  function mediaUrl(u) {
    if (!u) return "";
    let s = String(u);

    try {
      if (s.startsWith("http://") || s.startsWith("https://")) {
        const parsed = new URL(s);
        s = parsed.pathname;
      }
    } catch {}

    if (!s.startsWith("/")) s = "/" + s;

    if (s.startsWith("/static/nft_images/")) {
      const fname = s.split("/").pop();
      s = `/media/nft_images/${fname}`;
    }
    if (s.startsWith("/static/token_logos/")) {
      const fname = s.split("/").pop();
      s = `/media/token_logos/${fname}`;
    }

    return `${window.location.origin}${s}`;
  }

  async function smartFetch(url, options) {
    const finalUrl = buildApiUrl(typeof url === "string" ? url : (url?.url || url));
    return NATIVE_FETCH(finalUrl, options);
  }

  async function smartFetchJSON(url, options = {}) {
    const res = await smartFetch(url, options);
    const text = await res.text().catch(() => "");
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = text;
    }

    if (!res.ok) {
      const err = new Error((data && data.error) || "request_failed");
      err.status = res.status;
      err.payload = data;
      throw err;
    }
    return data;
  }

  const _onceCache = new Map();
  function fetchJSONOnce(url, options = {}) {
    const key = (typeof url === "string" ? url : JSON.stringify(url)) + "|" + JSON.stringify(options || {});
    if (_onceCache.has(key)) return _onceCache.get(key);
    const p = smartFetchJSON(url, options).finally(() => _onceCache.delete(key));
    _onceCache.set(key, p);
    return p;
  }

  window.FetchUtils = {
    normalizeApiPath,
    buildApiUrl,
    mediaUrl,
    smartFetch,
    smartFetchJSON,
    fetchJSONOnce,
  };

  // Optional: overwrite global fetch to auto-fix legacy calls everywhere
  window.__thronos_native_fetch = NATIVE_FETCH;
  window.fetch = smartFetch;

  console.log("✓ fetch_utils loaded (API prefix normalizer active)");
})();
