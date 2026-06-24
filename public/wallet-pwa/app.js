// ─── Crypto helpers ───────────────────────────────────────────────────────────

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
    km, { name: 'AES-GCM', length: 256 }, true, ['encrypt', 'decrypt']
  );
}

async function decryptBlob(blob, pin) {
  const p = typeof blob === 'string' ? JSON.parse(blob) : blob;
  const key = await pbkdfKey(pin, hexToBytes(p.salt));
  const plain = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: hexToBytes(p.iv) }, key, hexToBytes(p.ct)
  );
  return bytesToHex(new Uint8Array(plain));
}

async function encryptBlob(dataHex, pin) {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const key = await pbkdfKey(pin, salt);
  const ct = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, hexToBytes(dataHex));
  return { v: 1, salt: bytesToHex(salt), iv: bytesToHex(iv), ct: bytesToHex(new Uint8Array(ct)) };
}

// Generates a fresh secp256k1 keypair and derives a THR address using the
// same scheme as the mobile app (thrAddressFromPubKey in wallet.ts):
// THR + uppercase-hex(ripemd160(sha256(compressed_pubkey))).slice(0,40)
let _nobleLibs = null;
async function _loadNobleLibs() {
  if (_nobleLibs) return _nobleLibs;
  const [{ secp256k1 }, { sha256 }, { ripemd160 }] = await Promise.all([
    import('https://esm.sh/@noble/curves@1.4.0/secp256k1'),
    import('https://esm.sh/@noble/hashes@1.4.0/sha256'),
    import('https://esm.sh/@noble/hashes@1.4.0/ripemd160'),
  ]);
  _nobleLibs = { secp256k1, sha256, ripemd160 };
  return _nobleLibs;
}

async function generateThrKeypair() {
  const { secp256k1, sha256, ripemd160 } = await _loadNobleLibs();
  const privBytes = secp256k1.utils.randomPrivateKey();
  const pubBytes = secp256k1.getPublicKey(privBytes, true); // compressed
  const h1 = sha256(pubBytes);
  const h2 = ripemd160(h1);
  const address = 'THR' + bytesToHex(h2).substring(0, 40).toUpperCase();
  return { privHex: bytesToHex(privBytes), pubHex: bytesToHex(pubBytes), address };
}

async function encryptWithKey(rawKey32, dataHex) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const aesKey = await crypto.subtle.importKey('raw', rawKey32, 'AES-GCM', false, ['encrypt']);
  const ct = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, aesKey, hexToBytes(dataHex));
  return { iv: bytesToHex(iv), ct: bytesToHex(new Uint8Array(ct)) };
}

async function decryptWithKey(rawKey32, envelope) {
  const aesKey = await crypto.subtle.importKey('raw', rawKey32, 'AES-GCM', false, ['decrypt']);
  const plain = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: hexToBytes(envelope.iv) }, aesKey, hexToBytes(envelope.ct)
  );
  return bytesToHex(new Uint8Array(plain));
}

async function wrapForSession(address, privHex) {
  const sk = crypto.getRandomValues(new Uint8Array(32));
  const envelope = await encryptWithKey(sk, privHex);
  sessionStorage.setItem(`thr_sk_${address}`, bytesToHex(sk));
  return envelope;
}
async function unwrapFromSession(address, envelope) {
  const skHex = sessionStorage.getItem(`thr_sk_${address}`);
  if (!skHex) throw new Error('session_expired');
  return decryptWithKey(hexToBytes(skHex), envelope);
}

// ─── WebAuthn ─────────────────────────────────────────────────────────────────

const RP_ID = ['localhost', '127.0.0.1'].includes(location.hostname)
  ? 'localhost'
  : location.hostname.endsWith('thronoschain.org') ? 'thronoschain.org' : location.hostname;

const PRF_LABEL = new TextEncoder().encode('thronos-wallet-v1');

async function webauthnAvailable() {
  return !!(window.PublicKeyCredential &&
    await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable().catch(() => false));
}

async function registerWebAuthn(address) {
  const cred = await navigator.credentials.create({
    publicKey: {
      challenge: crypto.getRandomValues(new Uint8Array(32)),
      rp: { name: 'Thronos Wallet', id: RP_ID },
      user: { id: new TextEncoder().encode(address.slice(-32)), name: address, displayName: 'THR Wallet' },
      pubKeyCredParams: [{ alg: -7, type: 'public-key' }, { alg: -257, type: 'public-key' }],
      authenticatorSelection: { authenticatorAttachment: 'platform', userVerification: 'required', residentKey: 'preferred' },
      extensions: { prf: { eval: { first: PRF_LABEL } } },
      timeout: 60000
    }
  });
  return cred;
}

async function assertWebAuthn(credIdHex) {
  return navigator.credentials.get({
    publicKey: {
      challenge: crypto.getRandomValues(new Uint8Array(32)),
      rpId: RP_ID,
      allowCredentials: [{ type: 'public-key', id: hexToBytes(credIdHex) }],
      userVerification: 'required',
      extensions: { prf: { eval: { first: PRF_LABEL } } },
      timeout: 60000
    }
  });
}

// ─── Multi-account storage ────────────────────────────────────────────────────
// Schema:
//   thr_accounts  → JSON: [{ address, kit: string, label?: string }]
//   thr_active    → string: active address
//   thr_fid_<addr>→ JSON: { credId, mode }   (Face ID per account)
//   thr_env_<addr>→ JSON: { iv, ct }         (encrypted private key for FID)
//   sessionStorage thr_sk_<addr> → hex       (session key, cleared on tab close)

const LS = {
  get: k => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch {} },
  del: k => { try { localStorage.removeItem(k); } catch {} },
  getObj: k => { try { return JSON.parse(localStorage.getItem(k)); } catch { return null; } },
  setObj: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} }
};

function getAccounts() { return LS.getObj('thr_accounts') || []; }
function saveAccounts(accs) { LS.setObj('thr_accounts', accs); }
function getActiveAddr() { return LS.get('thr_active') || null; }
function setActiveAddr(addr) { LS.set('thr_active', addr); }

function getAccount(address) {
  return getAccounts().find(a => a.address === address) || null;
}

function upsertAccount(address, kit, label, pledge_send_secret) {
  const accs = getAccounts();
  const idx = accs.findIndex(a => a.address === address);
  const entry = { address, kit: typeof kit === 'string' ? kit : JSON.stringify(kit), label: label || shortAddr(address) };
  if (pledge_send_secret) entry.pledge_send_secret = pledge_send_secret;
  if (idx >= 0) accs[idx] = entry; else accs.push(entry);
  saveAccounts(accs);
}

function removeAccount(address) {
  saveAccounts(getAccounts().filter(a => a.address !== address));
  LS.del(`thr_fid_${address}`);
  LS.del(`thr_env_${address}`);
  sessionStorage.removeItem(`thr_sk_${address}`);
  if (getActiveAddr() === address) {
    const remaining = getAccounts();
    setActiveAddr(remaining.length ? remaining[0].address : null);
  }
}

function shortAddr(addr) { return addr ? `${addr.slice(0, 6)}…${addr.slice(-4)}` : ''; }

// ─── In-memory unlocked wallets ───────────────────────────────────────────────
// Map<address → { privHex }>  — only populated after successful unlock
const unlocked = new Map();

// ─── API ──────────────────────────────────────────────────────────────────────

// When running inside the Capacitor native shell, use absolute URL set by index.html
const _NATIVE_API = (window.__THRONOS_NATIVE__ && window.__THRONOS_API__) ? window.__THRONOS_API__ : null;
const API_BASE  = _NATIVE_API || (location.hostname === 'localhost' || location.hostname.startsWith('192.') ? '' : '');
const API_READ  = _NATIVE_API || 'https://api.thronoschain.org';
const API_WRITE = _NATIVE_API || 'https://api.thronoschain.org';

async function fetchBalances(address) {
  // Use the same endpoint as the web wallet: /api/balances?show_zero=true
  try {
    const r = await fetch(`${API_WRITE}/api/balances?address=${encodeURIComponent(address)}&show_zero=true`);
    if (r.ok) {
      const d = await r.json();
      const tokens = Array.isArray(d.tokens) ? d.tokens : [];
      const thr = tokens.find(t => t.symbol === 'THR')?.balance ?? d.thr_balance ?? 0;
      if (Number(thr) > 0 || tokens.length) return d;
    }
  } catch {}
  // If address has no balance, try legacy_address from Recovery Kit
  try {
    const acc = getAccount(address);
    const kitRaw = acc?.kit;
    const kit = kitRaw ? (typeof kitRaw === 'string' ? JSON.parse(kitRaw) : kitRaw) : null;
    const legacy = kit?.legacy_address;
    if (legacy && legacy !== address) {
      const r2 = await fetch(`${API_WRITE}/api/balances?address=${encodeURIComponent(legacy)}&show_zero=true`);
      if (r2.ok) return await r2.json();
    }
  } catch {}
  return null;
}


// ─── Cross-chain portfolio helpers ────────────────────────────────────────────

let _ethers = null;
async function _loadEthers() {
  if (_ethers) return _ethers;
  if (window.ethers) { _ethers = window.ethers; return _ethers; }
  await new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = 'https://cdn.jsdelivr.net/npm/ethers@5.7.2/dist/ethers.umd.min.js';
    s.onload = () => { _ethers = window.ethers; resolve(); };
    s.onerror = () => resolve(); // proceed even if CDN fails
    document.head.appendChild(s);
  });
  return _ethers;
}

async function _deriveEvmAddress(privHex) {
  try {
    const ethers = await _loadEthers();
    if (!ethers) return null;
    const wallet = new ethers.Wallet('0x' + privHex.replace(/^0x/, ''));
    return wallet.address;
  } catch { return null; }
}

async function _fetchBtcAddress(privHex, address) {
  if (!privHex) return '';
  const cacheKey = `thr_btc_address_${address}`;
  const cached = localStorage.getItem(cacheKey);
  if (cached) return cached;
  try {
    const r = await fetch(`${API_WRITE}/api/wallet/v1/btc-address-from-key`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ private_key_hex: privHex }),
    });
    const d = await r.json();
    if (d.ok && d.btc_address) {
      localStorage.setItem(cacheKey, d.btc_address);
      return d.btc_address;
    }
  } catch {}
  return '';
}

async function _fetchBtcBalance(btcAddr) {
  if (!btcAddr) return null;
  try {
    const r = await fetch(`https://blockstream.info/api/address/${encodeURIComponent(btcAddr)}`, { signal: AbortSignal.timeout(8000) });
    if (!r.ok) return null;
    const d = await r.json();
    const sats = (d.chain_stats?.funded_txo_sum || 0) - (d.chain_stats?.spent_txo_sum || 0);
    return sats / 1e8;
  } catch { return null; }
}

async function _fetchEvmNative(evmAddr, rpcUrl) {
  if (!evmAddr || !rpcUrl) return null;
  try {
    const r = await fetch(rpcUrl, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jsonrpc:'2.0', method:'eth_getBalance', params:[evmAddr,'latest'], id:1 }),
      signal: AbortSignal.timeout(8000),
    });
    const d = await r.json();
    if (d.error || !d.result) return null;
    return parseInt(d.result, 16) / 1e18;
  } catch { return null; }
}

async function _fetchErc20(evmAddr, tokenContract, rpcUrl, decimals) {
  if (!evmAddr || !tokenContract || !rpcUrl) return null;
  try {
    const data = '0x70a08231' + evmAddr.replace(/^0x/, '').padStart(64, '0');
    const r = await fetch(rpcUrl, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jsonrpc:'2.0', method:'eth_call', params:[{to:tokenContract, data},'latest'], id:1 }),
      signal: AbortSignal.timeout(8000),
    });
    const d = await r.json();
    if (d.error || !d.result || d.result === '0x' || d.result === '0x' + '0'.repeat(64)) return null;
    // Use BigInt to avoid precision loss on 256-bit ERC20 balances
    const raw = BigInt(d.result);
    if (raw === 0n) return null;
    const divisor = BigInt(10 ** decimals);
    const whole = Number(raw / divisor);
    const frac  = Number(raw % divisor) / (10 ** decimals);
    return whole + frac;
  } catch { return null; }
}

const _CC_RPC = {
  eth:  'https://eth.llamarpc.com',
  bnb:  'https://bsc-dataseed.binance.org',
  arb:  'https://arb1.arbitrum.io/rpc',
  op:   'https://mainnet.optimism.io',
  base: 'https://mainnet.base.org',
  poly: 'https://polygon-rpc.com',
};
const _USDT_BNB  = '0x55d398326f99059fF775485246999027B3197955'; // 18 dec
const _USDT_ARB  = '0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9'; // 6 dec
const _USDC_BASE = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'; // 6 dec

// EVM asset action config
const _EVM_CHAIN_IDS = { ethereum: 1, bnb: 56, arbitrum: 42161, base: 8453 };
const _EVM_TOKENS = {
  bnb:      { USDT: { contract: _USDT_BNB, decimals: 18 } },
  arbitrum: { USDT: { contract: _USDT_ARB, decimals: 6  } },
  base:     { USDC: { contract: _USDC_BASE, decimals: 6  } },
};
const _EVM_POOL_IDS = { bnb: 'bsc-usdt', base: 'base-usdc' };

// System addresses that must NEVER be used as a personal wallet sender.
// Includes Pythia pool vault and known fee-collector/treasury addresses.
const _EVM_BLOCKED_SENDERS = new Set([
  '0x76b1926f40c596e10c30ae7a359df8a0b21ac4a2', // Pythia pool vault
  '0x9aa993d1e59e777101443339b934a0605619cc69', // fee collector / treasury
]);

/**
 * Pre-send guard for EVM send. Returns {ok:true} or {ok:false, reason, userMsg}.
 * All checks must pass before any signing attempt is made.
 */
async function _pwaEvmSendGuard(network, evmAddr) {
  // 1. Wallet unlocked
  if (!_pwaSigningCtx?.privHex) {
    return { ok: false, reason: 'wallet_locked',
             userMsg: 'Wallet is locked. Unlock your wallet before sending.' };
  }
  // 2. Chain supported
  if (!_EVM_CHAIN_IDS[network]) {
    return { ok: false, reason: 'unsupported_chain',
             userMsg: `Chain "${network}" is not supported for EVM send.` };
  }
  // 3. Signer library present and has a valid sign method
  let _secp;
  try {
    const libs = await _loadNobleLibs();
    _secp = libs?.secp256k1;
  } catch (e) {
    return { ok: false, reason: 'signer_load_failed',
             userMsg: 'EVM signer unavailable. Wallet build must be updated before sending.' };
  }
  if (typeof _secp?.signAsync !== 'function' && typeof _secp?.sign !== 'function') {
    return { ok: false, reason: 'signer_missing',
             userMsg: 'EVM signer unavailable. Wallet build must be updated before sending.' };
  }
  // 4. Re-derive EVM address from live session key and verify it matches displayed From
  let derivedAddr;
  try {
    derivedAddr = await _deriveEvmAddress(_pwaSigningCtx.privHex);
  } catch (e) {
    return { ok: false, reason: 'derive_failed',
             userMsg: 'Could not derive EVM address for this wallet. EVM Send blocked.' };
  }
  if (!derivedAddr) {
    return { ok: false, reason: 'derive_empty',
             userMsg: 'Could not derive EVM address for this wallet. EVM Send blocked.' };
  }
  if (derivedAddr.toLowerCase() !== (evmAddr || '').toLowerCase()) {
    return {
      ok: false, reason: 'address_mismatch',
      userMsg: 'Sender address mismatch. Refusing to sign.\n\n' +
               'Displayed: ' + evmAddr + '\n' +
               'Derived:   ' + derivedAddr + '\n\n' +
               'This may indicate a fee collector or vault address was shown instead of your wallet address.',
    };
  }
  // 5. Block known system / vault / fee-collector addresses
  if (_EVM_BLOCKED_SENDERS.has((evmAddr || '').toLowerCase())) {
    return {
      ok: false, reason: 'blocked_sender',
      userMsg: 'Sender address mismatch. Refusing to sign.\n\n' +
               evmAddr + ' is a system or vault address and cannot be used as a personal wallet sender.',
    };
  }
  return { ok: true, derivedAddr, secp: _secp };
}

// Signing context set when wallet is unlocked in showWallet(); cleared on lock
let _pwaSigningCtx = null;

async function _fetchAllChainBalances(privHex, btcAddr) {
  const evmAddr = privHex ? await _deriveEvmAddress(privHex) : null;
  const [btc, eth, bnb, arb, op, base, usdtBnb, usdtArb, usdcBase] = await Promise.allSettled([
    _fetchBtcBalance(btcAddr),
    _fetchEvmNative(evmAddr, _CC_RPC.eth),
    _fetchEvmNative(evmAddr, _CC_RPC.bnb),
    _fetchEvmNative(evmAddr, _CC_RPC.arb),
    _fetchEvmNative(evmAddr, _CC_RPC.op),
    _fetchEvmNative(evmAddr, _CC_RPC.base),
    _fetchErc20(evmAddr, _USDT_BNB, _CC_RPC.bnb, 18),
    _fetchErc20(evmAddr, _USDT_ARB, _CC_RPC.arb, 6),
    _fetchErc20(evmAddr, _USDC_BASE, _CC_RPC.base, 6),
  ]);
  const v = r => r.status === 'fulfilled' ? r.value : null;
  return { evmAddr, btc: v(btc), eth: v(eth), bnb: v(bnb), arb: v(arb), op: v(op), base: v(base), usdtBnb: v(usdtBnb), usdtArb: v(usdtArb), usdcBase: v(usdcBase) };
}

async function fetchHistory(address) {
  try {
    const r = await fetch(`${API_WRITE}/wallet_data/${encodeURIComponent(address)}`);
    if (!r.ok) return [];
    const d = await r.json();
    return Array.isArray(d.transactions) ? d.transactions : [];
  } catch { return []; }
}

