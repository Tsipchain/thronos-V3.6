(function(window){
  if (window.ThronosWallet) return;

  const EVENTS = {
    OPEN: 'thronos:wallet:open',
    LOCK: 'thronos:wallet:lock',
    UNLOCK: 'thronos:wallet:unlock',
    TX_STATUS: 'thronos:wallet:tx_status'
  };

  function emit(eventName, detail){
    try {
      window.dispatchEvent(new CustomEvent(eventName, { detail }));
    } catch (e) {
      console.warn('ThronosWallet emit failed', e);
    }
  }

  function ensureWallet(){
    if (!window.walletSession) throw new Error('wallet_session_missing');
    const address = window.walletSession.getAddress();
    if (!address) throw new Error('wallet_not_initialized');
    return address;
  }

  function normalizeTab(tab){
    return (tab || 'all').toString().trim().toLowerCase();
  }

  function isSwapTx(tx){
    const type = String(tx.type || '').toUpperCase();
    const note = String(tx.note || '').toUpperCase();
    return type.startsWith('SWAP_') || note.startsWith('SWAP_') || note.startsWith('DEX_') || note.startsWith('AMM_') || note.startsWith('LIQUIDITY_');
  }

  function isTokenTx(tx){
    const type = String(tx.type || '').toUpperCase();
    const symbol = String(tx.symbol || tx.asset_symbol || '').toUpperCase();
    return type.startsWith('TOKEN_TRANSFER') || (symbol && symbol !== 'THR');
  }

  function isL2ETx(tx){
    const type = String(tx.type || '').toUpperCase();
    return type.startsWith('L2E_REWARD');
  }

  function isAiTx(tx){
    const type = String(tx.type || '').toUpperCase();
    const note = String(tx.note || '').toUpperCase();
    return type.startsWith('AI_') || type.startsWith('CREDITS_') || note.includes('AI TRANSFER');
  }

  function isIotTx(tx){
    const type = String(tx.type || '').toUpperCase();
    return type.startsWith('IOT_') || type.startsWith('PARKING_');
  }

  function isBridgeTx(tx){
    const type = String(tx.type || '').toUpperCase();
    return type.startsWith('BRIDGE_') || type.startsWith('DEPOSIT_');
  }

  function isThrTx(tx){
    return !isSwapTx(tx) && !isTokenTx(tx) && !isL2ETx(tx) && !isAiTx(tx) && !isIotTx(tx) && !isBridgeTx(tx);
  }

  function filterByTab(tab, txs){
    const t = normalizeTab(tab);
    if (t === 'all') return txs;
    if (t === 'swaps') return txs.filter(isSwapTx);
    if (t === 'tokens') return txs.filter(isTokenTx);
    if (t === 'l2e') return txs.filter(isL2ETx);
    if (t === 'ai') return txs.filter(isAiTx);
    if (t === 'iot') return txs.filter(isIotTx);
    if (t === 'bridge') return txs.filter(isBridgeTx);
    if (t === 'thr') return txs.filter(isThrTx);
    return txs;
  }

  async function open(options = {}){
    const address = ensureWallet();
    if (window.walletSession.isLocked && window.walletSession.isLocked()) {
      await unlock(options);
    }
    if (options.showUi !== false && typeof window.openHeaderWalletModal === 'function') {
      window.openHeaderWalletModal();
    }
    emit(EVENTS.OPEN, { address });
    return { address, locked: window.walletSession.isLocked ? window.walletSession.isLocked() : false };
  }

  async function lock(){
    if (window.walletSession.lockWallet) {
      window.walletSession.lockWallet();
    }
    if (typeof window.setWalletOpen === 'function') {
      window.setWalletOpen(false);
    }
    emit(EVENTS.LOCK, { address: window.walletSession.getAddress() });
    return { locked: true };
  }

  async function unlock(options = {}){
    if (!window.walletSession) throw new Error('wallet_session_missing');
    const ok = window.walletSession.unlockWallet ? await window.walletSession.unlockWallet(options) : true;
    if (!ok) throw new Error('unlock_failed');
    const address = window.walletSession.getAddress();
    emit(EVENTS.UNLOCK, { address });
    return { address, locked: false };
  }

  async function send({ token = 'THR', to, amount, speed = 'fast', passphrase = '' } = {}){
    const address = ensureWallet();
    if (window.walletSession.isLocked && window.walletSession.isLocked()) {
      throw new Error('wallet_locked');
    }
    const payload = {
      token: (token || 'THR').toString().toUpperCase(),
      from: address,
      to: (to || '').trim(),
      amount: amount,
      secret: window.walletSession.getSendSeed(),
      speed,
      passphrase
    };

    const resp = await fetch('/api/wallet/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await resp.json().catch(() => ({}));
    emit(EVENTS.TX_STATUS, { status: data.status || data.error || (resp.ok ? 'submitted' : 'failed'), tx: data.tx, response: data });
    if (!resp.ok || data.error) {
      throw new Error(data.error || 'send_failed');
    }
    return data;
  }

  async function getHistory({ tab = 'all', limit = 200 } = {}){
    const address = ensureWallet();
    const resp = await fetch(`/wallet_data/${address}`);
    const data = await resp.json();
    const txs = Array.isArray(data.transactions) ? data.transactions : [];
    const filtered = filterByTab(tab, txs).slice(0, limit || txs.length);
    return { address, tab: normalizeTab(tab), transactions: filtered };
  }

  function on(eventName, handler){
    window.addEventListener(eventName, handler);
    return () => off(eventName, handler);
  }

  function off(eventName, handler){
    window.removeEventListener(eventName, handler);
  }

  window.ThronosWallet = {
    EVENTS,
    open,
    lock,
    unlock,
    send,
    getHistory,
    on,
    off
  };

  // Hooks container for mobile/extension wrappers to inject biometric/passkey helpers
  window.ThronosWalletHooks = window.ThronosWalletHooks || {};
})(window);
