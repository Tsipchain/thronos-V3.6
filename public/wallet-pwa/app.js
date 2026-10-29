Warning: truncated output (original token count: 84996)
Total output lines: 6437

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
  const [{ secp256k1 }, { sha256 }, { ripemd160 }, sha3Mod] = await Promise.all([
    import('https://esm.sh/@noble/curves@1.4.0/secp256k1'),
    import('https://esm.sh/@noble/hashes@1.4.0/sha256'),
    import('https://esm.sh/@noble/hashes@1.4.0/ripemd160'),
    import('https://esm.sh/@noble/hashes@1.4.0/sha3'),
  ]);
  const keccak_256 = sha3Mod.keccak_256 || sha3Mod.keccak256;
  _nobleLibs = { secp256k1, sha256, ripemd160, keccak_256 };
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

// ─── Unified Transaction Approval Gate ────────────────────────────────────────
// Every wallet action that touches funds (send, swap, NFT, connect, token
// creation, pool deposit, withdraw) MUST pass through this gate.
// Biometric / passkey is REQUIRED — no PIN fallback, no confirm() fallback.
// If no passkey is registered the action is blocked until the user sets one up.

async function requireTxApproval({ action, lines, address }) {
  const addr = address || getActiveAddr();
  const fid = addr ? LS.getObj(`thr_fid_${addr}`) : null;
  const hasFid = !!(fid?.credId);

  return new Promise((resolve) => {
    const overlay = document.createElement('div');
    overlay.className = 'thr-tx-approval-overlay';
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.88);z-index:10001;display:flex;align-items:center;justify-content:center;padding:16px;';

    const detailRows = (lines || []).map(
      l => `<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #1a1535">
        <span style="color:var(--muted);font-size:.78rem">${escHtml(l.label)}</span>
        <span style="color:#fff;font-size:.85rem;font-weight:600;text-align:right;max-width:60%;word-break:break-all">${escHtml(String(l.value))}</span>
      </div>`
    ).join('');

    overlay.innerHTML = `
    <div style="background:#13112a;border:1px solid #2a2050;border-radius:12px;padding:20px;width:100%;max-width:400px;">
      <div style="font-weight:700;color:#b08cf8;margin-bottom:16px;font-size:15px;text-align:center;">
        🔐 ${escHtml(action || 'Transaction')} Approval
      </div>
      <div style="background:#0d0a1a;border:1px solid #2a2050;border-radius:8px;padding:14px;margin-bottom:16px;">
        ${detailRows}
      </div>
      ${hasFid ? `
        <button id="txApproveFidBtn" class="btn btn--faceid" style="width:100%;margin-bottom:8px">${fidSvg()} Confirm with Biometric</button>
        <div style="margin:6px 0;color:var(--muted);font-size:.72rem;text-align:center">Biometric verification required for all transactions</div>
      ` : `
        <div style="background:#1a1020;border:1px solid #f8446c44;border-radius:8px;padding:14px;margin-bottom:12px;text-align:center">
          <div style="color:#f8446c;font-weight:600;margin-bottom:6px">Biometric Not Set Up</div>
          <div style="color:var(--muted);font-size:.78rem">You must register Face ID / Touch ID / passkey before approving transactions.</div>
          <button id="txApproveSetupBtn" class="btn btn--primary" style="margin-top:10px;padding:8px 20px;font-size:.82rem">Set Up Biometric Now</button>
        </div>
      `}
      <button id="txApproveCancelBtn" style="width:100%;padding:8px;background:none;border:1px solid #333;border-radius:6px;color:#666;font-size:.82rem;cursor:pointer;">Cancel</button>
      <div id="txApproveErr" style="color:#ff6b6b;font-size:.82rem;margin-top:8px;text-align:center;min-height:16px"></div>
    </div>`;

    document.body.appendChild(overlay);
    const cleanup = (result) => { overlay.remove(); resolve(result); };

    overlay.querySelector('#txApproveCancelBtn').addEventListener('click', () => cleanup(false));
    overlay.addEventListener('click', (e) => { if (e.target === overlay) cleanup(false); });

    if (hasFid) {
      overlay.querySelector('#txApproveFidBtn').addEventListener('click', async () => {
        try {
          await assertWebAuthn(fid.credId);
          cleanup(true);
        } catch {
          const errEl = overlay.querySelector('#txApproveErr');
          if (errEl) errEl.textContent = 'Biometric verification failed or cancelled';
        }
      });
    } else {
      const setupBtn = overlay.querySelector('#txApproveSetupBtn');
      if (setupBtn) {
        setupBtn.addEventListener('click', async () => {
          cleanup(false);
          if (typeof showFaceIdSetup === 'function') showFaceIdSetup(addr);
        });
      }
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
    const { secp256k1, keccak_256 } = await _loadNobleLibs();
    if (!secp256k1 || !keccak_256) return null;
    const privBytes = hexToBytes(privHex.replace(/^0x/, ''));
    // getPublicKey(false) → 65-byte uncompressed point (04 || x || y)
    const pubUncompressed = secp256k1.getPublicKey(privBytes, false);
    const pubKeyBytes = pubUncompressed.slice(1); // strip 0x04 prefix → 64 bytes
    const hash = keccak_256(pubKeyBytes);          // keccak256 of x‖y
    return '0x' + bytesToHex(hash.slice(12));      // last 20 bytes = EVM address
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
    if (raw === 0n) return 0;
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
const _USDC_BASE = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'; // 6 dec — native Circle USDC
const _USDC_ARB  = '0xaf88d065e77c8cC2239327C5EDb3A432268e5831'; // 6 dec — native Circle USDC

// EVM asset action config
const _EVM_CHAIN_IDS = { ethereum: 1, bnb: 56, arbitrum: 42161, base: 8453, polygon: 137 };
const _USDT_POLY = '0xc2132D05D31c914a87C6611C10748AEb04B58e8F'; // 6 dec
const _USDC_POLY = '0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359'; // 6 dec
const _EVM_TOKENS = {
  bnb:      { USDT: { contract: _USDT_BNB, decimals: 18 } },
  arbitrum: { USDT: { contract: _USDT_ARB, decimals: 6 }, USDC: { contract: _USDC_ARB, decimals: 6 } },
  base:     { USDC: { contract: _USDC_BASE, decimals: 6  } },
  polygon:  { USDT: { contract: _USDT_POLY, decimals: 6  }, USDC: { contract: _USDC_POLY, decimals: 6 } },
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
  const [btc, eth, bnb, arb, op, base, poly, usdtBnb, usdtArb, usdcBase, usdcArb] = await Promise.allSettled([
    _fetchBtcBalance(btcAddr),
    _fetchEvmNative(evmAddr, _CC_RPC.eth),
    _fetchEvmNative(evmAddr, _CC_RPC.bnb),
    _fetchEvmNative(evmAddr, _CC_RPC.arb),
    _fetchEvmNative(evmAddr, _CC_RPC.op),
    _fetchEvmNative(evmAddr, _CC_RPC.base),
    _fetchEvmNative(evmAddr, _CC_RPC.poly),
    _fetchErc20(evmAddr, _USDT_BNB, _CC_RPC.bnb, 18),
    _fetchErc20(evmAddr, _USDT_ARB, _CC_RPC.arb, 6),
    _fetchErc20(evmAddr, _USDC_BASE, _CC_RPC.base, 6),
    _fetchErc20(evmAddr, _USDC_ARB, _CC_RPC.arb, 6),
  ]);
  const v = r => r.status === 'fulfilled' ? r.value : null;
  return { evmAddr, btc: v(btc), eth: v(eth), bnb: v(bnb), arb: v(arb), op: v(op), base: v(base), poly: v(poly), usdtBnb: v(usdtBnb), usdtArb: v(usdtArb), usdcBase: v(usdcBase), usdcArb: v(usdcArb) };
}

async function fetchHistory(address) {
  try {
    const r = await fetch(`${API_WRITE}/wallet_data/${encodeURIComponent(address)}`);
    if (!r.ok) return [];
    const d = await r.json();
    return Array.isArray(d.transactions) ? d.transactions : [];
  } catch { return []; }
}

async function sendToken(from, to, amount, token, privKeyOverride) {
  const ws = window.walletSession;
  const tok = (token || 'THR').toUpperCase();

  if (ws && ws.buildWalletActionIntent && ws.signWalletActionIntent && !(ws.isLocked && ws.isLocked())) {
    const payload = { to: to.trim(), token: tok, amount: String(amount) };
    const intent = await ws.buildWalletActionIntent(
      'internal_transfer',
      { from_thr: from, wallet_id: from, chain: 'thronos', asset: tok, amount: String(amount), recipient: to.trim() },
      payload
    );
    const { signature, public_key } = await ws.signWalletActionIntent(intent);
    const r = await fetch(`${API_WRITE}/api/wallet/v1/transfer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ intent, signature, public_key, payload }),
    });
    const d = await r.json().catch(() => ({}));
    if (r.ok && !d.error) return d;
    throw new Error(d.error || d.message || 'send_failed');
  }

  if (privKeyOverride && !_pwaSigningCtx?.privHex) {
    _pwaSigningCtx = { address: from, privHex: privKeyOverride };
  }
  if (!_pwaSigningCtx?.privHex) {
    throw new Error('Wallet is locked — unlock with biometric/passkey first.');
  }
  return _pwaSendSignedIntent(from, to.trim(), amount, tok);
}

async function _pwaSendSignedIntent(from, recipient, amount, asset) {
  const { secp256k1, sha256 } = await _loadNobleLibs();
  const privBytes = hexToBytes(_pwaSigningCtx.privHex.replace(/^0x/, ''));
  const pubBytes = secp256k1.getPublicKey(privBytes, true);

  const intent = {
    amount: String(amount),
    asset: asset,
    asset_origin_chain: 'thronos',
    created_at: new Date().toISOString(),
    fee_asset: 'THR',
    from_thr: from,
    nonce: bytesToHex(crypto.getRandomValues(new Uint8Array(16))),
    recipient: recipient,
    type: 'thronos_internal_transfer',
    version: '1',
  };

  const fields = ['amount','asset','asset_origin_chain','created_at',
                  'fee_asset','from_thr','nonce','recipient','type','version'];
  const canonical = '{' + fields.map(k => `"${k}":${JSON.stringify(String(intent[k]))}`).join(',') + '}';
  const msgBytes = new TextEncoder().encode(canonical);
  const hash = sha256(msgBytes);

  let sig;
  if (typeof secp256k1.sign === 'function') {
    sig = secp256k1.sign(hash, privBytes, { lowS: true });
  } else {
    sig = await secp256k1.signAsync(hash, privBytes, { lowS: true });
  }

  const r = await fetch(`${API_WRITE}/api/wallet/internal-transfer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      intent,
      signature: sig.toDERHex(),
      public_key: bytesToHex(pubBytes),
    }),
  });
  const d = await r.json().catch(() => ({}));
  if (r.ok && d.ok !== false) return d;
  throw new Error(d.error || d.detail || d.message || 'send_failed');
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

function showFaceIdSetup(addr) {
  const { privHex } = unlocked.get(addr) || {};
  if (privHex) { promptFaceID(addr, privHex); return; }
  showUnlock();
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

// Wallet-local token marks with a small network badge; no third-party image requests.
function _renderCrossChainAssetMark(sym, color, network) {
  const token = String(sym || '?').toUpperCase();
  let mark = '';
  if (token === 'USDC') {
    mark = '<circle cx="20" cy="20" r="17" fill="#2775ca"/><circle cx="20" cy="20" r="12" fill="none" stroke="#fff" stroke-width="2"/><text x="20" y="26" text-anchor="middle" font-size="17" font-weight="700" fill="#fff">$</text>';
  } else if (token === 'USDT') {
    mark = '<circle cx="20" cy="20" r="17" fill="#26a17b"/><path d="M8 10H32M20 10V31M12 16C14 19 26 19 28 16" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round"/>';
  } else if (token === 'BNB') {
    mark = '<circle cx="20" cy="20" r="17" fill="#f3ba2f"/><path d="M20 5L25 10L20 15L15 10ZM10 15L15 20L10 25L5 20ZM30 15L35 20L30 25L25 20ZM20 25L25 30L20 35L15 30ZM20 16L24 20L20 24L16 20Z" fill="#fff"/>';
  } else if (token === 'ETH') {
    mark = '<circle cx="20" cy="20" r="17" fill="#627eea"/><path d="M20 4L10 21L20 26L30 21ZM20 28L10 23L20 36L30 23Z" fill="#fff" fill-opacity=".95"/>';
  } else if (token === 'BTC') {
    mark = '<circle cx="20" cy="20" r="17" fill="#f7931a"/><text x="20" y="26" text-anchor="middle" font-size="18" font-weight="700" fill="#fff">₿</text>';
  } else {
    mark = '<circle cx="20" cy="20" r="17" fill="' + color + '"/><text x="20" y="25" text-anchor="middle" font-size="14" font-weight="700" fill="#fff">' + escHtml(token.slice(0, 1)) + '</text>';
  }
  const net = ({ bnb: 'BNB', arbitrum: 'ARB', base: 'BASE', ethereum: 'ETH', bitcoin: 'BTC' })[String(network || '').toLowerCase()] || '';
  const badgeColor = net === 'ARB' ? '#28a0f0' : net === 'BASE' ? '#0052ff' : net === 'BNB' ? '#f3ba2f' : '#64748b';
  const badge = net ? '<span style="position:absolute;right:-5px;bottom:-3px;min-width:20px;height:14px;padding:0 2px;border-radius:5px;background:' + badgeColor + ';border:1px solid #0d0b18;display:flex;align-items:center;justify-content:center;color:#fff;font-size:7px;font-weight:800;letter-spacing:-.2px">' + net + '</span>' : '';
  return '<span style="position:relative;width:36px;height:36px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;margin-right:1px"><svg width="34" height="34" viewBox="0 0 40 40" aria-hidden="true">' + mark + '</svg>' + badge + '</span>';
}

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
  const rowNetwork = evmMeta?.network || (/BNB/i.test(label) ? 'bnb' : /Arbitrum/i.test(label) ? 'arbitrum' : /Base/i.test(label) ? 'base' : /Bitcoin/i.test(label) ? 'bitcoin' : /Ethereum/i.test(label) ? 'ethereum' : '');
  const assetMark = _renderCrossChainAssetMark(sym, color, rowNetwork);
  return `<div${tapClass}${tapData} style="display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:1px solid #ffffff10${tapStyle}">
    ${assetMark}
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

  // Register device for 3FA push notifications (non-blocking)
  if (typeof register3FADevice === 'function') setTimeout(register3FADevice, 1000);

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
      <div style="display:flex;align-items:center;justify-content:space-between;background:#0d0a1a;border:1px solid #2a2050;border-radius:10px;padding:12px 14px;margin-bottom:10px">
        <span id="addrLine" style="font-family:'Courier New',monospace;font-size:.95rem;color:var(--accent);cursor:pointer;letter-spacing:.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0" title="Tap to copy full address">${address}</span>
        <button onclick="document.getElementById('copyAddrBtn').click()" style="background:#1a1040;border:1px solid var(--accent);color:var(--accent);font-size:.78rem;padding:5px 12px;border-radius:6px;cursor:pointer;margin-left:8px;flex-shrink:0;font-weight:600" id="copyAddrBtn">Copy</button>
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
        <button class="action-btn" id="earnBtn"><span class="action-btn__icon">✨</span>Earn</button>
        <button class="action-btn" id="historyBtn"><span class="action-btn__icon">📋</span>History</button>
        <button class="action-btn" id="createTokenBtn"><span class="action-btn__icon">🪙</span>Create Token</button>
        <button class="action-btn" id="nftBtn"><span class="action-btn__icon">🖼️</span>NFTs</button>
        <button class="action-btn" id="epochBtn"><span class="action-btn__icon">⏳</span>Epoch</button>
        <button class="action-btn" id="withdrawBtn"><span class="action-btn__icon">💰</span>Withdraw</button>
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
  document.getElementById('earnBtn').addEventListener('click', showEarn);
  document.getElementById('createTokenBtn').addEventListener('click', showCreateToken);
  document.getElementById('nftBtn').addEventListener('click', showNFTs);
  document.getElementById('epochBtn').addEventListener('click', showEpoch);
  document.getElementById('historyBtn').addEventListener('click', () => showHistory(address));
  document.getElementById('withdrawBtn').addEventListener('click', () => showWithdraw(address));

  const setAddrBarValue = (full) => {
    const lineEl = document.getElementById('addrLine');
    if (lineEl) lineEl.textContent = full || '(unlock wallet to see)';
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

    // ── Wallet-locked guard ───────────────────────────────────────────────────
    if (!_pwaSigningCtx?.privHex) {
      setAddrBarValue('');
      el.innerHTML = '<div style="color:#ff6b6b;text-align:center;padding:24px 0">Unlock wallet to view this network address</div>';
      return;
    }

    if (netId === 'bitcoin') {
      if (!homeBtcAddr) homeBtcAddr = await _fetchBtcAddress(_pwaSigningCtx.privHex, address).catch(() => '');
      setAddrBarValue(homeBtcAddr);
      if (!homeChainBalances) homeChainBalances = await _fetchAllChainBalances(_pwaSigningCtx.privHex, homeBtcAddr).catch(() => ({}));
      el.innerHTML = `<div style="font-size:.7rem;text-transform:uppercase;letter-spacing:1px;color:var(--accent);margin-bottom:4px">Assets</div>`
        + _renderHomeAssetRow('₿', 'Bitcoin', 'BTC', homeChainBalances.btc, '#f7931a', homeBtcAddr);
      return;
    }

    // ── EVM chains — derive address ONLY from signing context, never from fallback ──
    // Re-derive on each render if not already cached to prevent stale/wrong value.
    if (!_pwaSigningCtx?.privHex) {
      setAddrBarValue('');
      el.innerHTML = '<div style="color:#ff6b6b;text-align:center;padding:24px 0;font-size:.85rem">Unlock wallet to view / send EVM assets.</div>';
      return;
    }
    if (!homeEvmAddr) {
      homeEvmAddr = await _deriveEvmAddress(_pwaSigningCtx.privHex).catch(() => null);
    }

    // Validate: derivation must succeed and must not be a blocked system address
    if (!homeEvmAddr) {
      setAddrBarValue('');
      el.innerHTML = '<div style="color:#ff6b6b;text-align:center;padding:24px 0">Unable to derive wallet EVM address — check wallet crypto library</div>';
      return;
    }
    if (_EVM_BLOCKED_SENDERS.has(homeEvmAddr.toLowerCase())) {
      setAddrBarValue('');
      homeEvmAddr = null; // do not cache the bad value
      el.innerHTML = '<div style="color:#ff6b6b;text-align:center;padding:24px 0">Address error: system address detected. Do not use this address for personal sends.</div>';
      return;
    }

    const derivedUserEvmAddr = homeEvmAddr; // confirmed valid, non-system address

    setAddrBarValue(derivedUserEvmAddr);
    if (!homeChainBalances) homeChainBalances = await _fetchAllChainBalances(_pwaSigningCtx.privHex, homeBtcAddr).catch(() => ({}));
    const bal = homeChainBalances;
    let rows = '';
    if (netId === 'ethereum') {
      rows = _renderHomeAssetRow('Ξ', 'Ethereum', 'ETH', bal.eth, '#627eea', derivedUserEvmAddr);
    } else if (netId === 'bnb') {
      rows = _renderHomeAssetRow('🔶', 'BNB Chain', 'BNB', bal.bnb, '#f3ba2f', derivedUserEvmAddr)
           + _renderHomeAssetRow('₮', 'USDT on BNB', 'USDT', bal.usdtBnb, '#26a17b', derivedUserEvmAddr,
               { network: 'bnb', sym: 'USDT', addr: derivedUserEvmAddr });
    } else if (netId === 'arbitrum') {
      rows = _renderHomeAssetRow('🔵', 'Arbitrum', 'ETH', bal.arb, '#28a0f0', derivedUserEvmAddr)
           + _renderHomeAssetRow('₮', 'USDT on Arbitrum', 'USDT', bal.usdtArb, '#26a17b', derivedUserEvmAddr,
               { network: 'arbitrum', sym: 'USDT', addr: derivedUserEvmAddr })
           + _renderHomeAssetRow('$', 'USDC on Arbitrum', 'USDC', bal.usdcArb, '#2775ca', derivedUserEvmAddr,
               { network: 'arbitrum', sym: 'USDC', addr: derivedUserEvmAddr });
    } else if (netId === 'base') {
      rows = _renderHomeAssetRow('⬛', 'Base', 'ETH', bal.base, '#0052ff', derivedUserEvmAddr)
           + _renderHomeAssetRow('$', 'USDC on Base', 'USDC', bal.usdcBase, '#2775ca', derivedUserEvmAddr,
               { network: 'base', sym: 'USDC', addr: derivedUserEvmAddr });
    }

    // Debug row (temporary) — removed once address display is confirmed correct
    const debugHtml = `<div style="margin-top:6px;padding:6px 8px;background:#0d0a1a;border:1px solid #2a2050;border-radius:6px;font-size:.65rem;color:#888;font-family:monospace;word-break:break-all">
      <div>networkDisplayedAddr: ${escHtml(derivedUserEvmAddr)}</div>
      <div>rowEvmAddr: ${escHtml(derivedUserEvmAddr)}</div>
      <div>guardDerivedAddr: (guard runs at send time)</div>
      <div>guardCode: ok when derivedAddr matches rowEvmAddr</div>
    </div>`;

    el.innerHTML = `<div style="font-size:.7rem;text-transform:uppercase;letter-spacing:1px;color:var(--accent);margin-bottom:4px">Assets</div>${rows}${debugHtml}`;
    el.querySelectorAll('.pwa-evm-row').forEach(row => {
      row.addEventListener('click', () => {
        const net  = row.dataset.evmNet;
        const sym  = row.dataset.evmSym;
        const addr = row.dataset.evmAddr;
        // Safety: only open action modal if address is the derived user address, never a system address
        if (net && sym && addr && !_EVM_BLOCKED_SENDERS.has(addr.toLowerCase())) {
          pwaOpenEvmAssetActions(net, addr, sym);
        }
      });
    });
  };

  const refreshCurrentNet = () => {
    homeChainBalances = null; // force re-fetch
    homeEvmAddr = '';         // force re-derive on refresh (clears any stale value)
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

// ─── Earn (account-first, read-only from the wallet PWA) ──────────────────────
// The Earn Account remains independent from the local wallet.  This screen only
// reads the authenticated Earn session and never creates a wallet link, moves
// THC, or presents a simulated cash-out result.
async function showEarn() {
  render(`
    <div class="screen">
      <div class="header">
        <button class="btn--icon" id="earnBackBtn" aria-label="Back">←</button>
        <span class="logo--sm">✨ Earn</span>
        <span style="margin-left:auto;font-size:.72rem;color:var(--muted)">THC rewards</span>
      </div>
      <div class="card" id="earnPwaBody" style="padding:16px;margin-top:10px">
        <p styl…34996 tokens truncated… const address = getActiveAddr();
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

            <!-- V1: wallet session must be unlocked (PIN / biometric / passkey) -->
            ${window.walletSession && !window.walletSession.isLocked?.() ? `
              <div style="background:#0a1a0a;border:1px solid #00ff6640;border-radius:8px;padding:7px 10px;margin-bottom:10px;font-size:.75rem;color:#00ff66">
                ✓ Wallet unlocked — withdrawal will be signed
              </div>
            ` : `
              <div style="background:#1a0d30;border:1px solid #b08cf840;border-radius:8px;padding:7px 10px;margin-bottom:10px;font-size:.75rem;color:#ffb81c">
                🔐 Unlock wallet with PIN or biometric to withdraw
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
              Flat 0.20 USDT/USDC fee · ~5 min
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
      const flatFee = 0.20;
      if (amount <= flatFee) {
        feeRow.innerHTML = `<span style="color:#ff6b6b">Amount must exceed ${flatFee} ${token} fee</span>`;
        return;
      }
      const net = (amount - flatFee).toFixed(4);
      feeRow.innerHTML = `You receive <b style="color:#00ff66">${net} ${token}</b> · Fee: 0.20 ${token}`;
    };
    document.getElementById('wdAmount')?.addEventListener('input', updateFeeRow);

    document.getElementById('wdMaxBtn')?.addEventListener('click', () => {
      const inp = document.getElementById('wdAmount');
      if (inp) { inp.value = parseFloat(max_wd).toFixed(2); updateFeeRow(); }
    });

    document.getElementById('wdSubmitBtn')?.addEventListener('click', async () => {
      if (submitting) return;

      const amount    = parseFloat(document.getElementById('wdAmount')?.value || 0);
      const token     = document.getElementById('wdToken')?.value || 'USDT';
      const destChain = document.getElementById('wdChain')?.value || curChain;
      const destAddr  = (document.getElementById('wdDest')?.value || '').trim().toLowerCase();
      const maxWd     = parseFloat(max_wd);

      if (!amount || amount <= 0) return renderPage('Enter a valid amount.', { token, chain: destChain });
      if (amount <= 0.20) return renderPage('Amount must exceed 0.20 fee.', { token, chain: destChain });
      if (amount > maxWd) return renderPage(`Max withdrawal is $${max_wd}.`, { token, chain: destChain });
      if (!/^0x[0-9a-f]{40}$/i.test(destAddr)) return renderPage('Enter a valid EVM wallet address (0x…).', { token, chain: destChain });

      const ws = window.walletSession;
      if (!ws || !ws.buildWalletActionIntent || !ws.signWalletActionIntent) {
        return renderPage('Unlock wallet with PIN or biometric to withdraw.', { token, chain: destChain });
      }
      if (ws.isLocked && ws.isLocked()) {
        return renderPage('Wallet is locked. Unlock with PIN or biometric first.', { token, chain: destChain });
      }

      const wdApproved = await requireTxApproval({
        action: 'Withdraw',
        address,
        lines: [
          { label: 'Amount', value: `${amount} ${token}` },
          { label: 'Chain', value: destChain },
          { label: 'To', value: destAddr },
        ],
      });
      if (!wdApproved) return;

      submitting = true;
      document.getElementById('wdSubmitBtn').textContent = 'Signing…';
      document.getElementById('wdSubmitBtn').disabled = true;

      try {
        const payload = { amount: String(amount), token, dest_chain: destChain, dest_address: destAddr };
        const intent = await ws.buildWalletActionIntent(
          'crosschain_withdraw',
          { from_thr: address, wallet_id: address, chain: destChain, asset: token, amount: String(amount), recipient: destAddr },
          payload
        );
        const { signature, public_key } = await ws.signWalletActionIntent(intent);

        document.getElementById('wdSubmitBtn').textContent = 'Processing…';

        const resp = await fetch(`${API_WRITE}/api/wallet/v1/withdraw`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ intent, signature, public_key, payload }),
        }).then(r => r.json());

        if (resp.ok) {
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
                  ID: <span style="color:#b08cf8;font-family:monospace">${resp.withdraw_id}</span>
                </div>
                <div style="display:grid;gap:5px;font-size:.8rem;text-align:left;background:#0d0a1a;border-radius:8px;padding:12px;margin-bottom:14px">
                  ${[
                    ['Token',           resp.token],
                    ['Requested',       `${resp.amount} ${resp.token}`],
                    ['You receive',     `${resp.amount_net} ${resp.token}`],
                    ['Fee',             `${resp.flat_fee} ${resp.token}`],
                    ['Chain',           resp.dest_chain_label || resp.dest_chain],
                    ['External wallet', `${destAddr.slice(0,10)}…${destAddr.slice(-6)}`],
                  ].map(([k,v]) => `
                    <div style="display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid #ffffff08">
                      <span style="color:var(--muted)">${k}</span>
                      <span style="color:${k==='You receive'?'#00ff66':k==='Fee'?'#b08cf8':'#fff'};font-weight:${k==='You receive'?700:400}">${escHtml(String(v))}</span>
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
            signed_wallet_action_required: 'Wallet signing required. Unlock with PIN or biometric.',
            payload_hash_mismatch:         'Signing error — please try again.',
            chain_not_configured:          `Chain not available. Available: ${(resp.available || []).join(', ') || '—'}`,
            token_not_supported_on_chain:  `${resp.token || 'Token'} is not supported on that chain.`,
            insufficient_pool_liquidity:   `Pool liquidity too low. Available: $${resp.available_usdt?.toFixed(2)}`,
            amount_too_small:              `Amount must exceed the 0.20 ${token} fee.`,
            exceeds_max_withdrawal:        `Max withdrawal is $${resp.max_withdrawal}.`,
          }[resp.error] || resp.error || 'Withdrawal failed. Please try again.';
          renderPage(errMsg, { token, chain: destChain });
        }
      } catch (e) {
        submitting = false;
        renderPage(e.message || 'Network error. Please try again.', { token: curToken, chain: curChain });
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
  } catch {}
  renderPage(null);
}