// V1-compatible send: tries wallet_v1 signed transfer, falls back to legacy send_seed
async function sendToken(from, to, amount, token, privHex) {
  // Try V1 signed transfer endpoint first
  try {
    const r = await fetch(`${API_WRITE}/api/wallet/v1/transfer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ from, to: to.trim(), amount: String(amount),
        token: (token || 'THR').toUpperCase(), private_key_hex: privHex })
    });
    const d = await r.json().catch(() => ({}));
    if (r.ok && !d.error) return d;
  } catch {}
  // Fallback: legacy endpoint (works for old HMAC addresses using privHex as send_seed proxy)
  const r = await fetch(`${API_WRITE}/wallet/send`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token: (token || 'THR').toUpperCase(), from, to: to.trim(), amount: String(amount), secret: privHex, speed: 'fast', passphrase: '' })
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok || d.error) throw new Error(d.error || d.message || 'send_failed');
  return d;
}

// ─── DOM helpers ──────────────────────────────────────────────────────────────

const root = document.getElementById('root');
function render(html) { root.innerHTML = html; }
function setError(msg) { const e = document.getElementById('err'); if (e) { e.textContent = msg || ''; e.classList.toggle('hidden', !msg); } }
function setSuccess(msg) { const e = document.getElementById('ok'); if (e) { e.textContent = msg || ''; e.classList.toggle('hidden', !msg); } }
function readFile(file) {
  return new Promise((res, rej) => { const r = new FileReader(); r.onload = e => res(e.target.result); r.onerror = rej; r.readAsText(file); });
}

// ─── Token display helpers ────────────────────────────────────────────────────

const TOKEN_ICONS = { THR: '⬡', BTC: '₿', ETH: 'Ξ', WBTC: '₿', WETH: 'Ξ', USDT: '₮', USDC: '○', TZM: 'T' };

function tokenIcon(symbol) { return TOKEN_ICONS[(symbol || '').toUpperCase()] || '◆'; }

function renderBalances(data) {
  if (!data) return '<p style="color:var(--muted);font-size:.88rem">Could not load balances.</p>';
  // data may be an object { THR: "100", BTC: "0.001", ... } or { thr_balance: "100", balances: {...} }
  let tokens = {};
  if (data.thr_balance !== undefined) tokens.THR = data.thr_balance;
  if (data.balance !== undefined && !tokens.THR) tokens.THR = data.balance;
  if (data.balances && typeof data.balances === 'object') Object.assign(tokens, data.balances);
  // Also check top-level keys that look like token amounts
  for (const [k, v] of Object.entries(data)) {
    if (typeof v === 'string' || typeof v === 'number') {
      const sym = k.toUpperCase();
      if (!['ADDRESS', 'STATUS', 'NONCE', 'ERROR', 'MESSAGE'].includes(sym) && !tokens[sym]) tokens[sym] = v;
    }
  }
  const entries = Object.entries(tokens).filter(([, v]) => v !== undefined && v !== null && v !== '');
  if (!entries.length) return '<p style="color:var(--muted);font-size:.88rem">No balance data.</p>';
  return entries.map(([sym, val]) => `
    <div class="token-row">
      <span class="token-icon">${tokenIcon(sym)}</span>
      <span class="token-sym">${sym}</span>
      <span class="token-bal">${Number(val).toLocaleString(undefined, { maximumFractionDigits: 8 })}</span>
    </div>
  `).join('');
}

// ─── Import screen ────────────────────────────────────────────────────────────

async function showImport(addingExtra = false) {
  const title = addingExtra ? 'Add Account' : 'Import Wallet';
  const sub = addingExtra ? 'Import an additional Recovery Kit (.json) to add a new account.' : 'Open your Recovery Kit (.json) file and enter your PIN.';

  render(`
    <div class="screen">
      <div class="logo">⬡ THR</div>
      <p class="tagline">Thronos Chain Wallet</p>

      <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px">
        <button class="btn btn--ghost" id="tabCreate" style="flex:1;min-width:80px;padding:8px;font-size:.8rem;border-radius:10px;display:none">✨ New Wallet</button>
        <button class="btn" id="tabKit" style="flex:1;min-width:80px;padding:8px;font-size:.8rem;background:var(--accent);color:#fff;border-radius:10px">Recovery Kit</button>
        <button class="btn btn--ghost" id="tabBtcPledge" style="flex:1;min-width:80px;padding:8px;font-size:.8rem;border-radius:10px">₿ BTC Pledge</button>
        <button class="btn btn--ghost" id="tabUsdtPledge" style="flex:1;min-width:80px;padding:8px;font-size:.8rem;border-radius:10px">💵 USDT Pledge</button>
      </div>

      <!-- Create New Wallet tab -->
      <div id="paneCreate" class="card" style="display:none">
        <h2 style="font-size:1.1rem">Create New Wallet</h2>
        <p style="color:var(--muted);font-size:.85rem">Generate a brand-new Thronos address on this device. Your private key never leaves the browser.</p>
        <div id="createStep1">
          <button class="btn btn--primary" id="generateWalletBtn">⚡ Generate New Wallet</button>
        </div>
        <div id="createStep2" style="display:none;margin-top:12px">
          <div id="createAddrBox" style="background:#0d0a1a;border:1px solid var(--accent);border-radius:8px;padding:10px;font-size:.82rem;color:var(--accent);word-break:break-all;margin-bottom:10px"></div>
          <p style="color:#ff6b6b;font-size:.78rem;margin-bottom:8px">⚠️ Set a PIN to protect this wallet. There is no recovery if you lose both your PIN and the Recovery Kit file you'll download next.</p>
          <input type="text" id="createLabel" class="input" placeholder="Account label (optional)">
          <input type="password" id="createPin" class="input mt8" placeholder="New PIN (4-8 digits)" autocomplete="new-password">
          <input type="password" id="createPinConfirm" class="input mt8" placeholder="Confirm PIN" autocomplete="new-password">
          <button class="btn btn--primary mt8" id="createConfirmBtn">✅ Create Wallet</button>
        </div>
        <div id="createErr" class="banner banner--error hidden"></div>
      </div>

      <!-- Recovery Kit tab -->
      <div id="paneKit" class="card">
        <h2 style="font-size:1.1rem">${title}</h2>
        <p style="color:var(--muted);font-size:.85rem">${sub}</p>
        <button class="btn btn--primary" id="pickFile">Select Recovery Kit</button>
        <div id="filePill" class="file-pill hidden"></div>
        <div id="labelRow" class="hidden" style="display:flex;flex-direction:column;gap:8px">
          <input type="text" id="label" class="input" placeholder="Account label (optional)">
        </div>
        <div id="pinSection" class="hidden" style="display:flex;flex-direction:column;gap:12px">
          <input type="password" id="pin" class="input" placeholder="Enter PIN" autocomplete="current-password">
          <button class="btn btn--primary" id="importBtn">Unlock</button>
        </div>
        <div id="err" class="banner banner--error hidden"></div>
        <p style="margin-top:14px;font-size:.78rem;color:var(--muted);text-align:center">Migrating from old pledge system? <button class="btn--link" id="showPledgeSecretBtn" style="color:var(--accent);background:none;border:none;cursor:pointer;font-size:.78rem;padding:0;text-decoration:underline">Use your Pledge Secret →</button></p>
      </div>

      <!-- BTC Pledge tab (new wallet via direct BTC payment) -->
      <div id="paneBtcPledge" class="card" style="display:none">
        <h2 style="font-size:1.1rem">₿ BTC Pledge</h2>
        <p style="color:var(--muted);font-size:.85rem">Send a small BTC fee to the pledge address below, then submit your sending BTC address to claim a THR wallet.</p>
        <div id="btcPledgeStep1">
          <div style="background:#0d0a1a;border:1px solid #F7931A;border-radius:8px;padding:10px;font-size:.82rem;color:#F7931A;word-break:break-all;margin-bottom:10px" id="btcPledgeVaultBox">Loading vault address…</div>
          <input type="text" id="btcPledgeAddr" class="input" placeholder="Your BTC address (sender)" autocomplete="off">
          <input type="text" id="btcPledgeText" class="input mt8" placeholder="Pledge message (optional)">
          <button class="btn btn--primary mt8" id="btcPledgeSubmitBtn">📤 Submit Pledge</button>
        </div>
        <div id="btcPledgeStep2" style="display:none;margin-top:12px">
          <div id="btcPledgeInfo" style="background:#0d0a1a;border:1px solid var(--accent);border-radius:8px;padding:10px;font-size:.82rem;color:var(--accent);word-break:break-all;margin-bottom:10px"></div>
          <div id="btcPledgeSecretBox" style="background:#1a0a0a;border:1px solid #ff6b6b;border-radius:8px;padding:10px;font-size:.8rem;color:#ff6b6b;word-break:break-all;margin-bottom:10px"></div>
          <button class="btn btn--ghost" id="btcPledgeCheckBtn">🔄 Check Confirmation</button>
        </div>
        <div id="btcPledgeDone" style="display:none;margin-top:12px">
          <p style="color:var(--muted);font-size:.85rem">✅ BTC confirmed! Set a PIN to create your V1 wallet — we'll generate your Recovery Kit and encrypted PDF contract with LSB steganography.</p>
          <input type="password" id="btcPledgePin" class="input mt8" placeholder="New PIN (4-8 digits)" autocomplete="new-password">
          <input type="password" id="btcPledgePinConfirm" class="input mt8" placeholder="Confirm PIN" autocomplete="new-password">
          <button class="btn btn--primary mt8" id="btcPledgeCreateV1Btn">🔑 Create V1 Wallet</button>
        </div>
        <div id="btcPledgeErr" class="banner banner--error hidden"></div>
      </div>

      <!-- USDT/BNB Pledge tab (new wallet via USDT on BSC) -->
      <div id="paneUsdtPledge" class="card" style="display:none">
        <h2 style="font-size:1.1rem">💵 USDT Pledge (BNB Chain)</h2>
        <p style="color:var(--muted);font-size:.85rem">Register your BNB sending address, send USDT (BEP20) to the vault, then check payment. Once confirmed you'll get a V1 wallet, Recovery Kit, and PDF contract.</p>
        <div id="usdtPledgeStep1">
          <div style="background:#0d0a1a;border:1px solid #26A17B;border-radius:8px;padding:10px;font-size:.82rem;color:#26A17B;word-break:break-all;margin-bottom:10px" id="usdtPledgeVaultBox">Loading vault address…</div>
          <input type="text" id="usdtPledgeBnbAddr" class="input" placeholder="Your BNB sending address (0x...)" autocomplete="off">
          <button class="btn btn--primary mt8" id="usdtPledgeRegisterBtn">📋 Register Address</button>
        </div>
        <div id="usdtPledgePending" style="display:none;margin-top:12px">
          <div id="usdtPledgePendingInfo" style="background:#0d0a1a;border:1px solid #26A17B;border-radius:8px;padding:10px;font-size:.82rem;color:#26A17B;word-break:break-all;margin-bottom:10px"></div>
          <button class="btn btn--ghost" id="usdtPledgeCheckBtn">🔄 Check Payment</button>
        </div>
        <div id="usdtPledgeSetupV1" style="display:none;margin-top:12px">
          <p style="color:var(--muted);font-size:.85rem">✅ Payment confirmed! Set a PIN to create your V1 wallet — your Recovery Kit and PDF contract with LSB-embedded secret will be generated.</p>
          <input type="password" id="usdtPledgePin" class="input mt8" placeholder="New PIN (4-8 digits)" autocomplete="new-password">
          <input type="password" id="usdtPledgePinConfirm" class="input mt8" placeholder="Confirm PIN" autocomplete="new-password">
          <button class="btn btn--primary mt8" id="usdtPledgeCreateV1Btn">🔑 Create V1 Wallet</button>
        </div>
        <div id="usdtPledgeErr" class="banner banner--error hidden"></div>
      </div>

      <!-- Pledge Secret tab (HMAC/v0 wallet migration) -->
      <div id="panePledge" class="card" style="display:none">
        <h2 style="font-size:1.1rem">Pledge Wallet Migration</h2>
        <p style="color:var(--muted);font-size:.85rem">Enter the <strong>send secret</strong> from your original pledge. The system will find your address and create a V1 wallet.</p>
        <div id="pledgeStep1">
          <input type="password" id="pledgeSecret" class="input" placeholder="Pledge send secret / auth token" autocomplete="off">
          <button class="btn btn--primary mt8" id="pledgeLookupBtn">🔍 Find My Wallet</button>
        </div>
        <div id="pledgeStep2" style="display:none;margin-top:12px">
          <div id="pledgeInfo" style="background:#0d0a1a;border:1px solid var(--accent);border-radius:8px;padding:10px;font-size:.82rem;color:var(--accent);word-break:break-all;margin-bottom:10px"></div>
          <input type="password" id="pledgeMigratePin" class="input" placeholder="New PIN (4-8 digits)" autocomplete="new-password">
          <div style="display:flex;gap:8px;margin-top:8px">
            <button class="btn btn--primary" id="pledgeMigrateBtn" style="flex:2">✅ Migrate to V1</button>
            <button class="btn btn--ghost" id="pledgeBackBtn" style="flex:1">Back</button>
          </div>
        </div>
        <div id="pledgeErr" class="banner banner--error hidden"></div>
      </div>

      ${addingExtra ? '<button class="btn btn--ghost mt16" id="cancelBtn">Cancel</button>' : '<p class="mt24" style="color:var(--muted);font-size:.8rem;text-align:center">Your keys never leave this device.</p>'}
    </div>
  `);

  // Tab switching (Create / Kit / Pledge)
  function activateTab(name) {
    const panes = { create: 'paneCreate', kit: 'paneKit', btcpledge: 'paneBtcPledge', usdtpledge: 'paneUsdtPledge', pledge: 'panePledge' };
    const tabs  = { create: 'tabCreate',  kit: 'tabKit',  btcpledge: 'tabBtcPledge',  usdtpledge: 'tabUsdtPledge' };
    for (const k of Object.keys(panes)) {
      document.getElementById(panes[k]).style.display = (k === name) ? '' : 'none';
    }
    for (const k of Object.keys(tabs)) {
      document.getElementById(tabs[k]).style.background = (k === name) ? 'var(--accent)' : '';
      document.getElementById(tabs[k]).style.color = (k === name) ? '#fff' : '';
    }
  }
  document.getElementById('tabCreate').addEventListener('click', () => activateTab('create'));
  document.getElementById('tabKit').addEventListener('click', () => activateTab('kit'));
  document.getElementById('tabBtcPledge').addEventListener('click', () => { activateTab('btcpledge'); loadBtcPledgeVault(); });
  document.getElementById('tabUsdtPledge').addEventListener('click', () => { activateTab('usdtpledge'); loadUsdtPledgeVault(); });
  document.getElementById('showPledgeSecretBtn').addEventListener('click', () => activateTab('pledge'));

  // ── Create New Wallet ──
  let generatedKeypair = null;
  document.getElementById('generateWalletBtn').addEventListener('click', async () => {
    const btn = document.getElementById('generateWalletBtn');
    const errEl = document.getElementById('createErr');
    errEl.classList.add('hidden');
    btn.disabled = true; btn.textContent = 'Generating…';
    try {
      generatedKeypair = await generateThrKeypair();
      document.getElementById('createAddrBox').innerHTML =
        '✅ New address:<br><b>' + generatedKeypair.address + '</b>';
      document.getElementById('createStep1').style.display = 'none';
      document.getElementById('createStep2').style.display = '';
    } catch (e) {
      errEl.textContent = 'Could not generate wallet: ' + e.message;
      errEl.classList.remove('hidden');
    } finally {
      btn.disabled = false; btn.textContent = '⚡ Generate New Wallet';
    }
  });

  document.getElementById('createConfirmBtn').addEventListener('click', async () => {
    const errEl = document.getElementById('createErr');
    errEl.classList.add('hidden');
    if (!generatedKeypair) { errEl.textContent = 'Generate a wallet first'; errEl.classList.remove('hidden'); return; }
    const pin = document.getElementById('createPin')?.value?.trim();
    const pinConfirm = document.getElementById('createPinConfirm')?.value?.trim();
    const label = document.getElementById('createLabel')?.value?.trim();
    if (!pin || pin.length < 4) { errEl.textContent = 'PIN must be 4-8 digits'; errEl.classList.remove('hidden'); return; }
    if (pin !== pinConfirm) { errEl.textContent = 'PINs do not match'; errEl.classList.remove('hidden'); return; }

    const btn = document.getElementById('createConfirmBtn');
    btn.disabled = true; btn.textContent = 'Creating…';
    try {
      const { address, privHex, pubHex } = generatedKeypair;
      const encrypted_private_key_backup = await encryptBlob(privHex, pin);
      const kit = {
        version: 'wallet-v1-recovery-kit',
        canonical_v1_address: address,
        public_key: pubHex,
        encrypted_private_key_backup,
        created_at: new Date().toISOString(),
      };

      upsertAccount(address, kit, label || shortAddr(address));
      setActiveAddr(address);
      unlocked.set(address, { privHex });

      // Auto-download Recovery Kit so the user has an offline backup immediately
      const blob = new Blob([JSON.stringify(kit, null, 2)], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `thr-recovery-kit-${address.slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(a.href);

      // Offer Face ID / passkey setup now that the wallet is unlocked in-memory
      await promptFaceID(address, privHex);
    } catch (e) {
      btn.disabled = false; btn.textContent = '✅ Create Wallet';
      errEl.textContent = 'Could not create wallet: ' + e.message;
      errEl.classList.remove('hidden');
    }
  });

  // ── BTC Pledge ──
  let btcPledgeSecret = null;
  let btcPledgeBtcAddr = null;
  async function loadBtcPledgeVault() {
    const box = document.getElementById('btcPledgeVaultBox');
    if (!box || box.dataset.loaded) return;
    try {
      const r = await fetch(`${API_WRITE}/api/pledge/quote`);
      const d = await r.json().catch(() => ({}));
      if (r.ok && d.ok !== false) {
        box.innerHTML = `Send <b>${d.required_btc ?? '0.00001'} BTC</b> to:<br>${d.vault_address || '—'}`;
        box.dataset.loaded = '1';
      } else {
        box.textContent = 'Could not load vault address.';
      }
    } catch (e) {
      box.textContent = 'Network error loading vault address.';
    }
  }

  document.getElementById('btcPledgeSubmitBtn').addEventListener('click', async () => {
    const btcAddr = document.getElementById('btcPledgeAddr')?.value?.trim();
    const pledgeText = document.getElementById('btcPledgeText')?.value?.trim();
    const errEl = document.getElementById('btcPledgeErr');
    errEl.classList.add('hidden');
    if (!btcAddr) { errEl.textContent = 'Enter your sending BTC address'; errEl.classList.remove('hidden'); return; }
    const btn = document.getElementById('btcPledgeSubmitBtn');
    btn.disabled = true; btn.textContent = 'Submitting…';
    try {
      const r = await fetch(`${API_WRITE}/api/pledge`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ btc_address: btcAddr, pledge_text: pledgeText || 'I pledge to the Thronos Network' })
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok || !d.ok) {
        errEl.textContent = 'Pledge failed: ' + (d.error || 'make sure you already sent BTC to the vault address above');
        errEl.classList.remove('hidden'); return;
      }
      btcPledgeBtcAddr = btcAddr;
      document.getElementById('btcPledgeInfo').innerHTML = '⏳ THR Address (awaiting BTC confirmation):<br><b>' + (d.thr_address || '—') + '</b>';
      document.getElementById('btcPledgeStep1').style.display = 'none';
      document.getElementById('btcPledgeStep2').style.display = '';
    } catch (e) {
      errEl.textContent = 'Network error: ' + e.message; errEl.classList.remove('hidden');
    } finally {
      btn.disabled = false; btn.textContent = '📤 Submit Pledge';
    }
  });

  document.getElementById('btcPledgeCheckBtn').addEventListener('click', async () => {
    const errEl = document.getElementById('btcPledgeErr');
    errEl.classList.add('hidden');
    if (!btcPledgeBtcAddr) return;
    const btn = document.getElementById('btcPledgeCheckBtn');
    btn.disabled = true; btn.textContent = 'Checking…';
    try {
      const r = await fetch(`${API_WRITE}/api/pledge/status?btc=${encodeURIComponent(btcPledgeBtcAddr)}`);
      const d = await r.json().catch(() => ({}));
      if (d.ok && d.status === 'verified' && d.send_secret) {
        btcPledgeSecret = d.send_secret;
        document.getElementById('btcPledgeInfo').innerHTML = '✅ BTC Confirmed! THR Address:<br><b>' + (d.thr_address || '—') + '</b>';
        document.getElementById('btcPledgeStep2').style.display = 'none';
        document.getElementById('btcPledgeDone').style.display = '';
      } else if (d.ok && d.status === 'verified' && !d.send_secret) {
        errEl.textContent = 'Payment verified but secret not available — contact support';
        errEl.classList.remove('hidden');
      } else {
        errEl.textContent = 'BTC payment not confirmed yet. The watcher checks every few minutes.';
        errEl.classList.remove('hidden');
      }
    } catch (e) {
      errEl.textContent = 'Network error: ' + e.message; errEl.classList.remove('hidden');
    } finally {
      btn.disabled = false; btn.textContent = '🔄 Check Confirmation';
    }
  });

  document.getElementById('btcPledgeCreateV1Btn').addEventListener('click', async () => {
    const pin = document.getElementById('btcPledgePin')?.value?.trim();
    const pin2 = document.getElementById('btcPledgePinConfirm')?.value?.trim();
    const errEl = document.getElementById('btcPledgeErr');
    errEl.classList.add('hidden');
    if (!pin || pin.length < 4) { errEl.textContent = 'PIN must be 4-8 digits'; errEl.classList.remove('hidden'); return; }
    if (pin !== pin2) { errEl.textContent = 'PINs do not match'; errEl.classList.remove('hidden'); return; }
    if (!btcPledgeSecret) { errEl.textContent = 'No pledge secret — submit your pledge first'; errEl.classList.remove('hidden'); return; }
    const btn = document.getElementById('btcPledgeCreateV1Btn');
    btn.disabled = true; btn.textContent = 'Creating…';
    try {
      const r = await fetch(`${API_WRITE}/api/wallet/v1/pledge-migrate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ send_secret: btcPledgeSecret, pin })
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok || !d.ok) {
        errEl.textContent = 'V1 creation failed: ' + (d.error || d.detail || 'unknown');
        errEl.classList.remove('hidden'); return;
      }
      const canonical = d.canonical_v1_address;
      const kitObj = d.recovery_kit ? (() => { try { return JSON.parse(d.recovery_kit); } catch { return { canonical_v1_address: canonical }; } })() : { canonical_v1_address: canonical };
      upsertAccount(canonical, kitObj, shortAddr(canonical), btcPledgeSecret);
      setActiveAddr(canonical);
      let migratedPrivHex = null;
      try {
        const encBlob = kitObj.encrypted_private_key_backup ?? kitObj.wallet_v1_encrypted_priv ?? kitObj.encrypted_private_key ?? kitObj.enc_key;
        if (encBlob) migratedPrivHex = await decryptBlob(encBlob, pin);
      } catch {}
      if (migratedPrivHex) unlocked.set(canonical, { privHex: migratedPrivHex });
      if (d.recovery_kit) {
        const blob = new Blob([d.recovery_kit], { type: 'application/json' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `thr-recovery-kit-${canonical.slice(0, 10)}.json`;
        a.click();
        URL.revokeObjectURL(a.href);
      }
      if (d.pdf_url) {
        const pdfMsg = document.createElement('div');
        pdfMsg.style.cssText = 'margin:8px 0;padding:8px;background:#0d0a1a;border:1px solid var(--accent);border-radius:6px;font-size:.82rem;text-align:center';
        pdfMsg.innerHTML = `📄 <a href="${API_WRITE}${d.pdf_url}" target="_blank" style="color:var(--accent)">Download PDF Contract (LSB steganography)</a>`;
        document.getElementById('btcPledgeErr')?.parentNode?.insertBefore(pdfMsg, document.getElementById('btcPledgeErr'));
      }
      await promptFaceID(canonical, migratedPrivHex);
      showWallet();
    } catch (e) {
      errEl.textContent = 'Network error: ' + e.message; errEl.classList.remove('hidden');
    } finally { btn.disabled = false; btn.textContent = '🔑 Create V1 Wallet'; }
  });

  // ── USDT / BNB Pledge (new wallet via USDT on BSC) ──
  let usdtPledgeSecret = null;
  let usdtPledgeBnbAddr = null;
  async function loadUsdtPledgeVault() {
    const box = document.getElementById('usdtPledgeVaultBox');
    if (!box || box.dataset.loaded) return;
    try {
      const r = await fetch(`${API_WRITE}/api/pledge/bnb/quote`);
      const d = await r.json().catch(() => ({}));
      if (r.ok && d.ok !== false) {
        box.innerHTML = `Send <b>min ${d.min_usdt ?? 10} USDT</b> (BEP20) to:<br><span style="word-break:break-all">${d.vault_address || '—'}</span><br><small style="color:var(--muted)">Rate: 1 USDT ≈ ${d.usdt_thr_rate ?? 100} THR</small>`;
        box.dataset.loaded = '1';
      } else {
        box.textContent = 'Vault not configured yet.';
      }
    } catch (e) {
      box.textContent = 'Network error loading vault.';
    }
  }

  document.getElementById('usdtPledgeRegisterBtn').addEventListener('click', async () => {
    const bnbAddr = document.getElementById('usdtPledgeBnbAddr')?.value?.trim();
    const errEl = document.getElementById('usdtPledgeErr');
    errEl.classList.add('hidden');
    if (!bnbAddr || !/^0x[a-fA-F0-9]{40}$/.test(bnbAddr)) {
      errEl.textContent = 'Enter a valid BNB address (0x...)'; errEl.classList.remove('hidden'); return;
    }
    const btn = document.getElementById('usdtPledgeRegisterBtn');
    btn.disabled = true; btn.textContent = 'Registering…';
    try {
      const r = await fetch(`${API_WRITE}/api/pledge/bnb/register`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bnb_address: bnbAddr })
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok || !d.ok) {
        errEl.textContent = 'Registration failed: ' + (d.error || 'unknown');
        errEl.classList.remove('hidden'); return;
      }
      usdtPledgeBnbAddr = bnbAddr;
      document.getElementById('usdtPledgePendingInfo').innerHTML =
        '⏳ THR Address (awaiting USDT payment):<br><b>' + (d.thr_address || '—') + '</b><br>' +
        '<small style="color:var(--muted)">Send USDT from <b>' + bnbAddr.slice(0,10) + '…</b> to the vault above, then click Check Payment.</small>';
      document.getElementById('usdtPledgeStep1').style.display = 'none';
      document.getElementById('usdtPledgePending').style.display = '';
    } catch (e) {
      errEl.textContent = 'Network error: ' + e.message; errEl.classList.remove('hidden');
    } finally { btn.disabled = false; btn.textContent = '📋 Register Address'; }
  });

  document.getElementById('usdtPledgeCheckBtn').addEventListener('click', async () => {
    const errEl = document.getElementById('usdtPledgeErr');
    errEl.classList.add('hidden');
    if (!usdtPledgeBnbAddr) return;
    const btn = document.getElementById('usdtPledgeCheckBtn');
    btn.disabled = true; btn.textContent = 'Checking…';
    try {
      const r = await fetch(`${API_WRITE}/api/pledge/bnb/status?bnb=${encodeURIComponent(usdtPledgeBnbAddr)}`);
      const d = await r.json().catch(() => ({}));
      if (d.ok && d.status === 'verified' && d.send_secret) {
        usdtPledgeSecret = d.send_secret;
        document.getElementById('usdtPledgePending').style.display = 'none';
        document.getElementById('usdtPledgeSetupV1').style.display = '';
      } else if (d.ok && d.status === 'verified' && !d.send_secret) {
        errEl.textContent = 'Payment verified but secret not available — contact support';
        errEl.classList.remove('hidden');
      } else {
        errEl.textContent = 'USDT payment not confirmed yet. Send USDT from your registered address, then try again in a few minutes.';
        errEl.classList.remove('hidden');
      }
    } catch (e) {
      errEl.textContent = 'Network error: ' + e.message; errEl.classList.remove('hidden');
    } finally { btn.disabled = false; btn.textContent = '🔄 Check Payment'; }
  });

  document.getElementById('usdtPledgeCreateV1Btn').addEventListener('click', async () => {
    const pin = document.getElementById('usdtPledgePin')?.value?.trim();
    const pin2 = document.getElementById('usdtPledgePinConfirm')?.value?.trim();
    const errEl = document.getElementById('usdtPledgeErr');
    errEl.classList.add('hidden');
    if (!pin || pin.length < 4) { errEl.textContent = 'PIN must be 4-8 digits'; errEl.classList.remove('hidden'); return; }
    if (pin !== pin2) { errEl.textContent = 'PINs do not match'; errEl.classList.remove('hidden'); return; }
    if (!usdtPledgeSecret) { errEl.textContent = 'No pledge secret — check payment status first'; errEl.classList.remove('hidden'); return; }
    const btn = document.getElementById('usdtPledgeCreateV1Btn');
    btn.disabled = true; btn.textContent = 'Creating…';
    try {
      const r = await fetch(`${API_WRITE}/api/wallet/v1/pledge-migrate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ send_secret: usdtPledgeSecret, pin })
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok || !d.ok) {
        errEl.textContent = 'V1 creation failed: ' + (d.error || d.detail || 'unknown');
        errEl.classList.remove('hidden'); return;
      }
      const canonical = d.canonical_v1_address;
      const kitObj = d.recovery_kit ? (() => { try { return JSON.parse(d.recovery_kit); } catch { return { canonical_v1_address: canonical }; } })() : { canonical_v1_address: canonical };
      upsertAccount(canonical, kitObj, shortAddr(canonical), usdtPledgeSecret);
      setActiveAddr(canonical);
      let migratedPrivHex = null;
      try {
        const encBlob = kitObj.encrypted_private_key_backup ?? kitObj.wallet_v1_encrypted_priv ?? kitObj.encrypted_private_key ?? kitObj.enc_key;
        if (encBlob) migratedPrivHex = await decryptBlob(encBlob, pin);
      } catch {}
      if (migratedPrivHex) unlocked.set(canonical, { privHex: migratedPrivHex });
      if (d.recovery_kit) {
        const blob = new Blob([d.recovery_kit], { type: 'application/json' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `thr-recovery-kit-${canonical.slice(0, 10)}.json`;
        a.click();
        URL.revokeObjectURL(a.href);
      }
      if (d.pdf_url) {
        const pdfMsg = document.createElement('div');
        pdfMsg.style.cssText = 'margin:8px 0;padding:8px;background:#0d0a1a;border:1px solid var(--accent);border-radius:6px;font-size:.82rem;text-align:center';
        pdfMsg.innerHTML = `📄 <a href="${API_WRITE}${d.pdf_url}" target="_blank" style="color:var(--accent)">Download PDF Contract (LSB steganography)</a>`;
        document.getElementById('usdtPledgeErr')?.parentNode?.insertBefore(pdfMsg, document.getElementById('usdtPledgeErr'));
      }
      await promptFaceID(canonical, migratedPrivHex);
      showWallet();
    } catch (e) {
      errEl.textContent = 'Network error: ' + e.message; errEl.classList.remove('hidden');
    } finally { btn.disabled = false; btn.textContent = '🔑 Create V1 Wallet'; }
  });

  // Pledge lookup
  let pledgeFoundAddr = null;
  document.getElementById('pledgeLookupBtn').addEventListener('click', async () => {
    const secret = document.getElementById('pledgeSecret')?.value?.trim();
    const errEl = document.getElementById('pledgeErr');
    errEl.classList.add('hidden');
    if (!secret) { errEl.textContent = 'Enter your send secret first'; errEl.classList.remove('hidden'); return; }
    const btn = document.getElementById('pledgeLookupBtn');
    btn.disabled = true; btn.textContent = 'Searching…';
    try {
      const r = await fetch(`${API_WRITE}/api/wallet/v1/pledge-lookup`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ send_secret: secret })
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok || !d.ok) {
        errEl.textContent = d.error === 'pledge_not_found' ? 'No pledge found. Check your send secret.' : ('Error: ' + (d.error || 'lookup failed'));
        errEl.classList.remove('hidden'); return;
      }
      pledgeFoundAddr = d.thr_address;
      document.getElementById('pledgeInfo').innerHTML =
        '✅ Found:<br><b>' + (d.thr_address || '—') + '</b>' +
        (d.btc_address ? '<br><small style="color:var(--muted)">BTC: ' + d.btc_address + '</small>' : '');
      document.getElementById('pledgeStep1').style.display = 'none';
      document.getElementById('pledgeStep2').style.display = '';
    } catch(e) {
      errEl.textContent = 'Network error: ' + e.message; errEl.classList.remove('hidden');
    } finally { btn.disabled = false; btn.textContent = '🔍 Find My Wallet'; }
  });

  document.getElementById('pledgeBackBtn')?.addEventListener('click', () => {
    pledgeFoundAddr = null;
    document.getElementById('pledgeStep1').style.display = '';
    document.getElementById('pledgeStep2').style.display = 'none';
    document.getElementById('pledgeErr').classList.add('hidden');
  });

  document.getElementById('pledgeMigrateBtn').addEventListener('click', async () => {
    const secret = document.getElementById('pledgeSecret')?.value?.trim();
    const pin = document.getElementById('pledgeMigratePin')?.value?.trim();
    const errEl = document.getElementById('pledgeErr');
    errEl.classList.add('hidden');
    if (!pin || pin.length < 4) { errEl.textContent = 'PIN must be 4-8 digits'; errEl.classList.remove('hidden'); return; }
    const btn = document.getElementById('pledgeMigrateBtn');
    btn.disabled = true; btn.textContent = 'Migrating…';
    try {
      const r = await fetch(`${API_WRITE}/api/wallet/v1/pledge-migrate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ send_secret: secret, pin })
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok || !d.ok) {
        errEl.textContent = 'Migration failed: ' + (d.error || d.detail || 'unknown');
        errEl.classList.remove('hidden'); return;
      }
      const canonical = d.canonical_v1_address;

      // Store account — save send_secret so old/migration users can use cross-chain pools
      const kitObj = d.recovery_kit ? (() => { try { return JSON.parse(d.recovery_kit); } catch { return { canonical_v1_address: canonical }; } })() : { canonical_v1_address: canonical };
      upsertAccount(canonical, kitObj, shortAddr(canonical), secret);
      setActiveAddr(canonical);

      // Decrypt with the PIN just set so Face ID enrollment below has the real key
      let migratedPrivHex = null;
      try {
        const encBlob = kitObj.encrypted_private_key_backup ?? kitObj.wallet_v1_encrypted_priv ?? kitObj.encrypted_private_key ?? kitObj.enc_key;
        if (encBlob) migratedPrivHex = await decryptBlob(encBlob, pin);
      } catch {}
      if (migratedPrivHex) unlocked.set(canonical, { privHex: migratedPrivHex });

      // Auto-download Recovery Kit if server generated it
      if (d.recovery_kit) {
        const blob = new Blob([d.recovery_kit], { type: 'application/json' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `thr-recovery-kit-${canonical.slice(0,10)}.json`;
        a.click();
        URL.revokeObjectURL(a.href);
      }

      // Show PDF link if available
      if (d.pdf_url) {
        const pdfMsg = document.createElement('div');
        pdfMsg.style.cssText = 'margin:8px 0;padding:8px;background:#0d0a1a;border:1px solid var(--accent);border-radius:6px;font-size:.82rem;text-align:center';
        pdfMsg.innerHTML = `📄 <a href="${API_WRITE}${d.pdf_url}" target="_blank" style="color:var(--accent)">Download Pledge Contract PDF (LSB)</a>`;
        document.getElementById('pledgeErr')?.parentNode?.insertBefore(pdfMsg, document.getElementById('pledgeErr'));
      }

      // Offer Face ID / fingerprint
      await promptFaceID(canonical, migratedPrivHex);
      showWallet();
    } catch(e) {
      errEl.textContent = 'Network error: ' + e.message; errEl.classList.remove('hidden');
    } finally { btn.disabled = false; btn.textContent = '✅ Migrate to V1'; }
  });

  document.getElementById('cancelBtn')?.addEventListener('click', () => {
    const addr = getActiveAddr();
    if (addr && unlocked.has(addr)) showWallet(); else showUnlock();
  });

  let kitData = null;

  document.getElementById('pickFile').addEventListener('click', () => {
    const inp = document.createElement('input');
    inp.type = 'file'; inp.accept = '.json,application/json,text/json';
    inp.addEventListener('change', async e => {
      const file = e.target.files[0]; if (!file) return;
      try {
        kitData = JSON.parse(await readFile(file));
        document.getElementById('filePill').textContent = `✓  ${file.name}`;
        document.getElementById('filePill').classList.remove('hidden');
        document.getElementById('labelRow').classList.remove('hidden');
        document.getElementById('labelRow').style.display = 'flex';
        document.getElementById('pinSection').classList.remove('hidden');
        document.getElementById('pinSection').style.display = 'flex';
        setError(null);
      } catch { setError('Invalid JSON file — make sure it is a valid Recovery Kit'); }
    });
    inp.click();
  });

  root.addEventListener('click', async e => {
    if (e.target.id !== 'importBtn') return;
    if (!kitData) { setError('Select a Recovery Kit file first'); return; }
    const pin = document.getElementById('pin')?.value?.trim();
    if (!pin) { setError('Enter your PIN'); return; }
    const label = document.getElementById('label')?.value?.trim();

    const btn = e.target; btn.disabled = true; btn.textContent = 'Unlocking…';

    try {
      const encBlob = kitData.encrypted_private_key_backup ?? kitData.wallet_v1_encrypted_priv ?? kitData.encrypted_private_key ?? kitData.enc_key;
      if (!encBlob) throw new Error('No encrypted key found in this Recovery Kit');

      let privHex;
      try { privHex = await decryptBlob(encBlob, pin); }
      catch { throw new Error('Wrong PIN — check your PIN and try again'); }

      const address = (kitData.canonical_v1_address ?? kitData.address ?? '').trim().toUpperCase();
      if (!address || !/^THR[A-F0-9]{40}$/.test(address)) throw new Error('Invalid THR address in Recovery Kit');

      upsertAccount(address, kitData, label || shortAddr(address));
      setActiveAddr(address);
      unlocked.set(address, { privHex });

      await promptFaceID(address, privHex);
    } catch (err) {
      btn.disabled = false; btn.textContent = 'Unlock';
      setError(err.message || 'Import failed');
    }
  });
}

// ─── Face ID enrollment ───────────────────────────────────────────────────────

async function promptFaceID(address, privHex) {
  if (!(await webauthnAvailable())) { await showWallet(); return; }

  render(`
    <div class="screen screen--center">
      <div class="faceid-hero">⬡</div>
      <h2 style="font-size:1.3rem">Enable Face ID?</h2>
      <p style="color:var(--muted);max-width:300px">Unlock this account instantly without entering your PIN.</p>
      <button class="btn btn--faceid" id="enableFID">
        ${fidSvg()} Enable Face ID
      </button>
      <button class="btn btn--ghost" id="skipFID">Skip for now</button>
      <div id="err" class="banner banner--error hidden"></div>
    </div>
  `);

  document.getElementById('enableFID').addEventListener('click', async () => {
    const btn = document.getElementById('enableFID');
    btn.disabled = true; btn.textContent = 'Registering…';
    try {
      const cred = await registerWebAuthn(address);
      const credIdHex = bytesToHex(new Uint8Array(cred.rawId));
      const prfFirst = cred.getClientExtensionResults()?.prf?.results?.first;

      if (prfFirst) {
        const envelope = await encryptWithKey(new Uint8Array(prfFirst), privHex);
        LS.setObj(`thr_fid_${address}`, { credId: credIdHex, mode: 'prf' });
        LS.setObj(`thr_env_${address}`, envelope);
      } else {
        const envelope = await wrapForSession(address, privHex);
        LS.setObj(`thr_fid_${address}`, { credId: credIdHex, mode: 'session' });
        LS.setObj(`thr_env_${address}`, envelope);
      }
    } catch (err) {
      if (err.name !== 'NotAllowedError') console.warn('WebAuthn registration:', err);
    }
    await showWallet();
  });

  document.getElementById('skipFID').addEventListener('click', () => showWallet());
}

function fidSvg() {
  return `<svg class="faceid-symbol" viewBox="0 0 28 28" fill="none" stroke="currentColor" stroke-width="1.8">
    <rect x="1" y="1" width="8" height="8" rx="2"/><rect x="19" y="1" width="8" height="8" rx="2"/>
    <rect x="1" y="19" width="8" height="8" rx="2"/><rect x="19" y="19" width="8" height="8" rx="2"/>
    <circle cx="14" cy="11" r="2"/><path d="M10 17c0-2.2 1.8-4 4-4s4 1.8 4 4"/>
  </svg>`;
}

// ─── Unlock screen ────────────────────────────────────────────────────────────

async function showUnlock() {
  const address = getActiveAddr();
  if (!address) { showImport(); return; }

  // Auto-unlock via session key
  const fid = LS.getObj(`thr_fid_${address}`);
  const env = LS.getObj(`thr_env_${address}`);
  if (fid?.mode === 'session' && env) {
    try {
      const privHex = await unwrapFromSession(address, env);
      unlocked.set(address, { privHex });
      await showWallet(); return;
    } catch {}
  }

  const hasFid = !!(fid?.credId);
  const short = shortAddr(address);
  const accs = getAccounts();

  render(`
    <div class="screen screen--center">
      <div class="logo" style="margin-top:0">⬡</div>
      <p style="color:var(--muted);font-size:.88rem">${short}</p>
      ${accs.length > 1 ? `<button class="btn btn--ghost" id="switchAccBtn" style="font-size:.82rem;padding:8px 16px">Switch account ↓</button>` : ''}
      ${hasFid ? `<button class="btn btn--faceid" id="fidBtn">${fidSvg()} Unlock with Face ID</button><div class="divider">or</div>` : ''}
      <div style="width:100%;display:flex;flex-direction:column;gap:12px">
        <input type="password" id="pinInput" class="input" placeholder="Enter PIN" autocomplete="current-password">
        <button class="btn btn--primary" id="pinBtn">Unlock with PIN</button>
      </div>
      <button class="btn btn--ghost mt8" id="resetBtn" style="font-size:.82rem">Import a different wallet</button>
      <div id="err" class="banner banner--error hidden"></div>
    </div>
  `);

  document.getElementById('fidBtn')?.addEventListener('click', () => unlockFaceID(address));
  document.getElementById('pinBtn').addEventListener('click', () => {
    const pin = document.getElementById('pinInput')?.value?.trim();
    if (pin) unlockPin(address, pin); else setError('Enter your PIN');
  });
  document.getElementById('pinInput').addEventListener('keydown', e => { if (e.key === 'Enter') document.getElementById('pinBtn').click(); });
  document.getElementById('switchAccBtn')?.addEventListener('click', showAccountPicker);
  document.getElementById('resetBtn').addEventListener('click', () => {
    if (confirm('Remove this wallet from this device?')) { removeAccount(address); boot(); }
  });

  if (hasFid && fid.mode === 'prf') setTimeout(() => unlockFaceID(address), 400);
}

async function unlockFaceID(address) {
  const fid = LS.getObj(`thr_fid_${address}`);
  const env = LS.getObj(`thr_env_${address}`);
  const btn = document.getElementById('fidBtn');
  if (btn) btn.disabled = true;
  try {
    const assertion = await assertWebAuthn(fid.credId);
    if (fid.mode === 'prf') {
      const prf = assertion.getClientExtensionResults()?.prf?.results?.first;
      if (!prf) throw new Error('Face ID key derivation unavailable — use PIN');
      const privHex = await decryptWithKey(new Uint8Array(prf), env);
      unlocked.set(address, { privHex });
    } else {
      const privHex = await unwrapFromSession(address, env);
      unlocked.set(address, { privHex });
    }
    await showWallet();
  } catch (err) {
    if (btn) btn.disabled = false;
    setError(err.name === 'NotAllowedError' ? 'Face ID cancelled' : err.message || 'Face ID failed — use PIN');
  }
}

async function unlockPin(address, pin) {
  const acc = getAccount(address);
  if (!acc) { setError('Account not found'); return; }
  const btn = document.getElementById('pinBtn');
  if (btn) { btn.disabled = true; btn.textContent = 'Unlocking…'; }
  try {
    const kit = typeof acc.kit === 'string' ? JSON.parse(acc.kit) : acc.kit;
    const encBlob = kit.encrypted_private_key_backup ?? kit.wallet_v1_encrypted_priv ?? kit.encrypted_private_key ?? kit.enc_key;
    let privHex;
    try { privHex = await decryptBlob(encBlob, pin); }
    catch { throw new Error('Wrong PIN — check your PIN and try again'); }
    unlocked.set(address, { privHex });
    // Refresh session key if in session mode
    const fid = LS.getObj(`thr_fid_${address}`);
    if (fid?.mode === 'session' && fid.credId) {
      const envelope = await wrapForSession(address, privHex);
      LS.setObj(`thr_env_${address}`, envelope);
    }
    // Offer Face ID on first PIN unlock if not yet enrolled
    if (!fid?.credId && await webauthnAvailable()) {
      await promptFaceID(address, privHex);
    } else {
      await showWallet();
    }
  } catch (err) {
    if (btn) { btn.disabled = false; btn.textContent = 'Unlock with PIN'; }
    setError(err.message);
  }
}

// ─── Account picker ───────────────────────────────────────────────────────────

function showAccountPicker() {
  const accs = getAccounts();
  const active = getActiveAddr();

  render(`
    <div class="screen">
      <div class="header">
        <button class="btn--icon" id="backBtn">←</button>
        <span class="header__title">Accounts</span>
        <button class="btn--icon" id="addBtn" title="Add account">＋</button>
      </div>
      <div id="accList" style="margin-top:8px;display:flex;flex-direction:column;gap:10px">
        ${accs.map(acc => `
          <div class="acc-card ${acc.address === active ? 'acc-card--active' : ''}" data-addr="${acc.address}">
            <div class="acc-card__info">
              <div class="acc-card__label">${acc.label || shortAddr(acc.address)}</div>
              <div class="acc-card__addr">${shortAddr(acc.address)}</div>
              ${unlocked.has(acc.address) ? '<span class="acc-badge">Unlocked</span>' : ''}
            </div>
            <button class="btn--icon acc-card__del" data-addr="${acc.address}" title="Remove">✕</button>
          </div>
        `).join('')}
      </div>
    </div>
  `);

  document.getElementById('backBtn').addEventListener('click', () => {
    const addr = getActiveAddr();
    if (addr && unlocked.has(addr)) showWallet(); else showUnlock();
  });

  document.getElementById('addBtn').addEventListener('click', () => showImport(true));

  document.getElementById('accList').addEventListener('click', async e => {
    if (e.target.classList.contains('acc-card__del')) {
      const addr = e.target.dataset.addr;
      if (confirm(`Remove account ${shortAddr(addr)} from this device?`)) {
        removeAccount(addr);
        unlocked.delete(addr);
        showAccountPicker();
      }
      return;
    }
    const card = e.target.closest('.acc-card');
    if (!card) return;
    const addr = card.dataset.addr;
    setActiveAddr(addr);
    if (unlocked.has(addr)) { await showWallet(); }
    else { await showUnlock(); }
  });
}

// ─── Main wallet screen ───────────────────────────────────────────────────────

const HOME_NETWORKS = [
  { id: 'thronos',  icon: '⬡',  label: 'Thronos' },
  { id: 'bitcoin',  icon: '₿',  label: 'Bitcoin' },
  { id: 'ethereum', icon: 'Ξ',  label: 'Ethereum' },
  { id: 'bnb',      icon: '🔶', label: 'BNB Chain' },
  { id: 'arbitrum', icon: '🔵', label: 'Arbitrum' },
  { id: 'base',     icon: '⬛', label: 'Base' },
];

// evmMeta: { network, sym, addr } — if set the row becomes tappable for EVM actions
function _renderHomeAssetRow(icon, label, sym, val, color, addr, evmMeta) {
  const fmt = v => {
    if (v == null) return '—';
    const n = Number(v);
    if (n === 0) return '0';
    if (n >= 1000) return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
    if (n >= 1)    return n.toFixed(4);
    if (n >= 0.0001) return n.toFixed(6);
    return n.toFixed(8);
  };
  const tapClass = evmMeta ? ' class="pwa-evm-row"' : '';
  const tapData  = evmMeta
    ? ` data-evm-net="${evmMeta.network}" data-evm-sym="${escHtml(evmMeta.sym)}" data-evm-addr="${escHtml(evmMeta.addr)}"`
    : '';
  const tapStyle = evmMeta ? ';cursor:pointer' : '';
  return `<div${tapClass}${tapData} style="display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:1px solid #ffffff10${tapStyle}">
    <div style="width:28px;height:28px;border-radius:50%;background:${color}33;border:1px solid ${color};display:flex;align-items:center;justify-content:center;font-size:.8rem;flex-shrink:0">${icon}</div>
    <div style="flex:1;min-width:0">
      <div style="font-size:.88rem;font-weight:600;color:#fff">${escHtml(label)} <span style="color:var(--muted);font-size:.75rem">${sym}</span></div>
      ${addr ? `<div style="font-size:.7rem;color:var(--muted);font-family:monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${addr.slice(0,10)}…${addr.slice(-5)}</div>` : ''}
      ${evmMeta ? `<div style="font-size:.68rem;color:#56ff9a;margin-top:1px">Tap to send / deposit ›</div>` : ''}
    </div>
    <div style="text-align:right;flex-shrink:0">
      <div style="font-size:.88rem;color:${val ? '#fff' : 'var(--muted)'}">${fmt(val)} ${sym}</div>
    </div>
  </div>`;
}

async function showWallet() {
  const address = getActiveAddr();
  if (!address || !unlocked.has(address)) { showUnlock(); return; }

  const accs = getAccounts();
  const acc = getAccount(address);
  const label = acc?.label || shortAddr(address);
  const { privHex } = unlocked.get(address) || {};
  _pwaSigningCtx = privHex ? { address, privHex } : null;
  let homeBtcAddr = '';
  let homeEvmAddr = '';
  let homeChainBalances = null;

  render(`
    <div class="screen">
      <div class="header">
        <span class="logo--sm">⬡ THR</span>
        <div style="display:flex;gap:8px;align-items:center">
          ${accs.length > 1 ? `<button class="btn--icon" id="accBtn" title="Accounts">👤</button>` : ''}
          <button class="btn--icon" id="addAccBtn" title="Add account">＋</button>
          <button class="btn--icon" id="lockBtn" title="Lock">🔒</button>
        </div>
      </div>

      <!-- Network selector -->
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
        <span style="font-size:.7rem;text-transform:uppercase;letter-spacing:1px;color:var(--muted)">Network</span>
        <select id="homeNetSel" class="input" style="flex:1;margin:0;padding:6px 10px;font-size:.85rem;width:auto;background:#0d0a1a;border:1px solid #2a2050;color:#b08cf8">
          ${HOME_NETWORKS.map(n => `<option value="${n.id}">${n.icon} ${n.label}</option>`).join('')}
        </select>
      </div>

      <!-- Address bar -->
      <div style="display:flex;align-items:center;justify-content:space-between;background:#0d0a1a;border-radius:8px;padding:8px 12px;margin-bottom:10px">
        <span id="addrLine" style="font-family:monospace;font-size:.8rem;color:var(--accent);cursor:pointer" title="Tap to copy">${shortAddr(address)}</span>
        <button onclick="document.getElementById('copyAddrBtn').click()" style="background:none;border:1px solid var(--accent);color:var(--accent);font-size:.7rem;padding:2px 8px;border-radius:4px;cursor:pointer" id="copyAddrBtn">Copy</button>
      </div>

      <!-- Balances + Token list -->
      <div class="card" style="padding:12px;margin-bottom:10px">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
          <span style="font-size:.7rem;text-transform:uppercase;letter-spacing:1px;color:var(--accent)">Balance</span>
          <button id="refreshBalBtn" title="Refresh balance" style="background:none;border:none;color:var(--muted);font-size:.95rem;cursor:pointer;padding:2px 6px;line-height:1" aria-label="Refresh">🔄</button>
        </div>
        <div id="balancesArea">
          <div class="balance-amount balance-amount--loading">···</div>
        </div>
      </div>

      <!-- LP Positions panel (populated async) -->
      <div id="lpPositionsPanel"></div>

      <!-- Quick actions — matches web wallet -->
      <div class="actions mt8" style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:10px">
        <button class="action-btn" id="sendBtn"><span class="action-btn__icon">💸</span>Send</button>
        <button class="action-btn" id="receiveBtn"><span class="action-btn__icon">📥</span>Receive</button>
        <button class="action-btn" id="swapBtn"><span class="action-btn__icon">🔄</span>Swap</button>
        <button class="action-btn" id="poolsBtn"><span class="action-btn__icon">💧</span>Pools</button>
        <button class="action-btn" id="bridgeBtn"><span class="action-btn__icon">⚡</span>Bridge</button>
        <button class="action-btn" id="usdtPledgeBtn"><span class="action-btn__icon">💵</span>USDT Pledge</button>
        <button class="action-btn" id="networksBtn"><span class="action-btn__icon">🌐</span>Networks</button>
        <button class="action-btn" id="tokensBtn"><span class="action-btn__icon">◈</span>Tokens</button>
        <button class="action-btn" id="connectBtn"><span class="action-btn__icon">⬡</span>Connect</button>
        <button class="action-btn" id="musicBtn"><span class="action-btn__icon">🎵</span>Music</button>
        <button class="action-btn" id="historyBtn"><span class="action-btn__icon">📋</span>History</button>
        <button class="action-btn" id="createTokenBtn"><span class="action-btn__icon">🪙</span>Create Token</button>
        <button class="action-btn" id="nftBtn"><span class="action-btn__icon">🖼️</span>NFTs</button>
        <button class="action-btn" id="epochBtn"><span class="action-btn__icon">⏳</span>Epoch</button>
        <button class="action-btn" id="withdrawBtn" disabled style="opacity:0.38;cursor:not-allowed;" title="Withdraw — being upgraded"><span class="action-btn__icon">💰</span>Withdraw</button>
      </div>
    </div>
  `);

  document.getElementById('lockBtn').addEventListener('click', () => {
    sessionStorage.removeItem(`thr_sk_${address}`);
    unlocked.delete(address);
    _pwaSigningCtx = null;
    showUnlock();
  });

  // Load LP positions async — show only when Thronos network is active
  async function loadLpPositions() {
    const panel = document.getElementById('lpPositionsPanel');
    if (!panel) return;
    try {
      const r = await fetch(`${API_BASE}/api/v1/pools/positions/${address}`).then(x => x.json()).catch(() => null);
      const positions = r?.positions || [];
      if (!positions.length) { panel.innerHTML = ''; return; }
      const rows = positions.map(p => {
        const pct = p.share_pct != null ? `${Number(p.share_pct).toFixed(4)}%` : '—';
        const valThr = p.value_thr != null ? `≈ ${Number(p.value_thr).toFixed(4)} THR` : '';
        return `<div style="display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-bottom:1px solid #ffffff10;cursor:pointer"
                     onclick="showPools()">
          <div>
            <div style="font-size:.85rem;font-weight:600;color:#fff">${escHtml(p.token_a || '')}/${escHtml(p.token_b || '')}</div>
            <div style="font-size:.72rem;color:var(--muted)">${Number(p.liquidity_share || 0).toFixed(6)} LP shares · ${pct} of pool</div>
          </div>
          <div style="text-align:right">
            <div style="font-size:.82rem;color:#b08cf8">${valThr}</div>
            <div style="font-size:.68rem;color:var(--muted)">${p.pending_rewards > 0 ? `+${Number(p.pending_rewards).toFixed(6)} pending` : ''}</div>
          </div>
        </div>`;
      }).join('');
      panel.innerHTML = `
        <div class="card" style="padding:10px 12px;margin-bottom:10px">
          <div style="font-size:.7rem;text-transform:uppercase;letter-spacing:1px;color:#b08cf8;margin-bottom:6px">Pool Positions</div>
          ${rows}
        </div>`;
    } catch { panel.innerHTML = ''; }
  }

  document.getElementById('accBtn')?.addEventListener('click', showAccountPicker);
  document.getElementById('addAccBtn').addEventListener('click', () => showImport(true));
  document.getElementById('sendBtn').addEventListener('click', showSend);
  document.getElementById('receiveBtn').addEventListener('click', showReceive);
  document.getElementById('swapBtn').addEventListener('click', showSwap);
  document.getElementById('poolsBtn').addEventListener('click', showPools);
  document.getElementById('tokensBtn').addEventListener('click', showTokens);
  document.getElementById('bridgeBtn').addEventListener('click', () => showBridge('BTC', 'WBTC'));
  document.getElementById('usdtPledgeBtn').addEventListener('click', () => showUsdtPledge(address));
  document.getElementById('networksBtn').addEventListener('click', showMultiChain);
  document.getElementById('connectBtn').addEventListener('click', showWalletConnect);
  document.getElementById('musicBtn').addEventListener('click', showMusic);
  document.getElementById('createTokenBtn').addEventListener('click', showCreateToken);
  document.getElementById('nftBtn').addEventListener('click', showNFTs);
  document.getElementById('epochBtn').addEventListener('click', showEpoch);
  document.getElementById('historyBtn').addEventListener('click', () => showHistory(address));
  document.getElementById('withdrawBtn').addEventListener('click', (e) => {
    if (e.currentTarget.disabled) {
      alert(
        'Withdraw is being upgraded.\n\n' +
        'Use Send for personal wallet assets, or the Pools screen for pool withdrawals.\n\n' +
        '(Pool withdrawals require a confirmed pool position.)'
      );
    }
  });

  const setAddrBarValue = (full) => {
    const lineEl = document.getElementById('addrLine');
    if (lineEl) lineEl.textContent = full ? shortAddr(full) : '(unlock wallet to see)';
    const copyBtn = document.getElementById('copyAddrBtn');
    if (copyBtn) copyBtn.dataset.fullAddr = full || '';
  };
  setAddrBarValue(address);

  // Re-bind copy/tap handlers to read the currently-displayed network address
  document.getElementById('addrLine').addEventListener('click', async () => {
    const full = document.getElementById('copyAddrBtn')?.dataset.fullAddr || address;
    try { await navigator.clipboard.writeText(full); } catch {}
    const el = document.getElementById('addrLine');
    if (el) { el.textContent = 'Copied!'; setTimeout(() => setAddrBarValue(full), 1500); }
  });
  document.getElementById('copyAddrBtn').addEventListener('click', async () => {
    const full = document.getElementById('copyAddrBtn')?.dataset.fullAddr || address;
    try { await navigator.clipboard.writeText(full); } catch {}
    const b = document.getElementById('copyAddrBtn');
    if (b) { b.textContent = '✓'; setTimeout(() => { if (b) b.textContent = 'Copy'; }, 1500); }
  });

  const loadThronosAssets = () => fetchBalances(address).then(data => {
    const el = document.getElementById('balancesArea');
    if (!el) return;
    setAddrBarValue(address);
    const tokens = Array.isArray(data?.tokens) ? data.tokens : [];
    const totalTHR = tokens.filter(t => t.value_in_thr != null)
                          .reduce((s, t) => s + Number(t.value_in_thr || 0), 0);
    const totalUSD = tokens.filter(t => t.value_usd != null)
                          .reduce((s, t) => s + Number(t.value_usd || 0), 0);
    const totalBTC = tokens.filter(t => t.value_wbtc != null)
                          .reduce((s, t) => s + Number(t.value_wbtc || 0), 0);

    if (!tokens.length) {
      // Fallback to legacy thr_balance field
      const raw = data?.thr_balance ?? 0;
      el.innerHTML = `<div class="balance-amount">${Number(raw).toLocaleString()} THR</div>`;
      return;
    }

    const tokenRows = tokens.filter(t => Number(t.balance) > 0).map(t => {
      const bal = Number(t.balance || 0);
      const sym = t.symbol || '?';
      const color = t.color || '#00ff66';
      const logo = t.logo_url || t.logo || '';
      const valThr = t.value_in_thr != null ? `≈ ${Number(t.value_in_thr).toFixed(4)} THR` : '';
      const valUsd = t.value_usd != null ? `≈ $${Number(t.value_usd).toFixed(2)}` : '';
      const logoHtml = logo
        ? `<img src="${logo}" alt="${sym}" style="width:28px;height:28px;border-radius:50%;object-fit:cover" onerror="this.style.display='none'">`
        : `<div style="width:28px;height:28px;border-radius:50%;background:${color}33;border:1px solid ${color};display:flex;align-items:center;justify-content:center;font-size:.75rem;font-weight:bold;color:${color}">${sym[0]}</div>`;
      return `<div class="token-tap-row" style="display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:1px solid #ffffff10;cursor:pointer" data-token="${escHtml(JSON.stringify(t))}">
        ${logoHtml}
        <div style="flex:1;min-width:0">
          <div style="font-size:.88rem;font-weight:600;color:#fff">${escHtml(t.name || sym)} <span style="color:var(--muted);font-size:.75rem">${sym}</span></div>
          ${sym !== 'THR' && valThr ? `<div style="font-size:.72rem;color:var(--muted)">${valThr}</div>` : ''}
        </div>
        <div style="text-align:right">
          <div style="font-size:.88rem;color:#fff">${bal.toFixed(t.decimals ?? 6)} ${sym}</div>
          <div style="font-size:.72rem;color:var(--muted)">${valUsd}</div>
        </div>
      </div>`;
    }).join('');

    el.innerHTML = `
      <div style="text-align:center;padding:8px 0 12px">
        <div class="balance-amount">${tokens.length ? totalTHR.toFixed(4) : '—'} THR</div>
        <div style="color:var(--muted);font-size:.78rem;margin-top:3px">
          ≈ ${totalUSD > 0 ? '$' + totalUSD.toFixed(2) : '—'} · ₿ ${totalBTC > 0 ? totalBTC.toFixed(8) : '—'}
        </div>
      </div>
      <div style="font-size:.7rem;text-transform:uppercase;letter-spacing:1px;color:var(--accent);margin-bottom:4px">Assets</div>
      ${tokenRows || '<div style="color:var(--muted);font-size:.85rem;padding:8px 0">No tokens found</div>'}
    `;

    // Token row tap → detail modal
    el.querySelectorAll('.token-tap-row').forEach(row => {
      row.addEventListener('click', () => {
        try { showTokenDetail(JSON.parse(row.dataset.token)); } catch {}
      });
    });
  });

  // Load assets/address for a non-Thronos network on demand
  const loadOtherNetworkAssets = async (netId) => {
    const el = document.getElementById('balancesArea');
    if (!el) return;
    el.innerHTML = '<div class="balance-amount balance-amount--loading">···</div>';

    if (!privHex) {
      setAddrBarValue('');
      el.innerHTML = '<div style="color:#ff6b6b;text-align:center;padding:24px 0">Unlock wallet to view this network</div>';
      return;
    }

    if (netId === 'bitcoin') {
      if (!homeBtcAddr) homeBtcAddr = await _fetchBtcAddress(privHex, address).catch(() => '');
      setAddrBarValue(homeBtcAddr);
      if (!homeChainBalances) homeChainBalances = await _fetchAllChainBalances(privHex, homeBtcAddr).catch(() => ({}));
      el.innerHTML = `<div style="font-size:.7rem;text-transform:uppercase;letter-spacing:1px;color:var(--accent);margin-bottom:4px">Assets</div>`
        + _renderHomeAssetRow('₿', 'Bitcoin', 'BTC', homeChainBalances.btc, '#f7931a', homeBtcAddr);
      return;
    }

    // EVM-based chains share one address
    if (!homeEvmAddr) homeEvmAddr = await _deriveEvmAddress(privHex).catch(() => '');
    setAddrBarValue(homeEvmAddr);
    if (!homeChainBalances) homeChainBalances = await _fetchAllChainBalances(privHex, homeBtcAddr).catch(() => ({}));
    const bal = homeChainBalances;
    let rows = '';
    if (netId === 'ethereum') {
      rows = _renderHomeAssetRow('Ξ', 'Ethereum', 'ETH', bal.eth, '#627eea', homeEvmAddr);
    } else if (netId === 'bnb') {
      rows = _renderHomeAssetRow('🔶', 'BNB Chain', 'BNB', bal.bnb, '#f3ba2f', homeEvmAddr)
           + _renderHomeAssetRow('₮', 'USDT on BNB', 'USDT', bal.usdtBnb, '#26a17b', homeEvmAddr,
               { network: 'bnb', sym: 'USDT', addr: homeEvmAddr });
    } else if (netId === 'arbitrum') {
      rows = _renderHomeAssetRow('🔵', 'Arbitrum', 'ETH', bal.arb, '#28a0f0', homeEvmAddr)
           + _renderHomeAssetRow('₮', 'USDT on Arbitrum', 'USDT', bal.usdtArb, '#26a17b', homeEvmAddr,
               { network: 'arbitrum', sym: 'USDT', addr: homeEvmAddr });
    } else if (netId === 'base') {
      rows = _renderHomeAssetRow('⬛', 'Base', 'ETH', bal.base, '#0052ff', homeEvmAddr)
           + _renderHomeAssetRow('$', 'USDC on Base', 'USDC', bal.usdcBase, '#2775ca', homeEvmAddr,
               { network: 'base', sym: 'USDC', addr: homeEvmAddr });
    }
    el.innerHTML = `<div style="font-size:.7rem;text-transform:uppercase;letter-spacing:1px;color:var(--accent);margin-bottom:4px">Assets</div>${rows}`;
    el.querySelectorAll('.pwa-evm-row').forEach(row => {
      row.addEventListener('click', () => {
        const net = row.dataset.evmNet;
        const sym = row.dataset.evmSym;
        const addr = row.dataset.evmAddr;
        if (net && sym && addr) pwaOpenEvmAssetActions(net, addr, sym);
      });
    });
  };

  const refreshCurrentNet = () => {
    homeChainBalances = null; // force re-fetch
    const netId = document.getElementById('homeNetSel')?.value || 'thronos';
    if (netId === 'thronos') { loadThronosAssets(); return; }
    loadOtherNetworkAssets(netId);
  };

  document.getElementById('refreshBalBtn').addEventListener('click', () => {
    const btn = document.getElementById('refreshBalBtn');
    if (btn) { btn.style.opacity = '.4'; setTimeout(() => { if (btn) btn.style.opacity = '1'; }, 800); }
    refreshCurrentNet();
  });

  // Restore persisted network selection
  const _savedNet = LS.get(`thr_network_${address}`);
  if (_savedNet && document.getElementById('homeNetSel')) {
    document.getElementById('homeNetSel').value = _savedNet;
  }

  document.getElementById('homeNetSel').addEventListener('change', (e) => {
    homeChainBalances = null; // always re-fetch on network switch
    const netId = e.target.value;
    LS.set(`thr_network_${address}`, netId); // persist per wallet
    const lpPanel = document.getElementById('lpPositionsPanel');
    if (netId === 'thronos') {
      loadThronosAssets();
      loadLpPositions();
    } else {
      if (lpPanel) lpPanel.innerHTML = ''; // hide LP panel on external networks
      loadOtherNetworkAssets(netId);
    }
  });

  // Load balances — same API as web wallet
  // Load persisted network (or Thronos default)
  const _initNet = document.getElementById('homeNetSel')?.value || 'thronos';
  if (_initNet === 'thronos') { loadThronosAssets(); loadLpPositions(); } else { loadOtherNetworkAssets(_initNet); }

  // Auto-refresh every 30s while wallet is open
  const _autoRefreshId = setInterval(() => {
    if (!document.getElementById('refreshBalBtn')) { clearInterval(_autoRefreshId); return; }
    const netId = document.getElementById('homeNetSel')?.value || 'thronos';
    if (netId === 'thronos') { loadThronosAssets(); return; }
    homeChainBalances = null;
    loadOtherNetworkAssets(netId);
  }, 30000);
}

// ─── Token detail modal ────────────────────────────────────────────────────────

function showTokenDetail(t) {
  const sym   = t.symbol || '?';
  const name  = t.name || sym;
  const bal   = Number(t.balance || 0);
  const color = t.color || '#00ff66';
  const logo  = t.logo_url || t.logo || '';
  const valThr = t.value_in_thr != null ? `${Number(t.value_in_thr).toFixed(4)} THR` : '—';
  const valUsd = t.value_usd != null    ? `$${Number(t.value_usd).toFixed(2)}`        : '—';
  const valBtc = t.value_wbtc != null   ? `₿ ${Number(t.value_wbtc).toFixed(8)}`      : '';
  const logoHtml = logo
    ? `<img src="${logo}" alt="${sym}" style="width:56px;height:56px;border-radius:50%;object-fit:cover" onerror="this.style.display='none'">`
    : `<div style="width:56px;height:56px;border-radius:50%;background:${color}33;border:2px solid ${color};display:flex;align-items:center;justify-content:center;font-size:1.3rem;font-weight:bold;color:${color}">${sym[0]}</div>`;
  const explorerUrl = `https://thronoschain.org/token/${encodeURIComponent(sym)}`;

  // Overlay modal
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;background:#000000aa;z-index:999;display:flex;align-items:flex-end;justify-content:center;';
  overlay.innerHTML = `
    <div style="background:#13112a;border-radius:16px 16px 0 0;width:100%;max-width:480px;padding:20px 20px 32px;box-shadow:0 -4px 24px #00000088">
      <div style="display:flex;align-items:center;gap:14px;margin-bottom:18px">
        ${logoHtml}
        <div>
          <div style="font-size:1.15rem;font-weight:700;color:#fff">${escHtml(name)}</div>
          <div style="color:var(--muted);font-size:.85rem">${sym} · Thronos</div>
        </div>
        <button id="tdClose" style="margin-left:auto;background:none;border:none;color:var(--muted);font-size:1.4rem;cursor:pointer;padding:4px 8px">✕</button>
      </div>

      <div style="background:#0d0a1a;border-radius:10px;padding:14px;margin-bottom:16px">
        <div style="font-size:1.6rem;font-weight:700;color:#fff;margin-bottom:4px">${bal.toFixed(t.decimals ?? 6)} ${sym}</div>
        <div style="color:var(--muted);font-size:.82rem">≈ ${valUsd} · ${valThr}${valBtc ? ' · ' + valBtc : ''}</div>
      </div>

      ${t.description ? `<div style="font-size:.82rem;color:var(--muted);margin-bottom:14px;line-height:1.5">${escHtml(t.description)}</div>` : ''}

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
        <button id="tdSend" class="btn btn--primary" style="padding:12px">💸 Send</button>
        <a href="${explorerUrl}" target="_blank" id="tdExplore" style="display:flex;align-items:center;justify-content:center;padding:12px;background:var(--card);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:.88rem;text-decoration:none;font-weight:600">⬡ Explore</a>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
  overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
  overlay.querySelector('#tdClose').addEventListener('click', () => overlay.remove());
  overlay.querySelector('#tdSend').addEventListener('click', () => {
    overlay.remove();
    showSend(sym);
  });
}

// ─── Tokens screen ────────────────────────────────────────────────────────────

async function showTokens() {
  const address = getActiveAddr();
  render(`
    <div class="screen">
      <div class="header">
        <button class="btn--icon" id="backBtn">←</button>
        <span class="header__title">Token Balances</span>
      </div>
      <div id="tokenList" class="card mt16">
        <p style="color:var(--muted);font-size:.88rem">Loading…</p>
      </div>
    </div>
  `);

  document.getElementById('backBtn').addEventListener('click', showWallet);

  const data = await fetchBalances(address);
  const el = document.getElementById('tokenList');
  if (!el) return;
  el.innerHTML = renderBalances(data);
}

// ─── Send screen ──────────────────────────────────────────────────────────────

// ── WalletConnect — scan QR from ThronosBuilder or paste URI ──────────────────
// Architecture: lightweight custom relay.
// ThronosBuilder generates thrconnect:// URI + QR code → PWA scans → paired.
// Builder posts sign requests → PWA polls, shows approval → user approves.

const WC_POLL_INTERVAL = 4000;
let _wcPollTimer = null;

function showWalletConnect() {
  const address = getActiveAddr();
  // jsQR handles all browsers including iOS Safari — camera access is all we need
  const canScan = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);

  render(`
    <div class="screen">
      <div class="header">
        <button class="btn--icon" id="wcBackBtn">←</button>
        <span class="header__title">⬡ Connect dApp</span>
      </div>

      <!-- Camera scan -->
      ${canScan ? `
      <button class="btn btn--primary" id="scanQrBtn" style="width:100%;padding:14px;font-size:1rem;margin-bottom:14px;display:flex;align-items:center;justify-content:center;gap:8px">
        📷 Scan QR Code
      </button>
      <div style="text-align:center;color:var(--muted);font-size:.82rem;margin-bottom:12px">— or paste URI manually —</div>
      ` : `
      <div style="background:#1a1040;border:1px solid #7c5cbf;border-radius:8px;padding:10px 12px;margin-bottom:12px;font-size:.78rem;color:#b08cf8">
        Camera not available on this browser. Paste the URI from ThronosBuilder below.
      </div>
      `}

      <!-- Manual paste -->
      <div class="card" style="padding:12px;margin-bottom:12px">
        <label style="font-size:.82rem;color:var(--accent);display:block;margin-bottom:6px">Paste connection URI</label>
        <textarea id="wcUri" class="input" rows="3" placeholder="thrconnect://… or wc://…" style="font-family:monospace;font-size:.75rem;resize:none"></textarea>
        <button class="btn btn--primary mt8" id="wcConnectBtn" style="width:100%">🔗 Connect</button>
      </div>

      <!-- Status + pending requests -->
      <div style="background:#0d0a1a;border:1px solid var(--accent);border-radius:8px;padding:12px">
        <div id="wcStatus" style="font-size:.82rem;color:var(--accent);margin-bottom:8px">● Ready to connect</div>
        <div id="wcRequestArea"></div>
      </div>

      <div style="margin-top:12px;padding:10px;background:#0a0a14;border-radius:6px;font-size:.72rem;color:var(--muted)">
        <b style="color:var(--accent)">Wallet:</b><br>
        <span style="font-family:monospace;word-break:break-all">${address}</span>
      </div>
    </div>
  `);

  document.getElementById('wcBackBtn').addEventListener('click', () => {
    if (_wcPollTimer) { clearInterval(_wcPollTimer); _wcPollTimer = null; }
    showWallet();
  });

  if (canScan) {
    document.getElementById('scanQrBtn').addEventListener('click', () => _openQrScanner(address));
  }

  document.getElementById('wcConnectBtn').addEventListener('click', async () => {
    const uri = document.getElementById('wcUri')?.value?.trim();
    if (!uri) return;
    await _handleWcUri(uri, address);
  });

  // Resume polling if already paired this session
  const existingSession = sessionStorage.getItem('thr_wc_session');
  if (existingSession) {
    const statusEl = document.getElementById('wcStatus');
    if (statusEl) statusEl.textContent = `● Connected (session: ${existingSession.slice(0,8)}…)`;
    _startWcPoll(address, existingSession);
  } else {
    _startWcPoll(address, null);
  }
}

// ─── QR Scanner ───────────────────────────────────────────────────────────────

// Generic QR scanner — calls onResult(data) with the raw scanned string
async function _openQrScannerGeneric(onResult) {
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } }
    });
  } catch (e) {
    alert('Camera permission denied or unavailable: ' + e.message);
    return;
  }

  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;background:#000;z-index:9999;display:flex;flex-direction:column;align-items:center;justify-content:center;';
  overlay.innerHTML = `
    <div style="position:relative;width:min(100vw,480px);max-height:60vh;overflow:hidden;border-radius:10px">
      <video id="qrVideo2" autoplay playsinline muted style="width:100%;display:block"></video>
      <div style="position:absolute;inset:0;pointer-events:none">
        <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:200px;height:200px;
                    border:3px solid #f5c842;border-radius:12px;
                    box-shadow:0 0 0 4000px rgba(0,0,0,.55)"></div>
      </div>
    </div>
    <p style="color:#fff;margin:16px 0 8px;font-size:.9rem;text-align:center">Scan a QR code</p>
    <button id="cancelScanBtn2" style="padding:10px 28px;background:#222;color:#fff;border:1px solid #555;border-radius:8px;font-size:.9rem;cursor:pointer">Cancel</button>
  `;
  document.body.appendChild(overlay);

  const video = overlay.querySelector('#qrVideo2');
  video.srcObject = stream;

  const stopScan = () => { stream.getTracks().forEach(t => t.stop()); overlay.remove(); };
  overlay.querySelector('#cancelScanBtn2').addEventListener('click', stopScan);

  let _jsQR = window.jsQR || null;
  if (!_jsQR) {
    await new Promise((resolve) => {
      const s = document.createElement('script');
      s.src = 'https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.min.js';
      s.onload = () => { _jsQR = window.jsQR; resolve(); };
      s.onerror = () => resolve();
      document.head.appendChild(s);
    });
  }

  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');

  // Some browsers expose the BarcodeDetector API but throw at construction
  // or detect()-time (e.g. missing OS-level qr_code format support). If we
  // silently swallow that every frame and keep retrying the same broken
  // path, the scanner runs forever without ever falling back to jsQR. Once
  // BarcodeDetector fails, disable it permanently for this scan session.
  let barcodeDetectorOk = ('BarcodeDetector' in window);
  const scanLoop = async () => {
    if (!overlay.isConnected) return;
    let handled = false;
    if (barcodeDetectorOk) {
      try {
        const codes = await new BarcodeDetector({ formats: ['qr_code'] }).detect(video);
        for (const c of codes) { if (c.rawValue) { stopScan(); onResult(c.rawValue); return; } }
        handled = true;
      } catch (_) {
        barcodeDetectorOk = false;
      }
    }
    if (!handled && _jsQR && video.readyState >= 2) {
      try {
        const w = video.videoWidth || 640, h = video.videoHeight || 480;
        canvas.width = w; canvas.height = h;
        ctx.drawImage(video, 0, 0, w, h);
        const img = ctx.getImageData(0, 0, w, h);
        // attemptBoth: ThronosBuilder's QR uses inverted colors (white modules on
        // dark background), which 'dontInvert' cannot decode.
        const res = _jsQR(img.data, img.width, img.height, { inversionAttempts: 'attemptBoth' });
        if (res?.data) { stopScan(); onResult(res.data); return; }
      } catch (_) {}
    }
    requestAnimationFrame(scanLoop);
  };
  video.addEventListener('loadedmetadata', () => requestAnimationFrame(scanLoop));
  if (video.readyState >= 2) requestAnimationFrame(scanLoop);
}

// Scan a recipient address (THR address or anything) and deliver it to a callback
function _openQrScannerForAddress(onAddress) {
  _openQrScannerGeneric((data) => {
    // If it looks like a THR address, use it directly
    if (/^THR[A-Za-z0-9]{30,60}$/.test(data.trim())) {
      onAddress(data.trim());
    } else {
      // Ask user if they want to use the scanned value anyway
      if (confirm(`Scanned: ${data.slice(0, 60)}${data.length > 60 ? '…' : ''}\n\nUse as recipient address?`)) {
        onAddress(data.trim());
      }
    }
  });
}

async function _openQrScanner(address) {
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } }
    });
  } catch (e) {
    alert('Camera permission denied or unavailable: ' + e.message);
    return;
  }

  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;background:#000;z-index:9999;display:flex;flex-direction:column;align-items:center;justify-content:center;';
  overlay.innerHTML = `
    <div style="position:relative;width:min(100vw,480px);max-height:60vh;overflow:hidden;border-radius:10px">
      <video id="qrVideo" autoplay playsinline muted style="width:100%;display:block"></video>
      <!-- Viewfinder overlay -->
      <div style="position:absolute;inset:0;pointer-events:none">
        <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:200px;height:200px;
                    border:3px solid var(--accent,#00ff66);border-radius:12px;
                    box-shadow:0 0 0 4000px rgba(0,0,0,.55)"></div>
      </div>
    </div>
    <p style="color:#fff;margin:16px 0 8px;font-size:.9rem;text-align:center">
      Aim the QR code at the box above
    </p>
    <button id="cancelScanBtn" style="padding:10px 28px;background:#222;color:#fff;border:1px solid #555;border-radius:8px;font-size:.9rem;cursor:pointer">Cancel</button>
  `;
  document.body.appendChild(overlay);

  const video = overlay.querySelector('#qrVideo');
  video.srcObject = stream;

  const stopScan = () => {
    stream.getTracks().forEach(t => t.stop());
    overlay.remove();
  };

  overlay.querySelector('#cancelScanBtn').addEventListener('click', stopScan);

  // Load jsQR dynamically as a universal fallback (works on iOS Safari, all browsers)
  let _jsQR = window.jsQR || null;
  if (!_jsQR) {
    await new Promise((resolve) => {
      const s = document.createElement('script');
      s.src = 'https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.min.js';
      s.onload = () => { _jsQR = window.jsQR; resolve(); };
      s.onerror = () => resolve(); // proceed even if CDN fails
      document.head.appendChild(s);
    });
  }

  const _scanCanvas = document.createElement('canvas');
  const _scanCtx = _scanCanvas.getContext('2d');

  // See _openQrScannerGeneric for why BarcodeDetector failures must
  // permanently fall back to jsQR rather than being retried every frame.
  let _barcodeDetectorOk = ('BarcodeDetector' in window);
  const _scanLoop = async () => {
    if (!overlay.isConnected) return;
    let _handled = false;
    if (_barcodeDetectorOk) {
      try {
        // Native API (Chrome Android, Chrome desktop)
        const detector = new BarcodeDetector({ formats: ['qr_code'] });
        const codes = await detector.detect(video);
        for (const code of codes) {
          if (code.rawValue) { stopScan(); await _handleWcUri(code.rawValue, address); return; }
        }
        _handled = true;
      } catch (_) {
        _barcodeDetectorOk = false;
      }
    }
    if (!_handled && _jsQR && video.readyState >= 2) {
      // jsQR canvas decode — works on iOS Safari, Firefox, all browsers
      try {
        const w = video.videoWidth || 640;
        const h = video.videoHeight || 480;
        _scanCanvas.width = w;
        _scanCanvas.height = h;
        _scanCtx.drawImage(video, 0, 0, w, h);
        const imgData = _scanCtx.getImageData(0, 0, w, h);
        // attemptBoth: ThronosBuilder's QR uses inverted colors (white modules on
        // dark background), which 'dontInvert' cannot decode.
        const result = _jsQR(imgData.data, imgData.width, imgData.height, { inversionAttempts: 'attemptBoth' });
        if (result && result.data) {
          stopScan();
          await _handleWcUri(result.data, address);
          return;
        }
      } catch (_) {}
    } else if (!_handled && !_barcodeDetectorOk && !_jsQR) {
      // Neither native detector nor jsQR is usable — fall back to paste UI
      stopScan();
      alert('Camera QR scan unavailable. Please copy the URI from ThronosBuilder and paste it below.');
      return;
    }
    requestAnimationFrame(_scanLoop);
  };

  video.addEventListener('loadedmetadata', () => requestAnimationFrame(_scanLoop));
  // Start scan loop immediately if video is already ready
  if (video.readyState >= 2) requestAnimationFrame(_scanLoop);
}

// ─── dApp approval (requires PIN/Face ID before connection) ────────────────────

async function requestDappApproval(dappName) {
  return new Promise((resolve) => {
    const address = getActiveAddr();
    const fid = LS.getObj(`thr_fid_${address}`);
    const hasFid = !!(fid?.credId);

    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.92);z-index:9999;display:flex;align-items:center;justify-content:center;';
    overlay.innerHTML = `
      <div style="background:#0d0a1a;border-radius:12px;padding:24px;max-width:320px;text-align:center;border:1px solid #2a2050">
        <div style="font-size:2rem;margin-bottom:12px">🔐</div>
        <p style="font-size:1.1rem;font-weight:600;color:#fff;margin-bottom:6px">Approve dApp Connection</p>
        <p style="color:var(--muted);font-size:.9rem;margin-bottom:20px">Connecting to <strong>${escHtml(dappName)}</strong></p>
        ${hasFid ? `<button class="btn btn--faceid" id="fidApproveBtn" style="margin-bottom:12px;width:100%">${fidSvg()} Approve with Face ID</button><div class="divider">or</div>` : ''}
        <div style="width:100%;display:flex;flex-direction:column;gap:8px;margin-bottom:12px">
          <input type="password" id="pinApproveInput" class="input" placeholder="Enter PIN" autocomplete="current-password">
          <button class="btn btn--primary" id="pinApproveBtn">Approve with PIN</button>
        </div>
        <button class="btn btn--ghost" id="cancelApproveBtn" style="width:100%">Cancel</button>
      </div>
    `;
    document.body.appendChild(overlay);

    const closeOverlay = (result) => { overlay.remove(); resolve(result); };

    overlay.querySelector('#cancelApproveBtn')?.addEventListener('click', () => closeOverlay(false));
    overlay.querySelector('#pinApproveInput')?.addEventListener('keydown', e => {
      if (e.key === 'Enter') overlay.querySelector('#pinApproveBtn')?.click();
    });

    overlay.querySelector('#fidApproveBtn')?.addEventListener('click', async () => {
      try {
        const fid = LS.getObj(`thr_fid_${address}`);
        const env = LS.getObj(`thr_env_${address}`);
        if (!fid?.credId || !env) throw new Error('Face ID not available');
        const privHex = await unwrapFromSession(address, env);
        if (privHex) { closeOverlay(true); return; }
        throw new Error('Face ID unlock failed');
      } catch (err) {
        if (err.name === 'NotAllowedError') {
          closeOverlay(false);
        } else {
          alert('Face ID failed: ' + (err.message || 'try PIN instead'));
        }
      }
    });

    overlay.querySelector('#pinApproveBtn')?.addEventListener('click', async () => {
      const pin = overlay.querySelector('#pinApproveInput')?.value?.trim();
      if (!pin) { alert('Enter your PIN'); return; }
      try {
        const acc = getAccount(address);
        if (!acc) throw new Error('Account not found');
        const kit = typeof acc.kit === 'string' ? JSON.parse(acc.kit) : acc.kit;
        const encBlob = kit.encrypted_private_key_backup ?? kit.wallet_v1_encrypted_priv ?? kit.encrypted_private_key ?? kit.enc_key;
        const privHex = await decryptBlob(encBlob, pin);
        closeOverlay(true);
      } catch {
        alert('Wrong PIN — please try again');
      }
    });
  });
}

// ─── URI handler ──────────────────────────────────────────────────────────────

async function _handleWcUri(uri, address) {
  const statusEl = document.getElementById('wcStatus');
  const setStatus = t => { if (statusEl) statusEl.textContent = t; };

  // thrconnect://SESSION_ID?relay=URL&dapp=NAME
  if (uri.startsWith('thrconnect://')) {
    const withoutProto = uri.slice('thrconnect://'.length);
    const [sessionId, queryStr] = withoutProto.split('?');
    const params = new URLSearchParams(queryStr || '');
    const dapp   = params.get('dapp') || 'dApp';

    // Require PIN/Face ID authentication before approving the connection
    const approved = await requestDappApproval(dapp);
    if (!approved) {
      setStatus(`⚠️ Connection cancelled`);
      return;
    }

    setStatus(`🔗 Pairing with ${dapp}…`);
    try {
      const r = await fetch(`${API_WRITE}/api/wallet/wc/pair`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ address, session_id: sessionId, dapp })
      });
      const d = await r.json().catch(() => ({}));
      if (d.ok) {
        sessionStorage.setItem('thr_wc_session', sessionId);
        setStatus(`✅ Connected to ${dapp} — awaiting requests`);
        _startWcPoll(address, sessionId);
      } else {
        setStatus(`⚠️ Pair failed: ${d.error || 'unknown'}`);
      }
    } catch (e) {
      setStatus(`⚠️ Network error: ${e.message}`);
    }
    return;
  }

  // wc:// (standard WalletConnect v2)
  if (uri.startsWith('wc:')) {
    const topic = uri.split('@')[0].replace('wc:', '');

    // Require PIN/Face ID authentication before approving the connection
    const approved = await requestDappApproval('WalletConnect dApp');
    if (!approved) {
      setStatus(`⚠️ Connection cancelled`);
      return;
    }

    setStatus(`🔗 WC pairing: ${topic.slice(0,8)}…`);
    try {
      const r = await fetch(`${API_WRITE}/api/wallet/wc/pair`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ address, wc_uri: uri, topic })
      });
      const d = await r.json().catch(() => ({}));
      if (d.ok) {
        sessionStorage.setItem('thr_wc_session', d.session_id || topic);
        setStatus(`✅ Paired — waiting for sign requests`);
        _startWcPoll(address, d.session_id || topic);
      } else {
        setStatus(`⚠️ Pair failed: ${d.error || 'unknown'}`);
      }
    } catch (e) {
      setStatus(`⚠️ Error: ${e.message}`);
    }
    return;
  }

  alert('Unknown URI format. Expected thrconnect:// or wc://');
}

function _startWcPoll(address, sessionId) {
  if (_wcPollTimer) clearInterval(_wcPollTimer);
  _wcPollTimer = setInterval(() => _checkWcRequests(address, sessionId), WC_POLL_INTERVAL);
  _checkWcRequests(address, sessionId); // immediate first check
}

async function _checkWcRequests(address, sessionId) {
  const reqArea  = document.getElementById('wcRequestArea');
  const statusEl = document.getElementById('wcStatus');
  if (!reqArea) { clearInterval(_wcPollTimer); return; }
  try {
    const url = `${API_WRITE}/api/wallet/wc/requests?address=${encodeURIComponent(address)}`
              + (sessionId ? `&session=${encodeURIComponent(sessionId)}` : '');
    const r = await fetch(url);
    if (!r.ok) return;
    const d = await r.json().catch(() => ({}));
    const requests = d.requests || [];
    if (!requests.length) {
      if (statusEl && !statusEl.textContent.includes('Connected') && !statusEl.textContent.includes('Paired')) {
        statusEl.textContent = '● Ready — no pending requests';
      }
      reqArea.innerHTML = '';
      return;
    }
    if (statusEl) statusEl.textContent = `🔔 ${requests.length} request(s) need your approval`;
    reqArea.innerHTML = requests.map(req => {
      const p = req.payload || {};
      const toShort = p.to ? p.to.slice(0,12) + '…' : '—';
      const amtLine = p.amount ? `<div style="font-size:1rem;font-weight:700;color:#fff;margin:6px 0">${p.amount} ${p.token || 'THR'}</div>` : '';
      const toLine  = p.to    ? `<div style="font-size:.72rem;color:var(--muted)">To: <span style="font-family:monospace">${toShort}</span></div>` : '';
      return `
      <div style="background:#0d0a1a;border:2px solid #7c5cbf;border-radius:10px;padding:12px;margin-bottom:8px">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
          <div style="font-size:.78rem;color:#b08cf8;font-weight:600">${escHtml(req.dapp || 'dApp')} — ${escHtml(req.action || 'Sign Request')}</div>
          <div style="font-size:.7rem;color:var(--muted)">${new Date((req.ts || Date.now() / 1000) * 1000).toLocaleTimeString()}</div>
        </div>
        ${amtLine}${toLine}
        <div style="display:flex;gap:8px;margin-top:10px">
          <button class="btn btn--primary" style="flex:2;padding:10px;font-size:.85rem" onclick="_approveWcRequest('${escHtml(req.id)}', '${escHtml(address)}')">
            🔐 Approve
          </button>
          <button class="btn btn--ghost" style="flex:1;padding:10px;font-size:.85rem;color:#ff6b6b;border-color:#ff6b6b" onclick="_rejectWcRequest('${escHtml(req.id)}', '${escHtml(address)}')">
            ✗ Reject
          </button>
        </div>
      </div>`;
    }).join('');
  } catch { /* network error — retry next tick */ }
}

async function _approveWcRequest(requestId, address) {
  // Get session key (Face ID unlocks it)
  const sessionKey = sessionStorage.getItem(`thr_sk_${address}`);
  if (!sessionKey) {
    // Try Face ID unlock first
    const fidData = localStorage.getItem(`thr_fid_${address}`);
    if (fidData) {
      try {
        const parsed = JSON.parse(fidData);
        const cred = await navigator.credentials.get({
          publicKey: {
            challenge: crypto.getRandomValues(new Uint8Array(32)),
            rpId: location.hostname === 'localhost' ? 'localhost' : 'thronoschain.org',
            allowCredentials: [{ type: 'public-key', id: Uint8Array.from(atob(parsed.credId), c => c.charCodeAt(0)) }],
            userVerification: 'required',
            timeout: 60000,
          }
        });
        if (!cred) { alert('Face ID failed. Please unlock wallet first.'); return; }
        alert('Face ID verified — fetching signing key…');
      } catch(e) { alert('Face ID error: ' + e.message); return; }
    } else {
      alert('Wallet locked. Please unlock with PIN or Face ID first.'); return;
    }
  }

  try {
    const r = await fetch(`${API_WRITE}/api/wallet/wc/approve`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ request_id: requestId, address, session_key: sessionKey })
    });
    const d = await r.json().catch(() => ({}));
    if (d.ok) {
      const reqArea = document.getElementById('wcRequestArea');
      if (reqArea) {
        const el = reqArea.querySelector(`[onclick*="${requestId}"]`)?.closest('div[style]');
        if (el) { el.style.border = '1px solid #4a8a2a'; el.querySelector('div:last-child').innerHTML = '✅ Approved & signed'; }
      }
    } else {
      alert('Approval failed: ' + (d.error || 'unknown'));
    }
  } catch(e) { alert('Network error: ' + e.message); }
}

async function _rejectWcRequest(requestId, address) {
  await fetch(`${API_WRITE}/api/wallet/wc/reject`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ request_id: requestId, address })
  }).catch(() => {});
  _checkWcRequests(address, sessionStorage.getItem('thr_wc_session'));
}

// ─── Multi-chain portfolio ────────────────────────────────────────────────────

async function showMultiChain() {
  const address = getActiveAddr();
  const { privHex } = unlocked.get(address) || {};
  let btcAddr = privHex ? await _fetchBtcAddress(privHex, address) : '';

  render(`
    <div class="screen">
      <div class="header">
        <button class="btn--icon" id="backBtn">←</button>
        <span class="header__title">🌐 Networks</span>
        <button class="btn--icon" id="refreshCcBtn" title="Refresh balances">↻</button>
      </div>
      <div style="padding:0 12px">
        <div id="evmAddrRow" style="display:none;background:#12122a;border:1px solid #2a2050;border-radius:8px;padding:10px 12px;margin-bottom:12px">
          <div style="font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:4px">EVM Address (ETH / BNB / L2)</div>
          <div id="evmAddrVal" style="font-family:monospace;font-size:.75rem;color:#b08cf8;word-break:break-all"></div>
          <button id="copyEvmBtn" class="btn btn--ghost" style="margin-top:6px;padding:3px 10px;font-size:.72rem">📋 Copy</button>
        </div>
        <div id="ccBalances" style="display:flex;flex-direction:column;gap:8px">
          <div style="color:var(--muted);text-align:center;padding:32px 0">⏳ Fetching cross-chain balances…</div>
        </div>
        <div style="margin-top:16px;background:#1a1040;border:1px solid #7c5cbf;border-radius:12px;padding:14px">
          <div style="font-size:.88rem;font-weight:700;color:#fff;margin-bottom:6px">⚡ Instant Bridge → Thronos</div>
          <div style="font-size:.78rem;color:var(--muted);margin-bottom:10px">Convert BTC or ETH to WBTC on Thronos in minutes</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
            <button class="btn btn--primary" id="btcBridgeBtn" style="padding:10px;font-size:.82rem">₿ BTC → WBTC</button>
            <button class="btn btn--ghost" id="ethBridgeBtn" style="padding:10px;font-size:.82rem">Ξ ETH → Bridge</button>
          </div>
        </div>
      </div>
    </div>
  `);

  document.getElementById('backBtn').addEventListener('click', showWallet);
  document.getElementById('btcBridgeBtn').addEventListener('click', () => showBridge('BTC', 'WBTC'));
  document.getElementById('ethBridgeBtn').addEventListener('click', () => showBridge('ETH', 'THR'));

  const renderCc = async () => {
    const el = document.getElementById('ccBalances');
    if (!el) return;
    if (!privHex) {
      el.innerHTML = '<div style="color:#ff6b6b;text-align:center;padding:24px 0">Wallet locked — unlock to view balances</div>';
      return;
    }
    el.innerHTML = '<div style="color:var(--muted);text-align:center;padding:24px 0">⏳ Loading…</div>';
    const bal = await _fetchAllChainBalances(privHex, btcAddr);

    if (bal.evmAddr) {
      document.getElementById('evmAddrRow').style.display = '';
      document.getElementById('evmAddrVal').textContent = bal.evmAddr;
      document.getElementById('copyEvmBtn').addEventListener('click', async () => {
        try { await navigator.clipboard.writeText(bal.evmAddr); } catch {}
        const b = document.getElementById('copyEvmBtn');
        if (b) { b.textContent = '✓ Copied'; setTimeout(() => { if(b) b.textContent = '📋 Copy'; }, 2000); }
      });
    }

    const fmt = (v, d=8) => v == null ? '—' : v === 0 ? '0.00' : v.toFixed(d);
    const chains = [
      { icon:'₿', label:'Bitcoin',         sym:'BTC',  val:bal.btc,      color:'#f7931a', net:'bitcoin',  addr:btcAddr },
      { icon:'Ξ', label:'Ethereum',         sym:'ETH',  val:bal.eth,      color:'#627eea', net:'ethereum', addr:bal.evmAddr },
      { icon:'🔶',label:'BNB Chain',        sym:'BNB',  val:bal.bnb,      color:'#f3ba2f', net:'bnb',      addr:bal.evmAddr },
      { icon:'₮', label:'USDT on BNB',      sym:'USDT', val:bal.usdtBnb,  color:'#26a17b', net:'bnb',      addr:bal.evmAddr },
      { icon:'🔵',label:'Arbitrum',          sym:'ETH',  val:bal.arb,      color:'#28a0f0', net:'arbitrum', addr:bal.evmAddr },
      { icon:'₮', label:'USDT on Arbitrum', sym:'USDT', val:bal.usdtArb,  color:'#26a17b', net:'arbitrum', addr:bal.evmAddr },
      { icon:'⬛',label:'Optimism',          sym:'ETH',  val:bal.op,       color:'#ff0420', net:'optimism', addr:bal.evmAddr },
      { icon:'⬛',label:'Base',              sym:'ETH',  val:bal.base,     color:'#0052ff', net:'base',     addr:bal.evmAddr },
      { icon:'$', label:'USDC on Base',      sym:'USDC', val:bal.usdcBase, color:'#2775ca', net:'base',     addr:bal.evmAddr },
    ];

    el.innerHTML = chains.map(c => `
      <div style="background:#12122a;border:1px solid #2a2050;border-radius:10px;padding:11px 13px;display:flex;align-items:center;gap:10px">
        <div style="width:36px;height:36px;border-radius:50%;background:${c.color}20;border:1px solid ${c.color}40;display:flex;align-items:center;justify-content:center;font-size:1rem;flex-shrink:0">${c.icon}</div>
        <div style="flex:1;min-width:0">
          <div style="font-size:.84rem;font-weight:700;color:#fff">${c.label}</div>
          ${c.addr ? `<div style="font-size:.68rem;color:var(--muted);font-family:monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${c.addr.slice(0,14)}…${c.addr.slice(-5)}</div>` : ''}
        </div>
        <div style="text-align:right;flex-shrink:0">
          <div style="font-size:.88rem;font-weight:700;color:${c.val ? '#fff' : 'var(--muted)'}">${fmt(c.val)} ${c.sym}</div>
          ${(c.val && c.val > 0) ? `<button onclick="showBridge('${c.sym}','WBTC')" style="font-size:.68rem;padding:2px 7px;margin-top:3px;background:#2a1a4a;border:1px solid #7c5cbf;color:#b08cf8;border-radius:4px;cursor:pointer">Bridge→</button>` : ''}
        </div>
      </div>`).join('');
  };

  await renderCc();
  document.getElementById('refreshCcBtn')?.addEventListener('click', renderCc);
}

// ─── Bridge screen ─────────────────────────────────────────────────────────────

// ─── USDT-on-BNB-Chain Pledge (PWA/mobile only) ────────────────────────────

async function showUsdtPledge(address) {
  render(`
    <div class="screen">
      <div class="header">
        <button class="btn--icon" id="backBtn">←</button>
        <span class="logo--sm">⬡ THR</span>
        <span style="width:32px"></span>
      </div>
      <h2 style="font-size:1.1rem;margin-top:8px">💵 USDT Pledge (BNB Chain)</h2>
      <p style="color:var(--muted);font-size:.85rem">Send USDT (BEP20) on Binance Smart Chain to the vault below. Once confirmed, your THR equivalent is credited automatically — half is paired into the THR/USDT liquidity pool. Minimum pledge applies.</p>

      <div id="pledgeQuoteArea" class="card" style="padding:12px;margin-bottom:10px">
        <div style="color:var(--muted);font-size:.85rem">Loading vault details…</div>
      </div>

      <div class="card" style="padding:12px;margin-bottom:10px">
        <h3 style="font-size:.95rem;margin-bottom:6px">1. Register your sending BNB address</h3>
        <p style="color:var(--muted);font-size:.8rem">Enter the BNB/BEP20 address you'll send USDT FROM — this links your pledge to your THR wallet.</p>
        <input type="text" id="bnbAddrInput" class="input" placeholder="0x... (your BNB sending address)" autocomplete="off">
        <button class="btn btn--primary mt8" id="bnbRegisterBtn">Register Address</button>
        <div id="bnbRegisterMsg" style="margin-top:8px;font-size:.82rem"></div>
      </div>

      <div id="pledgeErr" class="banner banner--error hidden"></div>
    </div>
  `);

  document.getElementById('backBtn').addEventListener('click', showWallet);

  // Load quote (vault address, contract, min, rate)
  try {
    const r = await fetch(`${API_WRITE}/api/pledge/bnb/quote`);
    const d = await r.json().catch(() => ({}));
    const quoteEl = document.getElementById('pledgeQuoteArea');
    if (r.ok && d.ok !== false) {
      quoteEl.innerHTML = `
        <div style="font-size:.78rem;color:var(--muted);margin-bottom:4px">Send USDT (BEP20) to:</div>
        <div style="font-family:monospace;font-size:.82rem;color:var(--accent);word-break:break-all;background:#0d0a1a;border-radius:6px;padding:8px;margin-bottom:8px" id="vaultAddrLine">${d.vault_address || '—'}</div>
        <button class="btn btn--ghost" id="copyVaultBtn" style="font-size:.75rem;padding:4px 10px;margin-bottom:8px">Copy Address</button>
        <div style="font-size:.78rem;color:var(--muted)">Token contract: <span style="font-family:monospace">${d.token_contract || '—'}</span></div>
        <div style="font-size:.78rem;color:var(--muted)">Network: ${d.chain || 'BNB Smart Chain (BEP20)'}</div>
        <div style="font-size:.78rem;color:var(--muted)">Minimum pledge: ${d.min_usdt ?? 10} USDT</div>
        <div style="font-size:.78rem;color:var(--muted)">Rate: 1 USDT ≈ ${d.usdt_thr_rate ?? 100} THR</div>
      `;
      document.getElementById('copyVaultBtn')?.addEventListener('click', async () => {
        try { await navigator.clipboard.writeText(d.vault_address || ''); } catch {}
        const b = document.getElementById('copyVaultBtn');
        if (b) { b.textContent = '✓ Copied'; setTimeout(() => { if (b) b.textContent = 'Copy Address'; }, 1500); }
      });
    } else {
      quoteEl.innerHTML = `<div style="color:#ff6b6b;font-size:.85rem">Pledge vault not configured yet. Try again later.</div>`;
    }
  } catch (e) {
    document.getElementById('pledgeQuoteArea').innerHTML = `<div style="color:#ff6b6b;font-size:.85rem">Network error loading vault details.</div>`;
  }

  document.getElementById('bnbRegisterBtn').addEventListener('click', async () => {
    const bnbAddr = document.getElementById('bnbAddrInput')?.value?.trim();
    const msgEl = document.getElementById('bnbRegisterMsg');
    const errEl = document.getElementById('pledgeErr');
    errEl.classList.add('hidden');
    msgEl.textContent = '';
    if (!bnbAddr || !/^0x[a-fA-F0-9]{40}$/.test(bnbAddr)) {
      errEl.textContent = 'Enter a valid BNB (0x...) address';
      errEl.classList.remove('hidden');
      return;
    }
    const btn = document.getElementById('bnbRegisterBtn');
    btn.disabled = true; btn.textContent = 'Registering…';
    try {
      const r = await fetch(`${API_WRITE}/api/pledge/bnb/register`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ thr_address: address, bnb_address: bnbAddr })
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok || d.ok === false) {
        errEl.textContent = 'Registration failed: ' + (d.error || 'unknown');
        errEl.classList.remove('hidden');
        return;
      }
      msgEl.style.color = '#4ade80';
      msgEl.textContent = '✅ Address registered. Send USDT from this address to the vault above — THR will be credited once confirmed (~5 min).';
    } catch (e) {
      errEl.textContent = 'Network error: ' + e.message;
      errEl.classList.remove('hidden');
    } finally {
      btn.disabled = false; btn.textContent = 'Register Address';
    }
  });
}

const _BRIDGE_PAIRS = [
  { from:'BTC',  to:'WBTC', fee:0.1,  time:'~5 min',  label:'₿ BTC → WBTC',  available:true },
  { from:'WBTC', to:'BTC',  fee:0.1,  time:'~15 min', label:'WBTC → ₿ BTC',  available:true },
  { from:'THR',  to:'WBTC', fee:0.1,  time:'~2 min',  label:'THR → WBTC',    available:true },
  { from:'ETH',  to:'THR',  fee:0.2,  time:'~10 min', label:'Ξ ETH → THR',   available:false },
  { from:'BNB',  to:'THR',  fee:0.15, time:'~8 min',  label:'🔶 BNB → THR',  available:false },
];

async function showBridge(fromToken = 'BTC', toToken = 'WBTC') {
  const address = getActiveAddr();
  const { privHex } = unlocked.get(address) || {};
  let activePair = _BRIDGE_PAIRS.find(p => p.from === fromToken && p.to === toToken) || _BRIDGE_PAIRS[0];

  const pairBtns = _BRIDGE_PAIRS.map((p, i) => {
    const isActive = p.from === fromToken && p.to === toToken;
    return `<button class="bridge-pair-btn${isActive?' bpb-active':''}" data-from="${p.from}" data-to="${p.to}"
      style="background:${isActive?'#1a1040':'#0d0d1a'};border:1px solid ${isActive?'#7c5cbf':'#2a2050'};
      border-radius:10px;padding:11px 13px;display:flex;align-items:center;justify-content:space-between;
      cursor:${p.available?'pointer':'not-allowed'};color:${p.available?'#fff':'#555'}">
      <span style="font-size:.86rem;font-weight:600">${p.label}</span>
      <span style="font-size:.72rem;color:${p.available?'#b08cf8':'#555'}">${p.available?p.fee+'% · '+p.time:'Coming soon'}</span>
    </button>`;
  }).join('');

  render(`
    <div class="screen">
      <div class="header">
        <button class="btn--icon" id="backBtn">←</button>
        <span class="header__title">⚡ Bridge</span>
        <span style="width:36px"></span>
      </div>
      <div style="padding:0 12px;display:flex;flex-direction:column;gap:10px">
        <div style="display:flex;flex-direction:column;gap:6px">${pairBtns}</div>
        <div style="background:#12122a;border:1px solid #7c5cbf;border-radius:12px;padding:16px">
          <div id="bridgePairLabel" style="font-size:1rem;font-weight:700;color:#fff;margin-bottom:12px">${activePair.label}</div>
          <label style="color:var(--muted);font-size:.82rem">Amount (<span id="bridgeFromSym">${activePair.from}</span>)</label>
          <input type="number" id="bridgeAmt" class="input" placeholder="0.0001" step="any" inputmode="decimal" min="0">
          <div id="quoteBox" style="display:none;background:#0d0d1a;border-radius:8px;padding:10px;margin:10px 0;font-size:.82rem">
            <div style="display:flex;justify-content:space-between"><span style="color:var(--muted)">You receive</span><span id="quoteOut" style="color:#00ff66;font-weight:700"></span></div>
            <div style="display:flex;justify-content:space-between;margin-top:4px"><span style="color:var(--muted)">Fee</span><span id="quoteFee" style="color:#b08cf8"></span></div>
            <div style="display:flex;justify-content:space-between;margin-top:4px"><span style="color:var(--muted)">Est. time</span><span id="quoteTime" style="color:var(--muted)"></span></div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px">
            <button class="btn btn--ghost" id="quoteBtn" style="padding:12px">Get Quote</button>
            <button class="btn btn--primary" id="bridgeBtn" style="padding:12px" disabled>Bridge Now</button>
          </div>
          <div id="bridgeErr" style="margin-top:8px;color:#ff6b6b;font-size:.82rem;display:none"></div>
          <div id="bridgeOk" style="margin-top:8px;color:#00ff66;font-size:.82rem;display:none"></div>
        </div>
        <div style="font-size:.72rem;color:var(--muted);text-align:center">Non-custodial · Powered by Thronos Cross-Chain Protocol</div>
      </div>
    </div>
  `);

  document.getElementById('backBtn').addEventListener('click', showMultiChain);

  document.querySelectorAll('.bridge-pair-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const p = _BRIDGE_PAIRS.find(x => x.from === btn.dataset.from && x.to === btn.dataset.to);
      if (!p || !p.available) return;
      activePair = p;
      document.querySelectorAll('.bridge-pair-btn').forEach(b => {
        const active = b.dataset.from === p.from && b.dataset.to === p.to;
        b.style.background = active ? '#1a1040' : '#0d0d1a';
        b.style.borderColor = active ? '#7c5cbf' : '#2a2050';
      });
      document.getElementById('bridgePairLabel').textContent = p.label;
      document.getElementById('bridgeFromSym').textContent = p.from;
      document.getElementById('quoteBox').style.display = 'none';
      document.getElementById('bridgeBtn').disabled = true;
    });
  });

  document.getElementById('quoteBtn').addEventListener('click', () => {
    const amt = parseFloat(document.getElementById('bridgeAmt').value);
    document.getElementById('bridgeErr').style.display = 'none';
    if (!amt || amt <= 0) { document.getElementById('bridgeErr').textContent = 'Enter an amount'; document.getElementById('bridgeErr').style.display = ''; return; }
    const fee = amt * (activePair.fee / 100);
    document.getElementById('quoteOut').textContent = `${(amt - fee).toFixed(8)} ${activePair.to}`;
    document.getElementById('quoteFee').textContent = `${fee.toFixed(8)} ${activePair.from} (${activePair.fee}%)`;
    document.getElementById('quoteTime').textContent = activePair.time;
    document.getElementById('quoteBox').style.display = '';
    document.getElementById('bridgeBtn').disabled = false;
  });

  document.getElementById('bridgeBtn').addEventListener('click', async () => {
    if (!privHex) { document.getElementById('bridgeErr').textContent = 'Wallet locked'; document.getElementById('bridgeErr').style.display = ''; return; }
    const amt = parseFloat(document.getElementById('bridgeAmt').value);
    if (!amt || amt <= 0) return;
    const btn = document.getElementById('bridgeBtn');
    btn.disabled = true; btn.textContent = 'Bridging…';
    document.getElementById('bridgeErr').style.display = 'none';
    try {
      const r = await fetch(`${API_WRITE}/api/bridge/execute`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ from_token: activePair.from, to_token: activePair.to, amount: amt, from_address: address, private_key_hex: privHex }),
      });
      const d = await r.json().catch(() => ({}));
      if (r.ok && (d.ok || d.accepted || d.tx_id || d.txid)) {
        document.getElementById('bridgeOk').textContent = `✅ Bridge initiated! TX: ${d.tx_id || d.txid || 'submitted'}`;
        document.getElementById('bridgeOk').style.display = '';
        btn.textContent = 'Done ✓';
      } else {
        throw new Error(d.error || d.message || `HTTP ${r.status}`);
      }
    } catch (e) {
      document.getElementById('bridgeErr').textContent = e.message;
      document.getElementById('bridgeErr').style.display = '';
      btn.disabled = false; btn.textContent = 'Bridge Now';
    }
  });
}

// ─── Music screen ─────────────────────────────────────────────────────────────
// NOTE: L2E (Learn-to-Earn) = earned from Courses, NOT music.
//        Music listening rewards = T2E (Time-to-Earn) / boost credits.
//        GPS telemetry: activated during CarPlay/Android Auto sessions.

let _musicSession  = null;   // { session_id, track_id, started, artist_address }
let _musicAudio    = null;
let _gpsWatchId    = null;   // navigator.geolocation.watchPosition id
let _gpsPoints     = [];     // accumulated GPS points for route hash
let _trackQueue    = [];     // ordered list of track objects for prev/next
let _trackQueueIdx = -1;     // index of currently playing track in _trackQueue

// Detect CarPlay / Android Auto (audio session on external display)
function _detectCarPlayOrAuto() {
  const ua = navigator.userAgent || '';
  const isIOS     = /iPhone|iPad|iPod/.test(ua);
  const isAndroid = /Android/.test(ua);
  // CarPlay: iOS + audio output on external; use MediaDevices if available
  const hasExternalAudio = typeof AudioContext !== 'undefined';
  // Heuristic: standalone PWA on iOS = potential CarPlay context
  const isStandalone = window.matchMedia('(display-mode: standalone)').matches ||
                       window.navigator.standalone === true;
  return { isIOS, isAndroid, isStandalone, likelyCar: isStandalone && (isIOS || isAndroid) };
}

// SHA-256 hash of GPS route string (privacy-preserving)
async function _hashRoute(points) {
  if (!points.length) return '';
  const str = points.map(p => `${p.lat.toFixed(4)},${p.lng.toFixed(4)}`).join(';');
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(str));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2,'0')).join('');
}

function _startGpsTracking() {
  if (!navigator.geolocation) return;
  _gpsPoints = [];
  _gpsWatchId = navigator.geolocation.watchPosition(
    pos => {
      _gpsPoints.push({ lat: pos.coords.latitude, lng: pos.coords.longitude, ts: Date.now() });
      // Keep last 200 points to cap memory
      if (_gpsPoints.length > 200) _gpsPoints.shift();
    },
    () => {}, // permission denied — silent
    { enableHighAccuracy: true, maximumAge: 5000, timeout: 10000 }
  );
}

function _stopGpsTracking() {
  if (_gpsWatchId !== null) {
    navigator.geolocation.clearWatch(_gpsWatchId);
    _gpsWatchId = null;
  }
}

async function showMusic() {
  const address = getActiveAddr();

  render(`
    <div class="screen">
      <div class="header">
        <button class="btn--icon" id="backBtn">←</button>
        <span class="header__title">♪ Music</span>
        <button class="btn--icon" id="musicTabBtn" title="Library/Playlists">📚</button>
      </div>

      <!-- Now Playing (hidden until track selected) -->
      <div id="nowPlaying" style="display:none;background:#1a1040;border:1px solid #7c5cbf;border-radius:12px;padding:12px 14px;margin:10px 0">
        <div style="font-size:.72rem;color:var(--muted);margin-bottom:4px">NOW PLAYING</div>
        <div id="npTitle" style="font-weight:700;color:#fff;font-size:.95rem;margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis"></div>
        <div id="npArtist" style="font-size:.8rem;color:#b08cf8;margin-bottom:8px;cursor:pointer"></div>
        <!-- Progress bar -->
        <div style="height:3px;background:#2a2050;border-radius:2px;margin-bottom:10px;position:relative">
          <div id="npProgress" style="height:100%;background:linear-gradient(90deg,#7c5cbf,#b08cf8);border-radius:2px;width:0%;transition:width .5s linear"></div>
        </div>
        <!-- Controls row -->
        <div style="display:flex;align-items:center;gap:8px">
          <button class="btn btn--ghost" id="prevBtn" style="padding:7px 10px;font-size:1rem">⏮</button>
          <button class="btn btn--ghost" id="playPauseBtn" style="padding:7px 14px;font-size:1rem;flex:1">⏸ Pause</button>
          <button class="btn btn--ghost" id="nextBtn" style="padding:7px 10px;font-size:1rem">⏭</button>
          <button class="btn btn--primary" id="tipBtn" style="padding:7px 12px;font-size:.8rem">💰 Tip</button>
          <div id="sessionTimer" style="color:var(--accent);font-size:.78rem;min-width:38px;text-align:right"></div>
        </div>
        <div id="carPlayBadge" style="display:none;margin-top:8px;font-size:.72rem;color:#00ff66">🚗 CarPlay · GPS · +T2E</div>
      </div>

      <!-- Tabs: Library | Playlists -->
      <div style="display:flex;gap:0;margin-bottom:10px;border:1px solid var(--border);border-radius:8px;overflow:hidden">
        <button id="tabLibrary" style="flex:1;padding:8px;background:#1a1040;border:none;color:#b08cf8;font-size:.82rem;cursor:pointer;font-weight:600">🎵 Library</button>
        <button id="tabPlaylists" style="flex:1;padding:8px;background:transparent;border:none;color:var(--muted);font-size:.82rem;cursor:pointer">📋 Playlists</button>
      </div>

      <div id="musicContent" style="display:flex;flex-direction:column;gap:6px">
        <p style="color:var(--muted);font-size:.88rem">Loading…</p>
      </div>
    </div>
  `);

  let currentTab = 'library';

  document.getElementById('backBtn').addEventListener('click', () => {
    if (_musicAudio) _musicAudio.pause();
    showWallet();
  });
  document.getElementById('tipBtn').addEventListener('click', _showTipModal);

  const switchTab = (tab) => {
    currentTab = tab;
    document.getElementById('tabLibrary').style.background   = tab === 'library'   ? '#1a1040' : 'transparent';
    document.getElementById('tabLibrary').style.color        = tab === 'library'   ? '#b08cf8' : 'var(--muted)';
    document.getElementById('tabPlaylists').style.background = tab === 'playlists' ? '#1a1040' : 'transparent';
    document.getElementById('tabPlaylists').style.color      = tab === 'playlists' ? '#b08cf8' : 'var(--muted)';
    if (tab === 'library')   _loadMusicLibrary(address);
    if (tab === 'playlists') _loadPlaylists(address);
  };

  document.getElementById('tabLibrary').addEventListener('click',   () => switchTab('library'));
  document.getElementById('tabPlaylists').addEventListener('click', () => switchTab('playlists'));

  // Check CarPlay/car environment on open
  const carCtx = _detectCarPlayOrAuto();
  if (carCtx.likelyCar && _musicSession) {
    const badge = document.getElementById('carPlayBadge');
    if (badge) badge.style.display = '';
  }

  switchTab('library');
}

function _renderTrackRow(t, idx) {
  const tid      = t.id || t.track_id || '';
  const title    = t.title || t.name || tid || '—';
  const artist   = t.artist_name || t.artist || '';
  const dur      = t.duration_seconds
    ? `${Math.floor(t.duration_seconds / 60)}:${String(t.duration_seconds % 60).padStart(2,'0')}`
    : '';
  const artAddr  = t.artist_address || '';
  const isActive = _musicSession?.track_id === tid;
  const qidxAttr = idx !== undefined ? `data-qidx="${idx}"` : '';
  const activeBorder = isActive ? 'border:1px solid #7c5cbf;' : '';
  const activeIcon   = isActive ? '▶' : '▶';
  const activeIconBg = isActive ? '#3a1080' : '#1a1040';
  const activeIconColor = isActive ? '#fff' : '#b08cf8';
  return `<div class="tx-item music-track-row" style="cursor:pointer;${activeBorder}"
      data-tid="${escHtml(tid)}" data-title="${escHtml(title)}" data-artist="${escHtml(artist)}"
      data-artist-addr="${escHtml(artAddr)}" data-url="${escHtml(t.stream_url || t.audio_url || '')}" ${qidxAttr}>
    <div class="tx-item__dir" style="background:${activeIconBg};color:${activeIconColor};font-size:1rem">${isActive ? '🎵' : '▶'}</div>
    <div class="tx-item__info">
      <div class="tx-item__label" style="${isActive ? 'color:#b08cf8;' : ''}">${escHtml(title)}</div>
      <div class="tx-item__date">${escHtml(artist)}${dur ? ' · ' + dur : ''}</div>
    </div>
    <div class="tx-item__amount" style="color:#7c5cbf;font-size:.72rem">${isActive ? '▶ Playing' : '+T2E'}</div>
  </div>`;
}

async function _loadMusicLibrary(address) {
  const el = document.getElementById('musicContent');
  if (!el) return;
  el.innerHTML = '<p style="color:var(--muted);font-size:.88rem">Loading tracks…</p>';
  try {
    const r = await fetch(`${API_WRITE}/api/v1/music/tracks`);
    const d = r.ok ? await r.json() : { tracks: [] };
    const tracks = Array.isArray(d) ? d : (d.tracks || d.data || []);
    if (!tracks.length) { el.innerHTML = '<p style="color:var(--muted);font-size:.88rem">No tracks available.</p>'; return; }
    const visibleTracks = tracks.slice(0, 50);
    _trackQueue = visibleTracks;
    _trackQueueIdx = -1;
    el.innerHTML = visibleTracks.map((t, i) => _renderTrackRow(t, i)).join('');
    el.querySelectorAll('.music-track-row').forEach(row => {
      row.addEventListener('click', () => {
        const qidx = parseInt(row.dataset.qidx, 10);
        if (!isNaN(qidx)) _trackQueueIdx = qidx;
        _playTrack({
          id: row.dataset.tid, title: row.dataset.title,
          artist: row.dataset.artist, artist_address: row.dataset.artistAddr,
          url: row.dataset.url
        });
      });
    });
  } catch {
    el.innerHTML = '<p style="color:var(--muted);font-size:.88rem">Could not load tracks.</p>';
  }
}

async function _loadPlaylists(address) {
  const el = document.getElementById('musicContent');
  if (!el) return;
  el.innerHTML = '<p style="color:var(--muted);font-size:.88rem">Loading playlists…</p>';
  try {
    const r = await fetch(`${API_WRITE}/api/v1/music/playlists?address=${encodeURIComponent(address)}`);
    const d = r.ok ? await r.json() : {};
    const lists = Array.isArray(d) ? d : (d.playlists || []);
    if (!lists.length) {
      el.innerHTML = `
        <p style="color:var(--muted);font-size:.85rem;margin-bottom:12px">No playlists yet.</p>
        <button class="btn btn--primary" id="newPlaylistBtn">＋ New Playlist</button>`;
      document.getElementById('newPlaylistBtn')?.addEventListener('click', () => _createPlaylist(address));
      return;
    }
    el.innerHTML = `
      <button class="btn btn--ghost" id="newPlaylistBtn" style="margin-bottom:8px">＋ New Playlist</button>
      ${lists.map(pl => `
        <div class="tx-item" style="cursor:pointer" data-plid="${escHtml(pl.id || pl.playlist_id || '')}">
          <div class="tx-item__dir" style="background:#1a1040;color:#b08cf8">▶</div>
          <div class="tx-item__info">
            <div class="tx-item__label">${escHtml(pl.name || pl.title || 'Playlist')}</div>
            <div class="tx-item__date">${pl.track_count || pl.tracks?.length || 0} κομμάτια</div>
          </div>
        </div>`).join('')}`;
    document.getElementById('newPlaylistBtn')?.addEventListener('click', () => _createPlaylist(address));
    el.querySelectorAll('[data-plid]').forEach(row => {
      row.addEventListener('click', () => _openPlaylist(row.dataset.plid, address));
    });
  } catch {
    el.innerHTML = '<p style="color:var(--muted);font-size:.88rem">Could not load playlists.</p>';
  }
}

async function _createPlaylist(address) {
  const name = prompt('Playlist name:');
  if (!name) return;
  try {
    const r = await fetch(`${API_WRITE}/api/v1/music/playlists`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address, name })
    });
    const d = await r.json().catch(() => ({}));
    if (r.ok) { _loadPlaylists(address); }
    else { alert(d.error || 'Could not create playlist'); }
  } catch { alert('Network error'); }
}

async function _openPlaylist(playlistId, address) {
  const el = document.getElementById('musicContent');
  if (!el) return;
  el.innerHTML = '<p style="color:var(--muted)">Loading…</p>';
  try {
    const r = await fetch(`${API_WRITE}/api/v1/music/playlists/${encodeURIComponent(playlistId)}?address=${encodeURIComponent(address)}`);
    const d = r.ok ? await r.json() : {};
    const tracks = d.tracks || [];
    el.innerHTML = `
      <button class="btn btn--ghost" id="backToPlaylists" style="margin-bottom:8px">← Back</button>
      <div style="font-weight:600;color:#fff;margin-bottom:8px">${escHtml(d.name || 'Playlist')}</div>
      ${tracks.length ? tracks.map(_renderTrackRow).join('') : '<p style="color:var(--muted);font-size:.85rem">Empty playlist</p>'}`;
    document.getElementById('backToPlaylists')?.addEventListener('click', () => _loadPlaylists(address));
    el.querySelectorAll('.music-track-row').forEach(row => {
      row.addEventListener('click', () => _playTrack({
        id: row.dataset.tid, title: row.dataset.title,
        artist: row.dataset.artist, artist_address: row.dataset.artistAddr,
        url: row.dataset.url
      }));
    });
  } catch {
    el.innerHTML = '<p style="color:var(--muted)">Could not load playlist.</p>';
  }
}

function _showTipModal() {
  if (!_musicSession?.artist_address) {
    alert('No artist address available for this track.');
    return;
  }
  const artistAddr = _musicSession.artist_address;
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;background:#000000aa;z-index:999;display:flex;align-items:flex-end;justify-content:center;';
  overlay.innerHTML = `
    <div style="background:#13112a;border-radius:16px 16px 0 0;width:100%;max-width:480px;padding:20px 20px 32px">
      <div style="font-size:1rem;font-weight:700;color:#fff;margin-bottom:16px">💰 Send Tip to Artist</div>
      <div style="font-size:.8rem;color:var(--muted);margin-bottom:12px;word-break:break-all">${escHtml(artistAddr)}</div>
      <label style="font-size:.82rem;color:var(--muted)">Amount (THR)</label>
      <input type="number" id="tipAmount" class="input" value="1.00" min="0.01" step="0.01" inputmode="decimal" style="margin-bottom:14px">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
        <button id="tipCancel" class="btn btn--ghost" style="padding:12px">Cancel</button>
        <button id="tipSend" class="btn btn--primary" style="padding:12px">Send Tip</button>
      </div>
      <div id="tipErr" style="margin-top:10px;color:#ff6b6b;font-size:.82rem;display:none"></div>
    </div>`;
  document.body.appendChild(overlay);
  overlay.querySelector('#tipCancel').addEventListener('click', () => overlay.remove());
  overlay.querySelector('#tipSend').addEventListener('click', async () => {
    const amount = parseFloat(overlay.querySelector('#tipAmount').value);
    if (!amount || amount <= 0) { overlay.querySelector('#tipErr').textContent = 'Enter a valid amount'; overlay.querySelector('#tipErr').style.display = ''; return; }
    const address = getActiveAddr();
    const { privHex } = unlocked.get(address) || {};
    if (!privHex) { overlay.querySelector('#tipErr').textContent = 'Wallet locked'; overlay.querySelector('#tipErr').style.display = ''; return; }
    try {
      const result = await sendToken(address, artistAddr, amount, 'THR', privHex);
      overlay.innerHTML = `<div style="padding:24px 20px 40px;text-align:center;color:#00ff66;font-size:1rem">✅ Tip sent! TXid: ${result.tx_hash || result.txid || 'ok'}</div>`;
      setTimeout(() => overlay.remove(), 2500);
    } catch (e) {
      overlay.querySelector('#tipErr').textContent = e.message || 'Send failed';
      overlay.querySelector('#tipErr').style.display = '';
    }
  });
}

function escHtml(s) { return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

async function _playTrack(track) {
  const address = getActiveAddr();
  if (_musicSession) await _stopMusic();

  // Detect car environment for GPS + T2E boost
  const carCtx = _detectCarPlayOrAuto();
  if (carCtx.likelyCar) _startGpsTracking();

  // Register Media Session API (shows controls on CarPlay / lock screen)
  if ('mediaSession' in navigator) {
    navigator.mediaSession.metadata = new MediaMetadata({
      title:  track.title  || 'Unknown',
      artist: track.artist || 'Thronos Music',
      album:  'Thronos Network',
    });
    navigator.mediaSession.setActionHandler('stop',          _stopMusic);
    navigator.mediaSession.setActionHandler('pause',         _stopMusic);
    navigator.mediaSession.setActionHandler('previoustrack', _playPrev);
    navigator.mediaSession.setActionHandler('nexttrack',     _playNext);
  }

  // Start server session (telemetry / T2E)
  try {
    const carPayload = carCtx.likelyCar
      ? { car_context: true, platform: carCtx.isIOS ? 'carplay' : 'android_auto' }
      : {};
    const r = await fetch(`${API_WRITE}/api/music/session/start`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address, track_id: track.id,
        artist_address: track.artist_address || '',
        source: carCtx.likelyCar ? (carCtx.isIOS ? 'carplay' : 'android_auto') : 'pwa',
        ...carPayload })
    });
    const d = await r.json().catch(() => ({}));
    _musicSession = { session_id: d.session_id || '', track_id: track.id,
                      artist_address: track.artist_address || '',
                      started: Date.now(), car: carCtx.likelyCar };
  } catch {
    _musicSession = { session_id: '', track_id: track.id,
                      artist_address: track.artist_address || '',
                      started: Date.now(), car: carCtx.likelyCar };
  }

  // Audio playback
  if (track.url) {
    if (_musicAudio) { _musicAudio.pause(); _musicAudio = null; }
    _musicAudio = new Audio(track.url);
    _musicAudio.play().catch(() => {});
    _musicAudio.addEventListener('ended', _playNext);
    _musicAudio.addEventListener('timeupdate', () => {
      const progressEl = document.getElementById('npProgress');
      if (progressEl && _musicAudio && _musicAudio.duration) {
        progressEl.style.width = (_musicAudio.currentTime / _musicAudio.duration * 100).toFixed(1) + '%';
      }
    });
  }

  // Update UI
  const np = document.getElementById('nowPlaying');
  if (np) {
    np.style.display = '';
    const npTitle = document.getElementById('npTitle');
    if (npTitle) npTitle.textContent = track.title || '—';
    const npArtist = document.getElementById('npArtist');
    if (npArtist) {
      npArtist.textContent = track.artist || '';
      if (track.artist_address) {
        npArtist.onclick = () => _showArtistProfile(track.artist_address, track.artist || '');
        npArtist.style.textDecoration = 'underline';
      }
    }
    const badge = document.getElementById('carPlayBadge');
    if (badge) badge.style.display = carCtx.likelyCar ? '' : 'none';

    // Wire play/pause button
    const ppBtn = document.getElementById('playPauseBtn');
    if (ppBtn) {
      ppBtn.textContent = '⏸ Pause';
      ppBtn.onclick = () => {
        if (!_musicAudio) return;
        if (_musicAudio.paused) {
          _musicAudio.play().catch(() => {});
          ppBtn.textContent = '⏸ Pause';
        } else {
          _musicAudio.pause();
          ppBtn.textContent = '▶ Resume';
        }
      };
    }

    // Wire prev/next buttons
    const prevBtn = document.getElementById('prevBtn');
    if (prevBtn) prevBtn.onclick = _playPrev;
    const nextBtn = document.getElementById('nextBtn');
    if (nextBtn) nextBtn.onclick = _playNext;

    // Refresh track list rows to show active state
    document.querySelectorAll('.music-track-row').forEach(row => {
      const isActive = row.dataset.tid === (track.id || '');
      row.querySelector('.tx-item__dir').textContent = isActive ? '🎵' : '▶';
      row.querySelector('.tx-item__dir').style.background = isActive ? '#3a1080' : '#1a1040';
      row.querySelector('.tx-item__dir').style.color      = isActive ? '#fff'    : '#b08cf8';
      row.querySelector('.tx-item__label').style.color    = isActive ? '#b08cf8' : '';
      row.querySelector('.tx-item__amount').textContent   = isActive ? '▶ Playing' : '+T2E';
      row.style.border = isActive ? '1px solid #7c5cbf' : '';
    });
  }

  // Session timer — also send GPS route snapshot every 60s
  let gpsInterval = null;
  const tick = setInterval(async () => {
    const timerEl = document.getElementById('sessionTimer');
    if (!timerEl || !_musicSession) { clearInterval(tick); if (gpsInterval) clearInterval(gpsInterval); return; }
    const sec = Math.floor((Date.now() - _musicSession.started) / 1000);
    timerEl.textContent = `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2,'0')}`;
  }, 1000);

  // GPS route telemetry — batch-send every 60s if car context
  if (carCtx.likelyCar) {
    gpsInterval = setInterval(async () => {
      if (!_musicSession || !_gpsPoints.length) return;
      const routeHash = await _hashRoute(_gpsPoints);
      fetch(`${API_WRITE}/api/music/telemetry/route`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          address, session_id: _musicSession.session_id,
          route_hash: routeHash, point_count: _gpsPoints.length,
          platform: carCtx.isIOS ? 'carplay' : 'android_auto'
        })
      }).catch(() => {});
    }, 60000);
    _musicSession._gpsInterval = gpsInterval;
  }
}

function _playPrev() {
  if (!_trackQueue.length) return;
  _trackQueueIdx = (_trackQueueIdx - 1 + _trackQueue.length) % _trackQueue.length;
  _playTrack(_trackQueue[_trackQueueIdx]);
}
function _playNext() {
  if (!_trackQueue.length) return;
  _trackQueueIdx = (_trackQueueIdx + 1) % _trackQueue.length;
  _playTrack(_trackQueue[_trackQueueIdx]);
}

async function _showArtistProfile(artistAddr, artistName) {
  try {
    const r = await fetch(`${API_WRITE}/api/v1/music/artist/${encodeURIComponent(artistAddr)}`);
    const d = r.ok ? await r.json() : {};

    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:#000000aa;z-index:999;display:flex;align-items:flex-end;justify-content:center;';
    overlay.innerHTML = `
      <div style="background:#13112a;border-radius:16px 16px 0 0;width:100%;max-width:480px;padding:20px 20px 32px;max-height:70vh;overflow-y:auto">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
          <div>
            <div style="font-size:1.1rem;font-weight:700;color:#fff">${escHtml(d.name || artistName || 'Artist')}</div>
            <div style="font-size:.75rem;color:var(--muted);font-family:monospace">${escHtml(artistAddr.slice(0,18))}…</div>
          </div>
          <button id="apClose" style="background:none;border:none;color:var(--muted);font-size:1.4rem;cursor:pointer">✕</button>
        </div>
        ${d.bio ? `<p style="font-size:.82rem;color:var(--muted);margin-bottom:14px">${escHtml(d.bio)}</p>` : ''}
        <div style="font-size:.72rem;color:var(--accent);text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">Tracks</div>
        ${(d.tracks || []).slice(0,10).map(_renderTrackRow).join('') || '<p style="color:var(--muted);font-size:.82rem">No tracks</p>'}
        <button class="btn btn--primary mt8" id="apTip" style="width:100%;padding:12px;margin-top:14px">💰 Send Tip</button>
      </div>`;
    document.body.appendChild(overlay);
    overlay.querySelector('#apClose').addEventListener('click', () => overlay.remove());
    overlay.querySelector('#apTip').addEventListener('click', () => {
      if (!_musicSession) _musicSession = { artist_address: artistAddr };
      else _musicSession.artist_address = artistAddr;
      overlay.remove();
      _showTipModal();
    });
    overlay.querySelectorAll('.music-track-row').forEach(row => {
      row.addEventListener('click', () => {
        overlay.remove();
        _playTrack({ id: row.dataset.tid, title: row.dataset.title,
                     artist: row.dataset.artist, artist_address: row.dataset.artistAddr,
                     url: row.dataset.url });
      });
    });
  } catch {
    alert('Could not load artist profile');
  }
}

async function _stopMusic() {
  if (_musicAudio) { _musicAudio.pause(); _musicAudio = null; }
  _stopGpsTracking();
  if (_musicSession?._gpsInterval) clearInterval(_musicSession._gpsInterval);

  // Send final GPS route snapshot
  if (_musicSession?.car && _gpsPoints.length) {
    const address = getActiveAddr();
    const routeHash = await _hashRoute(_gpsPoints).catch(() => '');
    if (routeHash) {
      fetch(`${API_WRITE}/api/music/telemetry/route`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          address, session_id: _musicSession.session_id,
          route_hash: routeHash, point_count: _gpsPoints.length,
          final: true
        })
      }).catch(() => {});
    }
    _gpsPoints = [];
  }

  if (_musicSession?.session_id) {
    try {
      await fetch(`${API_WRITE}/api/music/session/end`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: _musicSession.session_id, reason: 'stop', tip_amount: 0 })
      });
    } catch {}
  }
  _musicSession = null;

  const np = document.getElementById('nowPlaying');
  if (np) np.style.display = 'none';

  if ('mediaSession' in navigator) {
    navigator.mediaSession.setActionHandler('stop',          null);
    navigator.mediaSession.setActionHandler('pause',         null);
    navigator.mediaSession.setActionHandler('previoustrack', null);
    navigator.mediaSession.setActionHandler('nexttrack',     null);
  }
}

function showSend(preselectedToken = null, prefillAddr = null) {
  const address = getActiveAddr();

  const NETWORKS_DEF = [
    { id: 'thronos', label: '🔗 THR',  placeholder: 'THR…',       addrKey: null },
    { id: 'bitcoin', label: '₿ BTC',   placeholder: 'bc1… or 1…', addrKey: 'btc' },
    { id: 'ethereum',label: 'Ξ ETH',   placeholder: '0x…',        addrKey: 'evm' },
    { id: 'bnb',     label: '🔶 BNB',  placeholder: '0x…',        addrKey: 'evm' },
    { id: 'arbitrum',label: '🔵 ARB',  placeholder: '0x…',        addrKey: 'evm' },
    { id: 'base',    label: '⬛ Base', placeholder: '0x…',        addrKey: 'evm' },
  ];

  render(`
    <div class="screen">
      <div class="header">
        <button class="btn--icon" id="backBtn">←</button>
        <span class="header__title">Send</span>
        <span style="width:36px"></span>
      </div>
      <div class="card mt16">
        <!-- Network selector -->
        <label style="color:var(--muted);font-size:.82rem;margin-bottom:6px;display:block">Network</label>
        <div style="display:flex;gap:0;overflow-x:auto;border:1px solid #2a2050;border-radius:8px;margin-bottom:12px" id="netTabs">
          ${NETWORKS_DEF.map((n,i) => `<button class="send-net-tab${i===0?' active':''}" data-net="${n.id}" style="flex:1;min-width:56px;padding:8px 6px;background:${i===0?'#1a1040':'transparent'};border:none;color:${i===0?'#b08cf8':'var(--muted)'};font-size:.75rem;cursor:pointer;white-space:nowrap;border-right:1px solid #2a2050">${n.label}</button>`).join('')}
        </div>
        <!-- Deposit address for current network -->
        <div id="depositAddrRow" style="display:none;background:#12122a;border:1px solid #2a2050;border-radius:8px;padding:8px 10px;margin-bottom:10px;font-size:.75rem">
          <div style="color:var(--muted);font-size:.7rem;text-transform:uppercase;letter-spacing:1px;margin-bottom:3px">Your address on this network</div>
          <div id="depositAddrVal" style="font-family:monospace;color:#b08cf8;word-break:break-all"></div>
        </div>
        <!-- Token -->
        <label style="color:var(--muted);font-size:.82rem">Token</label>
        <select id="tokenSel" class="input" style="cursor:pointer">
          <option value="THR">THR — Thronos</option>
          ${preselectedToken && preselectedToken !== 'THR' ? `<option value="${escHtml(preselectedToken)}" selected>${escHtml(preselectedToken)}</option>` : ''}
        </select>
        <!-- Recipient -->
        <label style="color:var(--muted);font-size:.82rem">Recipient address</label>
        <div style="display:flex;gap:8px;align-items:center;margin-bottom:4px">
          <input type="text" id="toAddr" class="input" placeholder="THR…" value="${escHtml(prefillAddr||'')}" autocomplete="off" autocorrect="off" spellcheck="false" style="flex:1;margin-bottom:0">
          <button id="scanAddrBtn" class="btn btn--ghost" style="padding:10px 12px;font-size:1.1rem" title="Scan QR">📷</button>
        </div>
        <!-- Amount -->
        <label style="color:var(--muted);font-size:.82rem">Amount</label>
        <input type="number" id="amount" class="input" placeholder="0.00" min="0.000001" step="any" inputmode="decimal">
        <!-- Speed -->
        <div style="display:flex;gap:8px;margin-top:8px" id="speedRow">
          <button class="btn btn--ghost speed-btn active" data-speed="fast" style="flex:1;padding:8px;font-size:.8rem;border:1px solid #7c5cbf;background:#1a1040">⚡ Fast <span style="color:var(--muted);font-size:.72rem">0.5%</span></button>
          <button class="btn btn--ghost speed-btn" data-speed="slow" style="flex:1;padding:8px;font-size:.8rem">🐢 Slow <span style="color:var(--muted);font-size:.72rem">0.09%</span></button>
        </div>
        <button class="btn btn--primary mt8" id="sendBtn">Send</button>
        <div id="err" class="banner banner--error hidden"></div>
        <div id="ok" class="banner banner--success hidden"></div>
      </div>
    </div>
  `);

  let selectedNetwork = 'thronos';
  let selectedSpeed = 'fast';
  let cachedEvmAddr = null;
  const { privHex } = unlocked.get(address) || {};

  // Pre-derive EVM address in background
  if (privHex) {
    _deriveEvmAddress(privHex).then(a => { cachedEvmAddr = a; }).catch(() => {});
  }

  let btcAddr = '';
  if (privHex) {
    _fetchBtcAddress(privHex, address).then(a => {
      btcAddr = a;
      if (selectedNetwork === 'bitcoin') {
        const depVal = document.getElementById('depositAddrVal');
        if (depVal) depVal.textContent = getDepositAddr('bitcoin');
      }
    }).catch(() => {});
  }

  const getDepositAddr = (netId) => {
    if (netId === 'bitcoin') return btcAddr || '(unlock wallet to see)';
    if (['ethereum','bnb','arbitrum','base'].includes(netId)) return cachedEvmAddr || '(unlock wallet to see)';
    return address;
  };

  const switchNet = (netId) => {
    selectedNetwork = netId;
    const def = NETWORKS_DEF.find(n => n.id === netId);
    document.querySelectorAll('.send-net-tab').forEach(b => {
      const isActive = b.dataset.net === netId;
      b.style.background = isActive ? '#1a1040' : 'transparent';
      b.style.color = isActive ? '#b08cf8' : 'var(--muted)';
    });
    const toEl = document.getElementById('toAddr');
    if (toEl) toEl.placeholder = def?.placeholder || '…';
    // Show deposit address for non-Thronos networks
    const depRow = document.getElementById('depositAddrRow');
    const depVal = document.getElementById('depositAddrVal');
    const speedRow = document.getElementById('speedRow');
    if (netId !== 'thronos') {
      if (depRow) depRow.style.display = '';
      if (depVal) depVal.textContent = getDepositAddr(netId);
      if (speedRow) speedRow.style.display = 'none';
    } else {
      if (depRow) depRow.style.display = 'none';
      if (speedRow) speedRow.style.display = '';
    }
    // Update token selector
    const sel = document.getElementById('tokenSel');
    if (sel) {
      const tokensByNet = {
        thronos:  ['THR','WBTC','L2E','T2E','JAM'],
        bitcoin:  ['BTC'],
        ethereum: ['ETH','USDT','USDC','WBTC'],
        bnb:      ['BNB','USDT','USDC','BUSD'],
        arbitrum: ['ETH','USDT','USDC','ARB'],
        base:     ['ETH','USDC','USDT'],
      };
      const tokens = tokensByNet[netId] || ['THR'];
      sel.innerHTML = tokens.map(t => `<option value="${t}"${t === (preselectedToken||tokens[0])?' selected':''}>${t}</option>`).join('');
    }
  };

  document.querySelectorAll('.send-net-tab').forEach(b => {
    b.addEventListener('click', () => switchNet(b.dataset.net));
  });

  document.querySelectorAll('.speed-btn').forEach(b => {
    b.addEventListener('click', () => {
      selectedSpeed = b.dataset.speed;
      document.querySelectorAll('.speed-btn').forEach(x => {
        x.style.background = x.dataset.speed === selectedSpeed ? '#1a1040' : 'transparent';
        x.style.borderColor = x.dataset.speed === selectedSpeed ? '#7c5cbf' : 'var(--border)';
      });
    });
  });

  document.getElementById('backBtn').addEventListener('click', showWallet);
  document.getElementById('scanAddrBtn').addEventListener('click', () => {
    _openQrScannerForAddress(addr => { const el = document.getElementById('toAddr'); if (el) el.value = addr; });
  });

  // Populate token selector from live balances (Thronos only)
  fetchBalances(address).then(data => {
    if (selectedNetwork !== 'thronos') return;
    const tokens = Array.isArray(data?.tokens) ? data.tokens.filter(t => Number(t.balance) > 0) : [];
    const sel = document.getElementById('tokenSel');
    if (!sel || !tokens.length) return;
    sel.innerHTML = tokens.map(t =>
      `<option value="${escHtml(t.symbol)}" ${t.symbol === (preselectedToken||'THR') ? 'selected' : ''}>${escHtml(t.symbol)} — ${escHtml(t.name||t.symbol)}</option>`
    ).join('');
  }).catch(() => {});

  document.getElementById('sendBtn').addEventListener('click', async () => {
    const to = document.getElementById('toAddr').value.trim();
    const amount = parseFloat(document.getElementById('amount').value);
    const token = document.getElementById('tokenSel').value;

    if (!to) { setError('Enter a recipient address'); return; }
    if (!amount || amount <= 0) { setError('Enter a valid amount'); return; }

    // Non-Thronos sends: route to bridge screen for now
    if (selectedNetwork !== 'thronos') {
      showBridge(token, 'WBTC');
      return;
    }

    const btn = document.getElementById('sendBtn');
    btn.disabled = true; btn.textContent = 'Sending…'; setError(null);
    try {
      if (!privHex) throw new Error('Wallet is locked — please unlock first');
      const result = await sendToken(address, to.toUpperCase(), amount, token, privHex);
      setSuccess(`Sent! TX: ${result.tx_hash || result.txid || result.tx || 'submitted'}`);
      btn.textContent = 'Sent ✓';
      setTimeout(showWallet, 3000);
    } catch (err) {
      btn.disabled = false; btn.textContent = 'Send';
      setError(err.message || 'Transaction failed');
    }
  });
}


// ─── Receive screen ───────────────────────────────────────────────────────────

function showReceive() {
  const address = getActiveAddr();
  const qr = `https://api.qrserver.com/v1/create-qr-code/?data=${encodeURIComponent(address)}&size=180x180&color=ffffff&bgcolor=0a0a0f&margin=8`;

  render(`
    <div class="screen">
      <div class="header">
        <button class="btn--icon" id="backBtn">←</button>
        <span class="header__title">Receive THR</span>
        <span style="width:36px"></span>
      </div>
      <div class="card mt16" style="align-items:center;gap:20px">
        <div class="qr-wrapper"><img src="${qr}" alt="QR" loading="lazy"></div>
        <p class="address-full">${address}</p>
        <button class="btn btn--primary" id="copyBtn">Copy Address</button>
        <div id="ok" class="banner banner--success hidden" style="width:100%;text-align:center"></div>
      </div>
    </div>
  `);

  document.getElementById('backBtn').addEventListener('click', showWallet);
  document.getElementById('copyBtn').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(address); } catch {}
    setSuccess('Address copied!');
    const btn = document.getElementById('copyBtn');
    if (btn) { btn.textContent = 'Copied!'; setTimeout(() => { if (btn) btn.textContent = 'Copy Address'; }, 2000); }
  });
}

