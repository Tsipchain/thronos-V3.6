// ─── Crypto helpers ───────────────────────────────────────────────────────────

function hexToBytes(hex) {
  const b = new Uint8Array(hex.length / 2);
  for (let i = 0; i < b.length; i++) b[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return b;
}

function bytesToHex(bytes) {
  return Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
}

// 250 000 iterations — matches wallet_session.js aesKeyFromPin
async function pbkdfKey(pin, saltBytes, exportable = false) {
  const km = await crypto.subtle.importKey(
    'raw', new TextEncoder().encode(pin), 'PBKDF2', false, ['deriveKey']
  );
  return crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt: saltBytes, iterations: 250000, hash: 'SHA-256' },
    km, { name: 'AES-GCM', length: 256 }, exportable, ['encrypt', 'decrypt']
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

// Wraps the private key under a random session key kept in sessionStorage
async function wrapForSession(privHex) {
  const sessionKey = crypto.getRandomValues(new Uint8Array(32));
  const envelope = await encryptWithKey(sessionKey, privHex);
  sessionStorage.setItem('thr_sk', bytesToHex(sessionKey));
  return envelope;
}

async function unwrapFromSession(envelope) {
  const skHex = sessionStorage.getItem('thr_sk');
  if (!skHex) throw new Error('session_expired');
  return decryptWithKey(hexToBytes(skHex), envelope);
}

// ─── WebAuthn ─────────────────────────────────────────────────────────────────

const RP_ID = (location.hostname === 'localhost' || location.hostname === '127.0.0.1')
  ? 'localhost'
  : 'thronoschain.org';

const PRF_LABEL = new TextEncoder().encode('thronos-wallet-v1');

async function webauthnAvailable() {
  return !!(window.PublicKeyCredential &&
    await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable().catch(() => false));
}

async function registerWebAuthn(address) {
  const challenge = crypto.getRandomValues(new Uint8Array(32));
  const cred = await navigator.credentials.create({
    publicKey: {
      challenge,
      rp: { name: 'Thronos Wallet', id: RP_ID },
      user: {
        id: new TextEncoder().encode(address.slice(-32)),
        name: address,
        displayName: 'THR Wallet'
      },
      pubKeyCredParams: [
        { alg: -7, type: 'public-key' },
        { alg: -257, type: 'public-key' }
      ],
      authenticatorSelection: {
        authenticatorAttachment: 'platform',
        userVerification: 'required',
        residentKey: 'preferred'
      },
      extensions: { prf: { eval: { first: PRF_LABEL } } },
      timeout: 60000
    }
  });
  return cred;
}

async function assertWebAuthn(credIdHex) {
  const challenge = crypto.getRandomValues(new Uint8Array(32));
  return navigator.credentials.get({
    publicKey: {
      challenge,
      rpId: RP_ID,
      allowCredentials: [{ type: 'public-key', id: hexToBytes(credIdHex) }],
      userVerification: 'required',
      extensions: { prf: { eval: { first: PRF_LABEL } } },
      timeout: 60000
    }
  });
}

// ─── Storage helpers ──────────────────────────────────────────────────────────

const LS = {
  get: k => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch {} },
  del: k => { try { localStorage.removeItem(k); } catch {} },
  getObj: k => { try { return JSON.parse(localStorage.getItem(k)); } catch { return null; } },
  setObj: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} }
};

// ─── API ──────────────────────────────────────────────────────────────────────
// thronoschain.org runs on Railway/nginx — use the backends directly.
// CORS is already enabled on these origins (wallet_sdk.js uses them in-browser).

const API_READ  = 'https://node-2.up.railway.app';
const API_WRITE = 'https://api.thronoschain.org';

async function fetchBalance(address) {
  try {
    const r = await fetch(`${API_READ}/balances?address=${encodeURIComponent(address)}`);
    if (!r.ok) return null;
    const d = await r.json();
    const raw = d.thr_balance ?? d.THR ?? d.balance ?? d.available ?? null;
    return raw !== null ? String(raw) : null;
  } catch {
    return null;
  }
}

