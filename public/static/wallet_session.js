(function(window){
  const ADDRESS_KEY = 'thr_address';
  const SEND_SECRET_KEY = 'send_secret';
  const SEND_SEED_KEY = 'send_seed';
  const SEND_SEED_COMPAT_KEY = 'thr_secret';
  const PIN_KEY = 'wallet_pin';
  const BOUND_KEY = 'wallet_bound';
  const LOCK_KEY = 'wallet_locked';
  const MIGRATION_META_KEY = 'wallet_v1_migration_meta';

  let customUnlockHandler = null;

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
    return localStorage.getItem(ADDRESS_KEY) || '';
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
    return !!getSendSeed(address);
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
  function getPin(){ return localStorage.getItem(PIN_KEY) || ''; }
  function setPin(pin){ setItem(PIN_KEY, pin ? pin.trim() : ''); }

  function lockWallet(){ unlockedPrivateKeyHex = null; setBound(false); localStorage.setItem(LOCK_KEY, '1'); }
  function lock(){ return lockWallet(); }
  function setCustomUnlockHandler(fn){ customUnlockHandler = typeof fn === 'function' ? fn : null; }

  function hexToBytes(hex){ const out=[]; for(let i=0;i<hex.length;i+=2) out.push(parseInt(hex.slice(i,i+2),16)); return new Uint8Array(out); }
  function bytesToHex(bytes){ return Array.from(bytes).map(b=>b.toString(16).padStart(2,'0')).join(''); }
  async function sha256Hex(s){ const d = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s)); return bytesToHex(new Uint8Array(d)); }
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
    return window.nobleSecp256k1 || window.secp256k1 || window.nobleSecp256k1Lib || window.NobleSecp256k1 || null;
  }

  async function _ensureSecpLoaded(){
    if (_getSecp()) return _getSecp();
    if (window.__nobleSecp256k1Ready && typeof window.__nobleSecp256k1Ready.then === 'function') {
      try { await window.__nobleSecp256k1Ready; } catch(_) {}
    }
    return _getSecp();
  }

  async function deriveAddressFromPublicKey(publicKey){
    const res = await fetch('/api/v1/address/derive', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({public_key: publicKey})});
    const data = await res.json();
    if (!res.ok || !data.address) throw new Error(data.error || 'address_derivation_failed');
    return data.address;
  }

  async function createWalletV1({pin} = {}){
    const secp = await _ensureSecpLoaded();
    if (!secp || !secp.getPublicKey || !secp.utils || !secp.sign) throw new Error('secp256k1_library_missing');
    if (!pin) throw new Error('pin_required');
    const privBytes = secp.utils.randomPrivateKey ? secp.utils.randomPrivateKey() : crypto.getRandomValues(new Uint8Array(32));
    const priv = bytesToHex(privBytes);
    const pub = bytesToHex(secp.getPublicKey(priv, true));
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
    getAddress,
    getActiveAddress,
    setAddress,
    getMigrationInfo,
    isMigrated,
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
    unlockWallet,
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
