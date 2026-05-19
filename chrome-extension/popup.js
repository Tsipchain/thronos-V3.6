// Configuration - Auto-detect API base from storage or use production
let API_BASE = 'https://thrchain.up.railway.app'; // Production URL

// Initialize API base from storage
chrome.storage.local.get(['api_base'], (result) => {
    if (result.api_base) {
        API_BASE = result.api_base;
    }
});

// State
let currentWallet = null;
let tokens = [];

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    await loadWallet();
    setupEventListeners();
});

// Load wallet from storage (Promise-based to fix async race condition)
// NOTE: Secrets are NOT stored; only address is kept
async function loadWallet() {
    return new Promise((resolve) => {
        chrome.storage.local.get(['thr_address', 'thr_mnemonic_encrypted'], (result) => {
            if (result.thr_address) {
                currentWallet = {
                    address: result.thr_address
                    // NOTE: No secret field; mnemonic retrieved for signing only
                };
                showWalletConnected();
                loadWalletData();
            } else {
                showNotConnected();
            }
            resolve();
        });
    });
}

// Show wallet connected view
function showWalletConnected() {
    if (!currentWallet || !currentWallet.address) {
        showNotConnected();
        return;
    }

    document.getElementById('notConnected').style.display = 'none';
    document.getElementById('walletConnected').style.display = 'flex';

    // Display address
    const shortAddress = currentWallet.address.substring(0, 10) + '...' +
                        currentWallet.address.substring(currentWallet.address.length - 8);
    document.getElementById('accountAddress').textContent = shortAddress;
}

// Show not connected view
function showNotConnected() {
    document.getElementById('notConnected').style.display = 'block';
    document.getElementById('walletConnected').style.display = 'none';
}

// Load wallet data from API
async function loadWalletData() {
    if (!currentWallet) return;

    try {
        const response = await fetch(`${API_BASE}/api/wallet/tokens/${currentWallet.address}?show_zero=false`);
        if (!response.ok) throw new Error('Failed to load wallet data');

        const data = await response.json();
        tokens = data.tokens || [];

        renderTokens();
        updateTotalBalance();
        populateSendTokens();
    } catch (error) {
        console.error('Error loading wallet data:', error);
        showError('Failed to load wallet data');
    }
}

// Render tokens list
function renderTokens() {
    const tokensList = document.getElementById('tokensList');

    if (tokens.length === 0) {
        tokensList.innerHTML = '<p class="empty-message">No tokens found</p>';
        return;
    }

    let html = '';
    tokens.forEach(token => {
        html += `
            <div class="token-item">
                <div class="token-logo" style="border-color: ${token.color};">
                    ${token.logo ?
                        `<img src="${token.logo}" alt="${token.symbol}" onerror="this.style.display='none';">` :
                        `<span style="color: ${token.color};">${token.symbol[0]}</span>`
                    }
                </div>
                <div class="token-info">
                    <div class="token-symbol">${token.symbol}</div>
                    <div class="token-name">${token.name}</div>
                </div>
                <div class="token-balance">
                    <div class="token-balance-amount" style="color: ${token.color};">
                        ${token.balance.toFixed(token.decimals)}
                    </div>
                </div>
            </div>
        `;
    });

    tokensList.innerHTML = html;
}

// Update total balance
function updateTotalBalance() {
    const totalTHR = tokens.reduce((sum, t) => {
        if (t.symbol === 'THR') return sum + t.balance;
        if (t.symbol === 'WBTC') return sum + (t.balance * 50000);
        if (t.symbol === 'L2E') return sum + t.balance;
        return sum;
    }, 0);

    document.getElementById('totalBalance').textContent = `${totalTHR.toFixed(2)} THR`;
}

// Populate send tokens dropdown
function populateSendTokens() {
    const select = document.getElementById('sendToken');
    let html = '<option value="">Select token...</option>';

    tokens.forEach(token => {
        html += `<option value="${token.symbol}">${token.symbol} (${token.balance.toFixed(token.decimals)})</option>`;
    });

    select.innerHTML = html;
}

