'use strict';

// ── Constants ──────────────────────────────────────────────────────────────────
const API = 'https://api.thronoschain.org';
const STORAGE_KEY = 'thr_ext_accounts'; // [{ address, kit, label, watchOnly }]
const ACTIVE_KEY  = 'thr_ext_active';

// ── Storage helpers ───────────────────────────────────────────────────────────
function stGet(key) {
  return new Promise(r => chrome.storage.local.get([key], d => r(d[key] ?? null)));
}
function stSet(key, val) {
  return new Promise(r => chrome.storage.local.set({ [key]: val }, r));
}
function stGetObj(key) { return stGet(key); }

async function getAccounts() { return (await stGetObj(STORAGE_KEY)) || []; }
async function saveAccounts(accs) { await stSet(STORAGE_KEY, accs); }
async function getActiveAddr() { return (await stGet(ACTIVE_KEY)) || null; }
async function setActiveAddr(addr) { await stSet(ACTIVE_KEY, addr); }
async function getAccount(addr) {
  const accs = await getAccounts();
  return accs.find(a => a.address === addr) || null;
}
async function upsertAccount(address, kit, label, watchOnly) {
  const accs = await getAccounts();
  const idx = accs.findIndex(a => a.address === address);
  const entry = { address, kit: kit ? JSON.stringify(kit) : null, label: label || shortAddr(address), watchOnly: !!watchOnly };
  if (idx >= 0) accs[idx] = entry; else accs.push(entry);
  await saveAccounts(accs);
}
async function removeAccount(address) {
  let accs = await getAccounts();
  accs = accs.filter(a => a.address !== address);
  await saveAccounts(accs);
  const active = await getActiveAddr();
  if (active === address) await setActiveAddr(accs.length ? accs[0].address : null);
}

// ── In-memory unlocked wallets ────────────────────────────────────────────────
// Map<address → privHex>
const unlocked = new Map();

// ── Crypto helpers ────────────────────────────────────────────────────────────
function hexToBytes(hex) {
  const b = new Uint8Array(hex.length / 2);
  for (let i = 0; i < b.length; i++) b[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return b;
}
function bytesToHex(b) {
  return Array.from(b).map(x => x.toString(16).padStart(2, '0')).join('');
}

async function pbkdfKey(pin, saltBytes) {
  const km = await crypto.subtle.importKey('raw', new TextEncoder().encode(pin), 'PBKDF2', false, ['deriveKey']);
  return crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt: saltBytes, iterations: 250000, hash: 'SHA-256' },
    km, { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']
  );
}
async function encryptPrivKey(privHex, pin) {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv   = crypto.getRandomValues(new Uint8Array(12));
  const key  = await pbkdfKey(pin, salt);
  const ct   = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, hexToBytes(privHex));
  return { v: 1, salt: bytesToHex(salt), iv: bytesToHex(iv), ct: bytesToHex(new Uint8Array(ct)) };
}
async function decryptPrivKey(blob, pin) {
  const p = typeof blob === 'string' ? JSON.parse(blob) : blob;
  const key = await pbkdfKey(pin, hexToBytes(p.salt));
  const plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: hexToBytes(p.iv) }, key, hexToBytes(p.ct));
  return bytesToHex(new Uint8Array(plain));
}

async function sha256Hex(str) {
  const d = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(str));
  return bytesToHex(new Uint8Array(d));
}

// secp256k1 is loaded from lib/secp256k1.js — available as window.nobleSecp256k1
function getSecp() {
  return window.nobleSecp256k1 || window.secp256k1 || null;
}

async function ensureSecpReady(secp) {
  if (!secp) throw new Error('secp256k1 library unavailable');
  // Wire up WebCrypto helpers needed by noble v1 async path
  const sha256Async = async (...msgs) => {
    const buf = msgs.reduce((a, b) => {
      const ab = a instanceof Uint8Array ? a : hexToBytes(a);
      const bb = b instanceof Uint8Array ? b : hexToBytes(b);
      const r = new Uint8Array(ab.length + bb.length);
      r.set(ab); r.set(bb, ab.length); return r;
    }, new Uint8Array(0));
    return new Uint8Array(await crypto.subtle.digest('SHA-256', buf));
  };
  const hmacSha256Async = async (key, ...msgs) => {
    const km = await crypto.subtle.importKey('raw',
      key instanceof Uint8Array ? key : hexToBytes(key),
      { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
    const buf = msgs.reduce((a, b) => {
      const ab = a instanceof Uint8Array ? a : new Uint8Array(0);
      const bb = b instanceof Uint8Array ? b : hexToBytes(typeof b === 'string' ? b : bytesToHex(b));
      const r = new Uint8Array(ab.length + bb.length);
      r.set(ab); r.set(bb, ab.length); return r;
    }, new Uint8Array(0));
    return new Uint8Array(await crypto.subtle.sign('HMAC', km, buf));
  };
  try {
    if (secp.etc) { secp.etc.sha256Async = sha256Async; secp.etc.hmacSha256Async = hmacSha256Async; }
    if (secp.utils) { secp.utils.sha256Async = sha256Async; secp.utils.hmacSha256Async = hmacSha256Async; }
  } catch (_) {}
}

function derInteger(bytes) {
  let i = 0; while (i < bytes.length - 1 && bytes[i] === 0) i++;
  let v = Array.from(bytes.slice(i)); if (!v.length) v = [0];
  if (v[0] & 0x80) v.unshift(0);
  return [0x02, v.length, ...v];
}
function toDerHex(compactBytes) {
  if (!compactBytes || compactBytes.length !== 64) return bytesToHex(compactBytes || []);
  const r = derInteger(compactBytes.slice(0, 32));
  const s = derInteger(compactBytes.slice(32, 64));
  return bytesToHex(new Uint8Array([0x30, r.length + s.length, ...r, ...s]));
}

async function signDigest(digestHex, privHex) {
  const secp = getSecp();
  if (!secp) throw new Error('secp256k1 unavailable');
  await ensureSecpReady(secp);
  let sig;
  if (typeof secp.signAsync === 'function') {
    sig = await secp.signAsync(digestHex, privHex);
  } else {
    sig = await secp.sign(digestHex, privHex);
  }
  if (sig && typeof sig.toDERHex === 'function') return sig.toDERHex();
  if (sig && typeof sig.toCompactRawBytes === 'function') return toDerHex(sig.toCompactRawBytes());
  if (sig instanceof Uint8Array) return toDerHex(sig);
  return typeof sig === 'string' ? sig : bytesToHex(sig);
}

function getPubKeyHex(privHex) {
  const secp = getSecp();
  if (!secp) throw new Error('secp256k1 unavailable');
  const pub = secp.getPublicKey(privHex, true);
  return typeof pub === 'string' ? pub.replace(/^0x/, '') : bytesToHex(pub);
}

async function deriveAddress(pubKeyHex) {
  const r = await fetch(`${API}/api/v1/address/derive`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ public_key: pubKeyHex, compressed_public_key: pubKeyHex })
  });
  const d = await r.json();
  if (!r.ok || !(d.address || d.thr_address)) throw new Error(d.error || 'address_derivation_failed');
  return d.address || d.thr_address;
}