async function fetchHistory(address) {
  try {
    const r = await fetch(`${API_READ}/wallet_data/${encodeURIComponent(address)}`);
    if (!r.ok) return [];
    const d = await r.json();
    return Array.isArray(d.transactions) ? d.transactions : [];
  } catch {
    return [];
  }
}

async function sendTHR(from, to, amount, privHex) {
  const r = await fetch(`${API_WRITE}/wallet/send`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      token: 'THR',
      from,
      to: to.trim(),
      amount: String(amount),
      secret: privHex,
      speed: 'fast',
      passphrase: ''
    })
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok || d.error) throw new Error(d.error || d.message || 'send_failed');
  return d;
}

// ─── In-memory wallet state ───────────────────────────────────────────────────

let wallet = null; // { address: string, privHex: string }

// ─── DOM helpers ──────────────────────────────────────────────────────────────

const root = document.getElementById('root');

function render(html) {
  root.innerHTML = html;
}

function setError(msg) {
  const el = document.getElementById('err');
  if (!el) return;
  if (msg) { el.textContent = msg; el.classList.remove('hidden'); }
  else el.classList.add('hidden');
}

function setSuccess(msg) {
  const el = document.getElementById('ok');
  if (!el) return;
  if (msg) { el.textContent = msg; el.classList.remove('hidden'); }
  else el.classList.add('hidden');
}

function readFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = e => resolve(e.target.result);
    reader.onerror = reject;
    reader.readAsText(file);
  });
}

// ─── Import screen ────────────────────────────────────────────────────────────

async function showImport() {
  render(`
    <div class="screen">
      <div class="logo">⬡ THR</div>
      <p class="tagline">Thronos Chain Wallet</p>

      <div class="card">
        <h2 style="font-size:1.15rem">Import Wallet</h2>
        <p style="color:var(--muted);font-size:0.88rem">
          Open your Recovery Kit (.json) file and enter your PIN.
        </p>
        <button class="btn btn--primary" id="pickFile">Select Recovery Kit</button>
        <div id="filePill" class="file-pill hidden"></div>
        <div id="pinSection" class="hidden" style="display:flex;flex-direction:column;gap:12px">
          <input type="password" id="pin" class="input" placeholder="Enter PIN" autocomplete="current-password">
          <button class="btn btn--primary" id="importBtn">Unlock</button>
        </div>
        <div id="err" class="banner banner--error hidden"></div>
      </div>

      <p class="mt24" style="color:var(--muted);font-size:0.8rem;text-align:center">
        Your keys never leave this device.
      </p>
    </div>
  `);

  let kitData = null;

  document.getElementById('pickFile').addEventListener('click', () => {
    const inp = document.createElement('input');
    inp.type = 'file';
    inp.accept = '.json,application/json,text/json';
    inp.addEventListener('change', async e => {
      const file = e.target.files[0];
      if (!file) return;
      try {
        const text = await readFile(file);
        kitData = JSON.parse(text);
        const pill = document.getElementById('filePill');
        pill.textContent = `✓  ${file.name}`;
        pill.classList.remove('hidden');
        const ps = document.getElementById('pinSection');
        ps.classList.remove('hidden');
        ps.style.display = 'flex';
        setError(null);
      } catch {
        setError('Could not read the file — make sure it is a valid Recovery Kit (.json)');
      }
    });
    inp.click();
  });

  document.getElementById('root').addEventListener('click', async e => {
    if (e.target.id !== 'importBtn') return;
    if (!kitData) { setError('Please select a Recovery Kit file first'); return; }

    const pin = document.getElementById('pin')?.value?.trim();
    if (!pin) { setError('Please enter your PIN'); return; }

    const btn = document.getElementById('importBtn');
    btn.disabled = true;
    btn.textContent = 'Unlocking…';

    try {
      const encBlob =
        kitData.encrypted_private_key_backup ??
        kitData.wallet_v1_encrypted_priv ??
        kitData.encrypted_private_key ??
        kitData.enc_key ?? null;

      if (!encBlob) throw new Error('No encrypted key found in this Recovery Kit');

      let privHex;
      try {
        privHex = await decryptBlob(encBlob, pin);
      } catch {
        throw new Error('Wrong PIN — check your PIN and try again');
      }

      const address = (
        kitData.canonical_v1_address ?? kitData.address ?? ''
      ).trim().toUpperCase();

      if (!address || !/^THR[A-F0-9]{40}$/.test(address)) {
        throw new Error('Recovery Kit does not contain a valid THR address');
      }

      wallet = { address, privHex };
      LS.set('thr_addr', address);
      LS.setObj('thr_kit', kitData);

      await promptFaceID(address, privHex);

    } catch (err) {
      const b = document.getElementById('importBtn');
      if (b) { b.disabled = false; b.textContent = 'Unlock'; }
      setError(err.message || 'Import failed');
    }
  });
}

