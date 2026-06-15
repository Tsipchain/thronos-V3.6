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
      return `<div style="display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:1px solid #ffffff10">
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

// ─── Music / T2E screen ───────────────────────────────────────────────────────
// Music telemetry: start session when track plays, end when stops.
// L2E (Learn-to-Earn): earned from music listening time, shown in Tokens.
// T2E (Time-to-Earn): music session tracked server-side; minted by admin.

let _musicSession = null;   // { session_id, track_id, audio }
let _musicAudio   = null;

async function showMusic() {
  const address = getActiveAddr();
  render(`
    <div class="screen">
      <div class="header">
        <button class="btn--icon" id="backBtn">←</button>
        <span class="header__title">♪ Music · T2E</span>
      </div>
      <div id="musicL2eBar" style="background:#0d0a1a;border:1px solid var(--accent);border-radius:8px;padding:8px 12px;margin:12px 0;font-size:.82rem;color:var(--accent)">
        <b>L2E Balance:</b> <span id="l2eAmt">…</span>
      </div>
      <div id="nowPlaying" style="display:none;background:#1a1040;border:1px solid #7c5cbf;border-radius:8px;padding:10px 12px;margin-bottom:10px">
        <div style="font-size:.8rem;color:var(--muted)">Now Playing</div>
        <div id="npTitle" style="font-weight:bold;color:#fff;margin:4px 0"></div>
        <div id="npArtist" style="font-size:.8rem;color:var(--muted)"></div>
        <div style="display:flex;gap:8px;margin-top:8px">
          <button class="btn btn--ghost" id="stopBtn" style="flex:1;padding:6px">⏹ Stop</button>
          <div id="sessionTimer" style="color:var(--accent);font-size:.8rem;line-height:32px;min-width:50px;text-align:right"></div>
        </div>
      </div>
      <div id="trackList" style="display:flex;flex-direction:column;gap:8px">
        <p style="color:var(--muted);font-size:.88rem">Loading tracks…</p>
      </div>
    </div>
  `);

  document.getElementById('backBtn').addEventListener('click', () => {
    if (_musicAudio) { _musicAudio.pause(); }
    showWallet();
  });
  document.getElementById('stopBtn')?.addEventListener('click', _stopMusic);

  // Load L2E balance
  fetch(`${API_WRITE}/api/v1/l2e/balance/${encodeURIComponent(address)}`)
    .then(r => r.ok ? r.json() : null)
    .then(d => {
      const el = document.getElementById('l2eAmt');
      if (!el) return;
      const bal = d?.balance ?? d?.l2e_balance ?? d?.amount ?? 0;
      el.textContent = `${Number(bal).toFixed(4)} L2E`;
    }).catch(() => {});

  // Load tracks
  fetch(`${API_WRITE}/api/v1/music/tracks`)
    .then(r => r.ok ? r.json() : { tracks: [] })
    .then(d => {
      const tracks = Array.isArray(d) ? d : (d.tracks || d.data || []);
      const el = document.getElementById('trackList');
      if (!el) return;
      if (!tracks.length) { el.innerHTML = '<p style="color:var(--muted);font-size:.88rem">No tracks available.</p>'; return; }
      el.innerHTML = tracks.slice(0, 30).map(t => {
        const tid = t.id || t.track_id || '';
        const title = t.title || t.name || tid || '—';
        const artist = t.artist_name || t.artist || '';
        const dur = t.duration_seconds ? `${Math.floor(t.duration_seconds/60)}:${String(t.duration_seconds%60).padStart(2,'0')}` : '';
        return `<div class="tx-item" data-tid="${escHtml(tid)}" data-title="${escHtml(title)}" data-artist="${escHtml(artist)}" data-url="${escHtml(t.stream_url || t.audio_url || '')}">
          <div class="tx-item__dir" style="background:#1a1040;color:#b08cf8">▶</div>
          <div class="tx-item__info"><div class="tx-item__label">${escHtml(title)}</div><div class="tx-item__date">${escHtml(artist)}${dur ? ' · '+dur : ''}</div></div>
          <div class="tx-item__amount" style="color:var(--muted);font-size:.75rem">+L2E</div>
        </div>`;
      }).join('');
      document.getElementById('trackList').addEventListener('click', e => {
        const row = e.target.closest('[data-tid]');
        if (!row) return;
        _playTrack({ id: row.dataset.tid, title: row.dataset.title,
                     artist: row.dataset.artist, url: row.dataset.url });
      });
    }).catch(() => {
      const el = document.getElementById('trackList');
      if (el) el.innerHTML = '<p style="color:var(--muted);font-size:.88rem">Could not load tracks.</p>';
    });
}

function escHtml(s) { return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

async function _playTrack(track) {
  const address = getActiveAddr();
  if (_musicSession) await _stopMusic();

  // Start server session (telemetry / T2E)
  try {
    const r = await fetch(`${API_WRITE}/api/music/session/start`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address, track_id: track.id,
        artist_address: track.artist_address || '', source: 'pwa' })
    });
    const d = await r.json().catch(() => ({}));
    _musicSession = { session_id: d.session_id || '', track_id: track.id, started: Date.now() };
  } catch { _musicSession = { session_id: '', track_id: track.id, started: Date.now() }; }

  // Audio playback (if URL available)
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
    document.getElementById('npTitle').textContent = track.title;
    document.getElementById('npArtist').textContent = track.artist || '';
  }

  // Session timer
  const tick = setInterval(() => {
    const timerEl = document.getElementById('sessionTimer');
    if (!timerEl || !_musicSession) { clearInterval(tick); return; }
    const sec = Math.floor((Date.now() - _musicSession.started) / 1000);
    timerEl.textContent = `${Math.floor(sec/60)}:${String(sec%60).padStart(2,'0')}`;
  }, 1000);
}

async function _stopMusic() {
  if (_musicAudio) { _musicAudio.pause(); _musicAudio = null; }
  if (_musicSession?.session_id) {
    try {
      await fetch(`${API_WRITE}/api/music/session/end`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: _musicSession.session_id,
          reason: 'stop', tip_amount: 0 })
      });
    } catch {}
  }
  _musicSession = null;
  const np = document.getElementById('nowPlaying');
  if (np) np.style.display = 'none';
  // Reload L2E balance after session ends
  const address = getActiveAddr();
  if (address) {
    fetch(`${API_WRITE}/api/v1/l2e/balance/${encodeURIComponent(address)}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        const el = document.getElementById('l2eAmt');
        if (!el || !d) return;
        const bal = d.balance ?? d.l2e_balance ?? d.amount ?? 0;
        el.textContent = `${Number(bal).toFixed(4)} L2E`;
      }).catch(() => {});
  }
}

function showSend() {
  const address = getActiveAddr();
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
          <option value="THR">THR — Thronos</option>
          <option value="WBTC">WBTC — Wrapped Bitcoin</option>
          <option value="WETH">WETH — Wrapped Ethereum</option>
          <option value="USDT">USDT</option>
          <option value="USDC">USDC</option>
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