// ── Transaction signing ───────────────────────────────────────────────────────
function canonicalTxMessage(tx) {
  const txType = tx.type || tx.action;
  if (txType === 'swap' || txType === 'execute_swap') {
    const from = String(tx.from || '').trim();
    const tokenIn = String(tx.token_in || tx.token || 'THR').trim();
    const tokenOut = String(tx.token_out || '').trim();
    const amountIn = String(tx.amount_in || tx.amount || '').trim();
    const nonce = String(tx.nonce || '').trim();
    const timestamp = String(tx.timestamp || '').trim();
    return '{"action":"swap","amount_in":' + JSON.stringify(amountIn)
      + ',"from":' + JSON.stringify(from)
      + ',"nonce":' + JSON.stringify(nonce)
      + ',"timestamp":' + JSON.stringify(timestamp)
      + ',"token_in":' + JSON.stringify(tokenIn)
      + ',"token_out":' + JSON.stringify(tokenOut)
      + ',"type":"swap"}';
  }
  return '{"amount":' + JSON.stringify(String(tx.amount || ''))
    + ',"from":' + JSON.stringify(String(tx.from || ''))
    + ',"nonce":' + JSON.stringify(String(tx.nonce || ''))
    + ',"timestamp":' + JSON.stringify(String(tx.timestamp || ''))
    + ',"to":' + JSON.stringify(String(tx.to || ''))
    + ',"token":' + JSON.stringify(String(tx.token || 'THR'))
    + '}';
}

async function signTx(address, txCore) {
  const privHex = unlocked.get(address);
  if (!privHex) throw new Error('wallet_locked');
  const digestHex = await sha256Hex(canonicalTxMessage(txCore));
  return signDigest(digestHex, privHex);
}

// ── API helpers ───────────────────────────────────────────────────────────────
async function fetchBalances(address) {
  try {
    const r = await fetch(`${API}/api/balances?address=${encodeURIComponent(address)}&show_zero=true`);
    if (r.ok) return r.json();
  } catch (_) {}
  return null;
}

async function fetchHistory(address, limit = 30) {
  try {
    const r = await fetch(`${API}/api/history?address=${encodeURIComponent(address)}&limit=${limit}`);
    if (r.ok) return r.json();
  } catch (_) {}
  return null;
}

async function fetchStakePools() {
  try {
    const r = await fetch(`${API}/api/stake/pools`);
    if (r.ok) return r.json();
  } catch (_) {}
  return null;
}

async function submitSend({ from, to, amount, token, speed }) {
  const privHex = unlocked.get(from);
  if (!privHex) throw new Error('Wallet locked — unlock first');
  const nonce = Date.now().toString();
  const timestamp = Math.floor(Date.now() / 1000);
  const txCore = { from, to, amount: String(amount), token: token || 'THR', nonce, timestamp, speed: speed || 'standard' };
  const pubKeyHex = getPubKeyHex(privHex);
  const signature = await signTx(from, txCore);
  const body = { tx: { ...txCore, publicKey: pubKeyHex, signature } };
  const r = await fetch(`${API}/api/v1/tx/send`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok && !d.ok) throw new Error(d.error || `HTTP ${r.status}`);
  return d;
}

async function submitSwap({ from, tokenIn, tokenOut, amountIn }) {
  const privHex = unlocked.get(from);
  if (!privHex) throw new Error('Wallet locked');
  const nonce = Date.now().toString();
  const timestamp = Math.floor(Date.now() / 1000);
  const txCore = { type: 'swap', action: 'swap', from, token_in: tokenIn, token_out: tokenOut, amount_in: String(amountIn), nonce, timestamp };
  const pubKeyHex = getPubKeyHex(privHex);
  const signature = await signTx(from, txCore);
  const body = { tx: { ...txCore, publicKey: pubKeyHex, signature } };
  const r = await fetch(`${API}/api/swap/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok && !d.ok) throw new Error(d.error || `HTTP ${r.status}`);
  return d;
}

async function submitBridge({ from, pair, amount, dest }) {
  const r = await fetch(`${API}/api/bridge/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ from_address: from, pair, amount: String(amount), destination_address: dest || from })
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok && !d.ok) throw new Error(d.error || `HTTP ${r.status}`);
  return d;
}

