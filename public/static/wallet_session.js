(function(window){
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

  let customUnlockHandler = null;
  let unlockedPrivateKeyHex = '';

  function setItem(key, value){
    if(value){
      localStorage.setItem(key, value);
    } else {
      localStorage.removeItem(key);
    }
  }

  function readJson(key){
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : null;
    } catch (_) {
      return null;
    }
  }


  function hexToBytes(hex){
    const clean = String(hex || '').replace(/^0x/, '');
    const out = new Uint8Array(clean.length / 2);
    for(let i = 0; i < out.length; i += 1) out[i] = parseInt(clean.slice(i * 2, i * 2 + 2), 16);
    return out;
  }

  function bytesToHex(bytes){
    return Array.from(bytes || []).map(b => b.toString(16).padStart(2, '0')).join('');
  }

  function bytesToBase64(bytes){
    return btoa(String.fromCharCode.apply(null, Array.from(bytes || [])));
  }

  function base64ToBytes(value){
    return new Uint8Array(atob(value || '').split('').map(ch => ch.charCodeAt(0)));
  }

  function _getSecp(){
    const secp = window.nobleSecp256k1 || window.secp256k1 || window.nobleSecp256k1Lib || window.NobleSecp256k1;
    if(!secp || typeof secp.getPublicKey !== 'function' || typeof secp.sign !== 'function') {
      throw new Error('secp256k1_library_missing');
    }
    return secp;
  }

  async function aesKeyFromPin(pin, saltBytes){
    const raw = await crypto.subtle.importKey('raw', new TextEncoder().encode(pin || ''), 'PBKDF2', false, ['deriveKey']);
    return crypto.subtle.deriveKey(
      { name: 'PBKDF2', salt: saltBytes, iterations: 150000, hash: 'SHA-256' },
      raw,
      { name: 'AES-GCM', length: 256 },
      false,
      ['encrypt', 'decrypt']
    );
  }

  async function encryptPrivateKeyHex(privateKeyHex, pin){
    const salt = crypto.getRandomValues(new Uint8Array(16));
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const key = await aesKeyFromPin(pin, salt);
    const ciphertext = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, hexToBytes(privateKeyHex));
    return JSON.stringify({ v: 1, kdf: 'PBKDF2-SHA256', cipher: 'AES-GCM', salt: bytesToBase64(salt), iv: bytesToBase64(iv), ciphertext: bytesToBase64(new Uint8Array(ciphertext)) });
  }

  async function decryptPrivateKeyHex(blob, pin){
    const data = typeof blob === 'string' ? JSON.parse(blob) : blob;
    const salt = data.salt ? base64ToBytes(data.salt) : hexToBytes(data.salt_hex || '');
    const iv = data.iv ? base64ToBytes(data.iv) : hexToBytes(data.iv_hex || '');
    const ciphertext = data.ciphertext ? base64ToBytes(data.ciphertext) : hexToBytes(data.ciphertext_hex || '');
    const key = await aesKeyFromPin(pin, salt);
    const plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, ciphertext);
    return bytesToHex(new Uint8Array(plain));
  }

  async function sha256Hex(message){
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(message));
    return bytesToHex(new Uint8Array(digest));
  }

  function canonicalTxMessage(txCore){
    const tx = txCore || {};
    return JSON.stringify({
      amount: tx.amount,
      from: tx.from,
      nonce: tx.nonce,
      timestamp: tx.timestamp,
      to: tx.to,
      token: tx.token || 'THR'
    });
  }

  function isWalletV1(){
    return !!(localStorage.getItem(V1_ENCRYPTED_KEY) || localStorage.getItem(V1_PUBLIC_KEY) || localStorage.getItem(V1_ADDRESS_KEY) || unlockedPrivateKeyHex);
  }

  function getPublicKey(){
    return localStorage.getItem(V1_PUBLIC_KEY) || '';
  }

  async function deriveAddressFromPublicKey(publicKeyHex){
    const resp = await fetch('/api/v1/address/derive', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ compressed_public_key: publicKeyHex })
    });
    const data = await resp.json();
    if(!resp.ok || !(data.address || data.thr_address)) throw new Error(data.error || 'address_derivation_failed');
    return data.address || data.thr_address;
  }

  async function createWalletV1({ pin } = {}){
    if(!pin) throw new Error('pin_required');
    const secp = _getSecp();
    const priv = secp.utils && typeof secp.utils.randomPrivateKey === 'function'
      ? secp.utils.randomPrivateKey()
      : crypto.getRandomValues(new Uint8Array(32));
    const privateKeyHex = typeof priv === 'string' ? priv.replace(/^0x/, '') : bytesToHex(priv);
    const pub = secp.getPublicKey(privateKeyHex, true);
    const publicKeyHex = typeof pub === 'string' ? pub.replace(/^0x/, '') : bytesToHex(pub);
    const encrypted = await encryptPrivateKeyHex(privateKeyHex, pin);
    const address = await deriveAddressFromPublicKey(publicKeyHex);
    localStorage.setItem(V1_ENCRYPTED_KEY, encrypted);
    localStorage.setItem(V1_PUBLIC_KEY, publicKeyHex);
    localStorage.setItem(V1_ADDRESS_KEY, address);
    setAddress(address);
    setPin(pin);
    unlockedPrivateKeyHex = privateKeyHex;
    setBound(true);
    localStorage.setItem(LOCK_KEY, '0');
    return { address, publicKey: publicKeyHex };
  }

  async function signTransaction(txCore){
    if(!unlockedPrivateKeyHex) throw new Error('missing_wallet_signing_material');
    const secp = _getSecp();
    const message = canonicalTxMessage(txCore || {});
    const digestHex = await sha256Hex(message);
    const sig = await secp.sign(digestHex, unlockedPrivateKeyHex, { der: true });
    const signature = typeof sig === 'string' ? sig.replace(/^0x/, '') : bytesToHex(sig);
    return Object.assign({}, txCore, { publicKey: getPublicKey(), signature });
  }

  async function migrateLegacyWallet({ old_address, legacy_secret, pin } = {}){
    const created = await createWalletV1({ pin });
    const resp = await fetch('/api/v1/wallet/migrate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ old_thr_address: old_address, legacy_secret, new_compressed_public_key: created.publicKey })
    });
    const data = await resp.json();
    if(!resp.ok || data.ok === false) throw new Error(data.error || 'wallet_migration_failed');
    const meta = { old_address, new_v1_address: created.address, migration_tx_id: data.migration_tx_id || data.tx_id || '', migrated_at: data.migrated_at || new Date().toISOString() };
    localStorage.setItem(MIGRATION_META_KEY, JSON.stringify(meta));
    localStorage.removeItem(SEND_SECRET_KEY);
    localStorage.removeItem(SEND_SEED_KEY);
    localStorage.removeItem(SEND_SEED_COMPAT_KEY);
    return Object.assign({}, data, meta);
  }

  function getMigrationInfo(){
    const meta = readJson(MIGRATION_META_KEY) || readJson('wallet_v1_migration_info') || readJson('wallet_migration_meta') || {};
    const oldAddress = meta.old_address || meta.oldAddress || localStorage.getItem('wallet_v1_old_address') || '';
    const newAddress = meta.new_v1_address || meta.newAddress || localStorage.getItem('wallet_v1_address') || '';
    return Object.assign({}, meta, {
      old_address: oldAddress,
      new_v1_address: newAddress,
      migrated_at: meta.migrated_at || meta.migratedAt || ''
    });
  }

  function isMigrated(){
    const info = getMigrationInfo();
    return !!(info.old_address && info.new_v1_address);
  }

  function getAddress(){
    return localStorage.getItem(V1_ADDRESS_KEY) || localStorage.getItem(ADDRESS_KEY) || '';
  }

  function getActiveAddress(){
    const info = getMigrationInfo();
    if (isMigrated() && info.new_v1_address) return info.new_v1_address;
    return getAddress();
  }

  function setAddress(addr){
    setItem(ADDRESS_KEY, addr ? addr.trim() : '');
  }

  function scopedCredentialKeys(address){
    if(!address) return [];
    return [
      `${SEND_SECRET_KEY}:${address}`,
      `${SEND_SEED_KEY}:${address}`,
      `${SEND_SEED_COMPAT_KEY}:${address}`,
      `${SEND_SECRET_KEY}_${address}`,
      `${SEND_SEED_KEY}_${address}`,
      `${SEND_SEED_COMPAT_KEY}_${address}`,
      `wallet:${address}:send_secret`,
      `wallet:${address}:send_seed`,
      `wallet:${address}:thr_secret`
    ];
  }

  function getRawSeedForAddress(address){
    for (const key of scopedCredentialKeys(address)) {
      const value = localStorage.getItem(key) || sessionStorage.getItem(key);
      if (value) return value;
    }
    return '';
  }

  function getCredentialLookupAddress(address){
    const active = address || getActiveAddress() || getAddress();
    const info = getMigrationInfo();
    if (active && getRawSeedForAddress(active)) return active;
    if (isMigrated()) {
      if (info.new_v1_address && getRawSeedForAddress(info.new_v1_address)) return info.new_v1_address;
      if (info.old_address && getRawSeedForAddress(info.old_address)) return info.old_address;
    }
    return active || info.old_address || info.new_v1_address || '';
  }

  function getSendSeed(address){
    const active = address || getActiveAddress() || getAddress();
    const info = getMigrationInfo();
    const direct = getRawSeedForAddress(active);
    if (direct) return direct;
    if (isMigrated()) {
      const newSeed = getRawSeedForAddress(info.new_v1_address);
      if (newSeed) return newSeed;
      const oldSeed = getRawSeedForAddress(info.old_address);
      if (oldSeed) return oldSeed;
    }
    return (
      localStorage.getItem(SEND_SECRET_KEY) ||
      localStorage.getItem(SEND_SEED_KEY) ||
      localStorage.getItem(SEND_SEED_COMPAT_KEY) ||
      ''
    );
  }

  function hasSigningMaterial(address){
    return !!(unlockedPrivateKeyHex || localStorage.getItem(V1_ENCRYPTED_KEY) || getSendSeed(address));
  }

  function getWalletAuthDiagnostics(address){
    const info = getMigrationInfo();
    const active = address || getActiveAddress() || getAddress();
    const credentialAddress = getCredentialLookupAddress(active);
    return {
      active_wallet_address: active || '',
      credential_lookup_address: credentialAddress || '',
      migration_old_address: info.old_address || '',
      migration_new_v1_address: info.new_v1_address || '',
      has_encrypted_send_seed: !!(
        localStorage.getItem(`encrypted_send_seed:${credentialAddress}`) ||
        localStorage.getItem(`wallet:${credentialAddress}:encrypted_send_seed`) ||
        localStorage.getItem('encrypted_send_seed')
      ),
      has_signing_material: hasSigningMaterial(active)
    };
  }

  function logWalletAuthDiagnostics(address){
    try {
      console.info('[WalletAuth]', getWalletAuthDiagnostics(address));
    } catch (_) {}
  }

  function setSendSeed(seed){
    setItem(SEND_SECRET_KEY, seed ? seed.trim() : '');
    // keep legacy keys in sync for older code paths
    setItem(SEND_SEED_KEY, seed ? seed.trim() : '');
    setItem(SEND_SEED_COMPAT_KEY, seed ? seed.trim() : '');
  }

  function getAddress(){ return localStorage.getItem(V1_ADDRESS_KEY) || localStorage.getItem(ADDRESS_KEY) || ''; }
  function setAddress(addr){ setItem(ADDRESS_KEY, addr ? addr.trim() : ''); }
  function getSendSeed(){ return localStorage.getItem(SEND_SECRET_KEY) || localStorage.getItem(SEND_SEED_KEY) || localStorage.getItem(SEND_SEED_COMPAT_KEY) || ''; }
  function setSendSeed(seed){ setItem(SEND_SECRET_KEY, seed ? seed.trim() : ''); setItem(SEND_SEED_KEY, seed ? seed.trim() : ''); setItem(SEND_SEED_COMPAT_KEY, seed ? seed.trim() : ''); }
  const getSendSecret = getSendSeed;
  const setSendSecret = setSendSeed;

  function getPin(){
    return localStorage.getItem(PIN_KEY) || '';
  }

  function setPin(pin){
    setItem(PIN_KEY, pin ? pin.trim() : '');
  }

  function isLocked(){
    return localStorage.getItem(LOCK_KEY) === '1';
  }

  function lockWallet(){
    // Keep credentials local but require unlock before use
    unlockedPrivateKeyHex = '';
    setBound(false);
    localStorage.setItem(LOCK_KEY, '1');
  }

  function setCustomUnlockHandler(fn){
    customUnlockHandler = typeof fn === 'function' ? fn : null;
  }

  async function unlockWallet(options = {}){
    // Short-circuit if already unlocked/bound with signing material
    if (!isLocked() && isBound() && hasSigningMaterial(options.address)) return true;

    // Custom (passkey/biometric) handler first
    if (customUnlockHandler) {
      try {
        const ok = await customUnlockHandler(options);
        if (ok) {
          setBound(true);
          localStorage.setItem(LOCK_KEY, '0');
          return true;
        }
      } catch (e) {
        console.warn('Custom unlock handler failed', e);
      }
    }

    // Optional biometric hook from wrapper
    if (options.useBiometrics && window.ThronosWalletHooks && typeof window.ThronosWalletHooks.biometricUnlock === 'function') {
      const ok = await window.ThronosWalletHooks.biometricUnlock();
      if (ok) {
        setBound(true);
        localStorage.setItem(LOCK_KEY, '0');
        return true;
      }
    }

    // PIN unlock
    const storedPin = getPin();
    if (storedPin) {
      const providedPin = options.pin || null;
      if (providedPin) {
        if (providedPin === storedPin && hasSigningMaterial(options.address)) {
          if (!unlockedPrivateKeyHex && localStorage.getItem(V1_ENCRYPTED_KEY)) {
            unlockedPrivateKeyHex = await decryptPrivateKeyHex(localStorage.getItem(V1_ENCRYPTED_KEY), providedPin);
          }
          setBound(true);
          localStorage.setItem(LOCK_KEY, '0');
          return true;
        }
        return false;
      }
      if (options.prompt !== false) {
        const entered = prompt('Enter wallet PIN to unlock');
        if (entered === null) return false;
        if (entered === storedPin && hasSigningMaterial(options.address)) {
          if (!unlockedPrivateKeyHex && localStorage.getItem(V1_ENCRYPTED_KEY)) {
            unlockedPrivateKeyHex = await decryptPrivateKeyHex(localStorage.getItem(V1_ENCRYPTED_KEY), entered);
          }
          setBound(true);
          localStorage.setItem(LOCK_KEY, '0');
          return true;
        }
        alert('Wrong PIN or missing wallet signing material.');
        return false;
      }
    }

    // If no PIN set, consider unlocked with saved credentials
    const hasCreds = !!(getAddress() && hasSigningMaterial(options.address));
    if (hasCreds) {
      setBound(true);
      localStorage.setItem(LOCK_KEY, '0');
      return true;
    }
    const hasLegacyCreds = !!(getAddress() && getSendSeed() && pin === getPin());
    if (hasLegacyCreds) { setBound(true); localStorage.setItem(LOCK_KEY, '0'); return true; }
    return false;
  }

  function isBound(){
    return localStorage.getItem(BOUND_KEY) === '1';
  }

  function setBound(v){
    localStorage.setItem(BOUND_KEY, v ? '1' : '0');
  }

  function disconnect(){
    // Only clear bound flag, keep credentials for PIN-only unlock
    setBound(false);
    localStorage.setItem(LOCK_KEY, '1');
  }

  function forgetDevice(){
    // Full wipe - only for "Forget Device" action
    localStorage.removeItem(ADDRESS_KEY);
    localStorage.removeItem(SEND_SECRET_KEY);
    localStorage.removeItem(SEND_SEED_KEY);
    localStorage.removeItem(SEND_SEED_COMPAT_KEY);
    localStorage.removeItem(PIN_KEY);
    localStorage.removeItem(BOUND_KEY);
    localStorage.removeItem(LOCK_KEY);
    localStorage.removeItem(V1_ENCRYPTED_KEY);
    localStorage.removeItem(V1_PUBLIC_KEY);
    localStorage.removeItem(V1_ADDRESS_KEY);
    localStorage.removeItem(MIGRATION_META_KEY);
    unlockedPrivateKeyHex = '';
  }

  function clearSession(){
    // Alias for backward compatibility - calls forgetDevice
    forgetDevice();
  }

  function saveSession({address, sendSeed, pin, bound}={}){
    setAddress(address || '');
    setSendSeed(sendSeed || '');
    setPin(pin || '');
    setBound(bound !== undefined ? !!bound : !!(address && sendSeed));
    // Save sessions default to unlocked state once credentials are present
    if (address || sendSeed) {
      localStorage.setItem(LOCK_KEY, '0');
    }
  }

  function disconnect(){ setBound(false); localStorage.setItem(LOCK_KEY, '1'); unlockedPrivateKeyHex = null; }
  function forgetDevice(){ [ADDRESS_KEY,SEND_SECRET_KEY,SEND_SEED_KEY,SEND_SEED_COMPAT_KEY,PIN_KEY,BOUND_KEY,LOCK_KEY,V1_ENCRYPTED_KEY,V1_PUBLIC_KEY,V1_ADDRESS_KEY,V1_MIGRATION_META].forEach(k => localStorage.removeItem(k)); unlockedPrivateKeyHex = null; }
  function clearSession(){ forgetDevice(); }
  function saveSession({address, sendSeed, pin, bound}){ setAddress(address || ''); setSendSeed(sendSeed || ''); setPin(pin || ''); setBound(bound !== undefined ? !!bound : !!(address && sendSeed)); if (address || sendSeed) localStorage.setItem(LOCK_KEY, '0'); }
  function requirePin(actionLabel = 'continue'){ const stored = getPin(); if(!stored) return true; const entered = prompt(`Enter wallet PIN to ${actionLabel}`); if(entered === null) return false; if(entered !== stored){ alert('Wrong PIN.'); return false; } return true; }

  window.walletSession = {
    ADDRESS_KEY,
    SEND_SECRET_KEY,
    SEND_SEED_KEY,
    PIN_KEY,
    BOUND_KEY,
    LOCK_KEY,
    MIGRATION_META_KEY,
    V1_ENCRYPTED_KEY,
    V1_PUBLIC_KEY,
    V1_ADDRESS_KEY,
    getAddress,
    getActiveAddress,
    setAddress,
    getMigrationInfo,
    isMigrated,
    isWalletV1,
    createWalletV1,
    getPublicKey,
    canonicalTxMessage,
    signTransaction,
    migrateLegacyWallet,
    encryptPrivateKeyHex,
    decryptPrivateKeyHex,
    getCredentialLookupAddress,
    getSendSeed,
    setSendSeed,
    getSendSecret,
    setSendSecret,
    hasSigningMaterial,
    getWalletAuthDiagnostics,
    logWalletAuthDiagnostics,
    getPin,
    setPin,
    isLocked,
    lockWallet,
    lock: lockWallet,
    unlockWallet,
    unlock: unlockWallet,
    setCustomUnlockHandler,
    isBound,
    setBound,
    disconnect,
    forgetDevice,
    clearSession,
    saveSession,
    requirePin
  };
})(window);