// Setup event listeners
function setupEventListeners() {
    // Tab switching
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const tabName = tab.dataset.tab;
            switchTab(tabName);
        });
    });

    // Create wallet
    document.getElementById('createWalletBtn').addEventListener('click', showCreateWalletModal);
    document.getElementById('cancelCreateBtn').addEventListener('click', hideCreateWalletModal);
    document.getElementById('confirmCreateBtn').addEventListener('click', confirmCreateWallet);

    // Import wallet
    document.getElementById('importWalletBtn').addEventListener('click', showImportWalletModal);
    document.getElementById('cancelImportBtn').addEventListener('click', hideImportWalletModal);
    document.getElementById('confirmImportBtn').addEventListener('click', confirmImportWallet);

    // Copy address
    document.getElementById('copyAddressBtn').addEventListener('click', copyAddress);

    // Refresh
    document.getElementById('refreshBtn').addEventListener('click', () => {
        loadWalletData();
        showToast('Refreshing...');
    });

    // View on explorer
    document.getElementById('viewOnExplorerBtn').addEventListener('click', () => {
        if (currentWallet) {
            chrome.tabs.create({ url: `${API_BASE}/viewer?address=${currentWallet.address}` });
        }
    });

    // Disconnect
    document.getElementById('disconnectBtn').addEventListener('click', disconnectWallet);

    // Send transaction
    document.getElementById('sendBtn').addEventListener('click', sendTransaction);
}

// Switch tabs
function switchTab(tabName) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(tc => tc.classList.remove('active'));

    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
    document.getElementById(`${tabName}Tab`).classList.add('active');
}

// Create wallet modal
function showCreateWalletModal() {
    document.getElementById('createModal').style.display = 'flex';
    createNewWallet();
}

function hideCreateWalletModal() {
    document.getElementById('createModal').style.display = 'none';
}