async function submitStake({ from, amount, poolId }) {
  const privHex = unlocked.get(from);
  if (!privHex) throw new Error('Wallet locked');
  const nonce = Date.now().toString();
  const timestamp = Math.floor(Date.now() / 1000);
  const txCore = { from, to: poolId || 'stake_pool_1', amount: String(amount), token: 'THR', nonce, timestamp };
  const pubKeyHex = getPubKeyHex(privHex);
  const signature = await signTx(from, txCore);
  const r = await fetch(`${API}/api/stake/deposit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tx: { ...txCore, publicKey: pubKeyHex, signature } })
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok && !d.ok) throw new Error(d.error || `HTTP ${r.status}`);
  return d;
}

// ── Utilities ─────────────────────────────────────────────────────────────────
function shortAddr(addr) { return addr ? `${addr.slice(0, 8)}…${addr.slice(-6)}` : ''; }
function fmtNum(n, dec = 4) {
  const v = Number(n);
  if (!isFinite(v)) return '—';
  if (v === 0) return '0';
  return v.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: dec });
}
function fmtDate(ts) {
  const d = new Date(typeof ts === 'number' && ts < 1e12 ? ts * 1000 : ts);
  if (isNaN(d)) return '';
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}
function copyText(txt) {
  try {
    navigator.clipboard.writeText(txt);
  } catch (_) {
    const t = document.createElement('textarea');
    t.value = txt; document.body.appendChild(t); t.select(); document.execCommand('copy'); t.remove();
  }
}

// ── UI state ──────────────────────────────────────────────────────────────────
let _currentAddress = null;
let _balanceData = null;
let _swapQuoteConfirmed = false;
let _swapQuoteData = null;

function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  const el = document.getElementById(id);
  if (el) el.classList.add('active');
}

function openModal(id) { document.getElementById(id).classList.add('open'); }
function closeModal(id) { document.getElementById(id).classList.remove('open'); }

function setStatus(id, msg, cls) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = msg;
  el.className = 'status-msg' + (cls ? ' ' + cls : '');
}

// ── PIN pad ───────────────────────────────────────────────────────────────────
let _pinBuffer = '';
const PIN_LEN = 6;

function buildPinPad() {
  const dots = document.getElementById('pinDots');
  const pad  = document.getElementById('pinPad');
  if (!dots || !pad) return;

  dots.innerHTML = '';
  for (let i = 0; i < PIN_LEN; i++) {
    const d = document.createElement('div');
    d.className = 'pin-dot';
    d.id = `dot${i}`;
    dots.appendChild(d);
  }

  pad.innerHTML = '';
  const keys = ['1','2','3','4','5','6','7','8','9','','0','⌫'];
  keys.forEach(k => {
    const btn = document.createElement('button');
    btn.className = 'pin-key' + (k === '⌫' ? ' del' : k === '' ? ' empty' : '');
    btn.textContent = k;
    if (k !== '') btn.addEventListener('click', () => pinKeyPress(k));
    pad.appendChild(btn);
  });
}

function updatePinDots() {
  for (let i = 0; i < PIN_LEN; i++) {
    const d = document.getElementById(`dot${i}`);
    if (d) d.classList.toggle('filled', i < _pinBuffer.length);
  }
}

function pinKeyPress(k) {
  if (k === '⌫') { _pinBuffer = _pinBuffer.slice(0, -1); updatePinDots(); return; }
  if (_pinBuffer.length >= PIN_LEN) return;
  _pinBuffer += k;
  updatePinDots();
  if (_pinBuffer.length === PIN_LEN) setTimeout(tryUnlockPin, 120);
}

async function tryUnlockPin() {
  const pin = _pinBuffer;
  _pinBuffer = '';
  updatePinDots();

  const addr = await getActiveAddr();
  if (!addr) { showScreen('welcomeScreen'); return; }
  const acc = await getAccount(addr);
  if (!acc || !acc.kit) {
    setStatus('pinError', 'No wallet key found — please re-import');
    return;
  }
  try {
    const kit = typeof acc.kit === 'string' ? JSON.parse(acc.kit) : acc.kit;
    const privHex = await decryptPrivKey(kit, pin);
    unlocked.set(addr, privHex);
    setStatus('pinError', '');
    _currentAddress = addr;
    showScreen('homeScreen');
    loadHome();
  } catch (_) {
    setStatus('pinError', 'Wrong PIN — try again');
    _pinBuffer = '';
    updatePinDots();
  }
}

// ── Home ──────────────────────────────────────────────────────────────────────
async function loadHome() {
  const addr = _currentAddress || await getActiveAddr();
  if (!addr) { showScreen('welcomeScreen'); return; }
  _currentAddress = addr;

  document.getElementById('addrDisplay').textContent = shortAddr(addr);
  document.getElementById('balAmount').textContent = '…';
  document.getElementById('tokenList').innerHTML = '<div class="status-msg"><div class="spinner"></div></div>';

  const data = await fetchBalances(addr);
  _balanceData = data;

  if (!data) {
    document.getElementById('balAmount').textContent = '0 THR';
    document.getElementById('tokenList').innerHTML = '<div class="status-msg">Could not load balances</div>';
    return;
  }

  const tokens = Array.isArray(data.tokens) ? data.tokens : [];
  const thr = tokens.find(t => t.symbol === 'THR');
  const thrBal = thr ? Number(thr.balance) : Number(data.thr_balance || 0);

  document.getElementById('balAmount').textContent = `${fmtNum(thrBal, 4)} THR`;
  if (data.thr_usd_value) document.getElementById('balUsd').textContent = `≈ $${fmtNum(data.thr_usd_value, 2)} USD`;

  const list = document.getElementById('tokenList');
  if (!tokens.length) {
    list.innerHTML = '<div class="status-msg">No tokens yet</div>';
    return;
  }
  list.innerHTML = tokens.filter(t => Number(t.balance) > 0 || t.symbol === 'THR').map(t => `
    <div class="token-row">
      <div class="token-icon">${tokenIcon(t.symbol)}</div>
      <div class="token-info">
        <div class="token-name">${t.symbol}</div>
        <div class="token-sub">${t.name || t.symbol}</div>
      </div>
      <div class="token-balance">
        <div class="token-bal-num">${fmtNum(t.balance, 6)}</div>
        ${t.usd_value ? `<div class="token-bal-usd">$${fmtNum(t.usd_value, 2)}</div>` : ''}
      </div>
    </div>`).join('');
}

function tokenIcon(sym) {
  const map = { THR: '🏛️', BTC: '₿', WBTC: '🟠', ETH: 'Ξ', WETH: '🔵', USDT: '💵', USDC: '🔵', BNB: '🟡', ARB: '🔷', OP: '🔴' };
  return map[sym] || '🪙';
}

// ── Send ──────────────────────────────────────────────────────────────────────
const SEND_TOKENS = {
  THR:  ['THR', 'USDT', 'USDC', 'WBTC', 'WETH', 'BNB', 'ARB'],
  BTC:  ['BTC'],
  ETH:  ['ETH', 'USDT', 'USDC', 'WBTC'],
  BNB:  ['BNB', 'USDT', 'USDC'],
  ARB:  ['ARB', 'ETH', 'USDC'],
};
const DEPOSIT_ADDRESSES = {
  BTC: 'Contact support for BTC deposit address',
  ETH: 'Contact support for ETH deposit address',
  BNB: 'Contact support for BNB deposit address',
  ARB: 'Contact support for ARB deposit address',
};

let _sendNet = 'THR';

function buildSendTokenList() {
  const sel = document.getElementById('sendToken');
  const tokens = SEND_TOKENS[_sendNet] || ['THR'];
  sel.innerHTML = tokens.map(t => `<option value="${t}">${t}</option>`).join('');

  const note = document.getElementById('nonThrNote');
  if (_sendNet !== 'THR') {
    note.textContent = `Deposit ${_sendNet} to your THR wallet's ${_sendNet} address to bridge it onto Thronos Chain, or use the Bridge feature.`;
    note.classList.remove('hidden');
  } else {
    note.classList.add('hidden');
  }
}