// ─── Swap ─────────────────────────────────────────────────────────────────────

async function showSwap(preselectedIn = null) {
  const address = getActiveAddr();
  if (!address || !unlocked.has(address)) { showUnlock(); return; }

  // Fetch tokens and pools for the selector
  let tokens = ['THR', 'WBTC', 'L2E', 'USDT'];
  try {
    const [pr, tr] = await Promise.all([
      fetch(`${API_BASE}/api/v1/pools`).then(r => r.json()).catch(() => ({})),
      fetch(`${API_BASE}/api/v1/tokens`).then(r => r.json()).catch(() => ({})),
    ]);
    const poolSyms = new Set();
    (pr.pools || []).forEach(p => {
      if (p.token_a) poolSyms.add(p.token_a.toUpperCase());
      if (p.token_b) poolSyms.add(p.token_b.toUpperCase());
    });
    (tr.tokens || []).forEach(t => poolSyms.add((t.symbol || '').toUpperCase()));
    if (poolSyms.size) tokens = [...poolSyms].filter(s => s);
  } catch {}

  const makeOptions = (selected) => tokens.map(t => `<option value="${t}" ${t === selected ? 'selected' : ''}>${t}</option>`).join('');

  render(`
    <div class="screen">
      <div class="header">
        <button class="btn--icon" id="backBtn">←</button>
        <span style="font-weight:700;color:#fff">🔄 Swap</span>
        <span></span>
      </div>
      <div class="card" style="padding:16px;margin-top:10px">
        <label style="font-size:.82rem;color:var(--muted)">From</label>
        <div style="display:flex;gap:8px;margin-bottom:12px">
          <select id="tokenIn" class="input" style="flex:1">${makeOptions(preselectedIn || 'THR')}</select>
          <input type="number" id="amountIn" class="input" style="flex:2" placeholder="0.00" min="0.000001" step="0.000001" inputmode="decimal">
        </div>
        <div style="text-align:center;margin:4px 0">
          <button id="swapDir" style="background:none;border:none;color:var(--accent);font-size:1.4rem;cursor:pointer">⇅</button>
        </div>
        <label style="font-size:.82rem;color:var(--muted)">To</label>
        <select id="tokenOut" class="input" style="margin-bottom:12px">${makeOptions('WBTC')}</select>

        <div id="quoteBox" style="background:#0d0a1a;border-radius:8px;padding:10px;margin-bottom:12px;min-height:48px;display:flex;align-items:center;justify-content:center">
          <span style="color:var(--muted);font-size:.85rem">Enter amount to see quote</span>
        </div>

        <button class="btn btn--primary" id="getQuoteBtn" style="width:100%;margin-bottom:8px">Get Quote</button>
        <button class="btn btn--primary" id="swapExecBtn" style="width:100%;display:none;background:#00c853">Swap Now</button>
        <div id="swapErr" style="color:#ff6b6b;font-size:.82rem;margin-top:8px;display:none"></div>
        <div id="swapOk" style="color:#00ff66;font-size:.82rem;margin-top:8px;display:none"></div>
      </div>
      <div class="card" style="padding:12px;margin-top:10px;opacity:.7;text-align:center;font-size:.82rem;color:var(--muted)">
        🌉 Cross-chain THR/USDT via Binance — <em>coming soon</em>
      </div>
    </div>
  `);

  document.getElementById('backBtn').addEventListener('click', showWallet);

  let lastQuote = null;

  const setSwapErr = (msg) => {
    const e = document.getElementById('swapErr');
    if (e) { e.textContent = msg || ''; e.style.display = msg ? '' : 'none'; }
  };
  const setSwapOk = (msg) => {
    const e = document.getElementById('swapOk');
    if (e) { e.textContent = msg || ''; e.style.display = msg ? '' : 'none'; }
  };

  document.getElementById('swapDir').addEventListener('click', () => {
    const ti = document.getElementById('tokenIn');
    const to = document.getElementById('tokenOut');
    const tmp = ti.value; ti.value = to.value; to.value = tmp;
    document.getElementById('swapExecBtn').style.display = 'none';
    lastQuote = null;
  });

  document.getElementById('getQuoteBtn').addEventListener('click', async () => {
    const tokenIn = document.getElementById('tokenIn').value;
    const tokenOut = document.getElementById('tokenOut').value;
    const amtIn = parseFloat(document.getElementById('amountIn').value);
    const qb = document.getElementById('quoteBox');
    setSwapErr(null);
    document.getElementById('swapExecBtn').style.display = 'none';
    lastQuote = null;

    if (!amtIn || amtIn <= 0) { setSwapErr('Enter a valid amount'); return; }
    if (tokenIn === tokenOut) { setSwapErr('Select different tokens'); return; }

    qb.innerHTML = '<span style="color:var(--muted)">Getting quote…</span>';
    try {
      const r = await fetch(`${API_BASE}/api/swap/quote?token_in=${encodeURIComponent(tokenIn)}&token_out=${encodeURIComponent(tokenOut)}&amount_in=${encodeURIComponent(amtIn)}`);
      const d = await r.json();
      if (!r.ok || d.status !== 'success') {
        qb.innerHTML = '<span style="color:#ff6b6b">No route found</span>';
        return;
      }
      lastQuote = d;
      const impact = d.price_impact ? ` (${(d.price_impact * 100).toFixed(2)}% impact)` : '';
      qb.innerHTML = `
        <div style="text-align:center">
          <div style="color:#00ff66;font-size:1.1rem;font-weight:700">${Number(d.amount_out).toLocaleString(undefined, {maximumFractionDigits:8})} ${tokenOut}</div>
          <div style="color:var(--muted);font-size:.78rem">fee: ${d.fee || '~'} ${tokenIn}${impact}</div>
          <div style="color:var(--muted);font-size:.75rem">Rate: 1 ${tokenIn} ≈ ${(d.amount_out / amtIn).toFixed(6)} ${tokenOut}</div>
        </div>`;
      document.getElementById('swapExecBtn').style.display = '';
    } catch {
      qb.innerHTML = '<span style="color:#ff6b6b">Quote failed</span>';
    }
  });

  document.getElementById('swapExecBtn').addEventListener('click', async () => {
    if (!lastQuote) { setSwapErr('Get a quote first'); return; }
    const { privHex } = unlocked.get(address) || {};
    if (!privHex) { setSwapErr('Wallet locked'); return; }
    const tokenIn = document.getElementById('tokenIn').value;
    const tokenOut = document.getElementById('tokenOut').value;
    const amtIn = parseFloat(document.getElementById('amountIn').value);
    const minOut = lastQuote.amount_out * 0.97; // 3% slippage tolerance

    const btn = document.getElementById('swapExecBtn');
    btn.disabled = true; btn.textContent = 'Swapping…';
    setSwapErr(null); setSwapOk(null);

    try {
      const r = await fetch(`${API_WRITE}/api/wallet/v1/swap`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ from: address, token_in: tokenIn, token_out: tokenOut, amount_in: amtIn, min_amount_out: minOut, private_key_hex: privHex })
      });
      const d = await r.json().catch(() => ({}));
      if (r.ok && d.status === 'success') {
        setSwapOk(`✅ Swapped! Received ${Number(d.amount_out).toLocaleString(undefined, {maximumFractionDigits:8})} ${tokenOut}`);
        btn.textContent = 'Swap Now';
        btn.disabled = false;
        lastQuote = null;
        document.getElementById('quoteBox').innerHTML = '<span style="color:var(--muted)">Enter amount to see quote</span>';
      } else {
        throw new Error(d.message || d.error || 'swap_failed');
      }
    } catch (e) {
      setSwapErr(e.message || 'Swap failed');
      btn.disabled = false; btn.textContent = 'Swap Now';
    }
  });
}

