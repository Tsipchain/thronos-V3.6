/**
 * Wallet V1 Centralized Signing Adapter
 *
 * All protected services (swap, pools, send, bridge, AI, IoT) MUST use this
 * single interface to create signed requests. Eliminates signature format
 * inconsistencies and ensures proper wallet locking/unlock flow.
 *
 * Usage:
 *   const signed = await walletV1Signer.buildSignedRequest('swap', {
 *     from: address,
 *     to_address: ...,
 *     amount: ...,
 *   });
 *   if (!signed.ok) {
 *     return showError(signed.error); // e.g., "Unlock Wallet V1 first"
 *   }
 *   const response = await fetch('/api/swap/execute', {
 *     method: 'POST',
 *     body: JSON.stringify(signed.request)
 *   });
 */

window.walletV1Signer = (function() {
  'use strict';

  const MODULE = '[WalletV1Signer]';

  /**
   * Build a signed request for a protected action.
   *
   * @param {string} action - Action name (swap, add_liquidity, send, etc)
   * @param {object} payload - Action payload (from, to, amount, etc)
   * @returns {Promise<{ok: boolean, error?: string, request?: object}>}
   *
   * Response on success:
   *   {
   *     ok: true,
   *     request: {
   *       action,
   *       payload,
   *       canonical_v1_address,
   *       from: canonical_v1_address,
   *       public_key,
   *       bound_key_address,
   *       signature,
   *       signature_format,
   *       timestamp,
   *       nonce,
   *       signing_payload_hash
   *     }
   *   }
   *
   * Response on error:
   *   {
   *     ok: false,
   *     error: "unlock_required" | "no_signer" | "signing_failed" | etc
   *   }
   */
  async function buildSignedRequest(action, payload) {
    try {
      // 1. Resolve canonical address
      const canonical = _getCanonicalAddress();
      if (!canonical || !canonical.ok) {
        console.warn(MODULE, 'No canonical address found');
        return {
          ok: false,
          error: 'no_active_wallet',
          message: 'Create or restore Wallet V1 first'
        };
      }
      const canonicalAddr = canonical.address;

      // 2. Check wallet is unlocked (runtime signer loaded)
      if (!_hasRuntimeSigner()) {
        console.warn(MODULE, 'Wallet is locked; runtime signer not available');
        return {
          ok: false,
          error: 'unlock_required',
          message: 'Unlock Wallet V1 first'
        };
      }

      // 3. Get signing material (public key + signing function)
      const signingMaterial = _getSigningMaterial();
      if (!signingMaterial) {
        console.error(MODULE, 'Signing material not available despite runtime signer');
        return {
          ok: false,
          error: 'signing_material_missing',
          message: 'Wallet signing key not found'
        };
      }

      const { publicKey, boundKeyAddress, signFn } = signingMaterial;

      // 4. Build canonical signing payload
      const timestamp = Math.floor(Date.now() / 1000);
      const nonce = _generateNonce();
      const signingPayload = {
        action,
        canonical_v1_address: canonicalAddr,
        payload,
        timestamp,
        nonce
      };

      // 5. Sign the payload
      const signingStr = JSON.stringify(signingPayload);
      const signature = await signFn(signingStr);
      if (!signature || !signature.ok) {
        console.error(MODULE, 'Signing failed:', signature?.error);
        return {
          ok: false,
          error: 'signing_failed',
          message: signature?.error || 'Failed to sign request'
        };
      }

      const signatureHex = signature.signature; // Compact 128-char hex format
      const signingPayloadHash = _hashPayload(signingStr);

      // 6. Build final signed request
      const signedRequest = {
        action,
        payload,
        canonical_v1_address: canonicalAddr,
        from: canonicalAddr,
        public_key: publicKey,
        bound_key_address: boundKeyAddress,
        signature: signatureHex,
        signature_format: 'compact_secp256k1_hex', // 128 hex chars
        signing_payload_hash: signingPayloadHash,
        timestamp,
        nonce
      };

      console.info(MODULE, `Built signed request for action="${action}"`, {
        canonical_short: canonicalAddr.substring(0, 10) + '...',
        has_signature: !!signatureHex,
        signature_format: 'compact_secp256k1_hex'
      });

      return {
        ok: true,
        request: signedRequest
      };
    } catch (err) {
      console.error(MODULE, 'Failed to build signed request:', err.message);
      return {
        ok: false,
        error: 'unexpected_error',
        message: err.message
      };
    }
  }

  /**
   * Get canonical address from wallet session
   * @returns {{ok: boolean, address?: string}}
   */
  function _getCanonicalAddress() {
    if (!window.walletSession || typeof window.walletSession.getActiveAddress !== 'function') {
      return { ok: false };
    }

    const addr = window.walletSession.getActiveAddress();
    if (!addr || !addr.startsWith('THR')) {
      return { ok: false };
    }

    return { ok: true, address: addr };
  }

  /**
   * Check if wallet has runtime signing material available (is unlocked)
   * @returns {boolean}
   */
  function _hasRuntimeSigner() {
    if (!window.walletSession) return false;

    // Check if wallet has runtime signing material
    const activeAddr = window.walletSession.getActiveAddress?.();
    if (!activeAddr) return false;

    const hasMaterial = window.walletSession.hasRuntimeSigningMaterial?.(activeAddr);
    return !!hasMaterial;
  }

  /**
   * Get signing material (public key + signing function)
   * @returns {{publicKey: string, boundKeyAddress: string, signFn: Function} | null}
   */
  function _getSigningMaterial() {
    if (!window.walletSession) return null;

    try {
      // Get active wallet and its signing info
      const activeAddr = window.walletSession.getActiveAddress?.();
      if (!activeAddr) return null;

      // Get public key
      const pubKeyInfo = window.walletSession.getPublicKeyInfo?.(activeAddr);
      if (!pubKeyInfo || !pubKeyInfo.public_key) {
        console.warn(MODULE, 'Public key not available');
        return null;
      }

      // Get bound key address (derived from public key)
      const boundAddr = pubKeyInfo.derived_address || activeAddr;

      // Get signing function
      const signFn = async (messageStr) => {
        try {
          // walletSession.sign() is the standard signing function
          const result = await window.walletSession.sign?.(messageStr, activeAddr);
          if (result && result.ok && result.signature) {
            return {
              ok: true,
              signature: result.signature // Should be 128-char compact hex
            };
          }
          return { ok: false, error: result?.error || 'Signing returned no signature' };
        } catch (err) {
          return { ok: false, error: err.message };
        }
      };

      return {
        publicKey: pubKeyInfo.public_key,
        boundKeyAddress: boundAddr,
        signFn
      };
    } catch (err) {
      console.error(MODULE, 'Failed to get signing material:', err.message);
      return null;
    }
  }

  /**
   * Hash a payload deterministically (for signing proof)
   * @param {string} str - Payload string
   * @returns {string} - SHA256 hash as hex
   */
  function _hashPayload(str) {
    // Use SubtleCrypto if available, else fallback to simple hash
    if (window.crypto && window.crypto.subtle) {
      // Async, but we're in async context
      const encoder = new TextEncoder();
      return crypto.subtle.digest('SHA-256', encoder.encode(str))
        .then(hashBuffer => {
          return Array.from(new Uint8Array(hashBuffer))
            .map(b => b.toString(16).padStart(2, '0'))
            .join('');
        })
        .catch(() => _simpleSHA256(str)); // Fallback if crypto fails
    }
    return _simpleSHA256(str);
  }

  /**
   * Simple SHA256 fallback (not cryptographically perfect, but deterministic)
   * @param {string} str
   * @returns {string} - 64-char hex hash
   */
  function _simpleSHA256(str) {
    // This is NOT a real SHA256. Use only as fallback.
    // In production, rely on crypto.subtle.digest
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      hash = ((hash << 5) - hash) + str.charCodeAt(i);
      hash = hash & hash; // Convert to 32-bit integer
    }
    return Math.abs(hash).toString(16).padStart(64, '0');
  }

  /**
   * Generate a unique nonce
   * @returns {string}
   */
  function _generateNonce() {
    return (Math.random().toString(36).substring(2, 15) +
            Math.random().toString(36).substring(2, 15) +
            Date.now().toString(36))
      .substring(0, 32);
  }

  // Public API
  return {
    buildSignedRequest,

    /**
     * Check if a service can call buildSignedRequest right now
     * (wallet unlocked and has signing material)
     * @returns {{canSign: boolean, reason?: string}}
     */
    canSign() {
      const canonical = _getCanonicalAddress();
      if (!canonical.ok) {
        return { canSign: false, reason: 'no_active_wallet' };
      }
      if (!_hasRuntimeSigner()) {
        return { canSign: false, reason: 'wallet_locked' };
      }
      if (!_getSigningMaterial()) {
        return { canSign: false, reason: 'no_signing_material' };
      }
      return { canSign: true };
    },

    /**
     * Get diagnostics (safe to log, no secrets)
     * @returns {object}
     */
    diagnostics() {
      const canonical = _getCanonicalAddress();
      const sigMat = _getSigningMaterial();
      return {
        canonical_v1_address_short: canonical.ok ? (canonical.address.substring(0, 10) + '...') : 'none',
        has_runtime_signer: _hasRuntimeSigner(),
        has_public_key: !!sigMat?.publicKey,
        bound_key_address_short: sigMat?.boundKeyAddress ? (sigMat.boundKeyAddress.substring(0, 10) + '...') : 'none'
      };
    }
  };
})();