async function initSendModal() {
  _sendNet = 'THR';
  document.querySelectorAll('#sendNetTabs .tab-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.net === 'THR');
  });
  document.getElementById('sendTo').value = '';
  document.getElementById('sendAmount').value = '';
  setStatus('sendStatus', '');
  buildSendTokenList();
  openModal('sendModal');
}

async function handleSendSubmit() {
  const from = _currentAddress;
  if (!from || !unlocked.has(from)) { setStatus('sendStatus', 'Wallet locked', 'status-err'); return; }
  if (_sendNet !== 'THR') {
    setStatus('sendStatus', 'Cross-chain sends require the Bridge feature', 'status-err');
    return;
  }
  const to = document.getElementById('sendTo').value.trim();
  const token = document.getElementById('sendToken').value;
  const amount = parseFloat(document.getElementById('sendAmount').value);
  const speed = document.getElementById('sendSpeed').value;
  if (!to) { setStatus('sendStatus', 'Enter recipient address', 'status-err'); return; }
  if (!amount || amount <= 0) { setStatus('sendStatus', 'Enter a valid amount', 'status-err'); return; }

  setStatus('sendStatus', 'Signing & sending…');
  document.getElementById('btnSendSubmit').disabled = true;
  try {
    const res = await submitSend({ from, to, amount, token, speed });
    setStatus('sendStatus', `✅ Sent! TX: ${(res.tx_hash || res.txid || '').slice(0, 16)}…`, 'status-ok');
    setTimeout(() => { closeModal('sendModal'); loadHome(); }, 2000);
  } catch (e) {
    setStatus('sendStatus', '❌ ' + (e.message || 'Send failed'), 'status-err');
  }
  document.getElementById('btnSendSubmit').disabled = false;
}

// ── Receive ───────────────────────────────────────────────────────────────────
function showReceiveModal() {
  const addr = _currentAddress;
  if (!addr) return;
  document.getElementById('receiveAddr').textContent = addr;
  const qrEl = document.getElementById('qrCanvas');
  qrEl.innerHTML = '';
  if (window.QRCode) {
    new QRCode(qrEl, { text: addr, width: 200, height: 200, colorDark: '#000', colorLight: '#fff' });
  } else {
    qrEl.textContent = addr;
  }
  openModal('receiveModal');
}

// ── Swap ──────────────────────────────────────────────────────────────────────
async function handleSwapSubmit() {
  const from = _currentAddress;
  if (!from || !unlocked.has(from)) { setStatus('swapStatus', 'Wallet locked', 'status-err'); return; }
  const tokenIn  = document.getElementById('swapFrom').value;
  const tokenOut = document.getElementById('swapTo').value;
  const amountIn = parseFloat(document.getElementById('swapAmount').value);

  if (!amountIn || amountIn <= 0) { setStatus('swapStatus', 'Enter amount', 'status-err'); return; }
  if (tokenIn === tokenOut) { setStatus('swapStatus', 'Choose different tokens', 'status-err'); return; }

  if (!_swapQuoteConfirmed) {
    // Fetch quote first
    setStatus('swapQuote', 'Getting quote…');
    try {
      const r = await fetch(`${API}/api/swap/quote?token_in=${tokenIn}&token_out=${tokenOut}&amount_in=${amountIn}`);
      const d = await r.json().catch(() => ({}));
      _swapQuoteData = d;
      _swapQuoteConfirmed = true;
      const out = d.amount_out || d.estimated_out || '?';
      setStatus('swapQuote', `≈ ${fmtNum(out)} ${tokenOut} (rate: ${d.rate || '?'})`, 'status-ok');
      document.getElementById('btnSwapSubmit').textContent = 'Confirm Swap';
    } catch (e) {
      setStatus('swapQuote', '❌ ' + e.message, 'status-err');
      _swapQuoteConfirmed = false;
    }
    return;
  }

  setStatus('swapStatus', 'Executing swap…');
  document.getElementById('btnSwapSubmit').disabled = true;
  try {
    const res = await submitSwap({ from, tokenIn, tokenOut, amountIn });
    setStatus('swapStatus', `✅ Swapped! ${fmtNum(amountIn)} ${tokenIn} → ${fmtNum(res.amount_out || amountIn)} ${tokenOut}`, 'status-ok');
    _swapQuoteConfirmed = false;
    document.getElementById('btnSwapSubmit').textContent = 'Get Quote';
    setTimeout(() => { closeModal('swapModal'); loadHome(); }, 2500);
  } catch (e) {
    setStatus('swapStatus', '❌ ' + e.message, 'status-err');
    _swapQuoteConfirmed = false;
    document.getElementById('btnSwapSubmit').textContent = 'Get Quote';
  }
  document.getElementById('btnSwapSubmit').disabled = false;
}