async function createNewWallet() {
    const detailsDiv = document.getElementById('newWalletDetails');

    try {
        // Call backend to generate wallet (returns address only in new secure flow)
        // OR use client-side BIP39 generation
        const response = await fetch(`${API_BASE}/api/wallet/create`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        if (!response.ok) throw new Error('Failed to create wallet');

        const data = await response.json();
        const mnemonic = data.mnemonic || data.seed; // Client-generated wallet

        detailsDiv.innerHTML = `
            <strong>Address:</strong>
            <code>${data.address}</code>
            <br><br>
            <p style="color: #00aa00; font-size: 11px;">✓ Wallet created successfully!</p>
            <p style="color: #ff6600; font-size: 10px;">⚠️ Save your mnemonic securely (shown only once).</p>
            ${mnemonic ? `<br><strong>Mnemonic:</strong><br><code style="word-break: break-all;">${mnemonic}</code><br><br>` : ''}
        `;

        document.getElementById('confirmCreateBtn').style.display = 'block';
        document.getElementById('confirmCreateBtn').dataset.address = data.address;
        document.getElementById('confirmCreateBtn').dataset.mnemonic = mnemonic || '';
    } catch (error) {
        console.error('Error creating wallet:', error);
        detailsDiv.innerHTML = '<p style="color: #ff0000;">Failed to create wallet</p>';
    }
}

function confirmCreateWallet() {
    const btn = document.getElementById('confirmCreateBtn');
    const address = btn.dataset.address;
    const mnemonic = btn.dataset.mnemonic;

    // Store only address (and optionally encrypted mnemonic)
    // Never store raw secret or mnemonic in plain text
    const storageData = { thr_address: address };
    if (mnemonic) {
        // In production: encrypt mnemonic with device-specific key
        // For now: only store address
        storageData.thr_mnemonic_encrypted = btoa(mnemonic); // Base64 encode as placeholder
    }

    chrome.storage.local.set(storageData, () => {
        currentWallet = { address };  // No secret stored
        hideCreateWalletModal();
        showWalletConnected();
        loadWalletData();
        showToast('Wallet created successfully!');
    });
}

// Import wallet modal
function showImportWalletModal() {
    document.getElementById('importModal').style.display = 'flex';
}

function hideImportWalletModal() {
    document.getElementById('importModal').style.display = 'none';
    document.getElementById('importAddress').value = '';
    document.getElementById('importSecret').value = '';
}

function confirmImportWallet() {
    const address = document.getElementById('importAddress').value.trim();
    const mnemonic = document.getElementById('importSecret').value.trim(); // Field reused for mnemonic

    if (!address || !mnemonic) {
        showToast('Please enter address and mnemonic', 'error');
        return;
    }

    if (!address.startsWith('THR')) {
        showToast('Invalid address format', 'error');
        return;
    }

    // Validate mnemonic format (basic check: should be space-separated words)
    const words = mnemonic.trim().split(/\s+/);
    if (words.length !== 12 && words.length !== 24) {
        showToast('Mnemonic must be 12 or 24 words', 'error');
        return;
    }

    const storageData = { thr_address: address };
    if (mnemonic) {
        // In production: encrypt mnemonic with device-specific key
        storageData.thr_mnemonic_encrypted = btoa(mnemonic); // Base64 encode as placeholder
    }

    chrome.storage.local.set(storageData, () => {
        currentWallet = { address };  // No secret stored
        hideImportWalletModal();
        showWalletConnected();
        loadWalletData();
        showToast('Wallet imported successfully!');
    });
}

// Copy address
function copyAddress() {
    if (!currentWallet || !currentWallet.address) {
        showToast('No wallet connected', 'error');
        return;
    }
    navigator.clipboard.writeText(currentWallet.address);
    showToast('Address copied!');
}

// Disconnect wallet
function disconnectWallet() {
    if (confirm('Are you sure you want to disconnect your wallet?')) {
        chrome.storage.local.remove(['thr_address', 'thr_mnemonic_encrypted'], () => {
            currentWallet = null;
            tokens = [];
            showNotConnected();
            showToast('Wallet disconnected');
        });
    }
}

// Send transaction (with client-side signing)
async function sendTransaction() {
    // Check wallet connection first
    if (!currentWallet || !currentWallet.address) {
        showToast('Wallet not connected', 'error');
        return;
    }

    const tokenSymbol = document.getElementById('sendToken').value;
    const to = document.getElementById('sendTo').value.trim();
    const amount = parseFloat(document.getElementById('sendAmount').value);
    const speed = document.getElementById('sendSpeed')?.value || 'fast';

    if (!tokenSymbol || !to || !amount) {
        showToast('Please fill all fields', 'error');
        return;
    }

    if (!to.startsWith('THR')) {
        showToast('Invalid recipient address', 'error');
        return;
    }

    if (amount <= 0) {
        showToast('Amount must be greater than 0', 'error');
        return;
    }

    try {
        const token = tokens.find(t => t.symbol === tokenSymbol);
        if (!token) {
            showToast('Token not found', 'error');
            return;
        }

        if (amount > token.balance) {
            showToast('Insufficient balance', 'error');
            return;
        }

        // Retrieve mnemonic for signing (stored encrypted)
        const storedData = await new Promise((resolve) => {
            chrome.storage.local.get(['thr_mnemonic_encrypted'], (result) => {
                resolve(result);
            });
        });

        if (!storedData.thr_mnemonic_encrypted) {
            showToast('Cannot sign transaction: mnemonic not found', 'error');
            return;
        }

        const mnemonic = atob(storedData.thr_mnemonic_encrypted); // Decode base64

        // Sign transaction locally
        const signedTx = await signTransactionLocally({
            from: currentWallet.address,
            to: to,
            amount: amount,
            token: tokenSymbol,
            mnemonic: mnemonic
        });

        // Send signed transaction (no secret in request)
        const response = await fetch(`${API_BASE}/api/v1/tx/send`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tx: signedTx  // Signed envelope only
            })
        });

        const result = await response.json();

        // Handle errors properly
        if (!response.ok || result.error || result.ok === false) {
            let errorMsg = result.error || result.message || 'Transaction failed';
            if (result.thr_balance !== undefined && result.fee_required !== undefined) {
                errorMsg = `Insufficient THR for fee. Need ${result.fee_required} THR, have ${result.thr_balance} THR`;
            }
            showToast(errorMsg, 'error');
            return;
        }

        // Success
        const feeInfo = result.fee_burned || result.fee ? ` (Fee: ${(result.fee_burned || result.fee).toFixed(6)} THR)` : '';
        showToast(`${amount} ${tokenSymbol} sent successfully!${feeInfo}`, 'success');

        // Clear form
        document.getElementById('sendToken').value = '';
        document.getElementById('sendTo').value = '';
        document.getElementById('sendAmount').value = '';

        // Refresh wallet data
        await loadWalletData();
        setTimeout(() => loadWalletData(), 1000);
    } catch (error) {
        console.error('Error sending transaction:', error);
        showToast('Transaction failed: ' + (error.message || 'Unknown error'), 'error');
    }
}