// ─── Face ID enrollment prompt ────────────────────────────────────────────────

async function promptFaceID(address, privHex) {
  const ok = await webauthnAvailable();
  if (!ok) { await showWallet(); return; }

  render(`
    <div class="screen screen--center">
      <div class="faceid-hero">⬡</div>
      <h2 style="font-size:1.3rem">Enable Face ID?</h2>
      <p style="color:var(--muted);max-width:300px">
        Use Face ID to unlock your wallet instantly on this device without entering your PIN each time.
      </p>
      <button class="btn btn--faceid" id="enableFID">
        <svg class="faceid-symbol" viewBox="0 0 28 28" fill="none" stroke="currentColor" stroke-width="1.8">
          <rect x="1" y="1" width="8" height="8" rx="2"/>
          <rect x="19" y="1" width="8" height="8" rx="2"/>
          <rect x="1" y="19" width="8" height="8" rx="2"/>
          <rect x="19" y="19" width="8" height="8" rx="2"/>
          <circle cx="14" cy="11" r="2"/>
          <path d="M10 17c0-2.2 1.8-4 4-4s4 1.8 4 4"/>
        </svg>
        Enable Face ID
      </button>
      <button class="btn btn--ghost" id="skipFID">Skip for now</button>
      <div id="err" class="banner banner--error hidden"></div>
    </div>
  `);

  document.getElementById('enableFID').addEventListener('click', async () => {
    const btn = document.getElementById('enableFID');
    btn.disabled = true;
    btn.textContent = 'Registering…';
    try {
      const cred = await registerWebAuthn(address);
      const credIdHex = bytesToHex(new Uint8Array(cred.rawId));
      const prfFirst = cred.getClientExtensionResults()?.prf?.results?.first;

      if (prfFirst) {
        // PRF available (iOS 17.4+, Chrome 132+): encrypt key with PRF output
        const envelope = await encryptWithKey(new Uint8Array(prfFirst), privHex);
        LS.set('thr_fid_cred', credIdHex);
        LS.setObj('thr_fid_env', envelope);
        LS.set('thr_fid_mode', 'prf');
      } else {
        // Session mode: wrap key in sessionStorage; re-derived on each PIN unlock
        const envelope = await wrapForSession(privHex);
        LS.set('thr_fid_cred', credIdHex);
        LS.setObj('thr_fid_env', envelope);
        LS.set('thr_fid_mode', 'session');
      }

    } catch (err) {
      if (err.name !== 'NotAllowedError') {
        console.warn('WebAuthn registration failed:', err);
      }
    }
    await showWallet();
  });

  document.getElementById('skipFID').addEventListener('click', async () => {
    await showWallet();
  });
}

// ─── Unlock screen ────────────────────────────────────────────────────────────