// ── Stake ─────────────────────────────────────────────────────────────────────
let _selectedPoolId = null;

async function loadStakePools() {
  const el = document.getElementById('stakePools');
  el.textContent = 'Loading pools…';
  const data = await fetchStakePools();
  if (!data || !Array.isArray(data.pools) || !data.pools.length) {
    el.textContent = 'No pools available';
    return;
  }
  _selectedPoolId = data.pools[0].pool_id || data.pools[0].id;
  el.innerHTML = data.pools.map(p => `
    <div class="token-row" style="cursor:pointer;margin-bottom:6px" data-pool="${p.pool_id || p.id}">
      <div class="token-icon">🔒</div>
      <div class="token-info">
        <div class="token-name">${p.name || p.pool_id || 'Pool'}</div>
        <div class="token-sub">APY: ${p.apy || p.apr || '—'}%</div>
      </div>
    </div>`).join('');
  el.querySelectorAll('[data-pool]').forEach(row => {
    row.addEventListener('click', () => {
      _selectedPoolId = row.dataset.pool;
      el.querySelectorAll('[data-pool]').forEach(r => r.style.borderColor = '');
      row.style.borderColor = 'var(--gold)';
    });
  });
}

async function handleStakeSubmit() {
  const from = _currentAddress;
  if (!from || !unlocked.has(from)) { setStatus('stakeStatus', 'Wallet locked', 'status-err'); return; }
  const amount = parseFloat(document.getElementById('stakeAmount').value);
  if (!amount || amount <= 0) { setStatus('stakeStatus', 'Enter amount', 'status-err'); return; }
  setStatus('stakeStatus', 'Staking…');
  document.getElementById('btnStakeSubmit').disabled = true;
  try {
    const res = await submitStake({ from, amount, poolId: _selectedPoolId });
    closeModal('stakeModal');
    document.getElementById('stakeSuccessMsg').textContent = `✅ Successfully staked ${fmtNum(amount)} THR!`;
    openModal('stakeSuccessModal');
    setTimeout(loadHome, 2000);
  } catch (e) {
    setStatus('stakeStatus', '❌ ' + e.message, 'status-err');
  }
  document.getElementById('btnStakeSubmit').disabled = false;
}

// ── Bridge ────────────────────────────────────────────────────────────────────
async function handleBridgeSubmit() {
  const from = _currentAddress;
  if (!from) return;
  const pair = document.getElementById('bridgePair').value;
  const amount = parseFloat(document.getElementById('bridgeAmount').value);
  const dest = document.getElementById('bridgeDest').value.trim();
  if (!amount || amount <= 0) { setStatus('bridgeStatus', 'Enter amount', 'status-err'); return; }
  setStatus('bridgeStatus', 'Submitting bridge request…');
  document.getElementById('btnBridgeSubmit').disabled = true;
  try {
    const res = await submitBridge({ from, pair, amount, dest });
    setStatus('bridgeStatus', `✅ Bridge initiated! ${res.message || 'Check history for status.'}`, 'status-ok');
    setTimeout(() => { closeModal('bridgeModal'); }, 3000);
  } catch (e) {
    setStatus('bridgeStatus', '❌ ' + e.message, 'status-err');
  }
  document.getElementById('btnBridgeSubmit').disabled = false;
}

// ── Cross-chain / Networks ────────────────────────────────────────────────────
async function loadNetworks() {
  const el = document.getElementById('networksContent');
  el.innerHTML = '<div class="spinner"></div><p style="text-align:center;margin-top:10px;color:var(--muted)">Loading cross-chain balances…</p>';
  openModal('networksModal');
  // Derive EVM address from private key
  const privHex = unlocked.get(_currentAddress);
  let evmAddr = '';
  if (privHex) {
    try {
      const pubHex = getPubKeyHex(privHex);
      // ethers not available in extension — use simple keccak approach
      evmAddr = await deriveEvmAddress(pubHex);
    } catch (_) {}
  }
  el.innerHTML = `
    <div style="margin-bottom:12px">
      <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:4px">THR Address</div>
      <div style="font-family:monospace;font-size:11px;word-break:break-all;color:var(--gold)">${_currentAddress || '—'}</div>
    </div>
    ${evmAddr ? `<div style="margin-bottom:12px">
      <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:4px">EVM Address (ETH/BNB/L2)</div>
      <div style="font-family:monospace;font-size:11px;word-break:break-all;color:var(--blue)">${evmAddr}</div>
    </div>` : ''}
    <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin:14px 0 8px">Network Balances</div>
    <div id="chainBalList"><div class="spinner"></div></div>
    <p style="font-size:11px;color:var(--muted);margin-top:14px;line-height:1.5">
      To deposit BTC, ETH, USDT or other assets, send them to your respective chain address above and use the Bridge to convert them to WBTC/WETH on Thronos Chain.
    </p>
    <button class="btn btn-secondary mt8" onclick="closeModal('networksModal');openModal('bridgeModal')">Open Bridge →</button>
  `;
  if (evmAddr) loadChainBalances(evmAddr);
  else document.getElementById('chainBalList').innerHTML = '<div class="status-msg">Unlock wallet to see cross-chain balances</div>';
}

async function deriveEvmAddress(compressedPubHex) {
  // Decompress public key and take keccak256 of the 64-byte uncompressed coords
  // Since we have noble secp256k1 loaded, we can use it
  const secp = getSecp();
  if (!secp) return '';
  const point = secp.Point ? secp.Point.fromHex(compressedPubHex) : null;
  if (!point) return '';
  const x = point.x.toString(16).padStart(64, '0');
  const y = point.y.toString(16).padStart(64, '0');
  const uncompressed = hexToBytes(x + y);
  // keccak256 the 64 bytes
  const hash = await keccak256(uncompressed);
  return '0x' + hash.slice(-40);
}