// ─── Pools ────────────────────────────────────────────────────────────────────

const HISTORY_FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'thr_transfer', label: 'THR' },
  { key: 'token_transfer', label: 'Tokens' },
  { key: 'swap', label: 'Swaps' },
  { key: 'liquidity', label: '💧 Liquidity' },
  { key: 'evm_sends', label: '📤 EVM Sends' },
  { key: 'mining_reward', label: 'Mining' },
  { key: 'pledge', label: 'Pledges' },
  { key: 'crosschain', label: 'Cross-Chain' },
  { key: 'rpc-crosschain', label: 'RPC / Cross-chain' },
  { key: 'bridge', label: 'Bridge' },
  { key: 'mint', label: 'Mint' },
  { key: 'burn', label: 'Burn' },
];

// Event types that belong to "pledge" filter category
const _PLEDGE_EVENT_TYPES = new Set([
  'pledge', 'pledge_usdt_bnb_confirmed',
]);

// Event types that belong to "liquidity" filter category
const _LIQUIDITY_FILTER_TYPES = new Set([
  'pool_deposit',
  'pool_external_deposit_detected',
  'pool_withdraw_intent',
  'pool_withdraw',
  'pool_out',
  'pool_seed',
  'pool_add_liquidity',
  'pool_add_liquidity_lp_minted',
]);

