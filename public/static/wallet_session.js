(function(window){
  const ADDRESS_KEY = 'thr_address';
  const SEND_SECRET_KEY = 'send_secret';
  const SEND_SEED_KEY = 'send_seed';
  const SEND_SEED_COMPAT_KEY = 'thr_secret';
  const PIN_KEY = 'wallet_pin';
  const BOUND_KEY = 'wallet_bound';
  const LOCK_KEY = 'wallet_locked';

  const V1_ENCRYPTED_KEY = 'wallet_v1_encrypted_priv';
  const V1_PUBLIC_KEY = 'wallet_v1_public_key';
  const V1_ADDRESS_KEY = 'wallet_v1_address';
  const V1_MIGRATION_META = 'wallet_v1_migration_meta';

  let customUnlockHandler = null;
  let unlockedPrivateKeyHex = null;

  function setItem(key, value){ if(value){ localStorage.setItem(key, value); } else { localStorage.removeItem(key); } }
  function getAddress(){ return localStorage.getItem(V1_ADDRESS_KEY) || localStorage.getItem(ADDRESS_KEY) || ''; }
  function setAddress(addr){ setItem(ADDRESS_KEY, addr ? addr.trim() : ''); }
  function getSendSeed(){ return (localStorage.getItem(SEND_SECRET_KEY)||localStorage.getItem(SEND_SEED_KEY)||localStorage.getItem(SEND_SEED_COMPAT_KEY)||''); }
  function setSendSeed(seed){ setItem(SEND_SECRET_KEY, seed ? seed.trim() : ''); setItem(SEND_SEED_KEY, seed ? seed.trim() : ''); setItem(SEND_SEED_COMPAT_KEY, seed ? seed.trim() : ''); }
  const getSendSecret = getSendSeed; const setSendSecret = setSendSeed;
  function getPin(){ return localStorage.getItem(PIN_KEY) || ''; }
  function setPin(pin){ setItem(PIN_KEY, pin ? pin.trim() : ''); }
  function isLocked(){ return localStorage.getItem(LOCK_KEY) === '1'; }
  function lockWallet(){ unlockedPrivateKeyHex = null; setBound(false); localStorage.setItem(LOCK_KEY, '1'); }
  function setCustomUnlockHandler(fn){ customUnlockHandler = typeof fn === 'function' ? fn : null; }
  function isBound(){ return localStorage.getItem(BOUND_KEY) === '1'; }
  function setBound(v){ localStorage.setItem(BOUND_KEY, v ? '1' : '0'); }

  async function sha256Hex(s){ const b = new TextEncoder().encode(s); const d = await crypto.subtle.digest('SHA-256', b); return Array.from(new Uint8Array(d)).map(x=>x.toString(16).padStart(2,'0')).join(''); }
  async function aesKeyFromPin(pin, salt){
    const material = await crypto.subtle.importKey('raw', new TextEncoder().encode(pin), 'PBKDF2', false, ['deriveKey']);
    return crypto.subtle.deriveKey({name:'PBKDF2',salt,iterations:250000,hash:'SHA-256'}, material, {name:'AES-GCM',length:256}, false, ['encrypt','decrypt']);
  }
  function hexToBytes(hex){ const out=[]; for(let i=0;i<hex.length;i+=2) out.push(parseInt(hex.slice(i,i+2),16)); return new Uint8Array(out); }
  function bytesToHex(bytes){ return Array.from(bytes).map(b=>b.toString(16).padStart(2,'0')).join(''); }

  async function encryptPrivateKeyHex(privateKeyHex, pin){
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const salt = crypto.getRandomValues(new Uint8Array(16));
    const key = await aesKeyFromPin(pin, salt);
    const cipher = await crypto.subtle.encrypt({name:'AES-GCM',iv}, key, hexToBytes(privateKeyHex));
    return JSON.stringify({v:1,salt:bytesToHex(salt),iv:bytesToHex(iv),ct:bytesToHex(new Uint8Array(cipher))});
  }

  async function decryptPrivateKeyHex(blob, pin){
    const p = JSON.parse(blob);
    const key = await aesKeyFromPin(pin, hexToBytes(p.salt));
    const clear = await crypto.subtle.decrypt({name:'AES-GCM',iv:hexToBytes(p.iv)}, key, hexToBytes(p.ct));
    return bytesToHex(new Uint8Array(clear));
  }

  function _getSecp(){
    return window.nobleSecp256k1 || window.secp256k1 || null;
  }

  async function deriveAddressFromPublicKey(publicKey){
    const res = await fetch('/api/v1/address/derive', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({publicKey})});
    const d = await res.json();
    if (!res.ok || !d.address) throw new Error(d.error || 'address_derivation_failed');
    return d.address;
  }

  async function createWalletV1({pin} = {}){
    const secp = _getSecp();
    if (!secp || !secp.utils || !secp.getPublicKey) throw new Error('secp256k1_library_missing');
    if (!pin) throw new Error('pin_required');
    const priv = bytesToHex(secp.utils.randomPrivateKey ? secp.utils.randomPrivateKey() : crypto.getRandomValues(new Uint8Array(32)));
    const pub = bytesToHex(secp.getPublicKey(priv, true));
    const address = await deriveAddressFromPublicKey(pub);
    const enc = await encryptPrivateKeyHex(priv, pin);
    localStorage.setItem(V1_ENCRYPTED_KEY, enc);
    localStorage.setItem(V1_PUBLIC_KEY, pub);
    localStorage.setItem(V1_ADDRESS_KEY, address);
    localStorage.setItem(PIN_KEY, pin);
    localStorage.setItem(LOCK_KEY, '0');
    setBound(true);
    unlockedPrivateKeyHex = priv;
    return { address, publicKey: pub };
  }

  async function unlockWallet(options = {}){
    if (!isLocked() && isBound()) return true;
    if (customUnlockHandler) { try { const ok = await customUnlockHandler(options); if (ok) { setBound(true); localStorage.setItem(LOCK_KEY,'0'); return true; } } catch(_) {} }
    const pin = options.pin || (options.prompt !== false ? prompt('Enter wallet PIN to unlock') : null);
    if (!pin) return false;
    const enc = localStorage.getItem(V1_ENCRYPTED_KEY);
    if (enc) {
      try { unlockedPrivateKeyHex = await decryptPrivateKeyHex(enc, pin); setBound(true); localStorage.setItem(LOCK_KEY,'0'); return true; } catch(_) { return false; }
    }
    if (pin === getPin() && getAddress()) { setBound(true); localStorage.setItem(LOCK_KEY,'0'); return true; }
    return false;
  }

  function getPublicKey(){ return localStorage.getItem(V1_PUBLIC_KEY) || ''; }

  async function signTransaction(txCore){
    if (isLocked() || !isBound()) throw new Error('wallet_locked');
    const secp = _getSecp();
    if (!secp || !secp.sign) throw new Error('secp256k1_library_missing');
    if (!unlockedPrivateKeyHex) throw new Error('wallet_locked');
    const canonical = JSON.stringify(txCore);
    const digestHex = await sha256Hex(canonical);
    const sig = await secp.sign(digestHex, unlockedPrivateKeyHex, { der: true });
    return typeof sig === 'string' ? sig : bytesToHex(sig);
  }

  function setMigrationMeta(meta){ localStorage.setItem(V1_MIGRATION_META, JSON.stringify(meta||{})); }
  function getMigrationMeta(){ try { return JSON.parse(localStorage.getItem(V1_MIGRATION_META)||'{}'); } catch(_) { return {}; } }

  function disconnect(){ unlockedPrivateKeyHex = null; setBound(false); localStorage.setItem(LOCK_KEY, '1'); }
  function forgetDevice(){ [ADDRESS_KEY,SEND_SECRET_KEY,SEND_SEED_KEY,SEND_SEED_COMPAT_KEY,PIN_KEY,BOUND_KEY,LOCK_KEY,V1_ENCRYPTED_KEY,V1_PUBLIC_KEY,V1_ADDRESS_KEY,V1_MIGRATION_META].forEach(k=>localStorage.removeItem(k)); unlockedPrivateKeyHex = null; }
  function clearSession(){ forgetDevice(); }
  function saveSession({address, sendSeed, pin, bound}){ setAddress(address || ''); setSendSeed(sendSeed || ''); setPin(pin || ''); setBound(bound !== undefined ? !!bound : !!(address && sendSeed)); if (address || sendSeed) localStorage.setItem(LOCK_KEY, '0'); }
  function requirePin(actionLabel = 'continue'){ const stored = getPin(); if(!stored) return true; const entered = prompt(`Enter wallet PIN to ${actionLabel}`); if(entered === null) return false; if(entered !== stored){ alert('Wrong PIN.'); return false; } return true; }

  window.walletSession = { ADDRESS_KEY,SEND_SECRET_KEY,SEND_SEED_KEY,PIN_KEY,BOUND_KEY,LOCK_KEY,getAddress,setAddress,getSendSeed,setSendSeed,getSendSecret,setSendSecret,getPin,setPin,isLocked,lockWallet,unlockWallet,setCustomUnlockHandler,isBound,setBound,disconnect,forgetDevice,clearSession,saveSession,requirePin,createWalletV1,getPublicKey,signTransaction,setMigrationMeta,getMigrationMeta };
})(window);