// Minimal keccak256 implementation (Ethereum-compatible)
// Using SubtleCrypto's SHA-3 is NOT Keccak-256 — we need a proper impl.
// Embed a tiny keccak-256 here.
async function keccak256(bytes) {
  // Tiny Keccak-256 by using the noble library's own utils if available
  const secp = getSecp();
  if (secp && secp.utils && typeof secp.utils.keccak256 === 'function') {
    const h = secp.utils.keccak256(bytes);
    return typeof h === 'string' ? h : bytesToHex(h);
  }
  // Fallback: derive via backend
  try {
    const r = await fetch(`${API}/api/utils/keccak256`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ data: bytesToHex(bytes) })
    });
    const d = await r.json().catch(() => ({}));
    return d.hash || '';
  } catch (_) { return ''; }
}

async function loadChainBalances(evmAddr) {
  const el = document.getElementById('chainBalList');
  if (!el) return;
  const chains = [
    { name: 'Ethereum', sym: 'ETH', rpc: 'https://eth.llamarpc.com' },
    { name: 'BNB Chain', sym: 'BNB', rpc: 'https://bsc-dataseed.binance.org' },
    { name: 'Arbitrum', sym: 'ETH', rpc: 'https://arb1.arbitrum.io/rpc' },
    { name: 'Base', sym: 'ETH', rpc: 'https://mainnet.base.org' },
  ];
  el.innerHTML = '<div class="spinner"></div>';
  const results = await Promise.allSettled(chains.map(c => fetchEvmNative(evmAddr, c.rpc)));
  el.innerHTML = chains.map((c, i) => {
    const bal = results[i].status === 'fulfilled' ? results[i].value : '?';
    return `<div class="token-row" style="margin-bottom:6px">
      <div class="token-icon">${tokenIcon(c.sym)}</div>
      <div class="token-info">
        <div class="token-name">${c.name}</div>
        <div class="token-sub">${evmAddr.slice(0, 10)}…</div>
      </div>
      <div class="token-balance">
        <div class="token-bal-num">${typeof bal === 'number' ? fmtNum(bal, 6) : bal} ${c.sym}</div>
      </div>
    </div>`;
  }).join('');
}

async function fetchEvmNative(addr, rpc) {
  try {
    const r = await fetch(rpc, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'eth_getBalance', params: [addr, 'latest'] })
    });
    const d = await r.json();
    const wei = parseInt(d.result, 16);
    return wei / 1e18;
  } catch (_) { return '?'; }
}

// ── History ───────────────────────────────────────────────────────────────────
async function loadHistory() {
  showScreen('historyScreen');
  const el = document.getElementById('txList');
  el.innerHTML = '<div class="status-msg"><div class="spinner"></div></div>';
  const data = await fetchHistory(_currentAddress);
  const txs = data?.transactions || data?.history || data?.txs || [];
  if (!txs.length) {
    el.innerHTML = '<div class="status-msg">No transactions yet</div>';
    return;
  }
  el.innerHTML = txs.map(tx => {
    const isSend = (tx.from || '').toLowerCase() === _currentAddress.toLowerCase();
    const amt = tx.amount || tx.value || '?';
    const tok = tx.token || tx.symbol || 'THR';
    return `<div class="tx-row">
      <div class="tx-icon">${isSend ? '↑' : '↓'}</div>
      <div class="tx-info">
        <div class="tx-type">${isSend ? 'Sent' : 'Received'} ${tok}</div>
        <div class="tx-addr">${isSend ? (tx.to || '?').slice(0,16) : (tx.from || '?').slice(0,16)}…</div>
      </div>
      <div class="tx-amount">
        <div class="tx-val ${isSend ? 'out' : 'in'}">${isSend ? '-' : '+'}${fmtNum(amt)} ${tok}</div>
        <div class="tx-date">${fmtDate(tx.timestamp || tx.time || tx.created_at)}</div>
      </div>
    </div>`;
  }).join('');
}

// ── Settings ──────────────────────────────────────────────────────────────────
async function handleExportKey() {
  const pin = document.getElementById('exportPin').value;
  if (!pin) { setStatus('exportStatus', 'Enter PIN', 'status-err'); return; }
  const acc = await getAccount(_currentAddress);
  if (!acc || !acc.kit) { setStatus('exportStatus', 'No key stored', 'status-err'); return; }
  try {
    const kit = typeof acc.kit === 'string' ? JSON.parse(acc.kit) : acc.kit;
    const privHex = await decryptPrivKey(kit, pin);
    const box = document.getElementById('exportKeyBox');
    box.textContent = privHex;
    box.classList.remove('hidden');
    setStatus('exportStatus', '⚠️ Copy and store securely. Never share.', 'status-err');
  } catch (_) {
    setStatus('exportStatus', 'Wrong PIN', 'status-err');
  }
}

// ── Accounts modal ────────────────────────────────────────────────────────────
async function showAccountsModal() {
  const accs = await getAccounts();
  const active = _currentAddress;
  const el = document.getElementById('accountsList');
  if (!accs.length) {
    el.innerHTML = '<div class="status-msg">No accounts</div>';
  } else {
    el.innerHTML = accs.map(a => `
      <div class="token-row" style="cursor:pointer;margin-bottom:6px;${a.address === active ? 'border-color:var(--gold)' : ''}" data-acc="${a.address}">
        <div class="token-icon">👛</div>
        <div class="token-info">
          <div class="token-name">${a.label || shortAddr(a.address)}</div>
          <div class="token-sub mono">${shortAddr(a.address)}</div>
        </div>
        ${a.address === active ? '<span style="color:var(--gold)">✓</span>' : ''}
      </div>`).join('');
    el.querySelectorAll('[data-acc]').forEach(row => {
      row.addEventListener('click', async () => {
        const addr = row.dataset.acc;
        await setActiveAddr(addr);
        _currentAddress = addr;
        closeModal('accountsModal');
        if (unlocked.has(addr)) {
          showScreen('homeScreen');
          loadHome();
        } else {
          // Need to unlock this account
          const hint = document.getElementById('lockAddrHint');
          if (hint) hint.textContent = `Unlock ${shortAddr(addr)}`;
          showScreen('lockScreen');
        }
      });
    });
  }
  openModal('accountsModal');
}

