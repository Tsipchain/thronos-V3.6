(function () {
  // Production API endpoints
  const DEFAULT_READ_BASE = "https://node-2.up.railway.app";
  const DEFAULT_WRITE_BASE = "https://api.thronoschain.org";
  // Fallback to relative paths for local development
  const IS_PRODUCTION = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';

  window.THRONOS_CONFIG = window.THRONOS_CONFIG || {};
  window.THRONOS_CONFIG.apiReadBase = window.THRONOS_CONFIG.apiReadBase || (IS_PRODUCTION ? DEFAULT_READ_BASE : "/api");
  window.THRONOS_CONFIG.apiWriteBase = window.THRONOS_CONFIG.apiWriteBase || (IS_PRODUCTION ? DEFAULT_WRITE_BASE : "/api");
})();

(function(window){
  if (window.ThronosWallet) return;

  const EVENTS = {
    OPEN: 'thronos:wallet:open',
    LOCK: 'thronos:wallet:lock',
    UNLOCK: 'thronos:wallet:unlock',
    TX_STATUS: 'thronos:wallet:tx_status'
  };

  const CFG = window.THRONOS_CONFIG || {};
  const API_READ_BASE = (CFG.apiReadBase || '/api').replace(/\/$/, '');
  const API_WRITE_BASE = (CFG.apiWriteBase || API_READ_BASE).replace(/\/$/, '');

  function resolveApiBase(base, path){
    const normalized = path.startsWith('/') ? path : `/${path}`;
    if (!base || base === '/api') {
      return normalized.startsWith('/api') ? normalized : `/api${normalized}`;
    }
    if (base.startsWith('http')) {
      return `${base}${normalized}`;
    }
    return `${base}${normalized}`;
  }

  async function verifyWalletConnection(address){
    const url = resolveApiBase(API_READ_BASE, `/balances?address=${encodeURIComponent(address)}`);
    try {
      const resp = await fetch(url);
      if (!resp.ok) throw new Error(`wallet_balance_fetch_failed:${resp.status}`);
      await resp.json().catch(() => ({}));
      return true;
    } catch (err) {
      if (typeof window.setDisconnectedUI === 'function') {
        window.setDisconnectedUI();
      }
      throw err;
    }
  }

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
    await verifyWalletConnection(address);
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
    await verifyWalletConnection(address);
    const payload = {
      token: (token || 'THR').toString().toUpperCase(),
      from: address,
      to: (to || '').trim(),
      amount: amount,
      secret: window.walletSession.getSendSeed(),
      speed,
      passphrase
    };

    const resp = await fetch(resolveApiBase(API_WRITE_BASE, '/wallet/send'), {
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
    const resp = await fetch(resolveApiBase(API_READ_BASE, `/wallet_data/${address}`));
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

  // ── Pool helpers (accounting only — no signing, no broadcast) ──────────────
  async function getPoolsStatus() {
    const resp = await fetch(resolveApiBase(API_READ_BASE, '/api/pools/status'));
    return resp.json();
  }

  async function getPoolTvl(poolId) {
    const q = poolId ? `?pool_id=${encodeURIComponent(poolId)}` : '';
    const resp = await fetch(resolveApiBase(API_READ_BASE, `/api/pools/tvl${q}`));
    return resp.json();
  }

  async function getPoolPositions(address) {
    const addr = address || ensureWallet();
    const resp = await fetch(resolveApiBase(API_READ_BASE, `/api/pools/positions?address=${encodeURIComponent(addr)}`));
    return resp.json();
  }

  async function depositToPool({ address, pool_id, side, asset, amount } = {}) {
    const resp = await fetch(resolveApiBase(API_WRITE_BASE, '/api/pools/deposit'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address, pool_id, side, asset, amount }),
    });
    return resp.json();
  }

  async function createPoolWithdrawIntent({ address, pool_id, side, asset, amount } = {}) {
    const resp = await fetch(resolveApiBase(API_WRITE_BASE, '/api/pools/withdraw-intent'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address, pool_id, side, asset, amount }),
    });
    return resp.json();
  }

  async function getWithdrawalQuote({ address, amount, token, dest_chain, destination_address } = {}) {
    const p = new URLSearchParams({ address: address || '', amount: String(amount || 0), token: token || 'USDT', dest_chain: dest_chain || 'bsc' });
    if (destination_address) p.set('destination_address', destination_address);
    const resp = await fetch(resolveApiBase(API_READ_BASE, `/api/v1/withdrawal/quote?${p}`));
    return resp.json();
  }

  async function getLiquidityHistory({ address, chain, source, limit } = {}) {
    const addr = address || ensureWallet();
    const p = new URLSearchParams({ address: addr, domain: 'liquidity', limit: String(limit || 100) });
    if (chain)  p.set('chain', chain);
    if (source) p.set('source', source);
    const resp = await fetch(resolveApiBase(API_READ_BASE, `/api/wallet/history/normalized?${p}`));
    return resp.json();
  }

  async function getNetworkHistory({ network = 'thronos', limit = 100 } = {}) {
    const address = ensureWallet();
    const CHAIN_MAP = { thronos:['thronos'], bnb:['bsc'], arbitrum:['arbitrum'], base:['base'], ethereum:['eth'], bitcoin:['btc'] };
    const chains = CHAIN_MAP[network] || [];
    const resp = await fetch(resolveApiBase(API_READ_BASE, `/api/wallet/history/normalized?address=${encodeURIComponent(address)}&domain=all&limit=${limit}`));
    const data = await resp.json();
    const txs = Array.isArray(data.events) ? data.events : (Array.isArray(data.transactions) ? data.transactions : []);
    const filtered = chains.length ? txs.filter(tx => {
        const c = (tx.chain || '').toLowerCase();
        if (!c) return network === 'thronos';
        return chains.includes(c);
    }) : txs;
    return { address, network, transactions: filtered };
  }

  window.ThronosWallet = {
    EVENTS,
    open,
    lock,
    unlock,
    send,
    getHistory,
    on,
    off,
    // Pool helpers
    getPoolsStatus,
    getPoolTvl,
    getPoolPositions,
    depositToPool,
    createPoolWithdrawIntent,
    getWithdrawalQuote,
    getLiquidityHistory,
    getNetworkHistory,
  };

  // Hooks container for mobile/extension wrappers to inject biometric/passkey helpers
  window.ThronosWalletHooks = window.ThronosWalletHooks || {};
})(window);
