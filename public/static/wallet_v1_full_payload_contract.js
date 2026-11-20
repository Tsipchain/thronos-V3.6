(function(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.WalletV1FullPayloadContract = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
  'use strict';

  const DOMAIN = 'thronos.wallet.service_request';
  const PROTOCOL_VERSION = '2';
  const CHAIN_ID = 'thronos-mainnet';
  const SIGNATURE_FORMAT = 'wallet_v1_full_payload_v2';

  function normalizePayloadValue(value, depth = 0) {
    if (depth > 32) throw new Error('payload_too_deep');
    if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;
    if (typeof value === 'number') {
      if (!Number.isFinite(value)) throw new Error('payload_number_not_finite');
      return String(value);
    }
    if (Array.isArray(value)) return value.map(item => normalizePayloadValue(item, depth + 1));
    if (value && Object.getPrototypeOf(value) === Object.prototype) {
      const normalized = {};
      Object.keys(value).sort().forEach(key => {
        const item = value[key];
        if (item === undefined || typeof item === 'function' || typeof item === 'symbol') {
          throw new Error('unsupported_payload_value');
        }
        normalized[key] = normalizePayloadValue(item, depth + 1);
      });
      return normalized;
    }
    throw new Error('unsupported_payload_value');
  }

  function canonicalJson(value) {
    if (Array.isArray(value)) return '[' + value.map(canonicalJson).join(',') + ']';
    if (value && typeof value === 'object') {
      return '{' + Object.keys(value).sort().map(
        key => JSON.stringify(key) + ':' + canonicalJson(value[key])
      ).join(',') + '}';
    }
    return JSON.stringify(value);
  }

  function buildEnvelope(fields) {
    return {
      action: String(fields.action || '').trim().toLowerCase(),
      canonical_v1_address: String(fields.canonical_v1_address || '').trim(),
      chain_id: CHAIN_ID,
      domain: DOMAIN,
      expires_at: String(fields.expires_at || '').trim(),
      issued_at: String(fields.issued_at || '').trim(),
      nonce: String(fields.nonce || '').trim(),
      payload: normalizePayloadValue(fields.payload || {}),
      protocol_version: PROTOCOL_VERSION,
      signer_address: String(fields.signer_address || '').trim()
    };
  }

  return {
    CHAIN_ID,
    DOMAIN,
    PROTOCOL_VERSION,
    SIGNATURE_FORMAT,
    buildEnvelope,
    canonicalJson,
    normalizePayloadValue
  };
});