// Event types that belong to "crosschain" filter category
const _CROSSCHAIN_FILTER_TYPES = new Set([
  'pool_add_liquidity_intent_created',
  'pool_add_liquidity_external_tx_confirmed',
  'crosschain_deposit_detected',
  'crosschain_transfer_received',
  'crosschain_transfer_sent',
  'crosschain_withdraw',
  'bridge_deposit_detected',
  'bridge',
]);

// Map from app network ID to chain IDs stored in wallet history events
const HISTORY_CHAIN_MAP = {
  thronos: ['thronos'],
  bnb:     ['bsc'],
  arbitrum:['arbitrum'],
  base:    ['base'],
  ethereum:['eth'],
  bitcoin: ['btc'],
};

// Explorer base URLs for history events (no RPC, display only)
const EXPLORER_BASES = {
  thronos:  { tx: 'https://api.thronoschain.org/viewer?tx={txid}', label: 'Thronos' },
  bsc:      { tx: 'https://bscscan.com/tx/{txid}',  label: 'BscScan' },
  arbitrum: { tx: 'https://arbiscan.io/tx/{txid}',  label: 'Arbiscan' },
  base:     { tx: 'https://basescan.org/tx/{txid}', label: 'BaseScan' },
  eth:      { tx: 'https://etherscan.io/tx/{txid}', label: 'Etherscan' },
  btc:      { tx: 'https://blockstream.info/tx/{txid}', label: 'Blockstream' },
};