async function showUnlock() {
  const address = LS.get('thr_addr');
  const fidCred = LS.get('thr_fid_cred');
  const fidMode = LS.get('thr_fid_mode');
  const fidEnv = LS.getObj('thr_fid_env');
  const short = address ? `${address.slice(0, 6)}…${address.slice(-4)}` : '';

  // Try auto-unlock via sessionStorage (same session)
  if (fidMode === 'session' && fidEnv) {
    try {
      const privHex = await unwrapFromSession(fidEnv);
      wallet = { address, privHex };
      await showWallet();
      return;
    } catch {}
  }

  const showFid = !!(fidCred && (fidMode === 'prf' || (fidMode === 'session' && fidEnv)));

  render(`
    <div class="screen screen--center">
      <div class="logo" style="margin-top:0">⬡</div>
      <p style="color:var(--muted);font-size:0.88rem">${short}</p>

      ${showFid ? `
      <button class="btn btn--faceid" id="fidBtn">
        <svg class="faceid-symbol" viewBox="0 0 28 28" fill="none" stroke="currentColor" stroke-width="1.8">
          <rect x="1" y="1" width="8" height="8" rx="2"/>
          <rect x="19" y="1" width="8" height="8" rx="2"/>
          <rect x="1" y="19" width="8" height="8" rx="2"/>
          <rect x="19" y="19" width="8" height="8" rx="2"/>
          <circle cx="14" cy="11" r="2"/>
          <path d="M10 17c0-2.2 1.8-4 4-4s4 1.8 4 4"/>
        </svg>
        Unlock with Face ID
      </button>
      <div class="divider">or</div>
      ` : ''}

      <div style="width:100%;display:flex;flex-direction:column;gap:12px">
        <input type="password" id="pinInput" class="input" placeholder="Enter PIN"
               autocomplete="current-password">
        <button class="btn btn--primary" id="pinBtn">Unlock with PIN</button>
      </div>

      <button class="btn btn--ghost mt8" id="resetBtn" style="font-size:0.82rem">
        Import a different wallet
      </button>

      <div id="err" class="banner banner--error hidden"></div>
    </div>
  `);

  if (showFid) {
    document.getElementById('fidBtn').addEventListener('click', () => unlockFaceID());
  }

  document.getElementById('pinBtn').addEventListener('click', () => {
    const pin = document.getElementById('pinInput')?.value?.trim();
    if (pin) unlockPin(pin);
    else setError('Enter your PIN');
  });

  document.getElementById('pinInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') document.getElementById('pinBtn').click();
  });

  document.getElementById('resetBtn').addEventListener('click', () => {
    if (confirm('This will remove the stored wallet from this device. Continue?')) {
      LS.del('thr_addr'); LS.del('thr_kit');
      LS.del('thr_fid_cred'); LS.del('thr_fid_env'); LS.del('thr_fid_mode');
      sessionStorage.removeItem('thr_sk');
      wallet = null;
      showImport();
    }
  });

  // Auto-focus Face ID button if available
  if (showFid && fidMode === 'prf') {
    setTimeout(() => unlockFaceID(), 400);
  }
}

async function unlockFaceID() {
  const fidCred = LS.get('thr_fid_cred');
  const fidMode = LS.get('thr_fid_mode');
  const fidEnv = LS.getObj('thr_fid_env');
  const address = LS.get('thr_addr');

  const btn = document.getElementById('fidBtn');
  if (btn) { btn.disabled = true; btn.childNodes[btn.childNodes.length - 1].textContent = ' Checking…'; }

  try {
    const assertion = await assertWebAuthn(fidCred);

    if (fidMode === 'prf') {
      const prfFirst = assertion.getClientExtensionResults()?.prf?.results?.first;
      if (!prfFirst) throw new Error('Face ID key derivation not available on this device — use PIN');
      const privHex = await decryptWithKey(new Uint8Array(prfFirst), fidEnv);
      wallet = { address, privHex };

    } else {
      // session mode: assertion proves identity, key in sessionStorage
      try {
        const privHex = await unwrapFromSession(fidEnv);
        wallet = { address, privHex };
      } catch {
        // Session expired — need PIN to re-establish session key
        setError('Session expired — please unlock with PIN once');
        if (btn) { btn.disabled = false; }
        return;
      }
    }

    await showWallet();

  } catch (err) {
    if (btn) btn.disabled = false;
    if (err.name === 'NotAllowedError') {
      setError('Face ID cancelled — enter PIN instead');
    } else {
      setError(err.message || 'Face ID failed — use PIN instead');
    }
  }
}