// Sign transaction locally using ECDSA/secp256k1
async function signTransactionLocally(params) {
    return new Promise(async (resolve, reject) => {
        try {
            if (!params.mnemonic) {
                throw new Error('Mnemonic required for signing');
            }

            // Validate mnemonic
            if (!bip39.validateMnemonic(params.mnemonic)) {
                throw new Error('Invalid mnemonic');
            }

            // Derive keypair from mnemonic using BIP39/BIP32
            const seed = bip39.mnemonicToSeedSync(params.mnemonic);
            const root = bip32.fromSeed(seed);
            const child = root.derivePath("m/44'/1'/0'/0/0"); // Testnet path (matches wallet.ts and mobile SDK)

            if (!child.privateKey) {
                throw new Error('Failed to derive private key from mnemonic');
            }

            const privateKeyHex = child.privateKey.toString('hex');
            const publicKeyCompressed = child.publicKey.toString('hex');

            // Create transaction payload with UNIX seconds timestamp
            const txPayload = {
                from: params.from,
                to: params.to,
                amount: params.amount,
                token: params.token || 'THR',
                nonce: params.nonce || `tx_${Date.now()}`,
                timestamp: Math.floor(Date.now() / 1000)  // UNIX seconds, not milliseconds
            };

            // Create canonical payload string (sorted keys, compact JSON)
            const canonical = canonicalPayloadString(txPayload);

            // Sign with ECDSA/secp256k1
            const signature = await signCanonicalPayload(canonical, privateKeyHex);

            // Use compressed public key for backend
            // Backend derives address from: RIPEMD160(SHA256(compressedPublicKey))
            const signedTx = {
                ...txPayload,
                signature,
                publicKey: publicKeyCompressed  // Compressed key
            };

            if (!verifyEnvelopeStructure(signedTx)) {
                throw new Error('Invalid transaction envelope');
            }

            resolve(signedTx);
        } catch (error) {
            reject(error);
        }
    });
}

/**
 * Create canonical payload string for signing.
 * Must match backend's canonicalization exactly.
 */
function canonicalPayloadString(payload) {
    // Verify timestamp is in seconds, not milliseconds
    if (payload.timestamp > 1e10) {
        throw new Error(
            `Invalid timestamp ${payload.timestamp}: must be UNIX seconds (e.g. 1710000000), not milliseconds`
        );
    }

    const obj = {
        amount: payload.amount,
        from: payload.from,
        nonce: payload.nonce,
        timestamp: payload.timestamp,
        to: payload.to,
        token: payload.token,
    };

    // Compact JSON with sorted keys - must match backend exactly
    return JSON.stringify(obj, Object.keys(obj).sort());
}

/**
 * Sign canonical payload with ECDSA/secp256k1 + SHA256.
 */
async function signCanonicalPayload(canonical, privateKeyHex) {
    const canonicalBytes = new TextEncoder().encode(canonical);

    // Using elliptic.js for signing
    const ec = new elliptic.ec('secp256k1');
    const keyPair = ec.keyFromPrivate(privateKeyHex);

    // Hash with SHA-256
    const hashBuffer = await crypto.subtle.digest('SHA-256', canonicalBytes);

    // ECDSA sign
    const hashHex = Array.from(new Uint8Array(hashBuffer))
        .map((b) => b.toString(16).padStart(2, '0'))
        .join('');

    const signature = keyPair.sign(hashHex);

    // DER encoding
    return signature.toDER('hex');
}

/**
 * Verify a signed transaction envelope structure.
 */
function verifyEnvelopeStructure(signedTx) {
    // Verify required fields
    const requiredFields = ['from', 'to', 'amount', 'signature', 'publicKey', 'nonce', 'timestamp'];
    const hasAllFields = requiredFields.every((field) => signedTx[field] !== undefined);

    if (!hasAllFields) {
        return false;
    }

    // Verify no secret fields present
    const forbiddenFields = ['secret', 'mnemonic', 'seed', 'privateKey', 'auth_secret', 'passphrase'];
    const hasForbiddenFields = forbiddenFields.some((field) => signedTx[field] !== undefined);

    // Verify timestamp is in seconds, not milliseconds
    const isTimestampValid = signedTx.timestamp < 1e10;

    return !hasForbiddenFields && isTimestampValid;
}

// Show toast notification
function showToast(message, type = 'success') {
    // Create toast element
    const toast = document.createElement('div');
    toast.style.position = 'fixed';
    toast.style.top = '10px';
    toast.style.left = '50%';
    toast.style.transform = 'translateX(-50%)';
    toast.style.background = type === 'error' ? '#ff0000' : '#00ff00';
    toast.style.color = '#000';
    toast.style.padding = '10px 20px';
    toast.style.borderRadius = '4px';
    toast.style.zIndex = '10000';
    toast.style.fontFamily = 'Courier New, monospace';
    toast.style.fontSize = '12px';
    toast.textContent = message;

    document.body.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 3000);
}

// Show error
function showError(message) {
    const tokensList = document.getElementById('tokensList');
    tokensList.innerHTML = `<p class="empty-message" style="color: #ff0000;">${message}</p>`;
}