function _parseTxDate(ts) {
  if (ts === undefined || ts === null || ts === '') return null;
  if (typeof ts === 'number') return new Date(ts > 1e12 ? ts : ts * 1000);
  const s = String(ts).trim();
  if (/^\d+$/.test(s)) {
    const n = Number(s);
    return new Date(n > 1e12 ? n : n * 1000);
  }
  const d = new Date(s.replace(' UTC', 'Z').replace(' ', 'T'));
  if (!isNaN(d.getTime())) return d;
  const d2 = new Date(s);
  return isNaN(d2.getTime()) ? null : d2;
}

const _EVENT_TYPE_LABELS = {
  pool_add_liquidity_intent_created:        '💧 LP intent created',
  pool_add_liquidity_external_tx_confirmed: '✅ External deposit confirmed',
  pool_add_liquidity_lp_minted:             '🌱 LP shares minted',
  pledge_usdt_bnb_confirmed:                '💵 USDT pledge confirmed',
  crosschain_deposit_detected:              '📥 Cross-chain deposit',
  crosschain_transfer_received:             '📥 Cross-chain transfer received',
  crosschain_transfer_sent:                 '📤 Cross-chain transfer sent',
  bridge_deposit_detected:                  '⚡ Bridge deposit',
  pool_deposit:                             '💧 Pool In · THR',
  pool_external_deposit_detected:           '🌉 External Pool Deposit',
  pool_withdraw_intent:                     '⏳ Withdrawal Intent',
  pool_out:                                 '↩ Pool Out',
  pool_seed:                                '💧 Pool seeded',
  pool_withdraw:                            '↩ Pool Out',
  pool_add_liquidity:                       '💧 Add liquidity',
  external_withdrawal_request:              '📤 External Withdrawal',
  crosschain_withdrawal_request:            '📤 External Withdrawal',
  pledge:                                   '🔒 Pledge',
  token_receive:                            '📥 Received',
  token_send:                               '📤 Sent',
  crosschain_withdraw:                      '🔄 Cross-chain withdrawal',
  gateway_payout:                           '💰 Gateway payout',
  bridge:                                   '⚡ Bridge',
};

function _renderHistoryRow(tx) {
  const kind = tx.event_type || tx.kind || tx.type || tx.category || 'transfer';
  const label = tx.category_label || _EVENT_TYPE_LABELS[kind] || kind.replace(/_/g, ' ');
  const direction = tx.direction || (kind === 'swap' ? 'swap' : 'out');
  const symbol = (tx.asset_symbol || tx.symbol || 'THR').toUpperCase();
  const amount = tx.display_amount !== undefined ? tx.display_amount : (tx.amount_in !== undefined ? tx.amount_in : tx.amount);
  const date = _parseTxDate(tx.timestamp);
  const dateStr = date ? date.toLocaleString() : (tx.timestamp || '—');
  const status = tx.status || (tx.reject_reason ? 'failed' : 'confirmed');
  const statusColor = status === 'failed' || status === 'rejected' ? '#ff6b6b' : (status === 'pending' ? '#ffb347' : '#00ff66');

  let amountHtml;
  if (kind === 'swap' && tx.amount_out !== undefined) {
    const symOut = (tx.symbol_out || '').toUpperCase();
    amountHtml = `<span style="color:#ff6b6b">-${Number(amount || 0).toLocaleString(undefined,{maximumFractionDigits:6})} ${symbol}</span>
      <span style="color:var(--muted)"> → </span>
      <span style="color:#00ff66">+${Number(tx.amount_out).toLocaleString(undefined,{maximumFractionDigits:6})} ${symOut}</span>`;
  } else if (kind === 'liquidity' && Array.isArray(tx.amounts)) {
    amountHtml = tx.amounts.map(a => `<span style="color:#fff">${Number(a.amount || a).toLocaleString(undefined,{maximumFractionDigits:6})} ${(a.symbol || '').toUpperCase()}</span>`).join(' / ');
  } else {
    const sign = direction === 'in' ? '+' : (direction === 'out' ? '-' : '');
    const color = direction === 'in' ? '#00ff66' : (direction === 'out' ? '#ff6b6b' : '#fff');
    amountHtml = `<span style="color:${color}">${sign}${Number(amount || 0).toLocaleString(undefined,{maximumFractionDigits:6})} ${symbol}</span>`;
  }

  const feeHtml = tx.fee_burned ? `<div style="font-size:.72rem;color:var(--muted)">Fee: ${Number(tx.fee_burned).toLocaleString(undefined,{maximumFractionDigits:6})} THR</div>` : '';
  const noteHtml = tx.note ? `<div style="font-size:.72rem;color:var(--muted);margin-top:2px">${tx.note}</div>` : '';
  const networkLabel = tx.network_label || (tx.chain ? tx.chain.toUpperCase() : '');
  const netBadge = networkLabel ? `<span style="font-size:.68rem;color:var(--muted);margin-top:1px">${networkLabel}</span>` : '';

  // Build explorer links from event fields
  const links = [];
  const chain = tx.chain || '';
  const expBase = EXPLORER_BASES[chain];

  // Internal Thronos viewer link — always available if we have an internal txid
  if (tx.internal_txid) {
    const thrUrl = `https://api.thronoschain.org/viewer?tx=${encodeURIComponent(tx.internal_txid)}`;
    links.push(`<a href="${thrUrl}" target="_blank" rel="noopener" style="font-size:.68rem;color:#b08cf8;text-decoration:none">Thronos ↗</a>`);
  }

  // External chain explorer link
  if (tx.external_txid && expBase) {
    const url = expBase.tx.replace('{txid}', tx.external_txid);
    links.push(`<a href="${url}" target="_blank" rel="noopener" style="font-size:.68rem;color:#b08cf8;text-decoration:none">${expBase.label} ↗</a>`);
  } else if (tx.explorer_url) {
    links.push(`<a href="${tx.explorer_url}" target="_blank" rel="noopener" style="font-size:.68rem;color:#b08cf8;text-decoration:none">Explorer ↗</a>`);
  } else if (tx.explorer_link) {
    links.push(`<a href="${tx.explorer_link}" target="_blank" rel="noopener" style="font-size:.68rem;color:#b08cf8;text-decoration:none">View ↗</a>`);
  }
  const linkHtml = links.length ? `<div style="display:flex;gap:6px">${links.join('')}</div>` : '';

  return `<div class="card" style="padding:10px 12px;margin-bottom:8px">
    <div style="display:flex;justify-content:space-between;align-items:flex-start">
      <div>
        <div style="font-size:.85rem;font-weight:700;color:#fff;text-transform:capitalize">${label}</div>
        <div style="font-size:.72rem;color:var(--muted)">${dateStr}</div>
        ${netBadge}
      </div>
      <div style="text-align:right;font-size:.85rem;font-weight:700">${amountHtml}</div>
    </div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:6px">
      <div>${feeHtml}${noteHtml}</div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;justify-content:flex-end">
        <span style="font-size:.7rem;color:${statusColor};text-transform:capitalize">${status}</span>
        ${linkHtml}
      </div>
    </div>
  </div>`;
}

async function showHistory(address) {
  address = address || getActiveAddr();
  if (!address || !unlocked.has(address)) { showUnlock(); return; }

  // Restore active network from persisted selection
  const savedNet = LS.get(`thr_network_${address}`) || 'thronos';

  render(`
    <div class="screen">
      <div class="header">
        <button class="btn--icon" id="backBtn">←</button>
        <span style="font-weight:700;color:#fff">📋 Transaction History</span>
        <span></span>
      </div>
      <div style="display:flex;align-items:center;gap:8px;padding:8px 0">
        <span style="font-size:.7rem;text-transform:uppercase;letter-spacing:1px;color:var(--muted)">Network</span>
        <select id="histNetSel" class="input" style="flex:1;margin:0;padding:5px 8px;font-size:.8rem;width:auto;background:#0d0a1a;border:1px solid #2a2050;color:#b08cf8">
          ${HOME_NETWORKS.map(n => `<option value="${n.id}" ${n.id === savedNet ? 'selected' : ''}>${n.icon} ${n.label}</option>`).join('')}
        </select>
      </div>
      <div id="historyFilters" style="display:flex;gap:6px;overflow-x:auto;padding:4px 0 8px;white-space:nowrap"></div>
      <div id="historyBody" style="margin-top:4px">
        <p style="color:var(--muted);text-align:center;padding:20px">Loading history…</p>
      </div>
    </div>
  `);

  document.getElementById('backBtn').addEventListener('click', showWallet);

  let allTx = [];
  let activeFilter = 'all';
  let activeNetwork = savedNet;

  function renderFilters() {
    const el = document.getElementById('historyFilters');
    if (!el) return;
    el.innerHTML = HISTORY_FILTERS.map(f => `
      <button class="btn ${f.key === activeFilter ? 'btn--primary' : 'btn--ghost'}" data-filter="${f.key}" style="padding:5px 10px;font-size:.73rem;flex-shrink:0">${f.label}</button>
    `).join('');
    el.querySelectorAll('button[data-filter]').forEach(btn => {
      btn.addEventListener('click', () => { activeFilter = btn.dataset.filter; renderFilters(); renderList(); });
    });
  }

  function renderList() {
    const el = document.getElementById('historyBody');
    if (!el) return;
    // Filter by active category
    let filtered = allTx;
    if (activeFilter !== 'all') {
      const et = tx => tx.event_type || tx.kind || tx.type || tx.category || '';
      if (activeFilter === 'pledge') {
        filtered = allTx.filter(tx => _PLEDGE_EVENT_TYPES.has(et(tx)));
      } else if (activeFilter === 'liquidity') {
        filtered = allTx.filter(tx =>
          _LIQUIDITY_FILTER_TYPES.has(et(tx)) ||
          (tx.domain === 'liquidity') ||
          (tx._raw_category === 'liquidity')
        );
      } else if (activeFilter === 'crosschain') {
        filtered = allTx.filter(tx => _CROSSCHAIN_FILTER_TYPES.has(et(tx)));
      } else if (activeFilter === 'rpc-crosschain') {
        filtered = allTx.filter(tx =>
          _CROSSCHAIN_FILTER_TYPES.has(et(tx)) ||
          _PLEDGE_EVENT_TYPES.has(et(tx)) ||
          (_LIQUIDITY_FILTER_TYPES.has(et(tx)) && (tx.chain || '').toLowerCase() !== 'thronos') ||
          (tx.domain === 'rpc-crosschain')
        );
      } else if (activeFilter === 'evm_sends') {
        filtered = allTx.filter(tx => {
          const typ = et(tx).toLowerCase();
          return typ === 'evm_token_send' || typ === 'evm_token_receive' || typ === 'token_send' || typ === 'token_receive';
        });
      } else {
        filtered = allTx.filter(tx => et(tx) === activeFilter);
      }
    }
    // Network filter: strict — only show events whose chain matches the selected network.
    // Exception: if chain field is empty/missing (legacy events), show on Thronos view only.
    const netChains = HISTORY_CHAIN_MAP[activeNetwork] || [];
    if (netChains.length) {
      filtered = filtered.filter(tx => {
        const c = (tx.chain || '').toLowerCase();
        if (!c) return activeNetwork === 'thronos'; // legacy events with no chain → Thronos only
        return netChains.includes(c);
      });
    }
    if (!filtered.length) {
      const netLabel = HOME_NETWORKS.find(n => n.id === activeNetwork)?.label || activeNetwork;
      el.innerHTML = `<p style="color:var(--muted);text-align:center;padding:20px">No transactions on ${netLabel}.</p>`;
      return;
    }
    const sorted = [...filtered].sort((a, b) => {
      const da = _parseTxDate(a.timestamp), db = _parseTxDate(b.timestamp);
      return (db ? db.getTime() : 0) - (da ? da.getTime() : 0);
    });
    el.innerHTML = sorted.map(_renderHistoryRow).join('');
  }

  async function loadHistory() {
    const el = document.getElementById('historyBody');
    if (el) el.innerHTML = '<p style="color:var(--muted);text-align:center;padding:20px">Loading history…</p>';
    try {
      // Load from both legacy endpoint and new v1 wallet history endpoint and merge
      const [legacyTx, v1Res] = await Promise.allSettled([
        fetchHistory(address),
        fetch(`${API_BASE}/api/wallet/history/${encodeURIComponent(address)}?limit=200`).then(r => r.json()).catch(() => null),
      ]);
      const legacy = legacyTx.status === 'fulfilled' ? (legacyTx.value || []) : [];
      const v1 = (v1Res.status === 'fulfilled' && v1Res.value?.ok) ? (v1Res.value.history || []) : [];
      // Merge: v1 events have event_type/chain/network_label; normalize kind for filter compat
      const v1Normalized = v1.map(e => ({
        ...e,
        kind: e.event_type || e.kind || 'transfer',
        category: e.event_type || e.kind,
        asset_symbol: e.asset || e.asset_symbol,
      }));
      // Deduplicate by id
      const seen = new Set();
      allTx = [];
      for (const tx of [...v1Normalized, ...legacy]) {
        const id = tx.id || tx.tx_id || tx.txid || JSON.stringify(tx).slice(0, 60);
        if (!seen.has(id)) { seen.add(id); allTx.push(tx); }
      }
      renderList();
    } catch (e) {
      const el2 = document.getElementById('historyBody');
      if (el2) el2.innerHTML = `<p style="color:#ff6b6b;text-align:center;padding:20px">Error: ${e.message}</p>`;
    }
  }

  document.getElementById('histNetSel')?.addEventListener('change', (e) => {
    activeNetwork = e.target.value;
    LS.set(`thr_network_${address}`, activeNetwork);
    renderList();
  });

  renderFilters();
  await loadHistory();
}

async function showPools() {
  const address = getActiveAddr();
  if (!address || !unlocked.has(address)) { showUnlock(); return; }

  render(`
    <div class="screen">
      <div class="header">
        <button class="btn--icon" id="backBtn">←</button>
        <span style="font-weight:700;color:#fff">💧 Liquidity Pools</span>
        <span></span>
      </div>
      <div id="poolsBody" style="margin-top:10px">
        <p style="color:var(--muted);text-align:center;padding:20px">Loading pools…</p>
      </div>
    </div>
  `);

  document.getElementById('backBtn').addEventListener('click', showWallet);

  try {
    const [pr, posr, pythiaRes, pythiaPosRes] = await Promise.all([
      fetch(`${API_BASE}/api/v1/pools`).then(r => r.json()).catch(() => ({})),
      fetch(`${API_BASE}/api/v1/pools/positions/${encodeURIComponent(address)}`).then(r => r.json()).catch(() => ({})),
      fetch(`${API_BASE}/api/pools/status`).then(r => r.json()).catch(() => ({})),
      fetch(`${API_BASE}/api/pools/positions?address=${encodeURIComponent(address)}`).then(r => r.json()).catch(() => ({})),
    ]);

    const pools = pr.pools || [];
    const positions = posr.positions || [];
    const posMap = {};
    positions.forEach(p => { posMap[p.pool_id] = p; });

    const pythiaPools    = pythiaRes.pools || [];
    const pythiaPositions = (pythiaPosRes.pool_positions || []).filter(p => (p.lp_shares || p.deposited_external || 0) > 0);

    const el = document.getElementById('poolsBody');
    if (!el) return;

    // ── Pythia AMM Pools section ────────────────────────────────────────────
    let pythiaHtml = '';
    if (pythiaPools.length) {
      pythiaHtml = `
        <div style="font-size:.75rem;text-transform:uppercase;letter-spacing:1px;color:#00c8ff;margin:10px 0 6px">⚙️ Pythia AMM Pools</div>
        <div style="background:rgba(255,165,0,0.08);border:1px solid #ffa50044;border-radius:6px;padding:8px 10px;font-size:.72rem;color:#ffa500;margin-bottom:8px">
          ⚠️ Accounting pools — no on-chain fund movement. Safety mode: accounting_only.
        </div>
        ${pythiaPools.map(p => {
          const extRes = Number(p.external_reserve || 0).toFixed(4);
          const thrRes = Number(p.thr_reserve || 0).toFixed(4);
          const tvl    = `$${Number(p.tvl_usd || 0).toFixed(2)}`;
          const myPos  = pythiaPositions.find(pp => pp.pool_id === p.pool_id);
          return `<div class="card" style="padding:12px;margin-bottom:8px;border:1px solid #00c8ff33">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
              <div style="font-size:.95rem;font-weight:700;color:#00c8ff">${p.pair}</div>
              <div style="font-size:.72rem;color:#ffa500;font-weight:600">${p.safety_mode || 'accounting_only'}</div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:5px;font-size:.75rem;color:var(--muted);margin-bottom:8px">
              <div>${p.external_asset} reserve: <span style="color:#fff">${extRes}</span></div>
              <div>THR reserve: <span style="color:#fff">${thrRes}</span></div>
              <div>TVL: <span style="color:#fff">${tvl}</span></div>
              <div>Chain: <span style="color:#fff">${p.chain}</span></div>
              <div>Worker: <span style="color:#fff">${p.worker || 'pythia_amm_worker'}</span></div>
            </div>
            ${myPos ? `<div style="background:#001a2a;border-radius:6px;padding:6px 8px;font-size:.75rem;color:#00c8ff;margin-bottom:8px">
              My position: ${Number(myPos.deposited_internal || 0).toFixed(4)} THR · ${Number(myPos.deposited_external || 0).toFixed(4)} ${p.external_asset}
            </div>` : ''}
            <div style="display:flex;gap:6px">
              <button class="btn btn--ghost" style="flex:1;padding:7px;font-size:.75rem" onclick="showPythiaDeposit('${p.pool_id}','${p.pair}','${p.external_asset}')">💧 Add</button>
              <button class="btn btn--ghost" style="flex:1;padding:7px;font-size:.75rem" onclick="showPythiaWithdrawIntent('${p.pool_id}','${p.pair}','${p.external_asset}')">📋 Intent</button>
              <button class="btn btn--ghost" style="flex:1;padding:7px;font-size:.75rem" onclick="showPythiaQuote('${p.chain}','${p.external_asset}')">📊 Quote</button>
            </div>
          </div>`;
        }).join('')}
      `;
    }

    if (!pools.length && !pythiaPools.length) {
      el.innerHTML = '<p style="color:var(--muted);text-align:center;padding:20px">No pools available yet.</p>';
      return;
    }

    // User positions summary
    let posHtml = '';
    if (positions.length) {
      posHtml = `<div class="card" style="padding:12px;margin-bottom:10px">
        <div style="font-size:.9rem;font-weight:700;color:#b08cf8;margin-bottom:8px">My Positions</div>
        ${positions.map(p => `
          <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #1a1040;font-size:.82rem">
            <span style="color:#fff">${p.token_a || '?'}/${p.token_b || '?'}</span>
            <span style="color:var(--accent)">${Number(p.share_percent || 0).toFixed(2)}% share</span>
          </div>
        `).join('')}
      </div>`;
    }

    el.innerHTML = pythiaHtml + posHtml + (pools.length ? '' : '') + pools.map(pool => {
      const a = pool.token_a || '?';
      const b = pool.token_b || '?';
      const ra = Number(pool.reserves_a || 0);
      const rb = Number(pool.reserves_b || 0);
      const apy = (pool.apy_estimate !== undefined && pool.apy_estimate !== null) ? `${Number(pool.apy_estimate).toFixed(1)}%` : 'N/A';
      const vol = pool.volume_24h ? `${Number(pool.volume_24h).toLocaleString(undefined, {maximumFractionDigits:2})} ${a}` : '—';
      const myPos = posMap[pool.id];

      return `<div class="card" style="padding:12px;margin-bottom:8px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <div style="font-size:1rem;font-weight:700;color:#fff">${a} / ${b}</div>
          <div style="font-size:.78rem;color:#00ff66;font-weight:700">APY ${apy}</div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:.78rem;color:var(--muted);margin-bottom:8px">
          <div>Reserves ${a}: <span style="color:#fff">${ra.toLocaleString(undefined,{maximumFractionDigits:4})}</span></div>
          <div>Reserves ${b}: <span style="color:#fff">${rb.toLocaleString(undefined,{maximumFractionDigits:4})}</span></div>
          <div>24h Volume: <span style="color:#fff">${vol}</span></div>
          <div>Fee: <span style="color:#fff">${pool.fee_bps ? pool.fee_bps/100 + '%' : '0.3%'}</span></div>
        </div>
        ${myPos ? `<div style="background:#1a1040;border-radius:6px;padding:6px 8px;font-size:.78rem;color:#b08cf8;margin-bottom:8px">My share: ${Number(myPos.share_percent || 0).toFixed(2)}%</div>` : ''}
        <div style="display:flex;gap:8px">
          <button class="btn btn--primary" style="flex:1;padding:8px;font-size:.8rem" onclick="showSwap('${a}')">🔄 Swap</button>
          <button class="btn btn--ghost" style="flex:1;padding:8px;font-size:.8rem" onclick="showAddLiquidity('${pool.id}','${a}','${b}')">+ Add Liquidity</button>
        </div>
      </div>`;
    }).join('');
  } catch (e) {
    const el = document.getElementById('poolsBody');
    if (el) el.innerHTML = `<p style="color:#ff6b6b;text-align:center;padding:20px">Error: ${e.message}</p>`;
  }
}

// ─── Pythia AMM PWA helpers ────────────────────────────────────────────────

async function showPythiaDeposit(poolId, pair, extAsset) {
  const address = getActiveAddr();
  if (!address) { showUnlock(); return; }
  const side  = prompt(`Side: internal (THR) or external (${extAsset})?`, 'internal');
  if (!side || !['internal','external'].includes(side.trim().toLowerCase())) return;
  const asset  = side.trim().toLowerCase() === 'internal' ? 'THR' : extAsset;
  const amount = parseFloat(prompt(`Amount of ${asset} to deposit (accounting only):`));
  if (!amount || amount <= 0) return;
  try {
    const r = await fetch(`${API_BASE}/api/pools/deposit`, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ address, pool_id: poolId, side: side.trim().toLowerCase(), asset, amount }),
    });
    const d = await r.json();
    alert(d.ok
      ? `✅ Deposit recorded\npool_event_id: ${d.pool_event_id}\nasset_origin: ${d.asset_origin_chain}\nsettlement: ${d.settlement_chain}\n\n⚠️ Accounting only.`
      : `❌ ${d.error || 'Failed'}`);
    if (d.ok) showPools();
  } catch (e) { alert(`❌ ${e.message}`); }
}

async function showPythiaWithdrawIntent(poolId, pair, extAsset) {
  const address = getActiveAddr();
  if (!address) { showUnlock(); return; }
  const side  = prompt(`Side: internal (THR) or external (${extAsset})?`, 'internal');
  if (!side || !['internal','external'].includes(side.trim().toLowerCase())) return;
  const asset  = side.trim().toLowerCase() === 'internal' ? 'THR' : extAsset;
  const amount = parseFloat(prompt(`Amount of ${asset} to withdraw intent (queued, no payout yet):`));
  if (!amount || amount <= 0) return;
  try {
    const r = await fetch(`${API_BASE}/api/pools/withdraw-intent`, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ address, pool_id: poolId, side: side.trim().toLowerCase(), asset, amount }),
    });
    const d = await r.json();
    alert(d.ok
      ? `✅ Intent queued\npool_event_id: ${d.pool_event_id}\nstatus: ${d.status}\n\n⚠️ No payout yet.`
      : `❌ ${d.error || 'Failed'}`);
    if (d.ok) showPools();
  } catch (e) { alert(`❌ ${e.message}`); }
}

async function showPythiaQuote(chain, token) {
  const amount = parseFloat(prompt(`Amount of ${token} to withdraw (quote only, no payout):`));
  if (!amount || amount <= 0) return;
  try {
    const p = new URLSearchParams({ address: getActiveAddr() || '', amount: String(amount), token, dest_chain: chain });
    const r = await fetch(`${API_BASE}/api/v1/withdrawal/quote?${p}`);
    const d = await r.json();
    const liq = d.pool_liquidity || {};
    const src = liq.liquidity_source || 'none';
    const srcLabel = src === 'pool_liquidity_ledger' ? 'Pythia AMM ledger' : src;
    alert(
      `Withdrawal Quote\n` +
      `Status: ${d.withdrawal_available ? '✅ Available' : '❌ Not available'}\n` +
      `${!d.withdrawal_available ? 'Reasons: ' + (d.disabled_reasons||[]).join(', ') + '\n' : ''}` +
      `Liquidity source: ${srcLabel}\n` +
      `Ledger reserve: ${liq.ledger_usdt_reserve ?? '—'} ${token}\n` +
      `Effective reserve: ${liq.effective_usdt_reserve ?? '—'}\n` +
      `Max drawable: ${liq.effective_max_drawable ?? '—'}\n` +
      `Amount net: ${(d.quote||{}).amount_net ?? '—'}`
    );
  } catch (e) { alert(`❌ ${e.message}`); }
}

// ─── Withdraw USDT/USDC from Thronos pool ──────────────────────────────────

