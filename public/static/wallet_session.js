(function(window){
  const VERSION = 'wallet-v1-state-sync-2026-05-30';
  const ADDRESS_KEY = 'thr_address';
  const SEND_SECRET_KEY = 'send_secret';
  const SEND_SEED_KEY = 'send_seed';
  const SEND_SEED_COMPAT_KEY = 'thr_secret';
  const PIN_KEY = 'wallet_pin';
  const BOUND_KEY = 'wallet_bound';
  const LOCK_KEY = 'wallet_locked';
  const MIGRATION_META_KEY = 'wallet_v1_migration_meta';
  const V1_ENCRYPTED_KEY = 'wallet_v1_encrypted_priv';
  const V1_PUBLIC_KEY = 'wallet_v1_public_key';
  const V1_ADDRESS_KEY = 'wallet_v1_address';
  const VERIFIED_LEGACY_SOURCE_ADDRESS = 'THR79ca94a7eb70a6aa99d12d7fdb01446ef246301a';
  const VERIFIED_CANONICAL_V1_ADDRESS = 'THR683318ACF083723B3EDFE6C0A30AD62670F00353';

  const SESSION_UNLOCK_KEY = 'thr_v1_session_unlock';
  const SESSION_UNLOCK_TTL = 30 * 60 * 1000; // 30 minutes

  function _saveSessionUnlock(address, privHex) {
    try {
      const payload = JSON.stringify({ a: address, k: privHex, ts: Date.now() });
      sessionStorage.setItem(SESSION_UNLOCK_KEY, btoa(payload));
    } catch (_) {}
  }
  function _clearSessionUnlock() {
    try { sessionStorage.removeItem(SESSION_UNLOCK_KEY); } catch (_) {}
  }
  function _loadSessionUnlock() {
    try {
      const raw = sessionStorage.getItem(SESSION_UNLOCK_KEY);
      if (!raw) return null;
      const o = JSON.parse(atob(raw));
      if (!o || !o.k || !o.a || !o.ts) { sessionStorage.removeItem(SESSION_UNLOCK_KEY); return null; }
      if (Date.now() - o.ts > SESSION_UNLOCK_TTL) { sessionStorage.removeItem(SESSION_UNLOCK_KEY); return null; }
      return o;
    } catch (_) { return null; }
  }

  let customUnlockHandler = null;
  let unlockedPrivateKeyHex = null;
  let unlockedForAddress = null; // Track which address the current in-memory key belongs to
  let lastSigningKeyMismatch = null; // Track mismatch details for UI recovery flow
  let lastUnusableKeyDiagnostics = null; // Track unusable/legacy format key diagnostics

  // Restore signing material from sessionStorage on page load (survives navigation, clears on tab close)
  (function _restoreSessionUnlock() {
    try {
      const s = _loadSessionUnlock();
      if (!s) return;
      // Validate the restored address matches active wallet before restoring key
      const storedAddr = (s.a || '').trim();
      const currentAddr = (localStorage.getItem(V1_ADDRESS_KEY) || localStorage.getItem(ADDRESS_KEY) || '').trim();
      if (storedAddr && currentAddr && storedAddr !== currentAddr) {
        _clearSessionUnlock();
        return;
      }
      unlockedPrivateKeyHex = s.k;
      unlockedForAddress = storedAddr || currentAddr;
      localStorage.setItem(LOCK_KEY, '0');
      localStorage.setItem(BOUND_KEY, '1'); // mark wallet as connected after session restore
    } catch (_) {}
  })();

  const SYSTEM_WALLETS = {
    'THR5DF27A86C477F381594E896F0E55357DEC5942BA': 'ai_game_wallet',
    'THR_AI_AGENT_WALLET_V1': 'ai_agent_system',
  };

  let _ignoredSystemWalletSource = null;

  function setItem(key, value){ value ? localStorage.setItem(key, value) : localStorage.removeItem(key); }
  function readJson(key){ try { return JSON.parse(localStorage.getItem(key) || '{}'); } catch(_) { return {}; } }
  function setBound(v){ localStorage.setItem(BOUND_KEY, v ? '1' : '0'); }
  function isBound(){ return localStorage.getItem(BOUND_KEY) === '1'; }
  function isLocked(){ return localStorage.getItem(LOCK_KEY) === '1'; }

  function normalizeAddress(addr){ return (addr || '').toString().trim(); }
  function isValidThrAddress(addr){
    const normalized = normalizeAddress(addr);
    return normalized.startsWith('THR') && normalized.length >= 20 && normalized.length <= 100;
  }
  function isSystemWalletAddress(addr){
    const normalized = normalizeAddress(addr);
    return SYSTEM_WALLETS.hasOwnProperty(normalized);
  }

  function isVerifiedMigrationInfo(info){
    const oldAddress = normalizeAddress(info && info.old_address);
    const newAddress = normalizeAddress(info && info.new_v1_address);
    if (oldAddress !== VERIFIED_LEGACY_SOURCE_ADDRESS || newAddress !== VERIFIED_CANONICAL_V1_ADDRESS) return false;
    if (!isValidThrAddress(oldAddress) || !isValidThrAddress(newAddress)) return false;
    if (isSystemWalletAddress(oldAddress) || isSystemWalletAddress(newAddress)) return false;
    return !!(info.migration_tx_id || info.migrated_at || info.verified === true || info.status === 'verified' || info.status === 'completed');
  }

  function getCanonicalMigrationAddress(info){
    const migrationInfo = info || getMigrationInfo();
    return isVerifiedMigrationInfo(migrationInfo) ? VERIFIED_CANONICAL_V1_ADDRESS : '';
  }

  function getLegacySourceAddress(info){
    const migrationInfo = info || getMigrationInfo();
    return isVerifiedMigrationInfo(migrationInfo) ? VERIFIED_LEGACY_SOURCE_ADDRESS : '';
  }

  function getWalletOrigin(address){
    const normalized = normalizeAddress(address || getActiveAddress());
    const canonical = getCanonicalMigrationAddress();
    if (normalized && isSystemWalletAddress(normalized)) return 'system';
    if (canonical && normalized === canonical) return 'migrated';
    if (normalized && normalized === normalizeAddress(localStorage.getItem(V1_ADDRESS_KEY)) && isValidThrAddress(normalized)) return 'ui_created';
    return normalized ? 'unknown' : 'unknown';
  }

  function getWalletIdentityStatus(address){
    const origin = getWalletOrigin(address);
    if (origin === 'ui_created') return 'ui_created_empty';
    return origin;
  }

  function hasPledgeOrMigrationSource(){
    // Pledge-backed activation: Check if wallet has established its canonical address
    // through pledge confirmation, verified migration, or recovery
    const info = getMigrationInfo();
    const canonical = getCanonicalMigrationAddress(info);
    if (canonical) return true; // Verified migration

    // TODO: Add pledge confirmation check when pledge API is available
    // const pledge = getPledgeStatus();
    // if (pledge && pledge.confirmed && pledge.canonical_address) return true;

    return false;
  }

  function getModalState(){
    // Wallet modal state machine for pledge-backed activation:
    // Determines which options to show/hide in the wallet modal
    const activeAddr = getActiveAddress();
    const hasEncrypted = !!localStorage.getItem(V1_ENCRYPTED_KEY);
    const hasRuntime = !!unlockedPrivateKeyHex;
    const hasPledge = hasPledgeOrMigrationSource();

    if (!activeAddr) {
      // No active wallet address established
      if (hasPledge) {
        // Pledge confirmed but no wallet yet - user should set up signing key
        return 'active_wallet_no_key';
      }
      // No pledge/migration/recovery - must establish one first
      return 'no_active_wallet';
    }

    // Active address exists - check key material
    if (!hasEncrypted) {
      // No signing key stored locally
      return 'active_wallet_no_key';
    }

    // Has active address and encrypted key
    if (hasRuntime) {
      // Key is unlocked in memory
      return 'signing_ready';
    }

    // Key exists but not unlocked
    return 'active_wallet_with_encrypted_key';
  }

  function getAddress(){ return getActiveAddress() || localStorage.getItem(V1_ADDRESS_KEY) || localStorage.getItem(ADDRESS_KEY) || ''; }
  function getActiveAddress(){
    _ignoredSystemWalletSource = null;
    const info = getMigrationInfo();
    const v1_addr = localStorage.getItem(V1_ADDRESS_KEY);
    const legacy_addr = localStorage.getItem(ADDRESS_KEY);
    const canonical = getCanonicalMigrationAddress(info);

    // Prefer verified migration mapping over UI-created wallets.
    // THR79ca94a7eb70a6aa99d12d7fdb01446ef246301a canonically maps to THR683318ACF083723B3EDFE6C0A30AD62670F00353.
    if (canonical) return canonical;

    if (info.new_v1_address && isSystemWalletAddress(info.new_v1_address)) _ignoredSystemWalletSource = 'migration.new_v1_address';

    // UI-created wallets are valid local wallets only when no verified migration identity exists.
    if (v1_addr && isValidThrAddress(v1_addr) && !isSystemWalletAddress(v1_addr)) return v1_addr;
    if (v1_addr && isSystemWalletAddress(v1_addr)) _ignoredSystemWalletSource = 'wallet_v1_address';

    if (info.new_v1_address && isValidThrAddress(info.new_v1_address) && !isSystemWalletAddress(info.new_v1_address)) return info.new_v1_address;

    if (legacy_addr && isValidThrAddress(legacy_addr) && !isSystemWalletAddress(legacy_addr)) return legacy_addr;
    if (legacy_addr && isSystemWalletAddress(legacy_addr)) _ignoredSystemWalletSource = 'thr_address';

    return '';
  }
  function setAddress(addr){ setItem(ADDRESS_KEY, addr ? addr.trim() : ''); }

  function persistActiveUserAddress(addr){
    const normalized = normalizeAddress(addr);
    if (!isValidThrAddress(normalized)) throw new Error('wallet_address_required');
    if (isSystemWalletAddress(normalized)) throw new Error('system_wallet_not_allowed');
    const canonical = getCanonicalMigrationAddress();
    if (canonical) {
      localStorage.setItem(V1_ADDRESS_KEY, canonical);
      localStorage.setItem(ADDRESS_KEY, canonical);
      if (unlockedPrivateKeyHex) unlockedForAddress = canonical;
      return canonical;
    }
    localStorage.setItem(V1_ADDRESS_KEY, normalized);
    localStorage.setItem(ADDRESS_KEY, normalized);
    if (unlockedPrivateKeyHex) unlockedForAddress = normalized;
    return normalized;
  }

  function scopedCredentialKeys(address){
    const normalized = (address || '').trim();
    if (!normalized) return [];
    return [
      `wallet:${normalized}:send_secret`,
      `wallet:${normalized}:send_seed`,
      `send_secret:${normalized}`,
      `send_seed:${normalized}`,
      `thr_secret:${normalized}`,
    ];
  }

  function getRawSeedForAddress(address){
    for (const key of scopedCredentialKeys(address)) {
      const value = localStorage.getItem(key);
      if (value) return value;
    }
    return '';
  }

  function getMigrationInfo(){ return readJson(MIGRATION_META_KEY); }
  function isMigrated(){ const info = getMigrationInfo(); return !!(info.old_address && info.new_v1_address); }

  async function restoreMigratedWallet(legacyAddress, migrationProof){
    // Restore canonical V1 address from backend migration lookup
    // Input: legacy/core THR address + optional migration proof (send_secret or migration tx id)
    // Output: {ok: true, legacy_address, canonical_v1_address, migration_status, has_signing_material}
    // Does NOT create, remigrate, or mutate canonical address
    // Only persists canonical_v1_address returned by backend
    try {
      const normalized = normalizeAddress(legacyAddress);
      if (!isValidThrAddress(normalized)) {
        return {ok: false, error: 'Invalid legacy address format'};
      }
      if (isSystemWalletAddress(normalized)) {
        return {ok: false, error: 'System wallets cannot be migrated'};
      }

      // Call backend to look up migration mapping
      const response = await fetch('/api/wallet/v1/restore-migration', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          legacy_address: normalized,
          migration_proof: migrationProof || '' // send_secret or migration tx id
        })
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        return {
          ok: false,
          error: errData.error || `Backend error: ${response.status}`
        };
      }

      const data = await response.json();
      if (!data.ok) {
        return {ok: false, error: data.error || 'Migration restore failed'};
      }

      // Validate response has canonical V1 address
      const canonicalAddr = normalizeAddress(data.canonical_v1_address);
      if (!isValidThrAddress(canonicalAddr)) {
        return {ok: false, error: 'Backend returned invalid canonical address'};
      }
      if (isSystemWalletAddress(canonicalAddr)) {
        return {ok: false, error: 'Backend returned system wallet address'};
      }

      // Persist canonical V1 address as active (do not remigrate)
      localStorage.setItem(V1_ADDRESS_KEY, canonicalAddr);
      localStorage.setItem(ADDRESS_KEY, canonicalAddr);

      // Store migration info with restore metadata
      const migrationInfo = {
        ...getMigrationInfo(),
        old_address: normalized,
        new_v1_address: canonicalAddr,
        migration_status: data.migration_status || 'confirmed',
        restored_at: Date.now(),
        restored_from: legacyAddress // For diagnostics only
      };
      localStorage.setItem(MIGRATION_META_KEY, JSON.stringify(migrationInfo));

      // Clear any runtime signing material (must re-unlock or re-import for this canonical address)
      unlockedPrivateKeyHex = null;
      unlockedForAddress = null;
      localStorage.setItem(LOCK_KEY, '1');

      return {
        ok: true,
        legacy_address: normalized,
        canonical_v1_address: canonicalAddr,
        migration_status: data.migration_status || 'confirmed',
        has_signing_material: data.has_signing_material || false,
        wallet_origin: 'migration_restore'
      };
    } catch (err) {
      return {
        ok: false,
        error: err && err.message ? err.message : 'Failed to restore migrated wallet'
      };
    }
  }

  function getCredentialLookupAddress(address){
    const active = (address || getActiveAddress() || getAddress() || '').trim();
    const info = getMigrationInfo();
    if (active && getRawSeedForAddress(active)) return active;
    if (info.new_v1_address && getRawSeedForAddress(info.new_v1_address)) return info.new_v1_address;
    if (info.old_address && getRawSeedForAddress(info.old_address)) return info.old_address;
    return active || info.new_v1_address || info.old_address || '';
  }

  function getSendSeed(address){
    const active = (address || getActiveAddress() || getAddress() || '').trim();
    const info = getMigrationInfo();
    const direct = getRawSeedForAddress(active);
    if (direct) return direct;
    const migrated = info.new_v1_address ? getRawSeedForAddress(info.new_v1_address) : '';
    if (migrated) return migrated;
    const legacy = info.old_address ? getRawSeedForAddress(info.old_address) : '';
    if (legacy) return legacy;
    return localStorage.getItem(SEND_SECRET_KEY) || localStorage.getItem(SEND_SEED_KEY) || localStorage.getItem(SEND_SEED_COMPAT_KEY) || '';
  }

  function setSendSeed(seed){
    const value = seed ? seed.trim() : '';
    setItem(SEND_SECRET_KEY, value);
    setItem(SEND_SEED_KEY, value);
    setItem(SEND_SEED_COMPAT_KEY, value);
    const address = getCredentialLookupAddress(getActiveAddress());
    if (address) {
      scopedCredentialKeys(address).slice(0, 2).forEach(key => setItem(key, value));
    }
  }

  const getSendSecret = getSendSeed;
  const setSendSecret = setSendSeed;
  function getPin(){ return localStorage.getItem(PIN_KEY) || ''; }
  function setPin(pin){ setItem(PIN_KEY, pin ? pin.trim() : ''); }

  function lockWallet(){ unlockedPrivateKeyHex = null; unlockedForAddress = null; localStorage.setItem(LOCK_KEY, '1'); _clearSessionUnlock(); }
  function lock(){ return lockWallet(); }
  function setCustomUnlockHandler(fn){ customUnlockHandler = typeof fn === 'function' ? fn : null; }

  function hexToBytes(hex){ const clean = String(hex || '').replace(/^0x/, ''); const out=[]; for(let i=0;i<clean.length;i+=2) out.push(parseInt(clean.slice(i,i+2),16)); return new Uint8Array(out); }
  function bytesToHex(bytes){ return Array.from(bytes || []).map(b=>b.toString(16).padStart(2,'0')).join(''); }
  function toUint8Bytes(value){
    if (!value) return new Uint8Array();
    if (value instanceof Uint8Array) return value;
    if (Array.isArray(value)) return new Uint8Array(value);
    if (typeof value === 'string') return hexToBytes(value);
    return new Uint8Array(value);
  }
  function concatBytes(parts){
    const arrays = Array.from(parts || []).map(toUint8Bytes);
    const total = arrays.reduce((sum, arr) => sum + arr.length, 0);
    const out = new Uint8Array(total);
    let offset = 0;
    arrays.forEach((arr) => { out.set(arr, offset); offset += arr.length; });
    return out;
  }
  function bytesFromSignature(sig){
    if (!sig) return new Uint8Array();
    if (sig instanceof Uint8Array) return sig;
    if (Array.isArray(sig)) return new Uint8Array(sig);
    if (typeof sig === 'string') return hexToBytes(sig);
    if (typeof sig.toDERRawBytes === 'function') return sig.toDERRawBytes();
    if (typeof sig.toCompactRawBytes === 'function') return sig.toCompactRawBytes();
    if (typeof sig.toRawBytes === 'function') return sig.toRawBytes();
    return new Uint8Array();
  }
  function derInteger(bytes){
    let start = 0;
    while (start < bytes.length - 1 && bytes[start] === 0) start++;
    let value = Array.from(bytes.slice(start));
    if (!value.length) value = [0];
    if (value[0] & 0x80) value.unshift(0);
    return [0x02, value.length, ...value];
  }
  function derEncodeCompactSignature(bytes){
    if (!bytes || bytes.length !== 64) return bytes;
    const r = derInteger(bytes.slice(0, 32));
    const s = derInteger(bytes.slice(32, 64));
    return new Uint8Array([0x30, r.length + s.length, ...r, ...s]);
  }
  function normalizeSignatureToDerHex(sig){
    if (sig && typeof sig.toDERHex === 'function') return sig.toDERHex();
    const bytes = bytesFromSignature(sig);
    if (!bytes.length) return '';
    if (bytes[0] === 0x30) return bytesToHex(bytes);
    return bytesToHex(derEncodeCompactSignature(bytes));
  }
  function getSecpContainer(secp, key){
    const container = secp && secp[key];
    return container && typeof container === 'object' ? container : null;
  }
  function readSecpHelper(secp, containerName, helperName){
    const container = getSecpContainer(secp, containerName);
    return container && typeof container[helperName] === 'function' ? container[helperName] : null;
  }
  function canMutateSecpObject(obj){
    return !!obj && typeof obj === 'object' && !(Object.isFrozen && Object.isFrozen(obj)) && (Object.isExtensible ? Object.isExtensible(obj) : true);
  }
  function ensureMutableSecpContainer(secp, key){
    const existing = getSecpContainer(secp, key);
    if (existing) return existing;
    if (!canMutateSecpObject(secp)) return null;
    try { secp[key] = {}; } catch (_) { return null; }
    return getSecpContainer(secp, key);
  }
  function setSecpHelper(secp, containerName, helperName, helperFn){
    if (readSecpHelper(secp, containerName, helperName)) return true;
    const container = ensureMutableSecpContainer(secp, containerName);
    if (!canMutateSecpObject(container)) return false;
    try { container[helperName] = helperFn; } catch (_) { return false; }
    return !!readSecpHelper(secp, containerName, helperName);
  }
  function getSecpCryptoDiagnostics(secp){
    return {
      has_secp: !!secp,
      has_etc: !!getSecpContainer(secp, 'etc'),
      has_utils: !!getSecpContainer(secp, 'utils'),
      has_hashes: !!getSecpContainer(secp, 'hashes'),
      is_frozen: !!(secp && Object.isFrozen && Object.isFrozen(secp))
    };
  }
  function logSecpCryptoDiagnostics(secp){
    if (typeof console !== 'undefined' && console.info) console.info('[WalletV1Crypto]', getSecpCryptoDiagnostics(secp));
  }
  function getSubtleCrypto(){
    const webCrypto = (typeof crypto !== 'undefined' && crypto) || (typeof window !== 'undefined' && window.crypto) || (typeof globalThis !== 'undefined' && globalThis.crypto) || null;
    return webCrypto && webCrypto.subtle ? webCrypto.subtle : null;
  }
  async function ensureSecpAsyncCrypto(secp){
    const subtle = getSubtleCrypto();
    if (!secp || !subtle) { logSecpCryptoDiagnostics(secp); throw new Error('wallet_crypto_not_ready'); }
    const sha256Async = async (...msgs) => new Uint8Array(await subtle.digest('SHA-256', concatBytes(msgs)));
    const hmacSha256Async = async (key, ...msgs) => {
      const cryptoKey = await subtle.importKey('raw', toUint8Bytes(key), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
      return new Uint8Array(await subtle.sign('HMAC', cryptoKey, concatBytes(msgs)));
    };
    const helpersReady = [
      setSecpHelper(secp, 'etc', 'sha256Async', sha256Async),
      setSecpHelper(secp, 'etc', 'hmacSha256Async', hmacSha256Async),
      setSecpHelper(secp, 'hashes', 'sha256Async', sha256Async),
      setSecpHelper(secp, 'hashes', 'hmacSha256Async', hmacSha256Async)
    ].every(Boolean);
    if (!helpersReady) { logSecpCryptoDiagnostics(secp); throw new Error('wallet_crypto_not_ready'); }
    if (!readSecpHelper(secp, 'utils', 'sha256') && !readSecpHelper(secp, 'hashes', 'sha256')) {
      // Noble v2 uses async helpers for nonce generation; keep sync slots untouched when unavailable.
    }
  }
  function isSecpCryptoHelperError(err){
    const msg = String((err && (err.message || err)) || '').toLowerCase();
    return msg.includes('option not supported') || msg.includes('hmacsha256sync') || msg.includes('sha256sync') || msg.includes('hashes') || msg.includes('wallet_crypto_not_ready') || msg.includes('cannot set properties') || msg.includes('cannot read properties');
  }
  async function tryNonMutatingAsyncSign(secp, digestHex, privateKeyHex){
    if (!secp || typeof secp.signAsync !== 'function') throw new Error('wallet_crypto_not_ready');
    return normalizeSignatureToDerHex(await secp.signAsync(digestHex, privateKeyHex));
  }
  async function signDigestDerHex(secp, digestHex, privateKeyHex){
    try {
      try { await ensureSecpAsyncCrypto(secp); }
      catch (setupErr) { return await tryNonMutatingAsyncSign(secp, digestHex, privateKeyHex); }
      if (typeof secp.signAsync === 'function') {
        return normalizeSignatureToDerHex(await secp.signAsync(digestHex, privateKeyHex));
      }
      return normalizeSignatureToDerHex(await secp.sign(digestHex, privateKeyHex, { der: true }));
    } catch (err) {
      if (!isSecpCryptoHelperError(err)) throw err;
      try {
        try { await ensureSecpAsyncCrypto(secp); }
        catch (setupErr) { return await tryNonMutatingAsyncSign(secp, digestHex, privateKeyHex); }
        if (typeof secp.signAsync === 'function') {
          return normalizeSignatureToDerHex(await secp.signAsync(digestHex, privateKeyHex));
        }
        return normalizeSignatureToDerHex(await secp.sign(digestHex, privateKeyHex));
      } catch (_) {
        throw new Error('wallet_crypto_not_ready');
      }
    }
  }
  async function sha256Hex(s){ const subtle = getSubtleCrypto(); if (!subtle) throw new Error('wallet_crypto_not_ready'); const d = await subtle.digest('SHA-256', new TextEncoder().encode(s)); return bytesToHex(new Uint8Array(d)); }
  async function aesKeyFromPin(pin, salt){
    const material = await crypto.subtle.importKey('raw', new TextEncoder().encode(pin), 'PBKDF2', false, ['deriveKey']);
    return crypto.subtle.deriveKey({name:'PBKDF2',salt,iterations:250000,hash:'SHA-256'}, material, {name:'AES-GCM',length:256}, false, ['encrypt','decrypt']);
  }
  async function encryptPrivateKeyHex(privateKeyHex, pin){
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const salt = crypto.getRandomValues(new Uint8Array(16));
    const key = await aesKeyFromPin(pin, salt);
    const cipher = await crypto.subtle.encrypt({name:'AES-GCM', iv}, key, hexToBytes(privateKeyHex));
    return JSON.stringify({v:1,salt:bytesToHex(salt),iv:bytesToHex(iv),ct:bytesToHex(new Uint8Array(cipher))});
  }
  async function decryptPrivateKeyHex(blob, pin){
    const p = JSON.parse(blob);
    const key = await aesKeyFromPin(pin, hexToBytes(p.salt));
    const clear = await crypto.subtle.decrypt({name:'AES-GCM', iv:hexToBytes(p.iv)}, key, hexToBytes(p.ct));
    return bytesToHex(new Uint8Array(clear));
  }

  function _getSecp(){
    return window.nobleSecp256k1 || window.secp256k1 || (window.noble && window.noble.secp256k1) || window.nobleSecp256k1Lib || window.NobleSecp256k1 || null;
  }

  async function _ensureSecpLoaded(){
    if (_getSecp()) return _getSecp();
    if (window.__nobleSecp256k1Ready && typeof window.__nobleSecp256k1Ready.then === 'function') {
      try { await window.__nobleSecp256k1Ready; } catch(_) {}
    }
    return _getSecp();
  }

  async function deriveAddressFromPublicKey(publicKey){
    const res = await fetch('/api/v1/address/derive', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({public_key: publicKey, compressed_public_key: publicKey})});
    const data = await res.json();
    if (!res.ok || !(data.address || data.thr_address)) throw new Error(data.error || 'address_derivation_failed');
    return data.address || data.thr_address;
  }

  async function createWalletV1({pin} = {}){
    const secp = await _ensureSecpLoaded();
    if (!secp || !secp.getPublicKey || !secp.utils || !secp.sign) throw new Error('secp256k1_library_missing');
    if (!pin) throw new Error('pin_required');
    const privBytes = secp.utils.randomPrivateKey ? secp.utils.randomPrivateKey() : crypto.getRandomValues(new Uint8Array(32));
    const priv = typeof privBytes === 'string' ? privBytes.replace(/^0x/, '') : bytesToHex(privBytes);
    const pubBytes = secp.getPublicKey(priv, true);
    const pub = typeof pubBytes === 'string' ? pubBytes.replace(/^0x/, '') : bytesToHex(pubBytes);
    const address = await deriveAddressFromPublicKey(pub);
    const enc = await encryptPrivateKeyHex(priv, pin);
    localStorage.setItem(V1_ENCRYPTED_KEY, enc);
    localStorage.setItem(V1_PUBLIC_KEY, pub);
    localStorage.setItem(V1_ADDRESS_KEY, address);
    setPin(pin);
    setBound(true);
    localStorage.setItem(LOCK_KEY, '0');
    unlockedPrivateKeyHex = priv;
    _saveSessionUnlock(address, priv);
    return { address, publicKey: pub };
  }

  async function generateV1KeyPair(){
    // Generate a new V1 key pair without storing it
    // Returns {success: true, publicKey, address} or {success: false, error}
    try {
      const secp = await _ensureSecpLoaded();
      if (!secp || !secp.getPublicKey || !secp.utils) {
        return {success: false, error: 'secp256k1_library_missing'};
      }

      const privBytes = secp.utils.randomPrivateKey ? secp.utils.randomPrivateKey() : crypto.getRandomValues(new Uint8Array(32));
      const priv = typeof privBytes === 'string' ? privBytes.replace(/^0x/, '') : bytesToHex(privBytes);
      const pubBytes = secp.getPublicKey(priv, true);
      const pub = typeof pubBytes === 'string' ? pubBytes.replace(/^0x/, '') : bytesToHex(pubBytes);

      const address = await deriveAddressFromPublicKey(pub);

      return {success: true, publicKey: pub, address: address, privateKey: priv};
    } catch(err) {
      return {success: false, error: err && err.message ? err.message : 'Failed to generate key pair'};
    }
  }

  async function derivePublicKeyAndAddress(privateKeyHex){
    // Derive public key and address from a private key hex string
    // Returns {success: true, publicKey, address} or {success: false, error}
    try {
      if (!privateKeyHex || typeof privateKeyHex !== 'string') {
        return {success: false, error: 'Invalid private key format'};
      }

      const secp = await _ensureSecpLoaded();
      if (!secp || !secp.getPublicKey) {
        return {success: false, error: 'secp256k1_library_missing'};
      }

      const pubBytes = secp.getPublicKey(privateKeyHex, true);
      const pub = typeof pubBytes === 'string' ? pubBytes.replace(/^0x/, '') : bytesToHex(pubBytes);

      const address = await deriveAddressFromPublicKey(pub);

      return {success: true, publicKey: pub, address: address};
    } catch(err) {
      return {success: false, error: err && err.message ? err.message : 'Failed to derive public key and address'};
    }
  }

  function hasSigningMaterial(address){
    return !!(localStorage.getItem(V1_ENCRYPTED_KEY) || unlockedPrivateKeyHex || getSendSeed(address));
  }

  async function unlockWallet(options = {}){
    if (!isLocked() && isBound() && hasSigningMaterial(options.address)) return true;
    if (customUnlockHandler) {
      try { const ok = await customUnlockHandler(options); if (ok) { setBound(true); localStorage.setItem(LOCK_KEY, '0'); return true; } }
      catch(_) {}
    }
    const pin = options.pin || (options.prompt !== false ? prompt('Enter wallet PIN to unlock') : null);
    if (!pin) return false;
    const activeAddr = options.address || getActiveAddress();
    // CRITICAL: Unlock requires an active/canonical wallet address
    // User must import, create, migrate, or restore a wallet first
    if (!activeAddr) {
      const err = new Error('wallet_import_required');
      err.code = 'WALLET_IMPORT_REQUIRED';
      throw err;
    }
    const enc = localStorage.getItem(V1_ENCRYPTED_KEY);
    if (enc) {
      let decryptSucceeded = false;
      try {
        const decryptedPrivKeyHex = await decryptPrivateKeyHex(enc, pin);
        decryptSucceeded = true;

        // Try to derive public key and address from decrypted material
        let keyDerivationSucceeded = false;
        let derivedAddress = '';
        let derivedPublicKey = '';

        try {
          const secp = await _ensureSecpLoaded();
          if (!secp || !secp.getPublicKey) throw new Error('secp256k1_library_missing');

          const pubBytes = secp.getPublicKey(decryptedPrivKeyHex, true);
          derivedPublicKey = typeof pubBytes === 'string' ? pubBytes.replace(/^0x/, '') : bytesToHex(pubBytes);
          derivedAddress = await deriveAddressFromPublicKey(derivedPublicKey);
          keyDerivationSucceeded = true;
        } catch (derivErr) {
          // Key derivation failed - mark as unusable/legacy format
          keyDerivationSucceeded = false;
          // Store diagnostics for recovery UI
          lastUnusableKeyDiagnostics = {
            decrypt_succeeded: true,
            key_parse_status: 'failed',
            active_address_short: activeAddr ? activeAddr.substring(0, 10) + '...' : 'unknown',
            derived_address_short: 'unknown',
            encrypted_seed_present: !!enc,
            runtime_material_present: !!unlockedPrivateKeyHex,
            recovery_recommended: 'rekey',
            error: derivErr && derivErr.message ? derivErr.message : 'Failed to derive public key/address',
            timestamp: Date.now()
          };
          const err = new Error('wallet_signing_key_unusable_or_legacy_format');
          err.code = 'KEY_UNUSABLE';
          err.decrypt_succeeded = true;
          err.key_parse_status = 'failed';
          throw err;
        }

        // Key derivation succeeded - check if it matches active address or binding
        const activeNormalized = normalizeAddress(activeAddr);
        const derivedNormalized = normalizeAddress(derivedAddress);

        if (activeNormalized && derivedNormalized && activeNormalized === derivedNormalized) {
          // Direct match - standard case
          unlockedPrivateKeyHex = decryptedPrivKeyHex;
          unlockedForAddress = activeAddr;
          setBound(true);
          localStorage.setItem(LOCK_KEY, '0');
          _saveSessionUnlock(activeAddr, decryptedPrivKeyHex);
          return true;
        }

        // Address mismatch - check for active binding (re-key ceremony case)
        if (activeNormalized && derivedNormalized && activeNormalized !== derivedNormalized) {
          // Try to verify through binding
          try {
            const binding = await getActiveKeyBinding(activeAddr);
            if (binding && binding.bound_key_address && derivedNormalized === normalizeAddress(binding.bound_key_address)) {
              // Binding exists and matches derived address - binding-aware unlock
              unlockedPrivateKeyHex = decryptedPrivKeyHex;
              unlockedForAddress = activeAddr;
              setBound(true);
              localStorage.setItem(LOCK_KEY, '0');
              _saveSessionUnlock(activeAddr, decryptedPrivKeyHex);
              return true;
            }
          } catch (bindingCheckErr) {
            // Binding check failed, fall through to mismatch error
          }

          // No matching binding - generic key mismatch
          const err = new Error('wallet_signing_key_does_not_match_active_address');
          err.code = 'KEY_MISMATCH';
          err.derived_address = derivedAddress;
          err.active_address = activeAddr;
          err.decrypt_succeeded = true;
          lastSigningKeyMismatch = {
            derived_address: derivedAddress,
            active_address: activeAddr,
            decrypt_succeeded: true,
            timestamp: Date.now()
          };
          throw err;
        }

        unlockedPrivateKeyHex = decryptedPrivKeyHex;
        unlockedForAddress = activeAddr;
        setBound(true);
        localStorage.setItem(LOCK_KEY, '0');
        _saveSessionUnlock(activeAddr, decryptedPrivKeyHex);
        return true;
      }
      catch(err) {
        // Clear any partially-cached material on error
        unlockedPrivateKeyHex = null;
        unlockedForAddress = null;
        _clearSessionUnlock();
        if ((err.message || '').includes('wallet_signing_key_does_not_match_active_address') ||
            (err.message || '').includes('wallet_signing_key_unusable_or_legacy_format')) {
          throw err;
        }
        // PIN decryption failed - return false to allow fallback to legacy creds
        return false;
      }
    }
    const credentialAddress = getCredentialLookupAddress(activeAddr);
    const hasLegacyCreds = !!(activeAddr && getSendSeed(credentialAddress) && pin === getPin());
    if (hasLegacyCreds) { unlockedForAddress = activeAddr; setBound(true); localStorage.setItem(LOCK_KEY, '0'); return true; }
    return false;
  }
  async function unlock(pinOrOptions){ const options = typeof pinOrOptions === 'string' ? {pin: pinOrOptions, prompt:false} : (pinOrOptions || {}); return unlockWallet(options); }

  function hasRuntimeSigningMaterial(address){
    const normalized = normalizeAddress(address || getActiveAddress());
    return !!(unlockedPrivateKeyHex && (!normalized || !unlockedForAddress || unlockedForAddress === normalized));
  }

  function isUnlockedFor(address){
    // Check if in-memory signing material belongs to the given address.
    // Does not expose the private key itself.
    return hasRuntimeSigningMaterial(address);
  }

  function getPublicKey(){ return localStorage.getItem(V1_PUBLIC_KEY) || ''; }
  function hasEncryptedPrivateKey(){ return !!localStorage.getItem(V1_ENCRYPTED_KEY); }
  function isWalletV1(){ return !!(localStorage.getItem(V1_PUBLIC_KEY) && localStorage.getItem(V1_ENCRYPTED_KEY)); }

  function canonicalTxMessage(txCore){
    const txType = txCore.type || txCore.action;

    // Swap transactions: use swap-specific canonical format matching server.py verification
    if (txType === 'swap' || txType === 'execute_swap') {
      const from = String(txCore.from || txCore.trader_thr || '').trim();
      const tokenIn = String(txCore.token_in || txCore.token || 'THR').trim();
      const tokenOut = String(txCore.token_out || '').trim();
      const amountIn = String(txCore.amount_in || txCore.amount || '').trim();
      const nonce = String(txCore.nonce || '').trim();
      const timestamp = String(txCore.timestamp || '').trim();
      // Alphabetically sorted: action, amount_in, from, nonce, timestamp, token_in, token_out, type
      return '{"action":"swap","amount_in":' + JSON.stringify(amountIn)
        + ',"from":' + JSON.stringify(from)
        + ',"nonce":' + JSON.stringify(nonce)
        + ',"timestamp":' + JSON.stringify(timestamp)
        + ',"token_in":' + JSON.stringify(tokenIn)
        + ',"token_out":' + JSON.stringify(tokenOut)
        + ',"type":"swap"}';
    }

    // Generic transactions (pools, etc.): use generic canonical format
    const txForSigning = {
      from: txCore.from || txCore.trader_thr || txCore.provider_thr,
      to: txCore.to,
      amount: txCore.amount || txCore.amount_in || txCore.shares,
      token: txCore.token || txCore.token_in,
      nonce: txCore.nonce,
      timestamp: txCore.timestamp,
    };
    const token = txForSigning.token || 'THR';
    return '{"amount":' + JSON.stringify(txForSigning.amount)
      + ',"from":' + JSON.stringify(txForSigning.from)
      + ',"nonce":' + JSON.stringify(txForSigning.nonce)
      + ',"timestamp":' + JSON.stringify(txForSigning.timestamp)
      + ',"to":' + JSON.stringify(txForSigning.to)
      + ',"token":' + JSON.stringify(token)
      + '}';
  }

  async function signTransaction(txCore){
    if (isLocked() || !isBound()) throw new Error('wallet_locked');
    const secp = await _ensureSecpLoaded();
    if (!secp || !secp.sign) throw new Error('secp256k1_library_missing');
    if (!unlockedPrivateKeyHex) throw new Error('wallet_locked');
    try {
      const digestHex = await sha256Hex(canonicalTxMessage(txCore));
      return await signDigestDerHex(secp, digestHex, unlockedPrivateKeyHex);
    } catch (err) {
      if (isSecpCryptoHelperError(err) || String((err && (err.message || err)) || '').includes('Cannot read properties of undefined')) {
        throw new Error('wallet_crypto_not_ready');
      }
      throw err;
    }
  }

  async function enrollSigningMaterial({address, credentialLookupAddress, pin, authSecret} = {}){
    const activeAddress = normalizeAddress(address || getActiveAddress());
    const lookupAddress = normalizeAddress(credentialLookupAddress || getCredentialLookupAddress(activeAddress));
    const legacySecret = authSecret || getSendSeed(lookupAddress) || getSendSeed(activeAddress);
    if (!activeAddress || !lookupAddress || !legacySecret) throw new Error('missing_wallet_signing_material');
    const unlockPin = pin || prompt('Wallet V1 signing upgrade required. Unlock with PIN to create encrypted V1 signing key.');
    if (!unlockPin) throw new Error('wallet_locked');
    const secp = await _ensureSecpLoaded();
    if (!secp || !secp.getPublicKey || !secp.utils || !secp.sign) throw new Error('secp256k1_library_missing');
    const privBytes = secp.utils.randomPrivateKey ? secp.utils.randomPrivateKey() : crypto.getRandomValues(new Uint8Array(32));
    const priv = bytesToHex(privBytes);
    const pub = bytesToHex(secp.getPublicKey(priv, true));
    const enc = await encryptPrivateKeyHex(priv, unlockPin);
    const res = await fetch('/api/v1/wallet/bind_public_key', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        address: activeAddress,
        credential_lookup_address: lookupAddress,
        public_key: pub,
        auth_secret: legacySecret
      })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) throw new Error(data.error || 'wallet_signing_enrollment_failed');
    localStorage.setItem(V1_ENCRYPTED_KEY, enc);
    localStorage.setItem(V1_PUBLIC_KEY, pub);
    localStorage.setItem(V1_ADDRESS_KEY, activeAddress);
    setPin(unlockPin);
    setBound(true);
    localStorage.setItem(LOCK_KEY, '0');
    unlockedPrivateKeyHex = priv;
    return { address: activeAddress, credentialLookupAddress: lookupAddress, publicKey: pub, binding: data.binding || data };
  }

  async function migrateLegacyWallet({oldAddress, sendSecret, pin, signedMigrationRequest} = {}){
    if (!oldAddress || !sendSecret || !pin) throw new Error('legacy_credentials_required');
    const created = await createWalletV1({ pin });
    try {
      const body = { old_thr_address: oldAddress, legacy_secret: sendSecret, new_compressed_public_key: created.publicKey };
      if (signedMigrationRequest) body.signed_migration_request = signedMigrationRequest;
      const res = await fetch('/api/v1/wallet/migrate', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'migration_failed');
      const meta = {
        old_address: oldAddress,
        new_v1_address: data?.migration?.new_v1_address || created.address,
        migration_tx_id: data?.migration?.migration_tx_id || data?.migration_tx_id || '',
        migrated_at: data?.migration?.migrated_at || new Date().toISOString(),
      };
      localStorage.setItem(MIGRATION_META_KEY, JSON.stringify(meta));
      setSendSeed('');
      return meta;
    } finally {
      sendSecret = '';
      localStorage.removeItem(SEND_SECRET_KEY);
      localStorage.removeItem(SEND_SEED_KEY);
      localStorage.removeItem(SEND_SEED_COMPAT_KEY);
    }
  }

  function getWalletAuthDiagnostics(address){
    const info = getMigrationInfo();
    const active = address || getActiveAddress();
    const credential = getCredentialLookupAddress(active);
    return {
      active_wallet_address: active || '',
      credential_lookup_address: credential || '',
      migration_old_address: info.old_address || '',
      migration_new_v1_address: info.new_v1_address || '',
      has_encrypted_send_seed: !!localStorage.getItem(V1_ENCRYPTED_KEY),
      has_signing_material: hasSigningMaterial(active),
      has_runtime_signing_material: hasRuntimeSigningMaterial(active),
      is_locked: isLocked(),
    };
  }

  function logWalletAuthDiagnostics(address){
    try { console.info('[WalletAuth]', getWalletAuthDiagnostics(address)); } catch(_) {}
  }

  function getDebugState(){
    // Safe diagnostics: NO secrets, NO PIN, NO seeds, NO keys
    const info = getMigrationInfo();
    const v1_addr = localStorage.getItem(V1_ADDRESS_KEY) || '';
    const legacy_addr = localStorage.getItem(ADDRESS_KEY) || '';
    const has_v1_encrypted = !!localStorage.getItem(V1_ENCRYPTED_KEY);
    const has_v1_pubkey = !!localStorage.getItem(V1_PUBLIC_KEY);
    const active = getActiveAddress();

    return {
      active_wallet: active,
      wallet_v1_address: v1_addr,
      thr_address: legacy_addr,
      legacy_source_address: getLegacySourceAddress(info),
      canonical_v1_address: getCanonicalMigrationAddress(info),
      wallet_origin: getWalletOrigin(active),
      wallet_identity_status: getWalletIdentityStatus(active),
      migration_new_v1_address: info.new_v1_address || '',
      has_signing_material: hasSigningMaterial(active),
      has_runtime_signing_material: hasRuntimeSigningMaterial(active),
      has_v1_encrypted_key: has_v1_encrypted,
      has_v1_public_key: has_v1_pubkey,
      is_bound: isBound(),
      is_locked: isLocked(),
      is_migrated: isMigrated(),
      ignored_system_wallet: !!_ignoredSystemWalletSource,
      ignored_system_wallet_source: _ignoredSystemWalletSource
    };
  }

  function restoreToMigratedWallet(){
    // Restore wallet_v1_address to migration.new_v1_address without creating new wallet
    // Used when migrated wallet was lost but migration record still exists
    const info = getMigrationInfo();
    if (!info.new_v1_address) {
      const err = new Error('No migration record found to restore');
      err.code = 'RESTORE_FAILED';
      throw err;
    }
    const restoreAddr = normalizeAddress(info.new_v1_address);
    // Block system wallets from being restored
    if (isSystemWalletAddress(restoreAddr)) {
      const err = new Error('system_wallet_not_allowed');
      err.code = 'SYSTEM_WALLET_NOT_ALLOWED';
      err.restore_candidate = restoreAddr;
      throw err;
    }
    const activeAddr = getActiveAddress();
    const canonical = getCanonicalMigrationAddress(info);
    // Log diagnostic (no secrets)
    try {
      console.info('[RestoreToMigrated]', {
        restore_candidate_short: restoreAddr.substring(0, 10) + '...',
        active_address_short: activeAddr ? activeAddr.substring(0, 10) + '...' : 'none',
        canonical_address_short: canonical ? canonical.substring(0, 10) + '...' : 'none',
        status: 'restoring',
        source: 'use_migrated_wallet'
      });
    } catch(_) {}
    localStorage.setItem(V1_ADDRESS_KEY, restoreAddr);
    // Also set legacy address pointer if it exists
    if (isValidThrAddress(restoreAddr)) {
      localStorage.setItem(ADDRESS_KEY, restoreAddr);
    }
    return true;
  }

  function resetActiveWalletPointers(){
    // Clear only active wallet pointer keys, preserve encrypted material
    localStorage.removeItem(ADDRESS_KEY);
    localStorage.removeItem(V1_ADDRESS_KEY);
    // Restore to migration if available, but validate it's not a system wallet
    const info = getMigrationInfo();
    if (info.new_v1_address && isValidThrAddress(info.new_v1_address)) {
      const restoreAddr = normalizeAddress(info.new_v1_address);
      // Block system wallets
      if (!isSystemWalletAddress(restoreAddr)) {
        localStorage.setItem(V1_ADDRESS_KEY, restoreAddr);
      } else {
        // System wallet in migration info - clear the bad migration pointer
        localStorage.removeItem(MIGRATION_META_KEY);
      }
    }
    return getActiveAddress();
  }

  function clearAllWalletData(){
    // Dangerous: clear wallet_v1_address, encrypted key, public key, etc
    // Does NOT call backend
    // Requires confirmation
    localStorage.removeItem(ADDRESS_KEY);
    localStorage.removeItem(V1_ADDRESS_KEY);
    localStorage.removeItem(V1_ENCRYPTED_KEY);
    localStorage.removeItem(V1_PUBLIC_KEY);
    localStorage.removeItem(PIN_KEY);
    unlockedPrivateKeyHex = null;
    // Note: MIGRATION_META_KEY is kept for recovery reference only
    return true;
  }

  function getSigningKeyMismatch(){
    // Return mismatch details for UI recovery flow: {derived_address, active_address, timestamp}
    return lastSigningKeyMismatch ? {...lastSigningKeyMismatch} : null;
  }

  function getUnusableKeyDiagnostics(){
    // Return safe diagnostics for unusable/legacy format key (no secrets, no PIN, no keys)
    return lastUnusableKeyDiagnostics ? {...lastUnusableKeyDiagnostics} : null;
  }

  async function getActiveKeyBinding(canonicalAddress){
    // Check if active key binding exists for canonical address (backend lookup)
    // Returns {bound_key_address, status, ...} or null if no binding
    try {
      const normalized = normalizeAddress(canonicalAddress);
      if (!normalized) return null;

      // Call backend to get binding info
      const response = await fetch(`/api/wallet/v1/key-binding/${encodeURIComponent(normalized)}`);
      if (!response.ok) return null;

      const data = await response.json();
      if (data && data.ok && data.binding && data.binding.status === 'active') {
        return data.binding;
      }
      return null;
    } catch(_) {
      // Network error or binding endpoint unavailable - binding not available
      return null;
    }
  }

  async function clearUnusableSigningKey(){
    // Remove ONLY unusable signing material, NOT wallet identity/balance
    // Safe to remove: encrypted key, runtime key, session cache
    // Must preserve: canonical_v1_address, balances, migration metadata, pledge data
    try {
      // Remove local signing material
      localStorage.removeItem(V1_ENCRYPTED_KEY);
      localStorage.removeItem(V1_PUBLIC_KEY);
      unlockedPrivateKeyHex = null;
      unlockedForAddress = null;
      _clearSessionUnlock();

      // Clear mismatch/unusable diagnostics
      lastSigningKeyMismatch = null;
      lastUnusableKeyDiagnostics = null;

      // Lock the wallet
      localStorage.setItem(LOCK_KEY, '1');

      return {success: true, message: 'Unusable signing key cleared'};
    } catch(err) {
      return {success: false, error: err && err.message ? err.message : 'Failed to clear unusable key'};
    }
  }

  function getWalletState(){
    // Returns wallet state: 'connected_readonly', 'locked', 'signing_ready', 'signing_key_mismatch', 'signing_key_unusable_legacy_format', 'missing_signing_key', or 'not_connected'
    const activeAddr = getActiveAddress();
    if (!activeAddr) return 'not_connected';

    // If there's an unusable/legacy format key recorded
    if (lastUnusableKeyDiagnostics) return 'signing_key_unusable_legacy_format';

    // If there's a signing key mismatch recorded
    if (lastSigningKeyMismatch) return 'signing_key_mismatch';

    // Check for encrypted signing material
    const hasEncryptedKey = !!localStorage.getItem(V1_ENCRYPTED_KEY);

    // If no encrypted key material at all
    if (!hasEncryptedKey) return 'missing_signing_key';

    // If encrypted key exists, check if it's unlocked in memory
    if (unlockedPrivateKeyHex) return 'signing_ready';

    // Encrypted key exists but not unlocked
    return 'locked';
  }

  function clearLocalSigningKey(){
    // Remove encrypted signing material only, preserve active wallet address
    localStorage.removeItem(V1_ENCRYPTED_KEY);
    localStorage.removeItem(V1_PUBLIC_KEY);
    localStorage.removeItem(PIN_KEY);
    unlockedPrivateKeyHex = null;
    lastSigningKeyMismatch = null;
    localStorage.setItem(LOCK_KEY, '1');
    return true;
  }

  async function importSigningKeyForAddress(privateKeyHex, pin, targetAddress) {
    // Validate that imported key derives the target address before saving
    // Returns {success: true} on success or {success: false, error: string} on failure
    try {
      if (!privateKeyHex || !pin || !targetAddress) {
        return {success: false, error: 'Invalid parameters'};
      }
      const normalized = normalizeAddress(targetAddress);
      if (isSystemWalletAddress(normalized)) {
        return {success: false, error: 'Cannot import signing key for system wallet'};
      }
      // Derive public key and address from the imported key
      const secp = await _ensureSecpLoaded();
      if (!secp || !secp.getPublicKey) {
        return {success: false, error: 'Cryptography library unavailable'};
      }
      const pubBytes = secp.getPublicKey(privateKeyHex, true);
      const pubHex = typeof pubBytes === 'string' ? pubBytes.replace(/^0x/, '') : bytesToHex(pubBytes);
      const derivedAddr = await deriveAddressFromPublicKey(pubHex);
      const derivedNormalized = normalizeAddress(derivedAddr);
      // Only allow if derived address matches target
      if (derivedNormalized !== normalized) {
        return {success: false, error: `Imported key derives ${derivedAddr} but target is ${targetAddress}`};
      }
      // Encrypt and save the key
      const encrypted = await encryptPrivateKeyHex(privateKeyHex, pin);
      localStorage.setItem(V1_ENCRYPTED_KEY, encrypted);
      localStorage.setItem(V1_PUBLIC_KEY, pubHex);
      localStorage.setItem(PIN_KEY, pin);
      unlockedPrivateKeyHex = null;
      lastSigningKeyMismatch = null;
      localStorage.setItem(LOCK_KEY, '1');
      return {success: true};
    } catch (e) {
      return {success: false, error: e && e.message ? e.message : 'Failed to import signing key'};
    }
  }

  function disconnect(){ setBound(false); localStorage.setItem(LOCK_KEY, '1'); unlockedPrivateKeyHex = null; }
  function forgetDevice(){ [ADDRESS_KEY,SEND_SECRET_KEY,SEND_SEED_KEY,SEND_SEED_COMPAT_KEY,PIN_KEY,BOUND_KEY,LOCK_KEY,V1_ENCRYPTED_KEY,V1_PUBLIC_KEY,V1_ADDRESS_KEY,MIGRATION_META_KEY].forEach(k => localStorage.removeItem(k)); unlockedPrivateKeyHex = null; }
  function clearSession(){ forgetDevice(); }
  function saveSession({address, sendSeed, pin, bound} = {}){ setAddress(address || ''); setSendSeed(sendSeed || ''); setPin(pin || ''); setBound(bound !== undefined ? !!bound : !!(address && sendSeed)); if (address || sendSeed) localStorage.setItem(LOCK_KEY, '0'); }
  function requirePin(actionLabel = 'continue'){ const stored = getPin(); if(!stored) return true; const entered = prompt(`Enter wallet PIN to ${actionLabel}`); if(entered === null) return false; if(entered !== stored){ alert('Wrong PIN.'); return false; } return true; }

  async function resolveCanonicalWalletAddress(options = {}) {
    const maxAttempts = options.maxAttempts || 10;
    const retryIntervalMs = options.retryIntervalMs || 250;
    const debug = options.debug || false;

    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      // Priority 1: WalletSession state
      try {
        const activeAddr = getActiveAddress();
        if (activeAddr && isValidThrAddress(activeAddr) && !isSystemWalletAddress(activeAddr)) {
          if (debug) console.log('[WalletV1] canonical resolver source: wallet_session.getActiveAddress (attempt ' + attempt + ')');
          return {
            ok: true,
            canonical_v1_address: activeAddr,
            source: 'wallet_session'
          };
        }
      } catch(_) {}

      // Priority 2: localStorage wallet_v1_address
      try {
        const stored = normalizeAddress(localStorage.getItem(V1_ADDRESS_KEY));
        if (stored && isValidThrAddress(stored) && stored !== 'loading...' && !isSystemWalletAddress(stored)) {
          if (debug) console.log('[WalletV1] canonical resolver source: localStorage.wallet_v1_address (attempt ' + attempt + ')');
          return {
            ok: true,
            canonical_v1_address: stored,
            source: 'localStorage'
          };
        }
      } catch(_) {}

      // Priority 3: localStorage canonical_v1_address
      try {
        const stored = normalizeAddress(localStorage.getItem('canonical_v1_address'));
        if (stored && isValidThrAddress(stored) && stored !== 'loading...' && !isSystemWalletAddress(stored)) {
          if (debug) console.log('[WalletV1] canonical resolver source: localStorage.canonical_v1_address (attempt ' + attempt + ')');
          return {
            ok: true,
            canonical_v1_address: stored,
            source: 'localStorage'
          };
        }
      } catch(_) {}

      // Priority 4: localStorage thr_address (fallback)
      try {
        const stored = normalizeAddress(localStorage.getItem(ADDRESS_KEY));
        if (stored && isValidThrAddress(stored) && stored !== 'loading...' && !isSystemWalletAddress(stored)) {
          if (debug) console.log('[WalletV1] canonical resolver source: localStorage.thr_address (attempt ' + attempt + ')');
          return {
            ok: true,
            canonical_v1_address: stored,
            source: 'localStorage'
          };
        }
      } catch(_) {}

      // Priority 5: sessionStorage from restored migration result
      try {
        const migrationMeta = localStorage.getItem(MIGRATION_META_KEY);
        if (migrationMeta) {
          const parsed = JSON.parse(migrationMeta);
          const canonicalFromMeta = normalizeAddress(parsed.canonical_v1_address);
          if (canonicalFromMeta && isValidThrAddress(canonicalFromMeta) && !isSystemWalletAddress(canonicalFromMeta)) {
            if (debug) console.log('[WalletV1] canonical resolver source: migration_metadata (attempt ' + attempt + ')');
            return {
              ok: true,
              canonical_v1_address: canonicalFromMeta,
              source: 'migration_metadata'
            };
          }
        }
      } catch(_) {}

      // Priority 6: Check wallet widget input if visible
      try {
        const walletInputField = document.getElementById('walletV1CanonicalAddr') ||
                                document.getElementById('canonicalWalletAddress');
        if (walletInputField && walletInputField.value) {
          const widgetAddr = normalizeAddress(walletInputField.value);
          if (widgetAddr && isValidThrAddress(widgetAddr) && widgetAddr !== 'loading...' && !isSystemWalletAddress(widgetAddr)) {
            if (debug) console.log('[WalletV1] canonical resolver source: widget_input (attempt ' + attempt + ')');
            return {
              ok: true,
              canonical_v1_address: widgetAddr,
              source: 'widget_input'
            };
          }
        }
      } catch(_) {}

      // Not found yet - wait and retry
      if (attempt < maxAttempts) {
        await new Promise(resolve => setTimeout(resolve, retryIntervalMs));
      }
    }

    // All attempts exhausted
    if (debug) console.log('[WalletV1] canonical resolver exhausted all sources after ' + maxAttempts + ' attempts');
    return {
      ok: false,
      error: 'canonical_address_not_found'
    };
  }

  async function deriveEvmAddress() {
    const pubkey = getPublicKey();
    if (!pubkey) return null;
    try {
      const res = await fetch(`/api/wallet/v1/evm-address?pubkey=${encodeURIComponent(pubkey)}`);
      if (!res.ok) return null;
      const data = await res.json();
      return (data.ok && data.evm_address) ? data.evm_address.toLowerCase() : null;
    } catch { return null; }
  }

  async function signEvmTxHash(txHashHex) {
    if (isLocked() || !isBound()) throw new Error('wallet_locked');
    if (!unlockedPrivateKeyHex) throw new Error('wallet_locked');
    const secp = await _ensureSecpLoaded();
    if (!secp) throw new Error('secp256k1_library_missing');
    const hash = txHashHex.replace(/^0x/, '');
    let sig;
    if (typeof secp.signAsync === 'function') {
      sig = await secp.signAsync(hash, unlockedPrivateKeyHex, { lowS: true });
    } else {
      const result = await secp.sign(hash, unlockedPrivateKeyHex, { lowS: true, recovered: true });
      if (Array.isArray(result)) { sig = result[0]; sig.recovery = result[1]; }
      else sig = result;
    }
    return {
      r: sig.r.toString(16).padStart(64, '0'),
      s: sig.s.toString(16).padStart(64, '0'),
      recovery: sig.recovery ?? 0,
    };
  }

  window.walletSession = {
    version: VERSION,
    ADDRESS_KEY, SEND_SECRET_KEY, SEND_SEED_KEY, PIN_KEY, BOUND_KEY, LOCK_KEY,
    MIGRATION_META_KEY, V1_ENCRYPTED_KEY, V1_PUBLIC_KEY, V1_ADDRESS_KEY,
    getAddress, getActiveAddress, setAddress,
    getMigrationInfo, isMigrated, isVerifiedMigrationInfo, getCanonicalMigrationAddress, getLegacySourceAddress,
    getWalletOrigin, getWalletIdentityStatus, isWalletV1,
    createWalletV1, getPublicKey, canonicalTxMessage, signTransaction,
    migrateLegacyWallet, restoreMigratedWallet, encryptPrivateKeyHex, decryptPrivateKeyHex,
    getCredentialLookupAddress, getSendSeed, setSendSeed, getSendSecret, setSendSecret,
    hasSigningMaterial, hasRuntimeSigningMaterial, getWalletAuthDiagnostics, logWalletAuthDiagnostics,
    getPin, setPin, isLocked, lockWallet, lock: lockWallet, unlockWallet, unlock: unlockWallet, unlock,
    setCustomUnlockHandler, isBound, setBound, disconnect, forgetDevice, clearSession, saveSession, requirePin,
    isUnlockedFor,
    getDebugState, restoreToMigratedWallet, resetActiveWalletPointers, clearAllWalletData, isValidThrAddress,
    persistActiveUserAddress, isSystemWalletAddress,
    getSigningKeyMismatch, getUnusableKeyDiagnostics, clearLocalSigningKey, clearUnusableSigningKey,
    getActiveKeyBinding, importSigningKeyForAddress, getWalletState,
    hasPledgeOrMigrationSource, getModalState,
    generateV1KeyPair, derivePublicKeyAndAddress,
    resolveCanonicalWalletAddress,
    signEvmTxHash, deriveEvmAddress,
  };
})(window);
