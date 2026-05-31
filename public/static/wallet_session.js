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

  let customUnlockHandler = null;
  let unlockedPrivateKeyHex = null;
  let unlockedForAddress = null; // Track which address the current in-memory key belongs to

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

  function lockWallet(){ unlockedPrivateKeyHex = null; unlockedForAddress = null; localStorage.setItem(LOCK_KEY, '1'); }
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
  function getSubtleCrypto(){
    const webCrypto = (typeof crypto !== 'undefined' && crypto) || (typeof window !== 'undefined' && window.crypto) || (typeof globalThis !== 'undefined' && globalThis.crypto) || null;
    return webCrypto && webCrypto.subtle ? webCrypto.subtle : null;
  }
  async function ensureSecpAsyncCrypto(secp){
    const subtle = getSubtleCrypto();
    if (!secp || !subtle) throw new Error('wallet_crypto_not_ready');
    const sha256Async = async (...msgs) => new Uint8Array(await subtle.digest('SHA-256', concatBytes(msgs)));
    const hmacSha256Async = async (key, ...msgs) => {
      const cryptoKey = await subtle.importKey('raw', toUint8Bytes(key), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
      return new Uint8Array(await subtle.sign('HMAC', cryptoKey, concatBytes(msgs)));
    };
    if (!getSecpContainer(secp, 'etc')) secp.etc = {};
    if (!getSecpContainer(secp, 'hashes')) secp.hashes = {};
    if (!readSecpHelper(secp, 'etc', 'sha256Async')) secp.etc.sha256Async = sha256Async;
    if (!readSecpHelper(secp, 'etc', 'hmacSha256Async')) secp.etc.hmacSha256Async = hmacSha256Async;
    if (!readSecpHelper(secp, 'hashes', 'sha256Async')) secp.hashes.sha256Async = sha256Async;
    if (!readSecpHelper(secp, 'hashes', 'hmacSha256Async')) secp.hashes.hmacSha256Async = hmacSha256Async;
    if (!readSecpHelper(secp, 'utils', 'sha256') && !readSecpHelper(secp, 'hashes', 'sha256')) {
      // Noble v2 uses async helpers for nonce generation; keep sync slots untouched when unavailable.
    }
  }
  function isSecpCryptoHelperError(err){
    const msg = String((err && (err.message || err)) || '').toLowerCase();
    return msg.includes('option not supported') || msg.includes('hmacsha256sync') || msg.includes('sha256sync') || msg.includes('hashes');
  }
  async function signDigestDerHex(secp, digestHex, privateKeyHex){
    try {
      await ensureSecpAsyncCrypto(secp);
      if (typeof secp.signAsync === 'function') {
        return normalizeSignatureToDerHex(await secp.signAsync(digestHex, privateKeyHex));
      }
      return normalizeSignatureToDerHex(await secp.sign(digestHex, privateKeyHex, { der: true }));
    } catch (err) {
      if (!isSecpCryptoHelperError(err)) throw err;
      try {
        await ensureSecpAsyncCrypto(secp);
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
    return { address, publicKey: pub };
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
    const enc = localStorage.getItem(V1_ENCRYPTED_KEY);
    if (enc) {
      try { unlockedPrivateKeyHex = await decryptPrivateKeyHex(enc, pin); unlockedForAddress = activeAddr; setBound(true); localStorage.setItem(LOCK_KEY, '0'); return true; }
      catch(_) { return false; }
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
      console.error('No migration record found to restore');
      return false;
    }
    localStorage.setItem(V1_ADDRESS_KEY, info.new_v1_address);
    // Also set legacy address pointer if it exists
    if (isValidThrAddress(info.new_v1_address)) {
      localStorage.setItem(ADDRESS_KEY, info.new_v1_address);
    }
    return true;
  }

  function resetActiveWalletPointers(){
    // Clear only active wallet pointer keys, preserve encrypted material
    localStorage.removeItem(ADDRESS_KEY);
    localStorage.removeItem(V1_ADDRESS_KEY);
    // Restore to migration if available
    const info = getMigrationInfo();
    if (info.new_v1_address && isValidThrAddress(info.new_v1_address)) {
      localStorage.setItem(V1_ADDRESS_KEY, info.new_v1_address);
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

  function disconnect(){ setBound(false); localStorage.setItem(LOCK_KEY, '1'); unlockedPrivateKeyHex = null; }
  function forgetDevice(){ [ADDRESS_KEY,SEND_SECRET_KEY,SEND_SEED_KEY,SEND_SEED_COMPAT_KEY,PIN_KEY,BOUND_KEY,LOCK_KEY,V1_ENCRYPTED_KEY,V1_PUBLIC_KEY,V1_ADDRESS_KEY,MIGRATION_META_KEY].forEach(k => localStorage.removeItem(k)); unlockedPrivateKeyHex = null; }
  function clearSession(){ forgetDevice(); }
  function saveSession({address, sendSeed, pin, bound} = {}){ setAddress(address || ''); setSendSeed(sendSeed || ''); setPin(pin || ''); setBound(bound !== undefined ? !!bound : !!(address && sendSeed)); if (address || sendSeed) localStorage.setItem(LOCK_KEY, '0'); }
  function requirePin(actionLabel = 'continue'){ const stored = getPin(); if(!stored) return true; const entered = prompt(`Enter wallet PIN to ${actionLabel}`); if(entered === null) return false; if(entered !== stored){ alert('Wrong PIN.'); return false; } return true; }

  window.walletSession = {
    version: VERSION,
    ADDRESS_KEY, SEND_SECRET_KEY, SEND_SEED_KEY, PIN_KEY, BOUND_KEY, LOCK_KEY,
    MIGRATION_META_KEY, V1_ENCRYPTED_KEY, V1_PUBLIC_KEY, V1_ADDRESS_KEY,
    getAddress, getActiveAddress, setAddress,
    getMigrationInfo, isMigrated, isVerifiedMigrationInfo, getCanonicalMigrationAddress, getLegacySourceAddress,
    getWalletOrigin, getWalletIdentityStatus, isWalletV1,
    createWalletV1, getPublicKey, canonicalTxMessage, signTransaction,
    migrateLegacyWallet, encryptPrivateKeyHex, decryptPrivateKeyHex,
    getCredentialLookupAddress, getSendSeed, setSendSeed, getSendSecret, setSendSecret,
    hasSigningMaterial, hasRuntimeSigningMaterial, getWalletAuthDiagnostics, logWalletAuthDiagnostics,
    getPin, setPin, isLocked, lockWallet, lock: lockWallet, unlockWallet, unlock: unlockWallet, unlock,
    setCustomUnlockHandler, isBound, setBound, disconnect, forgetDevice, clearSession, saveSession, requirePin,
    isUnlockedFor,
    getDebugState, restoreToMigratedWallet, resetActiveWalletPointers, clearAllWalletData, isValidThrAddress,
    persistActiveUserAddress, isSystemWalletAddress
  };
})(window);