async function unlockPin(pin) {
  const address = LS.get('thr_addr');
  const kit = LS.getObj('thr_kit');
  if (!kit) { setError('Wallet data missing — reimport'); return; }

  const btn = document.getElementById('pinBtn');
  if (btn) { btn.disabled = true; btn.textContent = 'Unlocking…'; }

  try {
    const encBlob =
      kit.encrypted_private_key_backup ??
      kit.wallet_v1_encrypted_priv ??
      kit.encrypted_private_key ??
      kit.enc_key;

    let privHex;
    try {
      privHex = await decryptBlob(encBlob, pin);
    } catch {
      throw new Error('Wrong PIN — check your PIN and try again');
    }

    wallet = { address, privHex };

    // Refresh session key if in session mode
    const fidMode = LS.get('thr_fid_mode');
    if (fidMode === 'session' && LS.get('thr_fid_cred')) {
      const envelope = await wrapForSession(privHex);
      LS.setObj('thr_fid_env', envelope);
    }

    await showWallet();

  } catch (err) {
    if (btn) { btn.disabled = false; btn.textContent = 'Unlock with PIN'; }
    setError(err.message);
  }
}

// ─── Main wallet screen ───────────────────────────────────────────────────────

async function showWallet() {
  const { address } = wallet;
  const short = `${address.slice(0, 8)}…${address.slice(-6)}`;

  render(`
    <div class="screen">
      <div class="header">
        <span class="logo--sm">⬡ THR</span>
        <button class="btn--icon" id="lockBtn" title="Lock wallet">🔒</button>
      </div>

      <div class="card--gradient">
        <div class="balance-label">Balance</div>
        <div class="balance-amount balance-amount--loading" id="balAmt">···</div>
        <div class="address-display" id="addrLine" title="Tap to copy">${short}</div>
      </div>

      <div class="actions mt16">
        <button class="action-btn" id="sendBtn">
          <span class="action-btn__icon">↑</span>
          Send
        </button>
        <button class="action-btn" id="receiveBtn">
          <span class="action-btn__icon">↓</span>
          Receive
        </button>
      </div>

      <div class="tx-feed">
        <div class="tx-feed__title">Recent Activity</div>
        <div id="txList"><p style="color:var(--muted);font-size:0.88rem">Loading…</p></div>
      </div>
    </div>
  `);

  document.getElementById('addrLine').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(address); } catch {}
    const el = document.getElementById('addrLine');
    if (el) {
      el.textContent = 'Address copied!';
      setTimeout(() => { if (el) el.textContent = short; }, 2000);
    }
  });

  document.getElementById('lockBtn').addEventListener('click', () => {
    wallet = null;
    sessionStorage.removeItem('thr_sk');
    showUnlock();
  });

  document.getElementById('sendBtn').addEventListener('click', showSend);
  document.getElementById('receiveBtn').addEventListener('click', showReceive);

  // Fetch balance
  fetchBalance(address).then(bal => {
    const el = document.getElementById('balAmt');
    if (!el) return;
    el.classList.remove('balance-amount--loading');
    el.textContent = bal !== null ? `${Number(bal).toLocaleString()} THR` : '— THR';
  });

  // Fetch history
  fetchHistory(address).then(txs => {
    const el = document.getElementById('txList');
    if (!el) return;
    if (!txs.length) { el.innerHTML = '<p style="color:var(--muted);font-size:0.88rem">No transactions yet.</p>'; return; }

    el.innerHTML = txs.slice(0, 20).map(tx => {
      const isIn = (tx.to || '').toUpperCase() === address;
      const dir = isIn ? 'in' : 'out';
      const label = isIn
        ? `From ${(tx.from || '').slice(0, 10)}…`
        : `To ${(tx.to || '').slice(0, 10)}…`;
      const amt = tx.amount ? (isIn ? '+' : '-') + tx.amount + ' THR' : '';
      const date = tx.timestamp ? new Date(tx.timestamp * 1000).toLocaleDateString() : '';
      return `
        <div class="tx-item">
          <div class="tx-item__dir tx-item__dir--${dir}">${isIn ? '↓' : '↑'}</div>
          <div class="tx-item__info">
            <div class="tx-item__label">${label}</div>
            <div class="tx-item__date">${date}</div>
          </div>
          <div class="tx-item__amount tx-item__amount--${dir}">${amt}</div>
        </div>
      `;
    }).join('');
  });
}