// ── Create wallet ─────────────────────────────────────────────────────────────
async function handleCreateWallet() {
  const pin  = document.getElementById('createPin').value;
  const pin2 = document.getElementById('createPin2').value;
  const label = document.getElementById('createLabel').value.trim();

  if (!pin || pin.length < 4) { setStatus('createStatus', 'PIN must be 4–8 digits', 'status-err'); return; }
  if (pin !== pin2) { setStatus('createStatus', 'PINs do not match', 'status-err'); return; }

  setStatus('createStatus', 'Generating keys…');
  document.getElementById('btnCreateWallet').disabled = true;

  try {
    const secp = getSecp();
    if (!secp) throw new Error('Crypto library not ready');
    const privBytes = secp.utils.randomPrivateKey ? secp.utils.randomPrivateKey() : crypto.getRandomValues(new Uint8Array(32));
    const privHex = bytesToHex(privBytes);
    const pubHex = getPubKeyHex(privHex);
    setStatus('createStatus', 'Deriving address…');
    const address = await deriveAddress(pubHex);
    const kit = await encryptPrivKey(privHex, pin);
    kit.pub = pubHex;
    await upsertAccount(address, kit, label || 'My Wallet', false);
    await setActiveAddr(address);
    unlocked.set(address, privHex);
    _currentAddress = address;

    // Show seed (use private key hex as recovery material)
    setStatus('createStatus', '✅ Wallet created!', 'status-ok');
    const seedSection = document.getElementById('seedSection');
    const seedGrid = document.getElementById('seedGrid');
    // Display private key as chunked recovery string
    const chunks = privHex.match(/.{1,8}/g) || [];
    seedGrid.innerHTML = chunks.map((c, i) => `<div class="seed-word"><span class="idx">${i+1}</span>${c}</div>`).join('');
    seedSection.classList.remove('hidden');
    document.getElementById('btnCreateWallet').classList.add('hidden');
    document.getElementById('btnCreateDone').classList.remove('hidden');
  } catch (e) {
    setStatus('createStatus', '❌ ' + (e.message || 'Creation failed'), 'status-err');
  }
  document.getElementById('btnCreateWallet').disabled = false;
}

// ── Import wallet ─────────────────────────────────────────────────────────────
async function handleImportKey() {
  const privHex = document.getElementById('importPrivKey').value.trim().replace(/^0x/, '');
  const pin = document.getElementById('importPin').value;
  const label = document.getElementById('importLabel').value.trim();

  if (!privHex || privHex.length !== 64) { setStatus('importStatus', 'Enter a valid 64-char hex private key', 'status-err'); return; }
  if (!pin || pin.length < 4) { setStatus('importStatus', 'PIN must be 4–8 digits', 'status-err'); return; }

  setStatus('importStatus', 'Deriving address…');
  document.getElementById('btnImportKey').disabled = true;
  try {
    const pubHex = getPubKeyHex(privHex);
    const address = await deriveAddress(pubHex);
    const kit = await encryptPrivKey(privHex, pin);
    kit.pub = pubHex;
    await upsertAccount(address, kit, label || 'Imported Wallet', false);
    await setActiveAddr(address);
    unlocked.set(address, privHex);
    _currentAddress = address;
    setStatus('importStatus', '✅ Imported!', 'status-ok');
    setTimeout(() => { showScreen('homeScreen'); loadHome(); }, 800);
  } catch (e) {
    setStatus('importStatus', '❌ ' + (e.message || 'Import failed'), 'status-err');
  }
  document.getElementById('btnImportKey').disabled = false;
}

async function handleImportAddr() {
  const addr = document.getElementById('importAddr').value.trim();
  if (!addr.startsWith('THR') || addr.length < 20) { setStatus('importAddrStatus', 'Enter a valid THR address', 'status-err'); return; }
  await upsertAccount(addr, null, 'Watch: ' + shortAddr(addr), true);
  await setActiveAddr(addr);
  _currentAddress = addr;
  setStatus('importAddrStatus', '✅ Watch address added', 'status-ok');
  setTimeout(() => { showScreen('homeScreen'); loadHome(); }, 800);
}

// ── Init / router ─────────────────────────────────────────────────────────────
async function init() {
  buildPinPad();
  wireEvents();

  const active = await getActiveAddr();
  if (!active) {
    showScreen('welcomeScreen');
    return;
  }
  _currentAddress = active;
  const acc = await getAccount(active);
  if (!acc) {
    showScreen('welcomeScreen');
    return;
  }
  if (acc.watchOnly) {
    showScreen('homeScreen');
    loadHome();
    return;
  }
  if (unlocked.has(active)) {
    showScreen('homeScreen');
    loadHome();
    return;
  }
  const hint = document.getElementById('lockAddrHint');
  if (hint) hint.textContent = `Unlock ${acc.label || shortAddr(active)}`;
  showScreen('lockScreen');
}

