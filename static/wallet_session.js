(function(window){
  const ADDRESS_KEY = 'thr_address';
  const SEND_SEED_KEY = 'send_seed';
  const SEND_SEED_COMPAT_KEY = 'thr_secret';
  const PIN_KEY = 'thr_pin';

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
    return localStorage.getItem(SEND_SEED_KEY) || localStorage.getItem(SEND_SEED_COMPAT_KEY) || '';
  }

  function setSendSeed(seed){
    setItem(SEND_SEED_KEY, seed ? seed.trim() : '');
    // keep legacy key in sync for older code paths
    setItem(SEND_SEED_COMPAT_KEY, seed ? seed.trim() : '');
  }

  function getPin(){
    return localStorage.getItem(PIN_KEY) || '';
  }

  function setPin(pin){
    setItem(PIN_KEY, pin ? pin.trim() : '');
  }

  function clearSession(){
    localStorage.removeItem(ADDRESS_KEY);
    localStorage.removeItem(SEND_SEED_KEY);
    localStorage.removeItem(SEND_SEED_COMPAT_KEY);
    localStorage.removeItem(PIN_KEY);
  }

  function saveSession({address, sendSeed, pin}){
    setAddress(address || '');
    setSendSeed(sendSeed || '');
    setPin(pin || '');
  }

  window.walletSession = {
    ADDRESS_KEY,
    SEND_SEED_KEY,
    PIN_KEY,
    getAddress,
    setAddress,
    getSendSeed,
    setSendSeed,
    getPin,
    setPin,
    clearSession,
    saveSession
  };
})(window);