// ─── Send screen ──────────────────────────────────────────────────────────────

function showSend() {
  render(`
    <div class="screen">
      <div class="header">
        <button class="btn--icon" id="backBtn">←</button>
        <span class="header__title">Send THR</span>
        <span style="width:36px"></span>
      </div>

      <div class="card mt16">
        <label style="color:var(--muted);font-size:0.85rem">Recipient address</label>
        <input type="text" id="toAddr" class="input" placeholder="THR…"
               autocomplete="off" autocorrect="off" spellcheck="false">
        <label style="color:var(--muted);font-size:0.85rem">Amount (THR)</label>
        <input type="number" id="amount" class="input" placeholder="0.00"
               min="0.000001" step="any" inputmode="decimal">
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

    if (!to || !/^THR[A-F0-9]{40}$/.test(to)) {
      setError('Enter a valid THR address'); return;
    }
    if (!amount || amount <= 0) { setError('Enter a valid amount'); return; }

    const btn = document.getElementById('sendBtn');
    btn.disabled = true;
    btn.textContent = 'Sending…';
    setError(null);

    try {
      const result = await sendTHR(wallet.address, to, amount, wallet.privHex);
      setSuccess(`Sent! TX: ${result.tx_hash || result.txid || result.tx || 'submitted'}`);
      btn.textContent = 'Sent ✓';
      setTimeout(showWallet, 3000);
    } catch (err) {
      btn.disabled = false;
      btn.textContent = 'Send';
      setError(err.message || 'Transaction failed');
    }
  });
}

// ─── Receive screen ───────────────────────────────────────────────────────────

function showReceive() {
  const { address } = wallet;
  const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?data=${encodeURIComponent(address)}&size=180x180&color=ffffff&bgcolor=0a0a0f&margin=8`;

  render(`
    <div class="screen">
      <div class="header">
        <button class="btn--icon" id="backBtn">←</button>
        <span class="header__title">Receive THR</span>
        <span style="width:36px"></span>
      </div>

      <div class="card mt16" style="align-items:center;gap:20px">
        <div class="qr-wrapper">
          <img src="${qrUrl}" alt="QR code for ${address}" loading="lazy">
        </div>
        <p class="address-full">${address}</p>
        <button class="btn btn--primary" id="copyBtn">Copy Address</button>
        <div id="ok" class="banner banner--success hidden" style="width:100%;text-align:center"></div>
      </div>
    </div>
  `);

  document.getElementById('backBtn').addEventListener('click', showWallet);

  document.getElementById('copyBtn').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(address); } catch {}
    setSuccess('Address copied to clipboard!');
    const btn = document.getElementById('copyBtn');
    if (btn) { btn.textContent = 'Copied!'; setTimeout(() => { if (btn) btn.textContent = 'Copy Address'; }, 2000); }
  });
}

// ─── Boot ─────────────────────────────────────────────────────────────────────

async function boot() {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/wallet-pwa/sw.js', { scope: '/wallet-pwa/' }).catch(() => {});
  }

  const addr = LS.get('thr_addr');
  const kit = LS.getObj('thr_kit');

  if (addr && kit) {
    await showUnlock();
  } else {
    await showImport();
  }
}

boot();
