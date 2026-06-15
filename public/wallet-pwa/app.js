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

function upsertAccount(address, kit, label) {
  const accs = getAccounts();
  const idx = accs.findIndex(a => a.address === address);
  const entry = { address, kit: typeof kit === 'string' ? kit : JSON.stringify(kit), label: label || shortAddr(address) };
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

const API_READ  = 'https://api.thronoschain.org';  // write node knows migration mapping
const API_WRITE = 'https://api.thronoschain.org';

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

      <div style="display:flex;gap:6px;margin-bottom:10px">
        <button class="btn" id="tabKit" style="flex:1;padding:8px;font-size:.82rem;background:var(--accent);color:#fff;border-radius:10px">Recovery Kit</button>
        <button class="btn btn--ghost" id="tabPledge" style="flex:1;padding:8px;font-size:.82rem;border-radius:10px">Pledge Secret</button>
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

  // Tab switching
  document.getElementById('tabKit').addEventListener('click', () => {
    document.getElementById('paneKit').style.display = '';
    document.getElementById('panePledge').style.display = 'none';
    document.getElementById('tabKit').style.background = 'var(--accent)';
    document.getElementById('tabKit').style.color = '#fff';
    document.getElementById('tabPledge').style.background = '';
    document.getElementById('tabPledge').style.color = '';
  });
  document.getElementById('tabPledge').addEventListener('click', () => {
    document.getElementById('paneKit').style.display = 'none';
    document.getElementById('panePledge').style.display = '';
    document.getElementById('tabPledge').style.background = 'var(--accent)';
    document.getElementById('tabPledge').style.color = '#fff';
    document.getElementById('tabKit').style.background = '';
    document.getElementById('tabKit').style.color = '';
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

      // Store account — include kit if server returned Recovery Kit
      const kitObj = d.recovery_kit ? (() => { try { return JSON.parse(d.recovery_kit); } catch { return { canonical_v1_address: canonical }; } })() : { canonical_v1_address: canonical };
      upsertAccount(canonical, kitObj, shortAddr(canonical));
      setActiveAddr(canonical);

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
      await promptFaceID(canonical, null);
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
    await showWallet();
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

async function showWallet() {
  const address = getActiveAddr();
  if (!address || !unlocked.has(address)) { showUnlock(); return; }

  const accs = getAccounts();
  const acc = getAccount(address);
  const label = acc?.label || shortAddr(address);

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

      <!-- Address bar -->
      <div style="display:flex;align-items:center;justify-content:space-between;background:#0d0a1a;border-radius:8px;padding:8px 12px;margin-bottom:10px">
        <span id="addrLine" style="font-family:monospace;font-size:.8rem;color:var(--accent);cursor:pointer" title="Tap to copy">${shortAddr(address)}</span>
        <button onclick="document.getElementById('copyAddrBtn').click()" style="background:none;border:1px solid var(--accent);color:var(--accent);font-size:.7rem;padding:2px 8px;border-radius:4px;cursor:pointer" id="copyAddrBtn">Copy</button>
      </div>

      <!-- Balances + Token list -->
      <div class="card" style="padding:12px;margin-bottom:10px">
        <div id="balancesArea">
          <div class="balance-amount balance-amount--loading">···</div>
        </div>
      </div>

      <!-- Quick actions — matches web wallet -->
      <div class="actions mt8" style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:10px">
        <button class="action-btn" id="sendBtn"><span class="action-btn__icon">💸</span>Send</button>
        <button class="action-btn" id="receiveBtn"><span class="action-btn__icon">📥</span>Receive</button>
        <button class="action-btn" id="tokensBtn"><span class="action-btn__icon">◈</span>Tokens</button>
        <button class="action-btn" id="connectBtn"><span class="action-btn__icon">⬡</span>Connect</button>
        <button class="action-btn" id="musicBtn"><span class="action-btn__icon">🎵</span>Music</button>
        <button class="action-btn" id="historyBtn"><span class="action-btn__icon">📋</span>History</button>
      </div>

      <div class="tx-feed" id="txFeed" style="display:none">
        <div class="tx-feed__title">Recent Activity</div>
        <div id="txList"><p style="color:var(--muted);font-size:.88rem">Loading…</p></div>
      </div>
    </div>
  `);

  document.getElementById('addrLine').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(address); } catch {}
    const el = document.getElementById('addrLine');
    if (el) { el.textContent = 'Copied!'; setTimeout(() => { if (el) el.textContent = shortAddr(address); }, 1500); }
  });
  document.getElementById('copyAddrBtn').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(address); } catch {}
    const b = document.getElementById('copyAddrBtn');
    if (b) { b.textContent = '✓'; setTimeout(() => { if (b) b.textContent = 'Copy'; }, 1500); }
  });

  document.getElementById('lockBtn').addEventListener('click', () => {
    sessionStorage.removeItem(`thr_sk_${address}`);
    unlocked.delete(address);
    showUnlock();
  });

  document.getElementById('accBtn')?.addEventListener('click', showAccountPicker);
  document.getElementById('addAccBtn').addEventListener('click', () => showImport(true));
  document.getElementById('sendBtn').addEventListener('click', showSend);
  document.getElementById('receiveBtn').addEventListener('click', showReceive);
  document.getElementById('tokensBtn').addEventListener('click', showTokens);
  document.getElementById('connectBtn').addEventListener('click', showWalletConnect);
  document.getElementById('musicBtn').addEventListener('click', showMusic);
  document.getElementById('historyBtn').addEventListener('click', () => {
    const feed = document.getElementById('txFeed');
    if (feed) feed.style.display = feed.style.display === 'none' ? '' : 'none';
    if (feed?.style.display !== 'none') {
      fetchHistory(address).then(txs => {
        const el = document.getElementById('txList');
        if (!el) return;
        if (!txs.length) { el.innerHTML = '<p style="color:var(--muted);font-size:.88rem">No transactions yet.</p>'; return; }
        el.innerHTML = txs.slice(0, 20).map(tx => {
          const isIn = (tx.to || '').toUpperCase() === address;
          const dir = isIn ? 'in' : 'out';
          const peer = isIn ? (tx.from || '').slice(0, 10) : (tx.to || '').slice(0, 10);
          const sym = tx.token || 'THR';
          const amt = tx.amount ? `${isIn ? '+' : '-'}${tx.amount} ${sym}` : '';
          const date = tx.timestamp ? new Date(tx.timestamp * 1000).toLocaleDateString() : '';
          return `<div class="tx-item">
            <div class="tx-item__dir tx-item__dir--${dir}">${isIn ? '↓' : '↑'}</div>
            <div class="tx-item__info"><div class="tx-item__label">${isIn ? 'From' : 'To'} ${peer}…</div><div class="tx-item__date">${date}</div></div>
            <div class="tx-item__amount tx-item__amount--${dir}">${amt}</div>
          </div>`;
        }).join('');
      });
    }
  });

  // Load balances — same API as web wallet
  fetchBalances(address).then(data => {
    const el = document.getElementById('balancesArea');
    if (!el) return;
    const tokens = Array.isArray(data?.tokens) ? data.tokens : [];
    const thrTok = tokens.find(t => t.symbol === 'THR');
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

// ── WalletConnect — sign from mobile without re-importing Recovery Kit ─────────
// Architecture: lightweight custom relay (no WalletConnect server needed).
// ThronosBuilder posts a sign request to /api/wallet/wc/request keyed by address.
// PWA polls for pending requests, shows Face ID prompt, signs, posts signature back.
// For full WalletConnect v2 URI support (wc://...), we parse the pairing topic
// and connect to the Thronos relay endpoint.

const WC_POLL_INTERVAL = 4000; // ms
let _wcPollTimer = null;

function showWalletConnect() {
  const address = getActiveAddr();
  render(`
    <div class="screen">
      <div class="card">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
          <h2 style="font-size:1.1rem;margin:0">⬡ Connect dApp</h2>
          <button class="btn btn--ghost" id="wcBackBtn" style="padding:6px 12px;font-size:.85rem">← Back</button>
        </div>
        <p style="color:var(--muted);font-size:.85rem;margin-bottom:14px">
          Scan a QR code or paste a <b>wc://</b> URI from ThronosBuilder or any compatible dApp to sign transactions from this wallet.
        </p>

        <div style="margin-bottom:12px">
          <label style="font-size:.85rem;color:var(--accent);display:block;margin-bottom:6px">Paste WC URI or connection code</label>
          <textarea id="wcUri" class="input" rows="3" placeholder="wc:// or thrconnect://..." style="font-family:monospace;font-size:.78rem;resize:none"></textarea>
          <button class="btn btn--primary mt8" id="wcConnectBtn" style="width:100%">🔗 Connect</button>
        </div>

        <div style="text-align:center;color:var(--muted);font-size:.82rem;margin:10px 0">— OR —</div>

        <div style="background:#0d0a1a;border:1px solid var(--accent);border-radius:8px;padding:12px;text-align:center">
          <div style="font-size:.82rem;color:var(--muted);margin-bottom:8px">Waiting for sign requests from connected dApps…</div>
          <div id="wcStatus" style="font-size:.85rem;color:var(--accent)">● Polling for requests…</div>
          <div id="wcRequestArea" style="margin-top:10px"></div>
        </div>

        <div style="margin-top:14px;padding:10px;background:#0a0a14;border-radius:6px;font-size:.78rem;color:var(--muted)">
          <b style="color:var(--accent)">Your wallet address:</b><br>
          <span style="font-family:monospace;word-break:break-all">${address}</span>
        </div>
      </div>
    </div>
  `);

  document.getElementById('wcBackBtn').addEventListener('click', showWallet);

  document.getElementById('wcConnectBtn').addEventListener('click', async () => {
    const uri = document.getElementById('wcUri')?.value?.trim();
    if (!uri) { alert('Paste a WC URI first'); return; }
    const statusEl = document.getElementById('wcStatus');

    // Handle thrconnect:// (our custom relay protocol)
    if (uri.startsWith('thrconnect://') || uri.startsWith('thr://')) {
      const sessionId = uri.replace(/^(thrconnect|thr):\/\//, '');
      statusEl.textContent = `✅ Connected (session: ${sessionId.slice(0,8)}…)`;
      sessionStorage.setItem('thr_wc_session', sessionId);
      _startWcPoll(address, sessionId);
      return;
    }

    // Handle wc:// URI — extract topic and relay server
    if (uri.startsWith('wc:')) {
      try {
        // wc:<topic>@<version>?relay-protocol=...&symKey=...
        const topic = uri.split('@')[0].replace('wc:', '');
        statusEl.textContent = `🔗 WC pairing: ${topic.slice(0,8)}…`;
        // Register with our relay
        const r = await fetch(`${API_WRITE}/api/wallet/wc/pair`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ address, wc_uri: uri, topic })
        });
        const d = await r.json().catch(() => ({}));
        if (d.ok) {
          statusEl.textContent = `✅ Paired — waiting for sign requests`;
          _startWcPoll(address, d.session_id || topic);
        } else {
          statusEl.textContent = `⚠️ Pair failed: ${d.error || 'unknown'}`;
        }
      } catch(e) {
        statusEl.textContent = `⚠️ Error: ${e.message}`;
      }
      return;
    }

    alert('Unknown URI format. Expected wc:// or thrconnect://');
  });

  // Start polling immediately
  _startWcPoll(address, sessionStorage.getItem('thr_wc_session') || null);
}

function _startWcPoll(address, sessionId) {
  if (_wcPollTimer) clearInterval(_wcPollTimer);
  _wcPollTimer = setInterval(() => _checkWcRequests(address, sessionId), WC_POLL_INTERVAL);
  _checkWcRequests(address, sessionId); // immediate first check
}

async function _checkWcRequests(address, sessionId) {
  const reqArea = document.getElementById('wcRequestArea');
  const statusEl = document.getElementById('wcStatus');
  if (!reqArea) { clearInterval(_wcPollTimer); return; }
  try {
    const url = sessionId
      ? `${API_WRITE}/api/wallet/wc/requests?address=${encodeURIComponent(address)}&session=${encodeURIComponent(sessionId)}`
      : `${API_WRITE}/api/wallet/wc/requests?address=${encodeURIComponent(address)}`;
    const r = await fetch(url);
    if (!r.ok) return;
    const d = await r.json().catch(() => ({}));
    const requests = d.requests || [];
    if (!requests.length) {
      statusEl.textContent = '● Polling — no pending requests';
      reqArea.innerHTML = '';
      return;
    }
    statusEl.textContent = `🔔 ${requests.length} sign request(s) pending`;
    reqArea.innerHTML = requests.map(req => `
      <div style="background:#0a0014;border:1px solid var(--accent);border-radius:8px;padding:10px;margin-bottom:8px">
        <div style="font-size:.82rem;color:#ccc;margin-bottom:6px">
          <b style="color:var(--accent)">${req.action || 'Sign Request'}</b>
          ${req.dapp ? `— from <b>${req.dapp}</b>` : ''}
        </div>
        <div style="font-size:.78rem;color:var(--muted);font-family:monospace;word-break:break-all;margin-bottom:8px">
          ${(req.payload_preview || JSON.stringify(req.payload || {})).slice(0,120)}…
        </div>
        <div style="display:flex;gap:6px">
          <button class="btn btn--primary" style="flex:2;padding:8px;font-size:.82rem" onclick="_approveWcRequest('${req.id}', '${address}')">
            🔐 Approve (Face ID)
          </button>
          <button class="btn btn--ghost" style="flex:1;padding:8px;font-size:.82rem" onclick="_rejectWcRequest('${req.id}', '${address}')">
            ✗ Reject
          </button>
        </div>
      </div>
    `).join('');
  } catch { /* network error — try again next tick */ }
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

// ─── Music screen ─────────────────────────────────────────────────────────────
// NOTE: L2E (Learn-to-Earn) = earned from Courses, NOT music.
//        Music listening rewards = T2E (Time-to-Earn) / boost credits.
//        GPS telemetry: activated during CarPlay/Android Auto sessions.

let _musicSession = null;   // { session_id, track_id, started, artist_address }
let _musicAudio   = null;
let _gpsWatchId   = null;   // navigator.geolocation.watchPosition id
let _gpsPoints    = [];     // accumulated GPS points for route hash

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
      <div id="nowPlaying" style="display:none;background:#1a1040;border:1px solid #7c5cbf;border-radius:10px;padding:12px;margin:10px 0">
        <div style="font-size:.75rem;color:var(--muted);margin-bottom:4px">Now Playing</div>
        <div id="npTitle" style="font-weight:700;color:#fff;font-size:1rem;margin-bottom:2px"></div>
        <div id="npArtist" style="font-size:.82rem;color:#b08cf8;cursor:pointer" id="npArtistLink"></div>
        <div style="display:flex;gap:8px;margin-top:10px;align-items:center">
          <button class="btn btn--ghost" id="stopBtn" style="flex:1;padding:8px">⏹ Stop</button>
          <button class="btn btn--primary" id="tipBtn" style="padding:8px 14px;font-size:.8rem">💰 Tip</button>
          <div id="sessionTimer" style="color:var(--accent);font-size:.8rem;min-width:42px;text-align:right"></div>
        </div>
        <div id="carPlayBadge" style="display:none;margin-top:8px;font-size:.72rem;color:#00ff66">🚗 CarPlay · GPS active · +T2E boost</div>
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
  document.getElementById('stopBtn').addEventListener('click', _stopMusic);
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

function _renderTrackRow(t) {
  const tid    = t.id || t.track_id || '';
  const title  = t.title || t.name || tid || '—';
  const artist = t.artist_name || t.artist || '';
  const dur    = t.duration_seconds
    ? `${Math.floor(t.duration_seconds / 60)}:${String(t.duration_seconds % 60).padStart(2,'0')}`
    : '';
  const artAddr = t.artist_address || '';
  return `<div class="tx-item music-track-row" style="cursor:pointer"
      data-tid="${escHtml(tid)}" data-title="${escHtml(title)}" data-artist="${escHtml(artist)}"
      data-artist-addr="${escHtml(artAddr)}" data-url="${escHtml(t.stream_url || t.audio_url || '')}">
    <div class="tx-item__dir" style="background:#1a1040;color:#b08cf8;font-size:1rem">▶</div>
    <div class="tx-item__info">
      <div class="tx-item__label">${escHtml(title)}</div>
      <div class="tx-item__date">${escHtml(artist)}${dur ? ' · ' + dur : ''}</div>
    </div>
    <div class="tx-item__amount" style="color:#7c5cbf;font-size:.72rem">+T2E</div>
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
    el.innerHTML = tracks.slice(0, 50).map(_renderTrackRow).join('');
    el.querySelectorAll('.music-track-row').forEach(row => {
      row.addEventListener('click', () => _playTrack({
        id: row.dataset.tid, title: row.dataset.title,
        artist: row.dataset.artist, artist_address: row.dataset.artistAddr,
        url: row.dataset.url
      }));
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
      <input type="number" id="tipAmount" class="input" placeholder="1.00" min="0.01" step="0.01" inputmode="decimal" style="margin-bottom:14px">
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
    navigator.mediaSession.setActionHandler('stop', _stopMusic);
    navigator.mediaSession.setActionHandler('pause', _stopMusic);
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
    _musicAudio.addEventListener('ended', _stopMusic);
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
    navigator.mediaSession.setActionHandler('stop',  null);
    navigator.mediaSession.setActionHandler('pause', null);
  }
}

function showSend(preselectedToken = null) {
  const address = getActiveAddr();

  // Fetch token list for the selector
  const buildTokenSel = (tokens) => {
    const defaults = ['THR','WBTC','WETH','USDT','USDC','L2E','JAM','MAR'];
    const syms = tokens.length
      ? tokens.filter(t => Number(t.balance) > 0).map(t => t.symbol)
      : defaults;
    const unique = [...new Set([...syms, ...defaults])];
    return unique.map(s => `<option value="${s}" ${s === (preselectedToken || 'THR') ? 'selected' : ''}>${s}</option>`).join('');
  };

  render(`
    <div class="screen">
      <div class="header">
        <button class="btn--icon" id="backBtn">←</button>
        <span class="header__title">Send</span>
        <span style="width:36px"></span>
      </div>
      <div class="card mt16">
        <label style="color:var(--muted);font-size:.85rem">Token</label>
        <select id="tokenSel" class="input" style="cursor:pointer">
          <option value="THR" ${!preselectedToken || preselectedToken==='THR' ? 'selected' : ''}>THR — Thronos</option>
          ${preselectedToken && preselectedToken !== 'THR' ? `<option value="${escHtml(preselectedToken)}" selected>${escHtml(preselectedToken)}</option>` : ''}
        </select>
        <label style="color:var(--muted);font-size:.85rem">Recipient address</label>
        <input type="text" id="toAddr" class="input" placeholder="THR…" autocomplete="off" autocorrect="off" spellcheck="false">
        <label style="color:var(--muted);font-size:.85rem">Amount</label>
        <input type="number" id="amount" class="input" placeholder="0.00" min="0.000001" step="any" inputmode="decimal">
        <button class="btn btn--primary mt8" id="sendBtn">Send</button>
        <div id="err" class="banner banner--error hidden"></div>
        <div id="ok" class="banner banner--success hidden"></div>
      </div>
    </div>
  `);

  document.getElementById('backBtn').addEventListener('click', showWallet);

  // Populate token selector from live balances
  fetchBalances(address).then(data => {
    const tokens = Array.isArray(data?.tokens) ? data.tokens.filter(t => Number(t.balance) > 0) : [];
    const sel = document.getElementById('tokenSel');
    if (!sel || !tokens.length) return;
    const current = sel.value;
    sel.innerHTML = tokens.map(t =>
      `<option value="${escHtml(t.symbol)}" ${t.symbol === (preselectedToken || current) ? 'selected' : ''}>${escHtml(t.symbol)} — ${escHtml(t.name || t.symbol)}</option>`
    ).join('');
  }).catch(() => {});

  document.getElementById('sendBtn').addEventListener('click', async () => {
    const to = document.getElementById('toAddr').value.trim().toUpperCase();
    const amount = parseFloat(document.getElementById('amount').value);
    const token = document.getElementById('tokenSel').value;

    if (!to) { setError('Enter a recipient address'); return; }
    if (!amount || amount <= 0) { setError('Enter a valid amount'); return; }

    const btn = document.getElementById('sendBtn');
    btn.disabled = true; btn.textContent = 'Sending…'; setError(null);

    try {
      const { privHex } = unlocked.get(address) || {};
      if (!privHex) throw new Error('Wallet is locked — please unlock first');
      const result = await sendToken(address, to, amount, token, privHex);
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

boot();
