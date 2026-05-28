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

  function requirePin(actionLabel = 'continue'){
    const stored = getPin();
    if(!stored) return true;
    const entered = prompt(`Enter wallet PIN to ${actionLabel}`);
    if(entered === null) return false;
    if(entered !== stored){
      alert('Wrong PIN.');
      return false;
    }
    return true;
  }

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