async function showWithdraw(address) {
  if (!address || !unlocked.has(address)) { showUnlock(); return; }

  let poolInfo   = null;
  let chainsInfo = null;    // { chains: [{id, label, tokens}], max_withdraw_usdt }
  let sendSecret = null;    // pledge ownership proof
  let submitting = false;

  // ── helpers ──────────────────────────────────────────────────────────────

  // Build chain <option> html filtered to those that support the selected token
  const chainOpts = (selectedToken, selectedChain) => {
    if (!chainsInfo?.chains?.length) return '<option value="">No chains available</option>';
    return chainsInfo.chains
      .filter(c => c.tokens.includes(selectedToken))
      .map(c => `<option value="${c.id}" ${c.id === selectedChain ? 'selected' : ''}>${c.label}</option>`)
      .join('');
  };

  // Build token <option> html for chains that have any supported token
  const tokenOpts = (selectedToken) => {
    if (!chainsInfo?.chains?.length) return '';
    const tokens = [...new Set(chainsInfo.chains.flatMap(c => c.tokens))].sort();
    return tokens.map(t => `<option value="${t}" ${t === selectedToken ? 'selected' : ''}>${t}</option>`).join('');
  };

  const renderPage = (err, state = {}) => {
    const usdt_reserve  = poolInfo ? Number(poolInfo.usdt_reserve  || 0).toFixed(2) : '…';
    const thr_price     = poolInfo ? `$${Number(poolInfo.thr_price_usd || 0).toFixed(4)}` : '…';
    const pledge_count  = poolInfo ? poolInfo.pledge_count   : '…';
    const next_at       = poolInfo ? poolInfo.next_level_at  : '…';
    const max_wd        = poolInfo ? Number(poolInfo.max_withdraw_usdt || 0).toFixed(2) : '150.00';
    const curToken      = state.token  || 'USDT';
    const curChain      = state.chain  || (chainsInfo?.chains?.[0]?.id ?? 'bsc');
    const hasChainsConfigured = chainsInfo?.chains?.length > 0;
    // Old users who imported wallet may not have secret cached — show manual entry
    const showSecretInput = !sendSecret;

    render(`
      <div class="screen">
        <div class="header">
          <button class="btn--icon" id="wdBackBtn">←</button>
          <span style="font-weight:700;color:#fff">💰 Withdraw</span>
          <span></span>
        </div>

        <!-- Pool info -->
        <div class="card" style="padding:10px 12px;margin-bottom:8px;background:#0d0a1a;border:1px solid #2a2050">
          <div style="font-size:.65rem;text-transform:uppercase;letter-spacing:1px;color:#b08cf8;margin-bottom:4px">THR/USDT Pool</div>
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:4px;font-size:.75rem">
            <div><span style="color:var(--muted)">Reserve </span><span style="color:#fff">${usdt_reserve} USDT</span></div>
            <div style="text-align:center"><span style="color:var(--muted)">THR </span><span style="color:#00ff66;font-weight:700">${thr_price}</span></div>
            <div style="text-align:right"><span style="color:var(--muted)">Max </span><span style="color:#b08cf8;font-weight:700">$${max_wd}</span></div>
          </div>
        </div>

        ${!hasChainsConfigured ? `
          <div class="card" style="padding:16px;text-align:center">
            <div style="font-size:1.4rem;margin-bottom:8px">🔧</div>
            <div style="color:#ff6b6b;font-size:.85rem;font-weight:600;margin-bottom:4px">No Withdrawal Chains Configured</div>
            <div style="color:var(--muted);font-size:.78rem">The operator hasn't enabled any outbound chains yet.<br>Contact support for assistance.</div>
          </div>
        ` : `
          <div class="card" style="padding:12px">
            <div style="font-size:.65rem;text-transform:uppercase;letter-spacing:1px;color:#b08cf8;margin-bottom:10px">Withdraw to External Wallet</div>

            <!-- Old-user / imported-wallet secret entry -->
            ${showSecretInput ? `
              <div style="background:#1a0d30;border:1px solid #b08cf840;border-radius:8px;padding:10px;margin-bottom:10px">
                <div style="font-size:.75rem;color:#b08cf8;font-weight:600;margin-bottom:6px">🔑 Pledge Secret</div>
                <div style="font-size:.72rem;color:var(--muted);margin-bottom:6px">
                  If you created your wallet via a BTC or USDT pledge, enter your <b>send secret</b> here.<br>
                  New users: complete a pledge first.
                </div>
                <input id="wdSecret" class="input" placeholder="Pledge send secret (hex)…" autocomplete="off"
                  style="font-family:monospace;font-size:.72rem;margin-bottom:0">
              </div>
            ` : `
              <div style="background:#0a1a0a;border:1px solid #00ff6640;border-radius:8px;padding:7px 10px;margin-bottom:10px;font-size:.75rem;color:#00ff66">
                ✓ Pledge credentials loaded
              </div>
            `}

            <!-- Token selector (only tokens available on configured chains) -->
            <label style="font-size:.75rem;color:var(--muted)">Token</label>
            <select id="wdToken" class="input" style="margin-bottom:8px">${tokenOpts(curToken)}</select>

            <!-- Chain selector (filtered by selected token) -->
            <label style="font-size:.75rem;color:var(--muted)">Destination Chain</label>
            <select id="wdChain" class="input" style="margin-bottom:8px">${chainOpts(curToken, curChain)}</select>

            <!-- External EVM wallet address -->
            <label style="font-size:.75rem;color:var(--muted)">External Wallet (EVM)</label>
            <input id="wdDest" class="input" placeholder="0x…" autocomplete="off"
              style="margin-bottom:8px;font-family:monospace;font-size:.75rem">

            <!-- Amount -->
            <label style="font-size:.75rem;color:var(--muted)">Amount (max $${max_wd})</label>
            <div style="display:flex;gap:6px;margin-bottom:8px">
              <input id="wdAmount" class="input" type="number" min="1" max="${max_wd}" step="0.01"
                placeholder="e.g. 50" style="flex:1;margin-bottom:0">
              <button class="btn btn--ghost" style="padding:6px 10px;font-size:.75rem;white-space:nowrap" id="wdMaxBtn">MAX</button>
            </div>

            <!-- Live fee preview -->
            <div id="wdFeeRow" style="font-size:.75rem;color:var(--muted);margin-bottom:10px;min-height:18px"></div>

            ${err ? `<div style="color:#ff6b6b;font-size:.8rem;margin-bottom:8px;padding:6px 8px;background:#ff6b6b10;border-radius:6px">${escHtml(err)}</div>` : ''}

            <button class="btn btn--primary" id="wdSubmitBtn" style="width:100%;padding:11px;font-size:.9rem;font-weight:700">
              Withdraw
            </button>
            <div style="font-size:.67rem;color:var(--muted);margin-top:6px;text-align:center">
              1% fee · 0.5% in THR burned · 0.5% in-kind · ~5 min
            </div>
          </div>
        `}
      </div>
    `);

    document.getElementById('wdBackBtn').addEventListener('click', showWallet);
    if (!hasChainsConfigured) return;

    // Token change → rebuild chain options (token/chain compatibility)
    const rebuildChainOpts = () => {
      const tok = document.getElementById('wdToken')?.value || 'USDT';
      const chainSel = document.getElementById('wdChain');
      if (chainSel) chainSel.innerHTML = chainOpts(tok, chainSel.value);
    };
    document.getElementById('wdToken')?.addEventListener('change', () => { rebuildChainOpts(); updateFeeRow(); });

    const updateFeeRow = () => {
      const amount  = parseFloat(document.getElementById('wdAmount')?.value || 0);
      const token   = document.getElementById('wdToken')?.value || 'USDT';
      const feeRow  = document.getElementById('wdFeeRow');
      if (!feeRow) return;
      if (!amount || amount <= 0) { feeRow.textContent = ''; return; }
      const feeTotalUsd  = amount * 0.01;
      const feeInKind    = (feeTotalUsd * 0.5).toFixed(4);
      const thrPrice     = poolInfo?.thr_price_usd || 10;
      const feeThr       = ((feeTotalUsd * 0.5) / thrPrice).toFixed(6);
      const net          = (amount - feeTotalUsd * 0.5).toFixed(4);
      feeRow.innerHTML   = `You receive <b style="color:#00ff66">${net} ${token}</b> · Fee: ${feeInKind} ${token} + ${feeThr} THR`;
    };
    document.getElementById('wdAmount')?.addEventListener('input', updateFeeRow);

    document.getElementById('wdMaxBtn')?.addEventListener('click', () => {
      const inp = document.getElementById('wdAmount');
      if (inp) { inp.value = parseFloat(max_wd).toFixed(2); updateFeeRow(); }
    });

    document.getElementById('wdSubmitBtn')?.addEventListener('click', async () => {
      if (submitting) return;

      // Resolve send_secret: cached or manually entered
      const secret = sendSecret || (document.getElementById('wdSecret')?.value || '').trim();
      if (!secret) return renderPage('Enter your pledge send secret to unlock withdrawals.', { token: curToken, chain: curChain });

      const amount    = parseFloat(document.getElementById('wdAmount')?.value || 0);
      const token     = document.getElementById('wdToken')?.value || 'USDT';
      const destChain = document.getElementById('wdChain')?.value || curChain;
      const destAddr  = (document.getElementById('wdDest')?.value || '').trim().toLowerCase();
      const maxWd     = parseFloat(max_wd);

      if (!amount || amount <= 0) return renderPage('Enter a valid amount.', { token, chain: destChain });
      if (amount > maxWd) return renderPage(`Max withdrawal is $${max_wd}.`, { token, chain: destChain });
      if (!/^0x[0-9a-f]{40}$/i.test(destAddr)) return renderPage('Enter a valid EVM wallet address (0x…).', { token, chain: destChain });

      submitting = true;
      document.getElementById('wdSubmitBtn').textContent = 'Processing…';
      document.getElementById('wdSubmitBtn').disabled = true;

      try {
        const resp = await fetch(`${API_BASE}/api/v1/withdraw`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            address:      address,
            send_secret:  secret,
            amount,
            token,
            dest_chain:   destChain,
            dest_address: destAddr,
          }),
        }).then(r => r.json());

        if (resp.ok) {
          // Cache secret in account metadata for future withdrawals (old-user path)
          if (!sendSecret && secret) {
            const acc = getAccount(address);
            if (acc) upsertAccount(address, acc.kit, acc.label, secret);
          }
          // Success screen
          render(`
            <div class="screen">
              <div class="header">
                <button class="btn--icon" id="wdDoneBack">←</button>
                <span style="font-weight:700;color:#fff">Withdrawal Submitted</span>
                <span></span>
              </div>
              <div class="card" style="padding:20px;text-align:center;margin-top:16px">
                <div style="font-size:2rem;margin-bottom:10px">✅</div>
                <div style="font-size:1rem;font-weight:700;color:#00ff66;margin-bottom:6px">Pending</div>
                <div style="font-size:.78rem;color:var(--muted);margin-bottom:14px">
                  ID: <span style="color:#b08cf8;font-family:monospace">${resp.withdrawal_id}</span>
                </div>
                <div style="display:grid;gap:5px;font-size:.8rem;text-align:left;background:#0d0a1a;border-radius:8px;padding:12px;margin-bottom:14px">
                  ${[
                    ['Token',           resp.token],
                    ['Requested',       `${resp.amount} ${resp.token}`],
                    ['You receive',     `${resp.amount_net} ${resp.token}`],
                    ['THR fee',         `${resp.fee_thr} THR`],
                    ['THR price (oracle)', `$${Number(resp.oracle_price_usd || 0).toFixed(4)}`],
                    ['Chain',           resp.dest_chain_label || resp.dest_chain],
                    ['External wallet', `${destAddr.slice(0,10)}…${destAddr.slice(-6)}`],
                  ].map(([k,v]) => `
                    <div style="display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid #ffffff08">
                      <span style="color:var(--muted)">${k}</span>
                      <span style="color:${k==='You receive'?'#00ff66':k==='THR fee'?'#b08cf8':'#fff'};font-weight:${k==='You receive'?700:400}">${escHtml(String(v))}</span>
                    </div>`).join('')}
                </div>
                <div style="color:var(--muted);font-size:.75rem">~${resp.estimated_minutes || 5} min delivery</div>
              </div>
            </div>
          `);
          document.getElementById('wdDoneBack').addEventListener('click', showWallet);
        } else {
          submitting = false;
          const errMsg = {
            invalid_credentials:       'Invalid pledge secret. Check your send secret and try again.',
            chain_not_configured:      `Chain not available. Available: ${resp.available?.join(', ') || '—'}`,
            token_not_supported_on_chain: `${resp.token || 'Token'} is not supported on that chain.`,
            insufficient_pool_liquidity: `Pool liquidity too low. Available: $${resp.available_usdt?.toFixed(2)}`,
            insufficient_thr_for_fee:  `Need ${resp.required_thr} THR for fee (have ${resp.thr_balance}).`,
            exceeds_max_withdrawal:    `Max withdrawal is $${resp.max_withdrawal}.`,
          }[resp.error] || resp.error || 'Withdrawal failed. Please try again.';
          renderPage(errMsg, { token, chain: destChain });
        }
      } catch (e) {
        submitting = false;
        renderPage('Network error. Please try again.', { token: curToken, chain: curChain });
      }
    });
  };

  // ── Load data ─────────────────────────────────────────────────────────────
  render(`<div class="screen"><div style="text-align:center;padding:60px;color:var(--muted)">Loading…</div></div>`);
  try {
    const [pi, ci] = await Promise.all([
      fetch(`${API_BASE}/api/v1/pool/thr-usdt`).then(r => r.json()).catch(() => null),
      fetch(`${API_BASE}/api/v1/withdraw/chains`).then(r => r.json()).catch(() => null),
    ]);
    poolInfo   = pi?.ok ? pi : null;
    chainsInfo = ci?.ok ? ci : null;
    // Load secret from account metadata (new-user path after pledge migration)
    const acc = getAccount(address);
    if (acc?.pledge_send_secret) sendSecret = acc.pledge_send_secret;
  } catch {}
  renderPage(null);
}

async function showAddLiquidity(poolId, tokenA, tokenB, poolMeta) {
  const address = getActiveAddr();
  const acc = getAccount(address);
  const authSecret = acc?.pledge_send_secret || '';

  // Cross-chain: THR + USDT/USDC handled by pending-intent endpoint
  const isCrossChain = tokenA === 'THR' && (tokenB === 'USDT' || tokenB === 'USDC');

  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;background:#000000aa;z-index:999;display:flex;align-items:flex-end;justify-content:center;overflow-y:auto;';

  // Load pool info (reserves + ratio) + external chains in parallel
  let poolInfo = null;
  let externalChains = [];
  try {
    const [poolRes, availRes] = await Promise.allSettled([
      fetch(`${API_BASE}/api/v1/pools`).then(r => r.json()).catch(() => null),
      isCrossChain ? fetch(`${API_BASE}/api/v1/pools/available`).then(r => r.json()).catch(() => null) : Promise.resolve(null),
    ]);
    if (poolRes.status === 'fulfilled') {
      poolInfo = (poolRes.value?.pools || []).find(p => p.id === poolId) || poolMeta || null;
    }
    if (availRes.status === 'fulfilled' && availRes.value?.ok) {
      externalChains = (availRes.value.pools || []).find(p => p.pool_id === poolId)?.external_chains || [];
    }
  } catch {}

  const resA = Number(poolInfo?.reserves_a || 0);
  const resB = Number(poolInfo?.reserves_b || 0);
  const poolRatio = resA > 0 && resB > 0 ? resB / resA : null;

  function fmtNum(v) {
    if (!v) return '—';
    const n = Number(v);
    if (n >= 1000) return n.toLocaleString(undefined, { maximumFractionDigits: 4 });
    if (n >= 1) return n.toFixed(6);
    return n.toFixed(8);
  }

  const reservesHtml = resA > 0 ? `
    <div style="background:#0d0a1a;border-radius:8px;padding:10px 12px;margin-bottom:12px;font-size:.78rem">
      <div style="display:flex;justify-content:space-between;margin-bottom:4px">
        <span style="color:var(--muted)">Pool Reserves</span>
        <span style="color:var(--muted)">Ratio</span>
      </div>
      <div style="display:flex;justify-content:space-between">
        <span style="color:#fff">${fmtNum(resA)} ${tokenA} / ${fmtNum(resB)} ${tokenB}</span>
        <span style="color:#b08cf8">1 ${tokenA} = ${poolRatio ? fmtNum(poolRatio) : '—'} ${tokenB}</span>
      </div>
    </div>` : '';

  function chainOptions() {
    if (!externalChains.length) return `<option value="">— no chains available —</option>`;
    return externalChains.map(c =>
      `<option value="${c.chain}" data-contract="${c.token_contract}" data-decimals="${c.decimals}" data-label="${c.label}">${c.label} (${c.token_standard})</option>`
    ).join('');
  }

  overlay.innerHTML = `
    <div style="background:#13112a;border-radius:16px 16px 0 0;width:100%;max-width:480px;padding:20px 20px 32px;margin-top:auto">
      <div style="font-size:1rem;font-weight:700;color:#fff;margin-bottom:12px">💧 Add Liquidity: ${tokenA}/${tokenB}</div>

      ${reservesHtml}

      ${isCrossChain ? `
      <label style="font-size:.82rem;color:var(--muted)">External Chain for ${tokenB}</label>
      <select id="liqChain" class="input" style="margin-bottom:10px">
        ${chainOptions()}
      </select>
      <label style="font-size:.82rem;color:var(--muted)">Your EVM Address (holding ${tokenB})</label>
      <input type="text" id="liqEvm" class="input" placeholder="0x..." style="margin-bottom:10px;font-family:monospace;font-size:.8rem">
      ` : ''}

      <label style="font-size:.82rem;color:var(--muted)">${tokenA} Amount</label>
      <input type="number" id="liqA" class="input" placeholder="0.00" min="0" step="0.000001" inputmode="decimal" style="margin-bottom:6px">

      <label style="font-size:.82rem;color:var(--muted)">${tokenB} Amount</label>
      <input type="number" id="liqB" class="input" placeholder="0.00" min="0" step="0.000001" inputmode="decimal" style="margin-bottom:6px">

      <div id="liqQuote" style="font-size:.78rem;color:#b08cf8;margin-bottom:10px;min-height:18px;padding:0 2px"></div>
      ${isCrossChain ? `<div style="font-size:.75rem;color:#ffb81c;margin-bottom:10px;padding:8px;background:#ffb81c10;border-radius:6px;border:1px solid #ffb81c30">⚠️ Gas required on external chain to send ${tokenB} to vault.</div>` : ''}

      ${!authSecret && isCrossChain ? `
      <label style="font-size:.82rem;color:var(--muted)">Auth Secret (send_secret from pledge)</label>
      <input type="password" id="liqAuth" class="input" placeholder="Enter your auth secret" style="margin-bottom:10px">
      ` : ''}

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
        <button id="liqCancel" class="btn btn--ghost" style="padding:12px">Cancel</button>
        <button id="liqAdd" class="btn btn--primary" style="padding:12px">${isCrossChain ? 'Create Intent' : 'Add Liquidity'}</button>
      </div>
      <div id="liqErr" style="margin-top:10px;color:#ff6b6b;font-size:.82rem;display:none"></div>
      <div id="liqOk" style="margin-top:10px;color:#00ff66;font-size:.82rem;display:none"></div>
    </div>`;
  document.body.appendChild(overlay);

  // Auto-calculate paired amount from pool ratio when either field changes
  let quoteTimer = null;

  function applyLocalRatio(changedSide) {
    if (!poolRatio) return;
    const aEl = overlay.querySelector('#liqA');
    const bEl = overlay.querySelector('#liqB');
    if (!aEl || !bEl) return;
    if (changedSide === 'a') {
      const v = parseFloat(aEl.value);
      if (v > 0) bEl.value = (v * poolRatio).toFixed(6);
    } else {
      const v = parseFloat(bEl.value);
      if (v > 0) aEl.value = (v / poolRatio).toFixed(6);
    }
  }

  async function updateQuote(changedSide) {
    applyLocalRatio(changedSide);
    const amtA = parseFloat(overlay.querySelector('#liqA')?.value || '');
    const quoteEl = overlay.querySelector('#liqQuote');
    if (!amtA || amtA <= 0) { if (quoteEl) quoteEl.textContent = ''; return; }
    try {
      const q = await fetch(`${API_BASE}/api/v1/pools/quote-add-liquidity?pool_id=${poolId}&amount_a=${amtA}`).then(r => r.json()).catch(() => null);
      if (q?.ok) {
        const liqBEl = overlay.querySelector('#liqB');
        if (liqBEl) liqBEl.value = q.amount_b;
        const tolMin = q.amount_b ? (q.amount_b * 0.98).toFixed(6) : '—';
        const tolMax = q.amount_b ? (q.amount_b * 1.02).toFixed(6) : '—';
        if (quoteEl) quoteEl.innerHTML =
          `Required: <strong>${q.amount_b} ${tokenB}</strong> (±2%: ${tolMin}–${tolMax})<br>` +
          `Est. LP shares: <strong>${q.lp_shares_estimate}</strong> · Your pool share: <strong>${q.share_pct}%</strong>`;
      }
    } catch {}
  }

  overlay.querySelector('#liqA')?.addEventListener('input', () => {
    clearTimeout(quoteTimer);
    quoteTimer = setTimeout(() => updateQuote('a'), 400);
  });
  overlay.querySelector('#liqB')?.addEventListener('input', () => {
    clearTimeout(quoteTimer);
    quoteTimer = setTimeout(() => updateQuote('b'), 400);
  });

  overlay.querySelector('#liqCancel').addEventListener('click', () => overlay.remove());

  overlay.querySelector('#liqAdd').addEventListener('click', async () => {
    const amtA = parseFloat(overlay.querySelector('#liqA').value);
    const amtB = parseFloat(overlay.querySelector('#liqB').value);
    const errEl = overlay.querySelector('#liqErr');
    const okEl = overlay.querySelector('#liqOk');
    errEl.style.display = 'none';

    if (!amtA || amtA <= 0 || !amtB || amtB <= 0) {
      errEl.textContent = 'Enter valid amounts for both tokens';
      errEl.style.display = '';
      return;
    }

    const btn = overlay.querySelector('#liqAdd');
    btn.disabled = true; btn.textContent = isCrossChain ? 'Creating Intent…' : 'Adding…';

    try {
      if (isCrossChain) {
        const chainSel = overlay.querySelector('#liqChain');
        const selOpt = chainSel?.selectedOptions[0];
        const chain = selOpt?.value || '';
        const tokenContract = selOpt?.dataset?.contract || '';
        const decimals = parseInt(selOpt?.dataset?.decimals || '18', 10);
        const evmAddress = (overlay.querySelector('#liqEvm')?.value || '').trim();
        const secret = authSecret || (overlay.querySelector('#liqAuth')?.value || '').trim();

        if (!chain) { throw new Error('Select an external chain'); }
        if (!evmAddress) { throw new Error(`Enter your EVM address holding ${tokenB}`); }
        if (!secret) { throw new Error('Auth secret required'); }

        const r = await fetch(`${API_WRITE}/api/v1/pools/add-liquidity`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pool_id: poolId, amount_a: amtA, amount_b: amtB, chain, token_contract: tokenContract, decimals, provider_thr: address, evm_address: evmAddress, auth_secret: secret }),
        });
        const d = await r.json().catch(() => ({}));
        if (r.ok && d.ok) {
          const chainLabel = selOpt?.dataset?.label || chain;
          okEl.innerHTML = `✅ Intent created.<br><br>Send <strong>${amtB} ${tokenB}</strong> to:<br>` +
            `<code style="font-size:.7rem;word-break:break-all;display:block;background:#1a1a2e;padding:8px;border-radius:4px;margin:8px 0">${d.vault_address}</code>` +
            `on ${chainLabel}.<br><br><small style="color:var(--muted)">Intent: ${d.intent_id}<br>Expires: ${new Date(d.expires_at * 1000).toLocaleString()}</small>`;
          okEl.style.display = '';
          setTimeout(() => overlay.remove(), 10000);
        } else {
          // Provide helpful ratio_mismatch message
          if (d.error === 'ratio_mismatch') {
            throw new Error(`${d.message || 'Ratio mismatch'}`);
          }
          throw new Error(d.message || d.error || 'Create intent failed');
        }
      } else {
        // Legacy internal pool path (WBTC/L2E pairs)
        const { privHex } = unlocked.get(address) || {};
        if (!privHex) { throw new Error('Wallet locked'); }
        const r = await fetch(`${API_WRITE}/api/wallet/v1/add_liquidity`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ from: address, pool_id: poolId, amount_a: amtA, amount_b: amtB, private_key_hex: privHex }),
        });
        const d = await r.json().catch(() => ({}));
        if (r.ok && (d.ok || d.status === 'success')) {
          okEl.textContent = '✅ Liquidity added!';
          okEl.style.display = '';
          setTimeout(() => overlay.remove(), 2000);
        } else {
          if (d.error === 'ratio_mismatch') throw new Error(d.message || 'Ratio mismatch');
          throw new Error(d.message || d.error || 'failed');
        }
      }
    } catch (e) {
      errEl.textContent = e.message || (isCrossChain ? 'Create intent failed' : 'Add liquidity failed');
      errEl.style.display = '';
      btn.disabled = false; btn.textContent = isCrossChain ? 'Create Intent' : 'Add Liquidity';
    }
  });
}

// ─── Epoch & Halving ────────────────────────────────────────────────────────────

async function showEpoch() {
  render(`
    <div class="screen">
      <div class="header">
        <button class="btn--icon" id="backBtn">←</button>
        <span style="font-weight:700;color:#fff">⏳ Epoch & Halving</span>
        <span></span>
      </div>
      <div id="epochArea" style="padding:4px 0;color:var(--muted);font-size:.85rem">Loading…</div>
    </div>
  `);
  document.getElementById('backBtn').addEventListener('click', showWallet);

  const area = document.getElementById('epochArea');
  try {
    const [epochRes, schedRes, statsRes] = await Promise.allSettled([
      fetch(`${API_BASE}/api/mining/current-epoch`).then((r) => r.json()),
      fetch(`${API_BASE}/api/mining/halving-schedule`).then((r) => r.json()),
      fetch(`${API_BASE}/api/mining/ecosystem-stats`).then((r) => r.json()),
    ]);
    const epoch = epochRes.status === 'fulfilled' ? epochRes.value : null;
    const halvings = schedRes.status === 'fulfilled' ? (schedRes.value.halvings || []) : [];
    const stats = statsRes.status === 'fulfilled' ? statsRes.value : null;

    const halvingRows = halvings.slice(0, 8).map((h) => `
      <div style="display:flex;justify-content:space-between;align-items:center;background:rgba(255,255,255,.04);
                  border:1px solid rgba(255,255,255,.08);border-radius:10px;padding:10px 12px;margin-bottom:6px">
        <div>
          <div style="font-weight:700;color:#fff;font-size:.88rem">Epoch ${h.epoch}</div>
          <div style="font-size:.74rem;color:var(--muted)">${new Date(h.halving_date).toLocaleDateString()}</div>
        </div>
        <div style="text-align:right">
          <div style="font-size:.82rem;color:#ddd">${h.reward_before} → ${h.reward_after}</div>
          <div style="font-size:.74rem;color:var(--muted)">${Number(h.supply_at_halving).toLocaleString()} THR</div>
        </div>
      </div>
    `).join('');

    area.innerHTML = `
      <div style="text-align:center;background:linear-gradient(135deg,#221600,#140f00,#0d0d1a);
                  border:1px solid rgba(255,215,0,.4);border-radius:18px;padding:20px;margin-bottom:14px">
        <div style="font-size:.74rem;letter-spacing:2px;color:rgba(255,215,0,.7);font-weight:700">CURRENT EPOCH</div>
        <div style="font-size:2.6rem;font-weight:800;color:#FFD700;margin-top:4px">${epoch?.epoch ?? '—'}</div>
        <div style="font-size:.74rem;color:var(--muted);margin-top:4px">Block ${epoch?.current_block?.toLocaleString() ?? '—'} · range ${epoch?.block_range ?? '—'}</div>
        <div style="display:flex;justify-content:center;gap:28px;margin-top:14px">
          <div><div style="font-weight:700;color:#fff">${epoch?.current_reward ?? '—'}</div><div style="font-size:.72rem;color:var(--muted)">Reward/Block</div></div>
          <div><div style="font-weight:700;color:#fff">${epoch?.blocks_until_halving?.toLocaleString() ?? '—'}</div><div style="font-size:.72rem;color:var(--muted)">Blocks to Halving</div></div>
        </div>
        <div style="font-size:.8rem;color:#ccc;margin-top:12px">
          Est. halving: ${epoch?.halving_date_estimate ? new Date(epoch.halving_date_estimate).toLocaleDateString() : '—'}
        </div>
      </div>

      <div style="background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:14px;padding:14px;margin-bottom:14px">
        <div style="display:flex;justify-content:space-between;margin-bottom:6px"><span style="color:var(--muted);font-size:.82rem">Circulating Supply</span><span style="font-weight:700;color:#fff;font-size:.82rem">${epoch?.supply_circulating?.toLocaleString() ?? '—'} THR</span></div>
        <div style="display:flex;justify-content:space-between;margin-bottom:6px"><span style="color:var(--muted);font-size:.82rem">Max Supply</span><span style="font-weight:700;color:#fff;font-size:.82rem">${(epoch?.supply_max ?? 21000001).toLocaleString()} THR</span></div>
        ${stats ? `
        <div style="display:flex;justify-content:space-between;margin-bottom:6px"><span style="color:var(--muted);font-size:.82rem">Halving Interval</span><span style="font-weight:700;color:#fff;font-size:.82rem">${stats.halving_interval_months} months</span></div>
        <div style="display:flex;justify-content:space-between"><span style="color:var(--muted);font-size:.82rem">Full Circulation (est.)</span><span style="font-weight:700;color:#fff;font-size:.82rem">~${stats.estimated_full_circulation_years} years</span></div>
        ` : ''}
      </div>

      <div style="font-size:.72rem;font-weight:700;color:var(--muted);letter-spacing:2px;margin-bottom:8px;text-transform:uppercase">Halving Schedule</div>
      ${halvingRows || '<p style="color:var(--muted);font-size:.82rem">No schedule data available.</p>'}
    `;
  } catch (e) {
    area.innerHTML = `<p style="color:#ff6b6b;font-size:.85rem">Failed to load epoch data.</p>`;
  }
}

// ─── Create Token ──────────────────────────────────────────────────────────────

