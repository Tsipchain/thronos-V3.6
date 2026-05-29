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

  function setItem(key, value){ value ? localStorage.setItem(key, value) : localStorage.removeItem(key); }
  function setBound(v){ localStorage.setItem(BOUND_KEY, v ? '1' : '0'); }
  function isBound(){ return localStorage.getItem(BOUND_KEY) === '1'; }
  function isLocked(){ return localStorage.getItem(LOCK_KEY) === '1'; }

  function normalizeAddress(addr){ return (addr || '').toString().trim(); }
  function getAddress(){ return localStorage.getItem(V1_ADDRESS_KEY) || localStorage.getItem(ADDRESS_KEY) || ''; }
  function getActiveAddress(){ const m = getMigrationInfo(); return normalizeAddress(m.new_v1_address || getAddress()); }
  function setAddress(addr){ setItem(ADDRESS_KEY, normalizeAddress(addr)); }

  function getScopedCredential(address){
    const addr = normalizeAddress(address);
    if (!addr) return '';
    const scopedKeys = [
      `wallet_v1_send_secret:${addr}`,
      `wallet_v1_send_seed:${addr}`,
      `wallet_v1_secret:${addr}`,
      `${SEND_SECRET_KEY}:${addr}`,
      `${SEND_SEED_KEY}:${addr}`,
      `${SEND_SEED_COMPAT_KEY}:${addr}`,
      `wallet_v1_send_secret_${addr}`,
      `wallet_v1_send_seed_${addr}`,
      `${SEND_SECRET_KEY}_${addr}`,
      `${SEND_SEED_KEY}_${addr}`,
      `${SEND_SEED_COMPAT_KEY}_${addr}`
    ];
    for (const key of scopedKeys) {
      const value = localStorage.getItem(key);
      if (value) return value;
    }
    for (const key of ['wallet_v1_credentials', 'wallet_credentials', 'thr_wallet_credentials']) {
      try {
        const credentials = JSON.parse(localStorage.getItem(key) || '{}');
        const record = credentials[addr] || credentials[addr.toLowerCase?.()] || null;
        const value = typeof record === 'string' ? record : (record && (record.send_secret || record.sendSeed || record.send_seed || record.thr_secret));
        if (value) return value;
      } catch (_) {}
    }
    return '';
  }

  function getSendSeed(address){
    const activeAddress = normalizeAddress(address || getAddress());
    const migration = getMigrationInfo();
    return getScopedCredential(activeAddress)
      || getScopedCredential(migration.new_v1_address)
      || getScopedCredential(migration.old_address)
      || localStorage.getItem(SEND_SECRET_KEY)
      || localStorage.getItem(SEND_SEED_KEY)
      || localStorage.getItem(SEND_SEED_COMPAT_KEY)
      || '';
  }

  function setSendSeed(seed, address){
    const value = seed ? seed.trim() : '';
    setItem(SEND_SECRET_KEY, value);
    setItem(SEND_SEED_KEY, value);
    setItem(SEND_SEED_COMPAT_KEY, value);
    const addr = normalizeAddress(address || getAddress());
    if (addr) setItem(`${SEND_SECRET_KEY}:${addr}`, value);
  }
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
    if (!isLocked() && isBound()) return true;
    if (customUnlockHandler) {
      try { const ok = await customUnlockHandler(options); if (ok) { setBound(true); localStorage.setItem(LOCK_KEY, '0'); return true; } }
      catch(_) {}
    }
    const pin = options.pin || (options.prompt !== false ? prompt('Enter wallet PIN to unlock') : null);
    if (!pin) return false;
    const enc = localStorage.getItem(V1_ENCRYPTED_KEY);
    if (enc) {
      try { unlockedPrivateKeyHex = await decryptPrivateKeyHex(enc, pin); setBound(true); localStorage.setItem(LOCK_KEY, '0'); return true; }
      catch(_) { return false; }
    }
    const hasLegacyCreds = !!(getAddress() && getSendSeed() && pin === getPin());
    if (hasLegacyCreds) { setBound(true); localStorage.setItem(LOCK_KEY, '0'); return true; }
    return false;
  }
  async function unlock(pinOrOptions){ const options = typeof pinOrOptions === 'string' ? {pin: pinOrOptions, prompt:false} : (pinOrOptions || {}); return unlockWallet(options); }

  function getPublicKey(){ return localStorage.getItem(V1_PUBLIC_KEY) || ''; }
  function hasEncryptedPrivateKey(){ return !!localStorage.getItem(V1_ENCRYPTED_KEY); }
  function isWalletV1(){ return !!(localStorage.getItem(V1_PUBLIC_KEY) && localStorage.getItem(V1_ENCRYPTED_KEY)); }
  function hasV1SigningMaterial(){ return !!(getPublicKey() && hasEncryptedPrivateKey() && typeof signTransaction === 'function'); }
  function getMigrationInfo(){ try { return JSON.parse(localStorage.getItem(V1_MIGRATION_META) || '{}'); } catch(_) { return {}; } }
  function isMigrated(){ const m = getMigrationInfo(); return !!(m.old_address && m.new_v1_address); }
  function getCredentialLookupAddress(activeAddress){
    const active = normalizeAddress(activeAddress || getActiveAddress());
    const m = getMigrationInfo();
    if (m.old_address && (!active || active === m.new_v1_address || active === getAddress())) return m.old_address;
    return active || m.new_v1_address || m.old_address || '';
  }


  function canonicalTxMessage(txCore){
    const txForSigning = {
      from: txCore.from,
      to: txCore.to,
      amount: txCore.amount,
      token: txCore.token,
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
    const digestHex = await sha256Hex(canonicalTxMessage(txCore));
    const sig = await secp.sign(digestHex, unlockedPrivateKeyHex, { der: true });
    return typeof sig === 'string' ? sig : bytesToHex(sig);
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
      localStorage.setItem(V1_MIGRATION_META, JSON.stringify(meta));
      setSendSeed('');
      return meta;
    } finally {
      sendSecret = '';
      localStorage.removeItem(SEND_SECRET_KEY);
      localStorage.removeItem(SEND_SEED_KEY);
      localStorage.removeItem(SEND_SEED_COMPAT_KEY);
    }
  }

  function disconnect(){ setBound(false); localStorage.setItem(LOCK_KEY, '1'); unlockedPrivateKeyHex = null; }
  function forgetDevice(){ [ADDRESS_KEY,SEND_SECRET_KEY,SEND_SEED_KEY,SEND_SEED_COMPAT_KEY,PIN_KEY,BOUND_KEY,LOCK_KEY,V1_ENCRYPTED_KEY,V1_PUBLIC_KEY,V1_ADDRESS_KEY,V1_MIGRATION_META].forEach(k => localStorage.removeItem(k)); unlockedPrivateKeyHex = null; }
  function clearSession(){ forgetDevice(); }
  function saveSession({address, sendSeed, pin, bound}){ setAddress(address || ''); setSendSeed(sendSeed || ''); setPin(pin || ''); setBound(bound !== undefined ? !!bound : !!(address && sendSeed)); if (address || sendSeed) localStorage.setItem(LOCK_KEY, '0'); }
  function requirePin(actionLabel = 'continue'){ const stored = getPin(); if(!stored) return true; const entered = prompt(`Enter wallet PIN to ${actionLabel}`); if(entered === null) return false; if(entered !== stored){ alert('Wrong PIN.'); return false; } return true; }

  window.walletSession = {
    ADDRESS_KEY, SEND_SECRET_KEY, SEND_SEED_KEY, PIN_KEY, BOUND_KEY, LOCK_KEY,
    getAddress, getActiveAddress, getCredentialLookupAddress, setAddress, getSendSeed, setSendSeed, getSendSecret, setSendSecret,
    getPin, setPin, isLocked, lockWallet, unlockWallet, setCustomUnlockHandler,
    isBound, setBound, disconnect, forgetDevice, clearSession, saveSession, requirePin,
    createWalletV1, getPublicKey, hasEncryptedPrivateKey, hasV1SigningMaterial, enrollSigningMaterial, signTransaction, isWalletV1, isMigrated, getMigrationInfo,
    lock, unlock, migrateLegacyWallet, canonicalTxMessage
  };
})(window);