async function showAddLiquidity(poolId, tokenA, tokenB, poolMeta) {
  const address = getActiveAddr();

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

        if (!chain) { throw new Error('Select an external chain'); }
        if (!evmAddress) { throw new Error(`Enter your EVM address holding ${tokenB}`); }

        const ws = window.walletSession;
        if (!ws || !ws.buildWalletActionIntent) throw new Error('Unlock wallet with PIN or biometric to approve this action.');
        if (ws.isLocked && ws.isLocked()) throw new Error('Unlock wallet with PIN or biometric to approve this action.');

        const liqPayload = { pool_id: poolId, amount_a: amtA, amount_b: amtB, chain, token_contract: tokenContract, decimals, provider_thr: address, evm_address: evmAddress };
        const liqIntent = await ws.buildWalletActionIntent(
          'crosschain_add_liquidity',
          { from_thr: address, wallet_id: address, chain, asset: poolId, amount: String(amtA) },
          liqPayload
        );
        const { signature, public_key } = await ws.signWalletActionIntent(liqIntent);

        const r = await fetch(`${API_WRITE}/api/v1/pools/add-liquidity`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ intent: liqIntent, signature, public_key, payload: liqPayload }),
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
          if (d.error === 'ratio_mismatch') {
            throw new Error(`${d.message || 'Ratio mismatch'}`);
          }
          throw new Error(d.message || d.error || 'Create intent failed');
        }
      } else {
        // Internal pool path (WBTC/L2E pairs) — signed intent required
        const ws = window.walletSession;
        if (!ws || !ws.buildWalletActionIntent) throw new Error('Unlock wallet with biometric/passkey to approve this action.');
        if (ws.isLocked && ws.isLocked()) throw new Error('Unlock wallet with biometric/passkey to approve this action.');
        const liqPayload = { pool_id: poolId, amount_a: amtA, amount_b: amtB };
        const liqIntent = await ws.buildWalletActionIntent(
          'pool_deposit_intent',
          { from_thr: address, wallet_id: address, chain: 'thronos', asset: poolId, amount: String(amtA) },
          liqPayload
        );
        const { signature, public_key } = await ws.signWalletActionIntent(liqIntent);
        const liqBody = { intent: liqIntent, signature, public_key, payload: liqPayload };
        const r = await fetch(`${API_WRITE}/api/wallet/v1/add_liquidity`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(liqBody),
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
    const ws = window.walletSession;
    if (ws && ws.isLocked && ws.isLocked()) {
      errEl.textContent = 'Unlock wallet with biometric/passkey to approve this action.';
      errEl.style.display = ''; return;
    }

    const tokenApproved = await requireTxApproval({
      action: 'Create Token',
      address,
      lines: [
        { label: 'Name', value: name },
        { label: 'Symbol', value: symbol },
        { label: 'Supply', value: supply.toLocaleString() },
        { label: 'Decimals', value: String(isNaN(decimals) ? 8 : decimals) },
      ],
    });
    if (!tokenApproved) return;

    const btn = document.getElementById('tokCreateBtn');
    btn.disabled = true; btn.textContent = 'Creating…';
    try {
      const effDecimals = isNaN(decimals) ? 8 : decimals;
      if (!ws || !ws.buildWalletActionIntent) {
        errEl.textContent = 'Unlock wallet with biometric/passkey to approve this action.'; errEl.style.display = ''; btn.disabled = false; btn.textContent = 'Create Token'; return;
      }
      const tokPayload = { name, symbol, total_supply: supply, decimals: effDecimals };
      const tokIntent = await ws.buildWalletActionIntent(
        'token_create',
        { from_thr: address, wallet_id: address, chain: 'thronos', asset: symbol, amount: String(supply) },
        tokPayload
      );
      const { signature, public_key } = await ws.signWalletActionIntent(tokIntent);
      const tokBody = { intent: tokIntent, signature, public_key, payload: tokPayload };
      btn.textContent = 'Creating…';
      const r = await fetch(`${API_WRITE}/api/wallet/v1/create_token`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(tokBody),
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
      errEl.textContent = e.message === 'wallet_locked' ? 'Unlock wallet with biometric/passkey to approve this action.' : (e.message || 'Token creation failed');
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
  const ws = window.walletSession;
  if (ws && ws.isLocked && ws.isLocked()) {
    alert('Unlock wallet with biometric/passkey to approve this action.'); return;
  }
  const approved = await requireTxApproval({
    action: 'Buy NFT',
    address,
    lines: [{ label: 'NFT', value: nftId }],
  });
  if (!approved) return;
  try {
    if (!ws || !ws.buildWalletActionIntent) { alert('Unlock wallet with biometric/passkey to approve this action.'); return; }
    const buyPayload = { nft_id: nftId };
    const buyIntent = await ws.buildWalletActionIntent(
      'nft_buy',
      { from_thr: address, wallet_id: address, chain: 'thronos', asset: nftId },
      buyPayload
    );
    const { signature, public_key } = await ws.signWalletActionIntent(buyIntent);
    const buyBody = { intent: buyIntent, signature, public_key, payload: buyPayload };
    const r = await fetch(`${API_WRITE}/api/wallet/v1/nfts/buy`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(buyBody),
    });
    const d = await r.json().catch(() => ({}));
    if (r.ok && (d.ok || d.status === 'success')) {
      alert('✅ NFT purchased!');
      showNFTs();
    } else {
      throw new Error(d.message || d.error || 'failed');
    }
  } catch (e) {
    alert('Buy failed: ' + (e.message === 'wallet_locked' ? 'Unlock wallet with biometric/passkey to approve this action.' : e.message));
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
    const ws = window.walletSession;
    if (ws && ws.isLocked && ws.isLocked()) {
      errEl.textContent = 'Unlock wallet with biometric/passkey to approve this action.';
      errEl.style.display = ''; return;
    }

    const mintApproved = await requireTxApproval({
      action: 'Mint NFT',
      address,
      lines: [
        { label: 'Name', value: name },
        { label: 'Price', value: `${price} THR` },
        { label: 'Royalties', value: `${royalties}%` },
      ],
    });
    if (!mintApproved) return;

    const btn = overlay.querySelector('#nftMintBtn');
    btn.disabled = true; btn.textContent = 'Minting…';
    try {
      let image_data_url = '';
      if (file) image_data_url = await readFileAsDataUrl(file);
      if (!ws || !ws.buildWalletActionIntent) {
        errEl.textContent = 'Unlock wallet with biometric/passkey to approve this action.'; errEl.style.display = ''; btn.disabled = false; btn.textContent = 'Mint'; return;
      }
      const mintPayload = { name, description, category: 'art', price, royalties };
      const mintIntent = await ws.buildWalletActionIntent(
        'nft_mint',
        { from_thr: address, wallet_id: address, chain: 'thronos', asset: 'NFT', amount: String(price) },
        mintPayload
      );
      const { signature, public_key } = await ws.signWalletActionIntent(mintIntent);
      const mintBody = { intent: mintIntent, signature, public_key, payload: mintPayload, image_data_url };
      btn.textContent = 'Minting…';
      const r = await fetch(`${API_WRITE}/api/wallet/v1/nfts/mint`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(mintBody),
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

// ─── Auto-update toast ───────────────────────────────────────────────────────

let _updateToastShown = false;
function _showUpdateToast() {
  if (_updateToastShown) return;
  _updateToastShown = true;
  const toast = document.createElement('div');
  toast.style.cssText = 'position:fixed;bottom:16px;left:16px;right:16px;z-index:20000;background:linear-gradient(135deg,#1a1040,#0d0a1a);border:1px solid #7c5cbf;border-radius:12px;padding:14px 16px;display:flex;align-items:center;justify-content:space-between;gap:12px;box-shadow:0 8px 32px rgba(0,0,0,.6);';
  toast.innerHTML = `
    <div style="color:#e8e0ff;font-size:.88rem;flex:1">
      <div style="font-weight:700;margin-bottom:2px">Update available</div>
      <div style="color:#b08cf8;font-size:.78rem">Tap refresh to get the latest version</div>
    </div>
    <button id="updateRefreshBtn" style="background:#7c5cbf;border:none;color:#fff;padding:8px 18px;border-radius:8px;font-weight:700;font-size:.85rem;cursor:pointer;flex-shrink:0">Refresh</button>
    <button id="updateDismissBtn" style="background:none;border:none;color:#666;font-size:1.1rem;cursor:pointer;padding:4px 6px;flex-shrink:0">✕</button>`;
  document.body.appendChild(toast);
  toast.querySelector('#updateRefreshBtn').addEventListener('click', () => location.reload());
  toast.querySelector('#updateDismissBtn').addEventListener('click', () => toast.remove());
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
  const rpcKey = {ethereum:'eth',bnb:'bnb',arbitrum:'arb',base:'base',polygon:'poly'}[network];
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
  const netLabel = {ethereum:'Ethereum',bnb:'BNB Chain',arbitrum:'Arbitrum',base:'Base',polygon:'Polygon'}[network] || network;
  const tokenLabel = tokenSym || 'Assets';
  const hasPool = !!_EVM_POOL_IDS[network];
  const overlay = document.createElement('div');
  overlay.id = 'pwaEvmActionSheet';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.78);z-index:10000;display:flex;align-items:flex-end;justify-content:center;';
  const sheet = document.createElement('div');
  sheet.style.cssText = 'background:#13112a;border:1px solid #2a2050;border-radius:14px 14px 0 0;padding:20px 20px 32px;width:100%;max-width:480px;';
  sheet.innerHTML = `
    <div style="font-size:14px;font-weight:700;color:#b08cf8;margin-bottom:14px;">${escHtml(tokenLabel)} on ${escHtml(netLabel)}</div>
    <button id="pwaEvmSendBtn" disabled style="width:100%;margin-bottom:4px;padding:12px;background:rgba(176,140,248,0.04);border:1px solid #1a1535;border-radius:8px;color:#777;font-size:13px;cursor:wait;text-align:left;opacity:0.55;">💸 Send ${escHtml(tokenLabel)}<span id="pwaEvmSendBtnSub" style="display:block;font-size:10px;color:#888;margin-top:2px;">Verifying signer &amp; address…</span></button>
    <div id="pwaEvmGuardDebug" style="margin-bottom:8px;padding:5px 8px;background:rgba(0,0,0,0.3);border-radius:5px;font-size:10px;font-family:monospace;color:#666;min-height:16px;"></div>
    ${hasPool ? `<button id="pwaEvmDepositBtn" style="width:100%;margin-bottom:8px;padding:12px;background:rgba(0,200,255,0.06);border:1px solid #004466;border-radius:8px;color:#fff;font-size:13px;cursor:pointer;text-align:left;">💧 Deposit to Pool</button>` : ''}
    <button id="pwaEvmCopyBtn" style="width:100%;margin-bottom:8px;padding:12px;background:rgba(0,0,0,0.3);border:1px solid #2a2050;border-radius:8px;color:#aaa;font-size:13px;cursor:pointer;text-align:left;">📋 Copy Address (${evmAddr.slice(0,6)}…${evmAddr.slice(-4)})</button>
    <button id="pwaEvmCancelBtn" style="width:100%;padding:10px;background:none;border:1px solid #333;border-radius:8px;color:#666;font-size:12px;cursor:pointer;">Cancel</button>
  `;
  overlay.appendChild(sheet);
  overlay.addEventListener('click', e => { if(e.target===overlay) overlay.remove(); });
  document.body.appendChild(overlay);

  // Async guard check — enables Send only when all 5 guards pass
  _pwaEvmSendGuard(network, evmAddr).then(guard => {
    const btn = sheet.querySelector('#pwaEvmSendBtn');
    const sub = sheet.querySelector('#pwaEvmSendBtnSub');
    const dbg = sheet.querySelector('#pwaEvmGuardDebug');
    const code = guard.reason || (guard.ok ? 'ok' : 'unknown');
    // Safe console debug — no privHex, only public address
    console.info('[pwa-evm-send-guard]', {
      network,
      displayed: evmAddr,
      derived: guard.derivedAddr || '(not derived)',
      code,
      ok: guard.ok,
    });
    if (!btn) return;
    if (guard.ok) {
      btn.disabled = false;
      btn.style.background = 'rgba(176,140,248,0.12)';
      btn.style.border = '1px solid #b08cf8';
      btn.style.color = '#b08cf8';
      btn.style.cursor = 'pointer';
      btn.style.opacity = '1';
      if (sub) sub.remove();
      if (dbg) { dbg.style.color = '#3a3'; dbg.textContent = 'guard: ok'; }
    } else {
      btn.style.cursor = 'not-allowed';
      btn.style.opacity = '0.38';
      if (sub) sub.textContent = guard.userMsg.split('\n')[0];
      if (dbg) {
        dbg.style.color = '#f88';
        dbg.textContent = 'guard: ' + code +
          (guard.derivedAddr ? ' · derived: ' + guard.derivedAddr.slice(0,10) + '…' : '') +
          ' · displayed: ' + evmAddr.slice(0,10) + '…';
      }
    }
  }).catch(err => {
    const sub = sheet.querySelector('#pwaEvmSendBtnSub');
    const dbg = sheet.querySelector('#pwaEvmGuardDebug');
    console.info('[pwa-evm-send-guard]', { network, displayed: evmAddr, code: 'guard_threw', ok: false, error: String(err) });
    if (sub) sub.textContent = 'Signer check failed.';
    if (dbg) { dbg.style.color = '#f88'; dbg.textContent = 'guard: guard_threw · ' + String(err).slice(0, 60); }
  });

  sheet.querySelector('#pwaEvmSendBtn').addEventListener('click', (e) => {
    if (e.currentTarget.disabled) return;
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
  const netLabel = {ethereum:'Ethereum',bnb:'BNB Chain',arbitrum:'Arbitrum',base:'Base',polygon:'Polygon'}[network] || network;
  const nativeSym = {ethereum:'ETH',bnb:'BNB',arbitrum:'ETH',base:'ETH'}[network] || 'ETH';
  const sendSym = tokenSym || nativeSym;

  const overlay = document.createElement('div');
  overlay.id = 'pwaEvmSendModal';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.88);z-index:10001;display:flex;align-items:center;justify-content:center;padding:16px;';
  overlay.innerHTML = `
  <div style="background:#13112a;border:1px solid #2a2050;border-radius:12px;padding:20px;width:100%;max-width:420px;font-size:13px;">
    <div style="font-weight:700;color:#b08cf8;margin-bottom:12px;font-size:15px;">💸 Send ${escHtml(sendSym)} on ${escHtml(netLabel)}</div>
    <div style="color:#888;font-size:10px;margin-bottom:12px;">From: <span style="font-family:monospace;color:#aaa">${evmAddr}</span></div>
    <label style="color:#aaa;font-size:11px;">Recipient address (Thronos THR… or external 0x…)</label>
    <input id="pwaEvmSendTo" placeholder="THR… or 0x…" style="width:100%;box-sizing:border-box;margin:4px 0 6px;padding:8px;background:#0d0a1a;border:1px solid #2a2050;border-radius:6px;color:#fff;font-family:monospace;font-size:12px;">
    <div id="pwaRecipientBadge" style="font-size:10px;min-height:14px;margin-bottom:8px;"></div>
    <div id="pwaIntAuthRow" style="display:none;">
      <div id="pwaIntSignerStatus" style="font-size:11px;color:#aaa;margin-bottom:6px;"></div>
      <div id="pwaIntLegacyToggleRow" style="margin-top:2px;">
        <a href="#" id="pwaIntLegacyToggle" style="font-size:10px;color:#555;text-decoration:underline;">Use legacy authorization instead</a>
      </div>
      <div id="pwaIntLegacyRow" style="display:none;margin-top:6px;">
        <label style="color:#888;font-size:10px;">Legacy authorization fallback</label>
        <input id="pwaIntAuthSecret" type="password" placeholder="Your send / pledge secret" autocomplete="off" style="width:100%;box-sizing:border-box;margin:4px 0 10px;padding:8px;background:#0d0a1a;border:1px solid #2a2050;border-radius:6px;color:#fff;font-size:12px;">
      </div>
    </div>
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
      ⚠ External sends use your Thronos secp256k1 key (EIP-155). Internal transfers use server-side ledger — no chain fee needed. Private key never leaves your device.
    </div>
  </div>`;
  overlay.addEventListener('click', e => { if(e.target===overlay) overlay.remove(); });
  document.body.appendChild(overlay);

  overlay.querySelector('#pwaEvmSendCancelBtn').addEventListener('click', () => overlay.remove());

  // ── Recipient resolver ───────────────────────────────────────────────────
  let _recipientResolved = null;  // cached resolve-recipient result
  async function _resolveRecipient(addr) {
    const badge   = overlay.querySelector('#pwaRecipientBadge');
    const authRow = overlay.querySelector('#pwaIntAuthRow');
    const gasBtn  = overlay.querySelector('#pwaEvmGasBtn');
    if (!addr) { _recipientResolved = null; if (badge) badge.textContent = ''; if (authRow) authRow.style.display='none'; return; }
    if (badge) badge.textContent = '…';
    try {
      const resp = await fetch('/api/wallet/resolve-recipient', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ recipient: addr, asset: tokenSym || sendSym, chain: network }),
      });
      const r = await resp.json();
      _recipientResolved = r;
      if (r.settlement_mode === 'internal') {
        // Show internal balance so user knows what's available before entering amount
        const fromThr = window.walletSession?.getAddress?.() || '';
        let balNote = '';
        if (fromThr) {
          try {
            const chainNorm = { bnb: 'bsc', ethereum: 'eth' }[network] || network;
            const assetStr  = (tokenSym || sendSym).toUpperCase();
            const bResp = await fetch(`/api/wallet/internal-balance?thr_address=${encodeURIComponent(fromThr)}&asset=${encodeURIComponent(assetStr)}&chain=${encodeURIComponent(chainNorm)}`);
            const bData = await bResp.json();
            if (bData.ok) balNote = ` | Available: ${bData.balance} ${assetStr} (${bData.balance_source === 'bootstrap_existing_wallet_balance' ? 'from history' : 'ledger'})`;
          } catch (_) {}
        }
        if (badge) { badge.style.color='#6f8'; badge.textContent=`🏠 Internal Thronos transfer — THR fee, no chain gas needed.${balNote}`; }
        if (authRow) authRow.style.display='block';
        if (gasBtn)  gasBtn.style.display='none';
        // Update signer status text based on wallet state
        const signerStatus = overlay.querySelector('#pwaIntSignerStatus');
        if (signerStatus) {
          const ws = window.walletSession;
          if (ws && !ws.isLocked() && ws.hasRuntimeSigningMaterial()) {
            signerStatus.style.color = '#6f8';
            signerStatus.textContent = '🔐 Confirm with wallet signer (biometric / passkey)';
          } else if (ws && ws.isBound()) {
            signerStatus.style.color = '#fa8';
            signerStatus.textContent = '🔒 Wallet locked — unlock with PIN to sign internal transfer';
          } else {
            signerStatus.style.color = '#888';
            signerStatus.textContent = 'No signing key bound — use legacy authorization below';
            const legacyRow = overlay.querySelector('#pwaIntLegacyRow');
            if (legacyRow) legacyRow.style.display = 'block';
          }
        }
        // Wire legacy toggle once
        const legacyToggle = overlay.querySelector('#pwaIntLegacyToggle');
        if (legacyToggle && !legacyToggle.dataset.wired) {
          legacyToggle.dataset.wired = '1';
          legacyToggle.addEventListener('click', e => {
            e.preventDefault();
            const legacyRow = overlay.querySelector('#pwaIntLegacyRow');
            if (legacyRow) legacyRow.style.display = legacyRow.style.display === 'none' ? 'block' : 'none';
          });
        }
      } else if (r.settlement_mode === 'external_chain') {
        if (badge) { badge.style.color='#8af'; badge.textContent=`🌐 External chain send on ${netLabel} — requires native gas.`; }
        if (authRow) authRow.style.display='none';
        if (gasBtn)  gasBtn.style.display='';
      } else {
        if (badge) { badge.style.color='#f88'; badge.textContent='⚠ Recipient not recognized.'; }
        if (authRow) authRow.style.display='none';
        _recipientResolved = null;
      }
    } catch (e) {
      if (badge) { badge.style.color='#f88'; badge.textContent='Recipient lookup failed — proceeding as external.'; }
      _recipientResolved = null;
    }
  }
  const toInput = overlay.querySelector('#pwaEvmSendTo');
  if (toInput) {
    toInput.addEventListener('blur', () => _resolveRecipient(toInput.value.trim()));
    toInput.addEventListener('change', () => _resolveRecipient(toInput.value.trim()));
  }

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
    const toAddr = (overlay.querySelector('#pwaEvmSendTo')?.value || '').trim();
    const amt = parseFloat(overlay.querySelector('#pwaEvmSendAmt')?.value || '0');
    if (!toAddr) { if (resultEl) resultEl.innerHTML = '<span style="color:#f88">Enter a recipient address.</span>'; return; }
    if (!amt || amt <= 0) { if (resultEl) resultEl.innerHTML = '<span style="color:#f88">Enter a valid amount.</span>'; return; }

    // Resolve recipient if not yet resolved
    if (!_recipientResolved) await _resolveRecipient(toAddr);

    // ── Internal Thronos transfer ─────────────────────────────────────────
    if (_recipientResolved?.settlement_mode === 'internal') {
      const fromThr = window.walletSession?.getAddress?.() || '';
      if (!fromThr) { if (resultEl) resultEl.innerHTML = '<span style="color:#f88">Cannot resolve your Thronos address — unlock wallet first.</span>'; return; }

      const ws = window.walletSession;
      const legacySecret = (overlay.querySelector('#pwaIntAuthSecret')?.value || '').trim();
      const legacyVisible = (overlay.querySelector('#pwaIntLegacyRow')?.style.display !== 'none') && legacySecret;
      const canSign = ws && !ws.isLocked() && ws.hasRuntimeSigningMaterial();

      if (!canSign && !legacyVisible) {
        if (ws && ws.isBound() && ws.isLocked()) {
          if (resultEl) resultEl.innerHTML = '<span style="color:#fa8">Wallet is locked. Unlock with PIN or use legacy authorization.</span>'; return;
        }
        if (resultEl) resultEl.innerHTML = '<span style="color:#f88">Provide authorization to proceed.</span>'; return;
      }

      if (resultEl) resultEl.innerHTML = '<span style="color:#8af">Processing internal transfer…</span>';

      const assetStr  = (tokenSym || sendSym).toUpperCase();
      const chainNorm = { bnb: 'bsc', ethereum: 'eth' }[network] || network;

      let postBody;
      if (canSign) {
        // Signed intent path (primary)
        const nonce = crypto.randomUUID ? crypto.randomUUID() : (Math.random().toString(36).slice(2) + Date.now());
        const intent = {
          type: 'thronos_internal_transfer',
          version: '1',
          from_thr: fromThr,
          recipient: toAddr,
          asset: assetStr,
          asset_origin_chain: chainNorm,
          amount: String(amt),
          fee_asset: 'THR',
          nonce: String(nonce),
          created_at: new Date().toISOString(),
        };
        try {
          const { signature, public_key } = await ws.signInternalTransferIntent(intent);
          postBody = { intent, signature, public_key };
        } catch (signErr) {
          if (resultEl) resultEl.innerHTML = `<span style="color:#f88">Signing failed: ${signErr.message}. Use legacy authorization below.</span>`;
          return;
        }
      } else {
        // Legacy fallback
        postBody = {
          from_thr: fromThr, recipient: toAddr,
          asset: assetStr, asset_origin_chain: chainNorm, amount: amt,
          auth_secret: legacySecret,
        };
      }

      try {
        const r = await fetch('/api/wallet/internal-transfer', {
          method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify(postBody),
        });
        const res = await r.json();
        if (res.ok) {
          if (resultEl) resultEl.innerHTML = `<span style="color:#6f8">✓ Internal transfer confirmed — ID: ${res.transfer_id}</span>`;
          setTimeout(() => overlay.remove(), 2500);
        } else {
          if (resultEl) resultEl.innerHTML = `<span style="color:#f88">Transfer failed: ${res.error || 'unknown error'}</span>`;
        }
      } catch (e) {
        if (resultEl) resultEl.innerHTML = `<span style="color:#f88">Transfer error: ${e.message}</span>`;
      }
      return;
    }

    // ── External chain send — original EVM signing flow ───────────────────
    // Re-run all guards at click time — wallet state may have changed since modal opened
    const guardCheck = await _pwaEvmSendGuard(network, evmAddr);
    if (!guardCheck.ok) {
      if (resultEl) resultEl.innerHTML = `<span style="color:#f88">${guardCheck.userMsg.replace(/\n/g,'<br>')}</span>`;
      return;
    }
    if (!toAddr.match(/^0x[0-9a-fA-F]{40}$/)) {
      if (resultEl) resultEl.innerHTML = '<span style="color:#f88">External sends require a 0x EVM address.</span>'; return;
    }
    const gasPrice = overlay.dataset.gasPrice ? BigInt(overlay.dataset.gasPrice) : null;
    const gasLimit = overlay.dataset.gasLimit ? BigInt(overlay.dataset.gasLimit) : null;
    const nonce    = overlay.dataset.nonce    ? parseInt(overlay.dataset.nonce)   : null;
    if (!gasPrice || !gasLimit || nonce === null) {
      if (resultEl) resultEl.innerHTML = '<span style="color:#f88">Click "Estimate Gas" first.</span>'; return;
    }

    // ── Biometric/passkey confirmation before broadcast — REQUIRED ──────────
    const evmApproved = await requireTxApproval({
      action: 'External Send',
      address: _pwaSigningCtx?.address || '',
      lines: [
        { label: 'Amount', value: `${amt} ${tokenSym || sendSym}` },
        { label: 'To', value: toAddr },
        { label: 'Network', value: network },
      ],
    });
    if (!evmApproved) {
      if (resultEl) resultEl.innerHTML = '<span style="color:#f88">Send cancelled — biometric approval required.</span>';
      return;
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
    <div style="color:#888;font-size:10px;margin-bottom:8px;">Pool: <b>${escHtml(poolId)}</b> · Both sides required (AMM)</div>
    <div id="pwaPoolRatioArea" style="margin-bottom:10px;color:#8af;font-size:10px;">Loading pool ratio…</div>
    <div id="pwaPoolVaultArea" style="margin-bottom:12px;color:#aaa;font-size:11px;">Loading vault address…</div>
    <label style="color:#aaa;font-size:11px;" id="pwaPoolExtLabel">External amount (USDT)</label>
    <input id="pwaPoolDepositAmt" type="number" min="0" step="any" placeholder="0.00" style="width:100%;box-sizing:border-box;margin:4px 0 10px;padding:8px;background:#071220;border:1px solid #004488;border-radius:6px;color:#fff;font-size:13px;">
    <label style="color:#aaa;font-size:11px;">THR amount (auto-calculated from pool ratio)</label>
    <input id="pwaPoolDepositThrAmt" type="number" min="0" step="any" placeholder="0.00" readonly style="width:100%;box-sizing:border-box;margin:4px 0 10px;padding:8px;background:#0a0f18;border:1px solid #234;color:#aaa;font-size:13px;">
    <button id="pwaPoolBroadcastBtn" style="width:100%;padding:10px;background:rgba(0,200,255,0.16);border:1px solid #00c8ff;color:#00c8ff;border-radius:6px;cursor:pointer;font-size:13px;font-weight:700;">🔐 Add liquidity — biometric confirm</button>
    <button id="pwaPoolConfirmBtn" style="width:100%;margin-top:6px;padding:8px;background:none;border:1px solid #234;color:#78a;border-radius:6px;cursor:pointer;font-size:11px;">I sent externally — record intent only</button>
    <button id="pwaPoolCancelBtn" style="width:100%;margin-top:8px;padding:8px;background:none;border:1px solid #333;border-radius:6px;color:#666;font-size:11px;cursor:pointer;">Cancel</button>
    <div id="pwaPoolDepositResult" style="margin-top:10px;font-size:11px;min-height:14px;"></div>
    <div style="margin-top:12px;padding:8px;background:rgba(0,200,255,0.04);border:1px solid #002244;border-radius:6px;font-size:10px;color:#557799;">
      📌 Adding liquidity requires <b>both sides</b>: your external (USDT/USDC) plus proportional THR at the current pool ratio. The USDT/USDC is broadcast to the Pythia vault on-chain; the THR is debited internally on Thronos. LP shares appear after the on-chain watcher confirms.
    </div>
  </div>`;
  overlay.addEventListener('click', e => { if(e.target===overlay) overlay.remove(); });
  document.body.appendChild(overlay);

  overlay.querySelector('#pwaPoolCancelBtn').addEventListener('click', () => overlay.remove());

  // Fetch vault address + pool ratio (both sides required for AMM add-liq)
  let poolRatio = null;
  try {
    const r = await fetch(`/api/pools/tvl?pool_id=${encodeURIComponent(poolId)}`);
    const d = await r.json();
    const vaultEl = overlay.querySelector('#pwaPoolVaultArea');
    const ratioEl = overlay.querySelector('#pwaPoolRatioArea');
    const extLabelEl = overlay.querySelector('#pwaPoolExtLabel');
    const asset = {bnb:'USDT', base:'USDC'}[network] || 'tokens';
    if (extLabelEl) extLabelEl.textContent = `External amount (${asset})`;

    // Pool ratio for auto-calculating THR side
    const extRes = Number(d.external_reserve || 0);
    const thrRes = Number(d.thr_reserve || 0);
    if (extRes > 0 && thrRes > 0) {
      poolRatio = thrRes / extRes; // THR per 1 external
      overlay.dataset.poolRatio = String(poolRatio);
      if (ratioEl) ratioEl.textContent = `Current pool ratio: 1 ${asset} ↔ ${poolRatio.toFixed(4)} THR`;
    } else if (ratioEl) {
      // Empty pool → first depositor sets the ratio
      ratioEl.textContent = 'Pool is empty — first liquidity sets the ratio. Enter both amounts manually.';
      const thrInput = overlay.querySelector('#pwaPoolDepositThrAmt');
      if (thrInput) { thrInput.readOnly = false; thrInput.style.background = '#071220'; thrInput.style.color = '#fff'; thrInput.style.borderColor = '#004488'; }
    }

    if (vaultEl) {
      const vault = d.pool_vault || d.evm_bsc_address || d.evm_base_address || '';
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

  // Auto-calculate THR amount as user types external amount
  overlay.querySelector('#pwaPoolDepositAmt')?.addEventListener('input', (e) => {
    const extAmt = parseFloat(e.target.value || '0');
    const ratio = parseFloat(overlay.dataset.poolRatio || '0');
    const thrInput = overlay.querySelector('#pwaPoolDepositThrAmt');
    if (ratio > 0 && extAmt > 0 && thrInput) {
      thrInput.value = (extAmt * ratio).toFixed(6);
    }
  });

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

  // ── In-app broadcast path — sign & send from this wallet, biometric-gated ──
  overlay.querySelector('#pwaPoolBroadcastBtn').addEventListener('click', async () => {
    const resultEl = overlay.querySelector('#pwaPoolDepositResult');
    const amt = parseFloat(overlay.querySelector('#pwaPoolDepositAmt')?.value || '0');
    const thrAmt = parseFloat(overlay.querySelector('#pwaPoolDepositThrAmt')?.value || '0');
    if (!amt || amt <= 0) { if (resultEl) resultEl.innerHTML = '<span style="color:#f88">Enter a valid external amount.</span>'; return; }
    if (!thrAmt || thrAmt <= 0) { if (resultEl) resultEl.innerHTML = '<span style="color:#f88">THR amount is required — AMM add-liquidity needs both sides.</span>'; return; }
    const thrAddr = _pwaSigningCtx?.address || '';
    if (!thrAddr) { if (resultEl) resultEl.innerHTML = '<span style="color:#f88">Wallet not connected.</span>'; return; }
    const asset = overlay.dataset.asset || ({bnb:'USDT', base:'USDC'}[network] || 'USDT');
    const vaultAddr = overlay.dataset.vaultAddr || '';
    if (!vaultAddr) { if (resultEl) resultEl.innerHTML = '<span style="color:#f88">Vault address not loaded — cannot broadcast.</span>'; return; }

    // Re-run send guard: ensure signer key matches displayed EVM address
    const guardCheck = await _pwaEvmSendGuard(network, evmAddr);
    if (!guardCheck.ok) {
      if (resultEl) resultEl.innerHTML = `<span style="color:#f88">${guardCheck.userMsg.replace(/\n/g,'<br>')}</span>`;
      return;
    }

    // ── Biometric / passkey confirmation — REQUIRED ──
    const poolApproved = await requireTxApproval({
      action: 'Pool Deposit',
      address: thrAddr,
      lines: [
        { label: 'External', value: `${amt} ${asset}` },
        { label: 'THR', value: String(thrAmt) },
        { label: 'Pool', value: poolId },
      ],
    });
    if (!poolApproved) {
      if (resultEl) resultEl.innerHTML = '<span style="color:#f88">Deposit cancelled — biometric approval required.</span>';
      return;
    }

    if (resultEl) resultEl.innerHTML = '<span style="color:#8af">Estimating gas…</span>';
    try {
      const tokenCfg = (_EVM_TOKENS[network] || {})[asset];
      if (!tokenCfg) { if (resultEl) resultEl.innerHTML = `<span style="color:#f88">No token config for ${asset} on ${network}.</span>`; return; }

      const [gasPriceHex, nonceHex] = await Promise.all([
        _pwaEvmRpc(network, 'eth_gasPrice', []),
        _pwaEvmRpc(network, 'eth_getTransactionCount', [evmAddr, 'pending']),
      ]);
      const gasPrice = BigInt(gasPriceHex);
      const nonceVal = parseInt(nonceHex, 16);
      const data = _pwaEncodeErc20Transfer(vaultAddr, amt, tokenCfg.decimals);
      let gasLimit = 80000n;
      try {
        const gasHex = await _pwaEvmRpc(network, 'eth_estimateGas', [{from:evmAddr, to:tokenCfg.contract, data, value:'0x0'}]);
        gasLimit = BigInt(gasHex) * 12n / 10n;
      } catch {}

      if (resultEl) resultEl.innerHTML = '<span style="color:#8af">Signing and broadcasting to vault…</span>';
      const txHash = await _pwaEvmSignAndBroadcast({ network, from:evmAddr, to:tokenCfg.contract, value:0n, data, gasLimit, gasPrice, nonce:nonceVal });
      if (resultEl) resultEl.innerHTML = `<span style="color:#56ff9a">✓ Broadcast! TX: <span style="font-family:monospace;font-size:9px;">${txHash}</span><br>Recording intent…</span>`;

      // Record intent with tx_hash so the pool_deposit_watcher can match this
      // event and credit LP shares to `thrAddr` once confirmed on-chain.
      try {
        const chainNorm = {bnb:'bsc',base:'base',arbitrum:'arbitrum',ethereum:'eth'}[network] || network;
        const r = await fetch('/api/wallet/pool-deposit-intent', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({
            address: thrAddr, pool_id: poolId, asset, amount: amt,
            vault_address: vaultAddr, tx_hash: txHash, sender_address: evmAddr,
          }),
        });
        const d = await r.json().catch(() => ({}));
        if (d.ok) {
          if (resultEl) resultEl.innerHTML = `<span style="color:#56ff9a">✓ Deposit broadcast + intent recorded (${d.intent_id}). LP shares will appear once the on-chain watcher confirms.</span>`;
        }
      } catch {}

      // Also register in normalized wallet history (fire-and-forget)
      try {
        const chainNorm = {bnb:'bsc',base:'base',arbitrum:'arbitrum',ethereum:'eth'}[network] || network;
        fetch('/api/wallet/evm-tx/record', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({address:thrAddr, chain:chainNorm, asset, to:vaultAddr, amount:amt, tx_hash:txHash, status:'submitted', direction:'out'}),
        }).catch(() => {});
      } catch {}

      // ── THR side (internal debit) — submit proportional THR deposit ──
      // Real AMM: LP requires BOTH sides. USDT/USDC broadcast to vault above,
      // THR debited from user's Thronos balance and credited to pool thr_reserve.
      try {
        if (resultEl) resultEl.innerHTML = `<span style="color:#8af">Debiting proportional THR (${thrAmt})…</span>`;
        const r = await fetch('/api/pools/deposit', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ address: thrAddr, pool_id: poolId, side: 'internal', asset: 'THR', amount: thrAmt }),
        });
        const d = await r.json().catch(() => ({}));
        if (r.ok && d.ok) {
          if (resultEl) resultEl.innerHTML = `<span style="color:#56ff9a">✓ Both sides submitted!<br>External: ${amt} ${asset} (tx ${txHash.slice(0,10)}…)<br>THR: ${thrAmt} debited internally.<br>LP shares appear once watcher confirms USDT on-chain.</span>`;
        } else if (d.error === 'insufficient_thr_balance') {
          if (resultEl) resultEl.innerHTML = `<span style="color:#fa8">USDT sent on-chain ✓ but THR debit failed: insufficient balance (${d.balance} < ${d.required}). Please deposit the missing THR side manually via internal transfer once your balance is topped up.</span>`;
        } else {
          if (resultEl) resultEl.innerHTML = `<span style="color:#fa8">USDT sent on-chain ✓ but THR side failed: ${d.error || d.message || 'unknown'}. Retry the THR deposit manually.</span>`;
        }
      } catch (err) {
        if (resultEl) resultEl.innerHTML = `<span style="color:#fa8">USDT sent on-chain ✓ but THR side error: ${err.message}</span>`;
      }
    } catch (err) {
      if (resultEl) resultEl.innerHTML = `<span style="color:#f88">Error: ${err.message}</span>`;
    }
  });
}

// ─── Boot ─────────────────────────────────────────────────────────────────────

async function boot() {
  if ('serviceWorker' in navigator) {
    const reg = await navigator.serviceWorker.register('/wallet-pwa/sw.js', { scope: '/wallet-pwa/' }).catch(() => null);
    if (reg) {
      reg.addEventListener('updatefound', () => {
        const nw = reg.installing;
        if (!nw) return;
        nw.addEventListener('statechange', () => {
          if (nw.state === 'activated' && navigator.serviceWorker.controller) {
            _showUpdateToast();
          }
        });
      });
      // Check for SW updates now and every 10 minutes
      reg.update().catch(() => {});
      setInterval(() => reg.update().catch(() => {}), 10 * 60 * 1000);
    }
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      if (document.visibilityState === 'visible') _showUpdateToast();
    });
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
window.showFaceIdSetup = showFaceIdSetup;
window.showPools = typeof showPools === 'function' ? showPools : () => {};

// ─── 3FA Push Notification Registration & Approval Handling ─────────────────

const VAPID_PUBLIC_KEY = localStorage.getItem('thr_vapid_public') || '';

async function register3FADevice() {
  const addr = getActiveAddr();
  if (!addr || !('serviceWorker' in navigator) || !('PushManager' in window)) return;

  try {
    const reg = await navigator.serviceWorker.ready;
    let sub = await reg.pushManager.getSubscription();
    if (!sub && VAPID_PUBLIC_KEY) {
      const key = Uint8Array.from(atob(VAPID_PUBLIC_KEY.replace(/-/g,'+').replace(/_/g,'/')), c => c.charCodeAt(0));
      sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key });
    }
    if (!sub) return;

    const deviceId = localStorage.getItem('thr_device_id') || crypto.randomUUID();
    localStorage.setItem('thr_device_id', deviceId);

    const biometric = !!(navigator.credentials && navigator.credentials.create);

    await fetch('/api/3fa/device/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        wallet: addr,
        device_id: deviceId,
        device_name: navigator.userAgent.slice(0, 60),
        push_subscription: sub.toJSON(),
        biometric_capable: biometric,
      }),
    });
  } catch (_) { /* silent — 3FA registration is optional */ }
}

async function handle3FAApproval(approvalId, action) {
  const addr = getActiveAddr();
  const deviceId = localStorage.getItem('thr_device_id') || '';
  if (!addr || !deviceId) return;

  if (action === 'deny') {
    const resp = await fetch('/api/3fa/approval/deny', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ approval_id: approvalId, device_id: deviceId }),
    });
    return resp.json();
  }

  const approved = await requireTxApproval({
    action: '3FA Approval',
    address: addr,
    lines: [{ label: 'Approval ID', value: approvalId }],
  });
  if (!approved) return { ok: false, error: 'biometric_denied' };

  const resp = await fetch('/api/3fa/approval/approve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ approval_id: approvalId, device_id: deviceId }),
  });
  return resp.json();
}

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.addEventListener('message', async (e) => {
    if (e.data && e.data.type === '3fa_action') {
      const { approval_id, user_action } = e.data;
      if (user_action === 'approve' || user_action === 'deny') {
        await handle3FAApproval(approval_id, user_action);
      } else {
        const details = e.data.details || {};
        const tfaLines = [];
        if (details.action) tfaLines.push({ label: 'Action', value: details.action });
        if (details.amount) tfaLines.push({ label: 'Amount', value: `${details.amount} THR` });
        if (details.to) tfaLines.push({ label: 'To', value: details.to });
        tfaLines.push({ label: 'Approval ID', value: approval_id });

        const approved = await requireTxApproval({
          action: details.action || 'Transaction',
          lines: tfaLines,
        });
        await handle3FAApproval(approval_id, approved ? 'approve' : 'deny');
      }
    }
  });

  const params = new URLSearchParams(location.search);
  const tfa3 = params.get('3fa');
  const tfaAction = params.get('action');
  if (tfa3) {
    setTimeout(() => handle3FAApproval(tfa3, tfaAction || 'open'), 500);
  }
}

window.register3FADevice = register3FADevice;
window.handle3FAApproval = handle3FAApproval;

boot();