function wireEvents() {
  // Welcome
  document.getElementById('btnCreate').addEventListener('click', () => showScreen('createScreen'));
  document.getElementById('btnImport').addEventListener('click', () => showScreen('importScreen'));

  // Create
  document.getElementById('createBack').addEventListener('click', () => showScreen('welcomeScreen'));
  document.getElementById('btnCreateWallet').addEventListener('click', handleCreateWallet);
  document.getElementById('btnCreateDone').addEventListener('click', () => { showScreen('homeScreen'); loadHome(); });
  document.getElementById('btnCopySeed').addEventListener('click', () => {
    const words = [...document.querySelectorAll('.seed-word')].map(w => w.textContent).join(' ');
    copyText(words);
  });

  // Import tabs
  document.querySelectorAll('#importScreen .tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#importScreen .tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById('tab-privkey').classList.toggle('hidden', btn.dataset.tab !== 'privkey');
      document.getElementById('tab-address').classList.toggle('hidden', btn.dataset.tab !== 'address');
    });
  });
  document.getElementById('importBack').addEventListener('click', () => showScreen('welcomeScreen'));
  document.getElementById('btnImportKey').addEventListener('click', handleImportKey);
  document.getElementById('btnImportAddr').addEventListener('click', handleImportAddr);

  // Lock screen
  document.getElementById('btnLockForgot').addEventListener('click', () => showScreen('accountsModal') || showAccountsModal());

  // Home
  document.getElementById('btnRefresh').addEventListener('click', loadHome);
  document.getElementById('btnAccounts').addEventListener('click', showAccountsModal);
  document.getElementById('btnCopyAddr').addEventListener('click', () => copyText(_currentAddress || ''));
  document.getElementById('actSend').addEventListener('click', initSendModal);
  document.getElementById('actReceive').addEventListener('click', showReceiveModal);
  document.getElementById('actSwap').addEventListener('click', () => {
    _swapQuoteConfirmed = false;
    document.getElementById('btnSwapSubmit').textContent = 'Get Quote';
    setStatus('swapQuote', '');
    setStatus('swapStatus', '');
    openModal('swapModal');
  });
  document.getElementById('actStake').addEventListener('click', () => {
    setStatus('stakeStatus', '');
    openModal('stakeModal');
    loadStakePools();
  });
  document.getElementById('actBridge').addEventListener('click', () => {
    setStatus('bridgeStatus', '');
    setStatus('bridgeQuote', '');
    openModal('bridgeModal');
  });
  document.getElementById('actHistory').addEventListener('click', loadHistory);
  document.getElementById('actNetworks').addEventListener('click', loadNetworks);
  document.getElementById('actSettings').addEventListener('click', () => showScreen('settingsScreen'));

  // History
  document.getElementById('historyBack').addEventListener('click', () => showScreen('homeScreen'));

  // Settings
  document.getElementById('settingsBack').addEventListener('click', () => showScreen('homeScreen'));
  document.getElementById('setLock').addEventListener('click', () => {
    unlocked.clear();
    const hint = document.getElementById('lockAddrHint');
    if (hint) hint.textContent = `Unlock ${shortAddr(_currentAddress || '')}`;
    _pinBuffer = '';
    updatePinDots();
    showScreen('lockScreen');
  });
  document.getElementById('setExportKey').addEventListener('click', () => {
    document.getElementById('exportPin').value = '';
    document.getElementById('exportKeyBox').classList.add('hidden');
    setStatus('exportStatus', '');
    openModal('exportModal');
  });
  document.getElementById('setAddAccount').addEventListener('click', () => showScreen('createScreen'));
  document.getElementById('setForget').addEventListener('click', async () => {
    if (!confirm('Remove ALL wallet data from this browser? Make sure you have your private key backed up.')) return;
    await chrome.storage.local.clear();
    unlocked.clear();
    _currentAddress = null;
    showScreen('welcomeScreen');
  });

  // Send modal
  document.getElementById('sendClose').addEventListener('click', () => closeModal('sendModal'));
  document.getElementById('sendPaste').addEventListener('click', async () => {
    try { document.getElementById('sendTo').value = await navigator.clipboard.readText(); } catch (_) {}
  });
  document.getElementById('sendMax').addEventListener('click', () => {
    if (!_balanceData) return;
    const token = document.getElementById('sendToken').value;
    const t = (_balanceData.tokens || []).find(t => t.symbol === token);
    if (t) document.getElementById('sendAmount').value = t.balance;
    else if (token === 'THR') document.getElementById('sendAmount').value = _balanceData.thr_balance || '';
  });
  document.querySelectorAll('#sendNetTabs .tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#sendNetTabs .tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      _sendNet = btn.dataset.net;
      buildSendTokenList();
    });
  });
  document.getElementById('btnSendSubmit').addEventListener('click', handleSendSubmit);

  // Receive modal
  document.getElementById('receiveClose').addEventListener('click', () => closeModal('receiveModal'));
  document.getElementById('btnCopyReceive').addEventListener('click', () => copyText(_currentAddress || ''));

  // Swap modal
  document.getElementById('swapClose').addEventListener('click', () => closeModal('swapModal'));
  document.getElementById('btnSwapSubmit').addEventListener('click', handleSwapSubmit);

  // Stake modal
  document.getElementById('stakeClose').addEventListener('click', () => closeModal('stakeModal'));
  document.getElementById('btnStakeSubmit').addEventListener('click', handleStakeSubmit);
  document.getElementById('stakeMax').addEventListener('click', () => {
    if (!_balanceData) return;
    const thr = (_balanceData.tokens || []).find(t => t.symbol === 'THR');
    if (thr) document.getElementById('stakeAmount').value = thr.balance;
    else document.getElementById('stakeAmount').value = _balanceData.thr_balance || '';
  });

  // Bridge modal
  document.getElementById('bridgeClose').addEventListener('click', () => closeModal('bridgeModal'));
  document.getElementById('btnBridgeSubmit').addEventListener('click', handleBridgeSubmit);

  // Networks modal
  document.getElementById('networksClose').addEventListener('click', () => closeModal('networksModal'));

  // Accounts modal
  document.getElementById('accountsClose').addEventListener('click', () => closeModal('accountsModal'));
  document.getElementById('btnAddAccModal').addEventListener('click', () => { closeModal('accountsModal'); showScreen('createScreen'); });

  // Export modal
  document.getElementById('exportClose').addEventListener('click', () => closeModal('exportModal'));
  document.getElementById('btnExportReveal').addEventListener('click', handleExportKey);

  // Stake success
  document.getElementById('stakeSuccessClose').addEventListener('click', () => closeModal('stakeSuccessModal'));
  document.getElementById('btnStakeSuccessDone').addEventListener('click', () => closeModal('stakeSuccessModal'));

  // Close modals on backdrop click
  document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', e => {
      if (e.target === overlay) overlay.classList.remove('open');
    });
  });
}

// Start
document.addEventListener('DOMContentLoaded', init);