async function showCreateToken() {
  const address = getActiveAddr();
  if (!address || !unlocked.has(address)) { showUnlock(); return; }

  render(`
    <div class="screen">
      <div class="header">
        <button class="btn--icon" id="backBtn">←</button>
        <span style="font-weight:700;color:#fff">🪙 Create Token</span>
        <span></span>
      </div>
      <div style="padding:4px 0">
        <p style="color:var(--muted);font-size:.8rem;margin-bottom:14px">
          Launch your own experimental token on the Thronos network. The full supply is minted to your address.
        </p>
        <label style="font-size:.82rem;color:var(--muted)">Token Name</label>
        <input type="text" id="tokName" class="input" placeholder="e.g. My Awesome Token" style="margin-bottom:10px">
        <label style="font-size:.82rem;color:var(--muted)">Symbol (1-8 chars, A-Z0-9)</label>
        <input type="text" id="tokSymbol" class="input" placeholder="e.g. MAT" maxlength="8" style="margin-bottom:10px;text-transform:uppercase">
        <label style="font-size:.82rem;color:var(--muted)">Total Supply</label>
        <input type="number" id="tokSupply" class="input" placeholder="1000000" min="0" step="1" inputmode="decimal" style="margin-bottom:10px">
        <label style="font-size:.82rem;color:var(--muted)">Decimals (0-18)</label>
        <input type="number" id="tokDecimals" class="input" placeholder="8" min="0" max="18" step="1" value="8" style="margin-bottom:14px">
        <button id="tokCreateBtn" class="btn btn--primary" style="width:100%;padding:13px">Create Token</button>
        <div id="tokErr" style="margin-top:10px;color:#ff6b6b;font-size:.82rem;display:none"></div>
        <div id="tokOk" style="margin-top:10px;color:#00ff66;font-size:.82rem;display:none"></div>
      </div>
    </div>
  `);

  document.getElementById('backBtn').addEventListener('click', showWallet);
  document.getElementById('tokCreateBtn').addEventListener('click', async () => {
    const name = document.getElementById('tokName').value.trim();
    const symbol = document.getElementById('tokSymbol').value.trim().toUpperCase();
    const supply = parseFloat(document.getElementById('tokSupply').value);
    const decimals = parseInt(document.getElementById('tokDecimals').value, 10);
    const errEl = document.getElementById('tokErr');
    const okEl = document.getElementById('tokOk');
    errEl.style.display = 'none'; okEl.style.display = 'none';

    if (!name || !symbol || !supply || supply <= 0) {
      errEl.textContent = 'Fill in name, symbol and a positive supply';
      errEl.style.display = '';
      return;
    }
    const { privHex } = unlocked.get(address) || {};
    if (!privHex) { errEl.textContent = 'Wallet locked'; errEl.style.display = ''; return; }

    const btn = document.getElementById('tokCreateBtn');
    btn.disabled = true; btn.textContent = 'Creating…';
    try {
      const r = await fetch(`${API_WRITE}/api/wallet/v1/create_token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          from: address, name, symbol, total_supply: supply,
          decimals: isNaN(decimals) ? 8 : decimals, private_key_hex: privHex,
        }),
      });
      const d = await r.json().catch(() => ({}));
      if (r.ok && (d.ok || d.status === 'success')) {
        okEl.textContent = `✅ Token ${symbol} created! Full supply credited to your wallet.`;
        okEl.style.display = '';
        btn.textContent = 'Created';
      } else {
        throw new Error(d.message || d.error || 'failed');
      }
    } catch (e) {
      errEl.textContent = e.message || 'Token creation failed';
      errEl.style.display = '';
      btn.disabled = false; btn.textContent = 'Create Token';
    }
  });
}

// ─── NFTs ──────────────────────────────────────────────────────────────────────

async function showNFTs() {
  const address = getActiveAddr();
  if (!address || !unlocked.has(address)) { showUnlock(); return; }

  render(`
    <div class="screen">
      <div class="header">
        <button class="btn--icon" id="backBtn">←</button>
        <span style="font-weight:700;color:#fff">🖼️ NFTs</span>
        <button class="btn--icon" id="mintBtn" title="Mint NFT">＋</button>
      </div>
      <div id="nftBody" style="margin-top:10px">
        <p style="color:var(--muted);text-align:center;padding:20px">Loading NFTs…</p>
      </div>
    </div>
  `);

  document.getElementById('backBtn').addEventListener('click', showWallet);
  document.getElementById('mintBtn').addEventListener('click', showMintNFT);

  try {
    const r = await fetch(`${API_BASE}/api/v1/nfts`);
    const d = await r.json().catch(() => ({}));
    const nfts = d.nfts || [];
    const el = document.getElementById('nftBody');
    if (!el) return;

    if (!nfts.length) {
      el.innerHTML = '<p style="color:var(--muted);text-align:center;padding:20px">No NFTs minted yet. Tap + to mint the first one.</p>';
      return;
    }

    el.innerHTML = nfts.slice().reverse().map(nft => {
      const isMine = (nft.owner || '').toUpperCase() === address;
      const img = nft.image_url
        ? `<img src="${nft.image_url}" style="width:100%;aspect-ratio:1;object-fit:cover;border-radius:8px;margin-bottom:8px">`
        : `<div style="width:100%;aspect-ratio:1;border-radius:8px;margin-bottom:8px;background:#1a1040;display:flex;align-items:center;justify-content:center;font-size:2rem">🖼️</div>`;
      return `<div class="card" style="padding:12px;margin-bottom:10px">
        ${img}
        <div style="font-size:.95rem;font-weight:700;color:#fff">${escHtml(nft.name || 'Untitled')}</div>
        <div style="font-size:.76rem;color:var(--muted);margin:2px 0 8px">${escHtml(nft.description || '')}</div>
        <div style="display:flex;justify-content:space-between;font-size:.78rem;color:var(--muted);margin-bottom:8px">
          <span>Owner: ${isMine ? 'You' : shortAddr(nft.owner || '')}</span>
          <span>${nft.price ? nft.price + ' THR' : 'Not for sale'}</span>
        </div>
        ${(!isMine && nft.for_sale && nft.price > 0)
          ? `<button class="btn btn--primary" style="width:100%;padding:9px;font-size:.82rem" onclick="buyNFT('${nft.id}')">Buy for ${nft.price} THR</button>`
          : ''}
      </div>`;
    }).join('');
  } catch (e) {
    const el = document.getElementById('nftBody');
    if (el) el.innerHTML = `<p style="color:#ff6b6b;text-align:center;padding:20px">Error: ${e.message}</p>`;
  }
}

async function buyNFT(nftId) {
  const address = getActiveAddr();
  const { privHex } = unlocked.get(address) || {};
  if (!privHex) { alert('Wallet locked'); return; }
  if (!confirm('Buy this NFT?')) return;
  try {
    const r = await fetch(`${API_WRITE}/api/wallet/v1/nfts/buy`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ from: address, nft_id: nftId, private_key_hex: privHex }),
    });
    const d = await r.json().catch(() => ({}));
    if (r.ok && (d.ok || d.status === 'success')) {
      alert('✅ NFT purchased!');
      showNFTs();
    } else {
      throw new Error(d.message || d.error || 'failed');
    }
  } catch (e) {
    alert('Buy failed: ' + e.message);
  }
}

function showMintNFT() {
  const address = getActiveAddr();
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;background:#000000aa;z-index:999;display:flex;align-items:flex-end;justify-content:center;';
  overlay.innerHTML = `
    <div style="background:#13112a;border-radius:16px 16px 0 0;width:100%;max-width:480px;padding:20px 20px 32px;max-height:88vh;overflow-y:auto">
      <div style="font-size:1rem;font-weight:700;color:#fff;margin-bottom:14px">🖼️ Mint NFT</div>
      <label style="font-size:.82rem;color:var(--muted)">Image (optional)</label>
      <input type="file" id="nftImg" accept="image/png,image/jpeg,image/gif,image/webp" style="margin-bottom:10px;width:100%;color:var(--muted)">
      <label style="font-size:.82rem;color:var(--muted)">Name</label>
      <input type="text" id="nftName" class="input" placeholder="NFT name" style="margin-bottom:10px">
      <label style="font-size:.82rem;color:var(--muted)">Description</label>
      <input type="text" id="nftDesc" class="input" placeholder="Optional description" style="margin-bottom:10px">
      <label style="font-size:.82rem;color:var(--muted)">Price (THR, 0 = not for sale)</label>
      <input type="number" id="nftPrice" class="input" placeholder="0" min="0" step="0.01" inputmode="decimal" style="margin-bottom:10px">
      <label style="font-size:.82rem;color:var(--muted)">Royalties % (0-50)</label>
      <input type="number" id="nftRoyalty" class="input" placeholder="10" min="0" max="50" step="1" value="10" style="margin-bottom:14px">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
        <button id="nftCancel" class="btn btn--ghost" style="padding:12px">Cancel</button>
        <button id="nftMintBtn" class="btn btn--primary" style="padding:12px">Mint</button>
      </div>
      <div id="nftErr" style="margin-top:10px;color:#ff6b6b;font-size:.82rem;display:none"></div>
      <div id="nftOk" style="margin-top:10px;color:#00ff66;font-size:.82rem;display:none"></div>
    </div>`;
  document.body.appendChild(overlay);
  overlay.querySelector('#nftCancel').addEventListener('click', () => overlay.remove());

  const readFileAsDataUrl = (file) => new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });

  overlay.querySelector('#nftMintBtn').addEventListener('click', async () => {
    const name = overlay.querySelector('#nftName').value.trim();
    const description = overlay.querySelector('#nftDesc').value.trim();
    const price = parseFloat(overlay.querySelector('#nftPrice').value) || 0;
    const royalties = parseInt(overlay.querySelector('#nftRoyalty').value, 10) || 0;
    const file = overlay.querySelector('#nftImg').files[0];
    const errEl = overlay.querySelector('#nftErr');
    const okEl = overlay.querySelector('#nftOk');
    errEl.style.display = 'none'; okEl.style.display = 'none';

    if (!name) { errEl.textContent = 'Enter a name'; errEl.style.display = ''; return; }
    const { privHex } = unlocked.get(address) || {};
    if (!privHex) { errEl.textContent = 'Wallet locked'; errEl.style.display = ''; return; }

    const btn = overlay.querySelector('#nftMintBtn');
    btn.disabled = true; btn.textContent = 'Minting…';
    try {
      let image_data_url = '';
      if (file) image_data_url = await readFileAsDataUrl(file);
      const r = await fetch(`${API_WRITE}/api/wallet/v1/nfts/mint`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          from: address, name, description, price, royalties,
          image_data_url, private_key_hex: privHex,
        }),
      });
      const d = await r.json().catch(() => ({}));
      if (r.ok && (d.ok || d.status === 'success')) {
        okEl.textContent = '✅ NFT minted!';
        okEl.style.display = '';
        setTimeout(() => { overlay.remove(); showNFTs(); }, 1500);
      } else {
        throw new Error(d.message || d.error || 'failed');
      }
    } catch (e) {
      errEl.textContent = e.message || 'Mint failed';
      errEl.style.display = '';
      btn.disabled = false; btn.textContent = 'Mint';
    }
  });
}

// ─── Extra CSS for new components (injected once) ────────────────────────────

function injectExtraStyles() {
  if (document.getElementById('pwa-extra-css')) return;
  const s = document.createElement('style');
  s.id = 'pwa-extra-css';
  s.textContent = `
    .token-row {
      display: flex; align-items: center; gap: 12px;
      padding: 12px 0; border-bottom: 1px solid var(--border);
    }
    .token-row:last-child { border-bottom: none; }
    .token-icon { font-size: 1.3rem; width: 28px; text-align: center; }
    .token-sym { font-weight: 600; flex: 1; }
    .token-bal { color: var(--text); font-size: .95rem; font-weight: 500; }
    .acc-card {
      background: var(--card); border: 1px solid var(--border);
      border-radius: var(--radius); padding: 14px 16px;
      display: flex; align-items: center; gap: 12px; cursor: pointer;
      transition: border-color .15s;
    }
    .acc-card--active { border-color: var(--accent); }
    .acc-card:active { background: var(--card2); }
    .acc-card__info { flex: 1; }
    .acc-card__label { font-weight: 600; font-size: .95rem; }
    .acc-card__addr { color: var(--muted); font-size: .8rem; font-family: monospace; margin-top: 2px; }
    .acc-card__del { color: var(--muted); font-size: .9rem; }
    .acc-badge {
      display: inline-block; background: var(--success-bg); color: var(--success-text);
      font-size: .72rem; padding: 2px 7px; border-radius: 99px; margin-top: 4px;
    }
  `;
  document.head.appendChild(s);
}

// ─── EVM Asset Actions (PWA) ──────────────────────────────────────────────────

// Minimal RLP encoder — EIP-155 compatible
const _pwaRlp = (() => {
  const h2b = h => { h = h.replace(/^0x/,''); if(h.length%2)h='0'+h; const a=new Uint8Array(h.length/2); for(let i=0;i<a.length;i++)a[i]=parseInt(h.slice(i*2,i*2+2),16); return a; };
  const cat = (...arrs) => { const r=new Uint8Array(arrs.reduce((s,a)=>s+a.length,0)); let o=0; for(const a of arrs){r.set(a,o);o+=a.length;} return r; };
  const bn2b = n => { if(n===0n||n===0)return new Uint8Array(0); let h=(typeof n==='bigint'?n:BigInt(n)).toString(16); if(h.length%2)h='0'+h; return h2b(h); };
  const lenHdr = (len,base) => { if(len<56)return new Uint8Array([base+len]); const lb=bn2b(BigInt(len)); return cat(new Uint8Array([base+55+lb.length]),lb); };
  const enc = v => {
    if(Array.isArray(v)){const inner=cat(...v.map(enc));return cat(lenHdr(inner.length,0xc0),inner);}
    let bytes=v instanceof Uint8Array?v:(typeof v==='string'&&v.startsWith('0x')?h2b(v):bn2b(typeof v==='bigint'?v:BigInt(v)));
    if(bytes.length===1&&bytes[0]<0x80)return bytes;
    return cat(lenHdr(bytes.length,0x80),bytes);
  };
  return { encode:enc, hexToBytes:h2b, cat, bn2b };
})();

function _pwaEncodeErc20Transfer(toAddress, amount, decimals) {
  const sel = 'a9059cbb';
  const addrPad = toAddress.replace(/^0x/,'').toLowerCase().padStart(64,'0');
  const amtPad = BigInt(Math.round(amount * 10 ** decimals)).toString(16).padStart(64,'0');
  return '0x' + sel + addrPad + amtPad;
}

async function _pwaEvmRpc(network, method, params) {
  const rpcKey = {ethereum:'eth',bnb:'bnb',arbitrum:'arb',base:'base'}[network];
  const rpc = rpcKey ? _CC_RPC[rpcKey] : null;
  if (!rpc) throw new Error('unknown_network');
  const r = await fetch(rpc, {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({jsonrpc:'2.0', method, params, id: Date.now()}),
    signal: AbortSignal.timeout(10000),
  });
  const d = await r.json();
  if (d.error) throw new Error(d.error.message || JSON.stringify(d.error));
  return d.result;
}

// Sign EVM transaction (EIP-155 legacy) using noble secp256k1 from _loadNobleLibs
async function _pwaEvmSignAndBroadcast({ network, from, to, value=0n, data='0x', gasLimit, gasPrice, nonce }) {
  const chainId = _EVM_CHAIN_IDS[network];
  if (!chainId) throw new Error('unsupported_network');
  if (!_pwaSigningCtx?.privHex) throw new Error('wallet_locked');

  const unsigned = _pwaRlp.encode([
    _pwaRlp.bn2b(BigInt(nonce)),
    _pwaRlp.bn2b(BigInt(gasPrice)),
    _pwaRlp.bn2b(BigInt(gasLimit)),
    _pwaRlp.hexToBytes(to),
    _pwaRlp.bn2b(BigInt(value)),
    _pwaRlp.hexToBytes(data.replace(/^0x/,'')||''),
    _pwaRlp.bn2b(BigInt(chainId)),
    new Uint8Array(0),
    new Uint8Array(0),
  ]);
  const unsignedHex = '0x' + Array.from(unsigned).map(b=>b.toString(16).padStart(2,'0')).join('');

  // Keccak256 via server (hash utility — no keys sent)
  const hashRes = await fetch('/api/wallet/v1/keccak256', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({hex: unsignedHex}),
  });
  const hashData = await hashRes.json();
  if (!hashData.ok) throw new Error('keccak256_failed');
  const txHashHex = hashData.hash.replace(/^0x/,'');

  // Sign with secp256k1 — private key stays in JS memory only.
  // @noble/curves  → .sign()      (synchronous, returns Signature with .recovery)
  // @noble/secp256k1 → .signAsync() (async)
  // Support both to avoid "signAsync is not a function" at runtime.
  const { secp256k1 } = await _loadNobleLibs();
  const privBytes = _pwaRlp.hexToBytes(_pwaSigningCtx.privHex.replace(/^0x/,''));
  let sig;
  if (typeof secp256k1.signAsync === 'function') {
    sig = await secp256k1.signAsync(txHashHex, privBytes, { lowS: true });
  } else if (typeof secp256k1.sign === 'function') {
    sig = secp256k1.sign(txHashHex, privBytes, { lowS: true });
  } else {
    throw new Error('EVM signer unavailable. Wallet build must be updated before sending.');
  }
  const recovery = sig.recovery ?? 0;
  const v = BigInt(chainId) * 2n + 35n + BigInt(recovery);
  const r32 = sig.r.toString(16).padStart(64,'0');
  const s32 = sig.s.toString(16).padStart(64,'0');

  const signed = _pwaRlp.encode([
    _pwaRlp.bn2b(BigInt(nonce)),
    _pwaRlp.bn2b(BigInt(gasPrice)),
    _pwaRlp.bn2b(BigInt(gasLimit)),
    _pwaRlp.hexToBytes(to),
    _pwaRlp.bn2b(BigInt(value)),
    _pwaRlp.hexToBytes(data.replace(/^0x/,'')||''),
    _pwaRlp.bn2b(v),
    _pwaRlp.hexToBytes(r32),
    _pwaRlp.hexToBytes(s32),
  ]);
  const signedHex = '0x' + Array.from(signed).map(b=>b.toString(16).padStart(2,'0')).join('');
  return await _pwaEvmRpc(network, 'eth_sendRawTransaction', [signedHex]);
}

function pwaOpenEvmAssetActions(network, evmAddr, tokenSym) {
  const existing = document.getElementById('pwaEvmActionSheet');
  if (existing) existing.remove();
  const netLabel = {ethereum:'Ethereum',bnb:'BNB Chain',arbitrum:'Arbitrum',base:'Base'}[network] || network;
  const tokenLabel = tokenSym || 'Assets';
  const hasPool = !!_EVM_POOL_IDS[network];
  const overlay = document.createElement('div');
  overlay.id = 'pwaEvmActionSheet';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.78);z-index:10000;display:flex;align-items:flex-end;justify-content:center;';
  const sheet = document.createElement('div');
  sheet.style.cssText = 'background:#13112a;border:1px solid #2a2050;border-radius:14px 14px 0 0;padding:20px 20px 32px;width:100%;max-width:480px;';
  sheet.innerHTML = `
    <div style="font-size:14px;font-weight:700;color:#b08cf8;margin-bottom:14px;">${escHtml(tokenLabel)} on ${escHtml(netLabel)}</div>
    <button id="pwaEvmSendBtn" disabled style="width:100%;margin-bottom:8px;padding:12px;background:rgba(176,140,248,0.04);border:1px solid #1a1535;border-radius:8px;color:#555;font-size:13px;cursor:not-allowed;text-align:left;opacity:0.45;">💸 Send ${escHtml(tokenLabel)}<span style="display:block;font-size:10px;color:#664;margin-top:2px;">Temporarily disabled — signer &amp; address binding verification pending</span></button>
    ${hasPool ? `<button id="pwaEvmDepositBtn" style="width:100%;margin-bottom:8px;padding:12px;background:rgba(0,200,255,0.06);border:1px solid #004466;border-radius:8px;color:#fff;font-size:13px;cursor:pointer;text-align:left;">💧 Deposit to Pool</button>` : ''}
    <button id="pwaEvmCopyBtn" style="width:100%;margin-bottom:8px;padding:12px;background:rgba(0,0,0,0.3);border:1px solid #2a2050;border-radius:8px;color:#aaa;font-size:13px;cursor:pointer;text-align:left;">📋 Copy Address (${evmAddr.slice(0,6)}…${evmAddr.slice(-4)})</button>
    <button id="pwaEvmCancelBtn" style="width:100%;padding:10px;background:none;border:1px solid #333;border-radius:8px;color:#666;font-size:12px;cursor:pointer;">Cancel</button>
  `;
  overlay.appendChild(sheet);
  overlay.addEventListener('click', e => { if(e.target===overlay) overlay.remove(); });
  document.body.appendChild(overlay);

  sheet.querySelector('#pwaEvmSendBtn').addEventListener('click', (e) => {
    if (e.currentTarget.disabled) return; // button is disabled — no-op
    overlay.remove();
    pwaOpenEvmSendModal(network, evmAddr, tokenSym);
  });
  if (hasPool) {
    sheet.querySelector('#pwaEvmDepositBtn').addEventListener('click', () => {
      overlay.remove();
      pwaOpenPoolDepositModal(network, evmAddr);
    });
  }
  sheet.querySelector('#pwaEvmCopyBtn').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(evmAddr); } catch {}
    const btn = sheet.querySelector('#pwaEvmCopyBtn');
    if (btn) btn.textContent = '✓ Copied';
  });
  sheet.querySelector('#pwaEvmCancelBtn').addEventListener('click', () => overlay.remove());
}

async function pwaOpenEvmSendModal(network, evmAddr, tokenSym) {
  // ── Run all pre-send guards before rendering any signing UI ─────────────
  const guard = await _pwaEvmSendGuard(network, evmAddr);
  if (!guard.ok) {
    alert(guard.userMsg);
    return;
  }
  // ── Guards passed — safe to open modal ───────────────────────────────────

  const existing = document.getElementById('pwaEvmSendModal');
  if (existing) existing.remove();
  const netLabel = {ethereum:'Ethereum',bnb:'BNB Chain',arbitrum:'Arbitrum',base:'Base'}[network] || network;
  const nativeSym = {ethereum:'ETH',bnb:'BNB',arbitrum:'ETH',base:'ETH'}[network] || 'ETH';
  const sendSym = tokenSym || nativeSym;

  const overlay = document.createElement('div');
  overlay.id = 'pwaEvmSendModal';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.88);z-index:10001;display:flex;align-items:center;justify-content:center;padding:16px;';
  overlay.innerHTML = `
  <div style="background:#13112a;border:1px solid #2a2050;border-radius:12px;padding:20px;width:100%;max-width:420px;font-size:13px;">
    <div style="font-weight:700;color:#b08cf8;margin-bottom:12px;font-size:15px;">💸 Send ${escHtml(sendSym)} on ${escHtml(netLabel)}</div>
    <div style="color:#888;font-size:10px;margin-bottom:12px;">From: <span style="font-family:monospace;color:#aaa">${evmAddr}</span></div>
    <label style="color:#aaa;font-size:11px;">Recipient address</label>
    <input id="pwaEvmSendTo" placeholder="0x..." style="width:100%;box-sizing:border-box;margin:4px 0 10px;padding:8px;background:#0d0a1a;border:1px solid #2a2050;border-radius:6px;color:#fff;font-family:monospace;font-size:12px;">
    <label style="color:#aaa;font-size:11px;">Amount (${escHtml(sendSym)})</label>
    <input id="pwaEvmSendAmt" type="number" min="0" step="any" placeholder="0.00" style="width:100%;box-sizing:border-box;margin:4px 0 10px;padding:8px;background:#0d0a1a;border:1px solid #2a2050;border-radius:6px;color:#fff;font-size:13px;">
    <div id="pwaEvmGasEst" style="font-size:10px;color:#888;margin-bottom:10px;min-height:14px;"></div>
    <div style="display:flex;gap:8px;margin-top:4px;">
      <button id="pwaEvmGasBtn" style="flex:1;padding:9px;background:rgba(0,0,0,0.4);border:1px solid #2a2050;color:#8af;border-radius:6px;cursor:pointer;font-size:12px;">Estimate Gas</button>
      <button id="pwaEvmSendConfirmBtn" style="flex:1;padding:9px;background:rgba(176,140,248,0.15);border:1px solid #b08cf8;color:#b08cf8;border-radius:6px;cursor:pointer;font-size:12px;font-weight:700;">Send</button>
    </div>
    <button id="pwaEvmSendCancelBtn" style="width:100%;margin-top:8px;padding:8px;background:none;border:1px solid #333;border-radius:6px;color:#666;font-size:11px;cursor:pointer;">Cancel</button>
    <div id="pwaEvmSendResult" style="margin-top:10px;font-size:11px;min-height:14px;"></div>
    <div style="margin-top:12px;padding:8px;background:rgba(255,200,0,0.04);border:1px solid #332200;border-radius:6px;font-size:10px;color:#887766;">
      ⚠ Signing uses your Thronos secp256k1 key (EIP-155). Wallet must be unlocked. Private key never leaves your device.
    </div>
  </div>`;
  overlay.addEventListener('click', e => { if(e.target===overlay) overlay.remove(); });
  document.body.appendChild(overlay);

  overlay.querySelector('#pwaEvmSendCancelBtn').addEventListener('click', () => overlay.remove());

  overlay.querySelector('#pwaEvmGasBtn').addEventListener('click', async () => {
    const gasEl = overlay.querySelector('#pwaEvmGasEst');
    if (gasEl) gasEl.textContent = 'Estimating…';
    const toAddr = (overlay.querySelector('#pwaEvmSendTo')?.value || '').trim();
    const amt = parseFloat(overlay.querySelector('#pwaEvmSendAmt')?.value || '0');
    if (!toAddr || !amt) { if (gasEl) gasEl.textContent = 'Enter recipient and amount first.'; return; }
    try {
      const tokenCfg = (_EVM_TOKENS[network] || {})[tokenSym];
      const [gasPriceHex, nonceHex] = await Promise.all([
        _pwaEvmRpc(network, 'eth_gasPrice', []),
        _pwaEvmRpc(network, 'eth_getTransactionCount', [evmAddr, 'pending']),
      ]);
      const gasPrice = BigInt(gasPriceHex);
      const nonce = parseInt(nonceHex, 16);
      let gasLimit = 21000n;
      if (tokenCfg) {
        const data = _pwaEncodeErc20Transfer(toAddr, amt, tokenCfg.decimals);
        try {
          const gasHex = await _pwaEvmRpc(network, 'eth_estimateGas', [{from:evmAddr, to:tokenCfg.contract, data, value:'0x0'}]);
          gasLimit = BigInt(gasHex) * 12n / 10n;
        } catch { gasLimit = 80000n; }
      }
      const nativeSym2 = {ethereum:'ETH',bnb:'BNB',arbitrum:'ETH',base:'ETH'}[network] || 'ETH';
      const feeEth = Number(gasPrice * gasLimit) / 1e18;
      if (gasEl) gasEl.textContent = `Gas fee ≈ ${feeEth.toFixed(6)} ${nativeSym2} · Nonce: ${nonce}`;
      overlay.dataset.gasPrice = gasPrice.toString();
      overlay.dataset.gasLimit = gasLimit.toString();
      overlay.dataset.nonce = nonce;
    } catch (err) {
      if (gasEl) gasEl.textContent = `Gas estimate failed: ${err.message}`;
    }
  });

  overlay.querySelector('#pwaEvmSendConfirmBtn').addEventListener('click', async () => {
    const resultEl = overlay.querySelector('#pwaEvmSendResult');
    // Re-run all guards at click time — wallet state may have changed since modal opened
    const guardCheck = await _pwaEvmSendGuard(network, evmAddr);
    if (!guardCheck.ok) {
      if (resultEl) resultEl.innerHTML = `<span style="color:#f88">${guardCheck.userMsg.replace(/\n/g,'<br>')}</span>`;
      return;
    }
    const toAddr = (overlay.querySelector('#pwaEvmSendTo')?.value || '').trim();
    const amt = parseFloat(overlay.querySelector('#pwaEvmSendAmt')?.value || '0');
    if (!toAddr || !toAddr.match(/^0x[0-9a-fA-F]{40}$/)) {
      if (resultEl) resultEl.innerHTML = '<span style="color:#f88">Invalid recipient address.</span>'; return;
    }
    if (!amt || amt <= 0) {
      if (resultEl) resultEl.innerHTML = '<span style="color:#f88">Enter a valid amount.</span>'; return;
    }
    const gasPrice = overlay.dataset.gasPrice ? BigInt(overlay.dataset.gasPrice) : null;
    const gasLimit = overlay.dataset.gasLimit ? BigInt(overlay.dataset.gasLimit) : null;
    const nonce    = overlay.dataset.nonce    ? parseInt(overlay.dataset.nonce)   : null;
    if (!gasPrice || !gasLimit || nonce === null) {
      if (resultEl) resultEl.innerHTML = '<span style="color:#f88">Click "Estimate Gas" first.</span>'; return;
    }
    if (resultEl) resultEl.innerHTML = '<span style="color:#8af">Signing and broadcasting…</span>';
    try {
      const tokenCfg = (_EVM_TOKENS[network] || {})[tokenSym];
      let txHash;
      if (tokenCfg) {
        const data = _pwaEncodeErc20Transfer(toAddr, amt, tokenCfg.decimals);
        txHash = await _pwaEvmSignAndBroadcast({ network, from:evmAddr, to:tokenCfg.contract, value:0n, data, gasLimit, gasPrice, nonce });
      } else {
        const weiAmt = BigInt(Math.round(amt * 1e18));
        txHash = await _pwaEvmSignAndBroadcast({ network, from:evmAddr, to:toAddr, value:weiAmt, data:'0x', gasLimit, gasPrice, nonce });
      }
      if (resultEl) resultEl.innerHTML = `<span style="color:#56ff9a">✓ Broadcast! TX: <span style="font-family:monospace;font-size:9px;">${txHash}</span></span>`;
      // Record in normalized history (fire-and-forget)
      const thrAddr = _pwaSigningCtx?.address || '';
      if (thrAddr) {
        const chainNorm = {bnb:'bsc',base:'base',arbitrum:'arbitrum',ethereum:'eth'}[network] || network;
        fetch('/api/wallet/evm-tx/record', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({address:thrAddr, chain:chainNorm, asset:tokenSym||'', to:toAddr, amount:amt, tx_hash:txHash, status:'submitted', direction:'out'}),
        }).catch(() => {});
      }
    } catch (err) {
      if (resultEl) resultEl.innerHTML = `<span style="color:#f88">Error: ${err.message}</span>`;
    }
  });
}

async function pwaOpenPoolDepositModal(network, evmAddr) {
  const existing = document.getElementById('pwaPoolDepositModal');
  if (existing) existing.remove();
  const poolId = _EVM_POOL_IDS[network];
  if (!poolId) { alert('No pool configured for this network.'); return; }

  const overlay = document.createElement('div');
  overlay.id = 'pwaPoolDepositModal';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.88);z-index:10001;display:flex;align-items:center;justify-content:center;padding:16px;';
  overlay.innerHTML = `
  <div style="background:#0d1520;border:1px solid #004488;border-radius:12px;padding:20px;width:100%;max-width:420px;font-size:13px;">
    <div style="font-weight:700;color:#00c8ff;margin-bottom:4px;font-size:15px;">💧 Deposit to Pythia Pool</div>
    <div style="color:#888;font-size:10px;margin-bottom:14px;">Pool: <b>${escHtml(poolId)}</b></div>
    <div id="pwaPoolVaultArea" style="margin-bottom:12px;color:#aaa;font-size:11px;">Loading vault address…</div>
    <label style="color:#aaa;font-size:11px;">Amount to deposit</label>
    <input id="pwaPoolDepositAmt" type="number" min="0" step="any" placeholder="0.00" style="width:100%;box-sizing:border-box;margin:4px 0 10px;padding:8px;background:#071220;border:1px solid #004488;border-radius:6px;color:#fff;font-size:13px;">
    <button id="pwaPoolConfirmBtn" style="width:100%;padding:10px;background:rgba(0,200,255,0.12);border:1px solid #0088cc;color:#00c8ff;border-radius:6px;cursor:pointer;font-size:13px;font-weight:700;">Confirm Deposit</button>
    <button id="pwaPoolCancelBtn" style="width:100%;margin-top:8px;padding:8px;background:none;border:1px solid #333;border-radius:6px;color:#666;font-size:11px;cursor:pointer;">Cancel</button>
    <div id="pwaPoolDepositResult" style="margin-top:10px;font-size:11px;min-height:14px;"></div>
    <div style="margin-top:12px;padding:8px;background:rgba(0,200,255,0.04);border:1px solid #002244;border-radius:6px;font-size:10px;color:#557799;">
      📌 Send the exact amount from your external wallet to the Pythia vault address above, then confirm here. Pythia vault only appears in pool deposit flows — never as your personal receive address.
    </div>
  </div>`;
  overlay.addEventListener('click', e => { if(e.target===overlay) overlay.remove(); });
  document.body.appendChild(overlay);

  overlay.querySelector('#pwaPoolCancelBtn').addEventListener('click', () => overlay.remove());

  // Fetch vault address
  try {
    const r = await fetch(`/api/pools/tvl?pool_id=${encodeURIComponent(poolId)}`);
    const d = await r.json();
    const vaultEl = overlay.querySelector('#pwaPoolVaultArea');
    if (vaultEl) {
      const vault = d.pool_vault || d.evm_bsc_address || d.evm_base_address || '';
      const asset = {bnb:'USDT', base:'USDC'}[network] || 'tokens';
      if (vault) {
        overlay.dataset.vaultAddr = vault;
        overlay.dataset.asset = asset.toUpperCase();
        vaultEl.innerHTML = `<div style="color:#aaa;">Send <b style="color:#56ff9a">${escHtml(asset)}</b> to Pythia vault:</div>`
          + `<div style="font-family:monospace;font-size:10px;background:#071220;padding:6px;border-radius:4px;margin-top:4px;color:#00c8ff;word-break:break-all;">${vault}</div>`
          + `<button id="pwaPoolCopyVault" style="margin-top:4px;padding:3px 10px;background:none;border:1px solid #004488;color:#8af;border-radius:3px;font-size:10px;cursor:pointer;">Copy address</button>`;
        overlay.querySelector('#pwaPoolCopyVault')?.addEventListener('click', async () => {
          try { await navigator.clipboard.writeText(vault); } catch {}
          const btn = overlay.querySelector('#pwaPoolCopyVault');
          if (btn) btn.textContent = '✓ Copied';
        });
      } else {
        vaultEl.textContent = 'Vault address not configured yet.';
      }
    }
  } catch {
    const vaultEl = overlay.querySelector('#pwaPoolVaultArea');
    if (vaultEl) vaultEl.textContent = 'Could not load vault address.';
  }

  overlay.querySelector('#pwaPoolConfirmBtn').addEventListener('click', async () => {
    const resultEl = overlay.querySelector('#pwaPoolDepositResult');
    const amt = parseFloat(overlay.querySelector('#pwaPoolDepositAmt')?.value || '0');
    if (!amt || amt <= 0) { if (resultEl) resultEl.innerHTML = '<span style="color:#f88">Enter a valid amount.</span>'; return; }
    const thrAddr = _pwaSigningCtx?.address || '';
    if (!thrAddr) { if (resultEl) resultEl.innerHTML = '<span style="color:#f88">Wallet not connected.</span>'; return; }
    const asset = overlay.dataset.asset || ({bnb:'USDT', base:'USDC'}[network] || 'USDT');
    const vaultAddr = overlay.dataset.vaultAddr || '';
    if (resultEl) resultEl.innerHTML = '<span style="color:#8af">Recording deposit intent…</span>';
    try {
      // Intent only — no accounting change. Shares are credited only after
      // pool_deposit_watcher confirms the on-chain transfer.
      const r = await fetch('/api/wallet/pool-deposit-intent', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({address:thrAddr, pool_id:poolId, asset, amount:amt, vault_address:vaultAddr}),
      });
      const d = await r.json();
      if (d.ok) {
        if (resultEl) resultEl.innerHTML = `<span style="color:#56ff9a">✓ Deposit intent of ${amt} ${asset} registered (intent: ${d.intent_id}). Shares are credited only after the on-chain transfer is confirmed by the pool watcher.</span>`;
      } else {
        if (resultEl) resultEl.innerHTML = `<span style="color:#f88">Error: ${d.error || 'intent_failed'}</span>`;
      }
    } catch (err) {
      if (resultEl) resultEl.innerHTML = `<span style="color:#f88">Error: ${err.message}</span>`;
    }
  });
}

// ─── Boot ─────────────────────────────────────────────────────────────────────

async function boot() {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/wallet-pwa/sw.js', { scope: '/wallet-pwa/' }).catch(() => {});
  }
  injectExtraStyles();

  const accs = getAccounts();
  if (!accs.length) { showImport(); return; }

  const active = getActiveAddr() || accs[0].address;
  setActiveAddr(active);
  await showUnlock();
}

// Expose functions referenced by inline onclick="" HTML attributes — those
// attributes execute in the global scope, but this file is loaded as an ES
// module, so top-level function declarations are NOT added to `window` by
// default. Without this, clicking these buttons throws a silent
// "X is not defined" ReferenceError and appears to do nothing.
window.showBridge = showBridge;
window.showSwap = showSwap;
window.showAddLiquidity = showAddLiquidity;
window._approveWcRequest = _approveWcRequest;
window._rejectWcRequest = _rejectWcRequest;
window.buyNFT = buyNFT;
window.pwaOpenEvmAssetActions = pwaOpenEvmAssetActions;
window.pwaOpenEvmSendModal = pwaOpenEvmSendModal;
window.pwaOpenPoolDepositModal = pwaOpenPoolDepositModal;

boot();
