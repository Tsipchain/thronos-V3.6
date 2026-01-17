(function(window){
  const ADDRESS_KEY = 'thr_address';
  const SEND_SECRET_KEY = 'send_secret';
  const SEND_SEED_KEY = 'send_seed';
  const SEND_SEED_COMPAT_KEY = 'thr_secret';
  const PIN_KEY = 'wallet_pin';
  const BOUND_KEY = 'wallet_bound';
  const LOCK_KEY = 'wallet_locked';

  let customUnlockHandler = null;

  function setItem(key, value){
    if(value){
      localStorage.setItem(key, value);
    } else {
      localStorage.removeItem(key);
    }
  }

  function getAddress(){
    return localStorage.getItem(ADDRESS_KEY) || '';
  }

  function setAddress(addr){
    setItem(ADDRESS_KEY, addr ? addr.trim() : '');
  }

  function getSendSeed(){
    return (
      localStorage.getItem(SEND_SECRET_KEY) ||
      localStorage.getItem(SEND_SEED_KEY) ||
      localStorage.getItem(SEND_SEED_COMPAT_KEY) ||
      ''
    );
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
    // Short-circuit if already unlocked/bound
    if (!isLocked() && isBound()) return true;

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
        if (providedPin === storedPin) {
          setBound(true);
          localStorage.setItem(LOCK_KEY, '0');
          return true;
        }
        return false;
      }
      if (options.prompt !== false) {
        const entered = prompt('Enter wallet PIN to unlock');
        if (entered === null) return false;
        if (entered === storedPin) {
          setBound(true);
          localStorage.setItem(LOCK_KEY, '0');
          return true;
        }
        alert('Wrong PIN.');
        return false;
      }
    }

    // If no PIN set, consider unlocked with saved credentials
    const hasCreds = !!(getAddress() && getSendSeed());
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

  function saveSession({address, sendSeed, pin, bound}){
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
    getAddress,
    setAddress,
    getSendSeed,
    setSendSeed,
    getSendSecret,
    setSendSecret,
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
