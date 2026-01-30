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
    const base = window.__API_BASE__ || window.THRONOS_API_BASE || "";
    return String(base).replace(/\/+$/, "");
  }

  function isProbablyApiPath(p) {
    if (!p) return false;
    return (
      p.startsWith("/api/") ||
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

    try {
      const raw = String(input);
      const u = new URL(raw, window.location.origin);
      let path = u.pathname || "";

      // Ensure all paths start with "/"
      if (!path.startsWith("/")) path = "/" + path;
      // Auto-correct "api/" to "/api/" for consistency (hard rule: all API paths must be absolute)
      if (path.startsWith("/api/") === false && path.includes("api/")) {
        path = path.replace(/^\/(.*)api\//, "/api/");
      }

      if (!isProbablyApiPath(path)) {
        if (/^https?:\/\//i.test(raw)) {
          return raw;
        }
        return path + (u.search || "") + (u.hash || "");
      }

      path = path.replace(/^\/api\/v1\/read\/api\//, "/api/");
      path = path.replace(/^\/api\/v1\/write\/api\//, "/api/");
      path = path.replace(/^\/api\/v1\/read\//, "/api/");
      path = path.replace(/^\/api\/v1\/write\//, "/api/");
      path = path.replace(/^\/api\/api\//, "/api/");
      path = path.replace(/^\/api\/v1\//, "/api/");

      if (!path.startsWith("/api/")) {
        path = `/api${path}`;
      }

      return path + (u.search || "") + (u.hash || "");
    } catch (e) {
      const m = String(input).match(/^([^?#]*)(\?[^#]*)?(#.*)?$/);
      let base = (m?.[1] || "").trim();
      const search = m?.[2] || "";
      const hash = m?.[3] || "";

      if (!base.startsWith("/")) base = "/" + base;
      if (base.startsWith("api/")) base = "/" + base;

      if (!isProbablyApiPath(base)) {
        return base + search + hash;
      }

      base = base.replace(/^\/api\/v1\/read\/api\//, "/api/");
      base = base.replace(/^\/api\/v1\/write\/api\//, "/api/");
      base = base.replace(/^\/api\/v1\/read\//, "/api/");
      base = base.replace(/^\/api\/v1\/write\//, "/api/");
      base = base.replace(/^\/api\/api\//, "/api/");
      base = base.replace(/^\/api\/v1\//, "/api/");

      if (!base.startsWith("/api/")) {
        base = `/api${base}`;
      }

      return base + search + hash;
    }
  }

  function buildApiUrl(urlLike) {
    if (typeof urlLike !== "string") return urlLike;

    const normalized = normalizeApiPath(urlLike);

    // If normalized is still absolute url, keep it
    if (/^https?:\/\//i.test(normalized)) return normalized;

    if (!normalized.startsWith("/api/")) return normalized;

    const base = getApiBase();
    if (!base) return normalized; // same-origin

    return base + normalized;
  }

  function resolveMediaUrl(raw, fallback = "") {
    if (!raw) return fallback;
    let s = String(raw).trim();

    s = s.replace(/^https?:\/\/localhost:\d+/i, "");
    s = s.replace(/^https?:\/\/127\.0\.0\.1:\d+/i, "");
    s = s.replace(/^https?:\/\/0\.0\.0\.0:\d+/i, "");
    s = s.replace(/^https?:\/\/thrchain\.vercel\.app/i, "");
    s = s.replace(/^https?:\/\/thrchain\.up\.railway\.app/i, "");

    s = s.replace(/\/{2,}/g, "/");

    if (s.startsWith("/media/static/")) {
      return s.replace("/media/static/", "/static/");
    }

    if (s.startsWith("/media/") || s.startsWith("/static/")) return s;

    const mediaIndex = s.indexOf("/media/");
    if (mediaIndex !== -1) return s.slice(mediaIndex);

    const staticIndex = s.indexOf("/static/");
    if (staticIndex !== -1) return s.slice(staticIndex);

    if (s.startsWith("media/") || s.startsWith("static/")) {
      return `/${s}`;
    }

    try {
      const parsed = new URL(s);
      return parsed.pathname + (parsed.search || "");
    } catch (e) {
      return s;
    }
  }

  function normalizeMediaUrl(raw, fallback = "") {
    if (!raw) return fallback;
    const base = (window.__API_BASE__ || window.location.origin || "").replace(/\/+$/, "");
    const value = String(raw).trim();
    if (!value) return fallback;

    if (/^https?:\/\/(localhost|127\.0\.0\.1|0\.0\.0\.0):\d+/i.test(value)) {
      return value.replace(/^https?:\/\/(localhost|127\.0\.0\.1|0\.0\.0\.0):\d+/i, base);
    }

    if (value.startsWith("/media/")) {
      try {
        return new URL(value, base).toString();
      } catch {
        return value;
      }
    }

    if (/^https?:\/\//i.test(value)) {
      return value;
    }

    try {
      return new URL(value, base).toString();
    } catch {
      return value;
    }
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
    resolveMediaUrl,
    normalizeMediaUrl,
    smartFetch,
    smartFetchJSON,
    fetchJSONOnce,
  };

  // Optional: overwrite global fetch to auto-fix legacy calls everywhere
  window.__thronos_native_fetch = NATIVE_FETCH;
  window.fetch = smartFetch;

  console.log("✓ fetch_utils loaded (API prefix normalizer active)");
})();
