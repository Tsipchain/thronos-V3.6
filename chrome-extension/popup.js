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
async function loadWallet() {
    return new Promise((resolve) => {
        chrome.storage.local.get(['thr_address', 'thr_secret'], (result) => {
            if (result.thr_address && result.thr_secret) {
                currentWallet = {
                    address: result.thr_address,
                    secret: result.thr_secret
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
        const response = await fetch(`${API_BASE}/api/wallet/create`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        if (!response.ok) throw new Error('Failed to create wallet');

        const data = await response.json();

        detailsDiv.innerHTML = `
            <strong>Address:</strong>
            <code>${data.address}</code>
            <br><br>
            <strong>Secret Key:</strong>
            <code>${data.secret}</code>
            <br><br>
            <p style="color: #ff6600; font-size: 10px;">⚠️ Save this secret key securely! You cannot recover it later.</p>
        `;

        document.getElementById('confirmCreateBtn').style.display = 'block';
        document.getElementById('confirmCreateBtn').dataset.address = data.address;
        document.getElementById('confirmCreateBtn').dataset.secret = data.secret;
    } catch (error) {
        console.error('Error creating wallet:', error);
        detailsDiv.innerHTML = '<p style="color: #ff0000;">Failed to create wallet</p>';
    }
}

function confirmCreateWallet() {
    const btn = document.getElementById('confirmCreateBtn');
    const address = btn.dataset.address;
    const secret = btn.dataset.secret;

    chrome.storage.local.set({ thr_address: address, thr_secret: secret }, () => {
        currentWallet = { address, secret };
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
    const secret = document.getElementById('importSecret').value.trim();

    if (!address || !secret) {
        showToast('Please enter both address and secret key', 'error');
        return;
    }

    if (!address.startsWith('THR')) {
        showToast('Invalid address format', 'error');
        return;
    }

    chrome.storage.local.set({ thr_address: address, thr_secret: secret }, () => {
        currentWallet = { address, secret };
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
        chrome.storage.local.remove(['thr_address', 'thr_secret'], () => {
            currentWallet = null;
            tokens = [];
            showNotConnected();
            showToast('Wallet disconnected');
        });
    }
}

// Send transaction
async function sendTransaction() {
    // Check wallet connection first
    if (!currentWallet || !currentWallet.address || !currentWallet.secret) {
        showToast('Wallet not connected', 'error');
        return;
    }

    const tokenSymbol = document.getElementById('sendToken').value;
    const to = document.getElementById('sendTo').value.trim();
    const amount = parseFloat(document.getElementById('sendAmount').value);

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

        const response = await fetch(`${API_BASE}/api/wallet/send`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                from: currentWallet.address,
                to: to,
                amount: amount,
                token: tokenSymbol,
                secret: currentWallet.secret
            })
        });

        if (!response.ok) throw new Error('Transaction failed');

        const result = await response.json();

        showToast('Transaction sent successfully!', 'success');

        // Clear form
        document.getElementById('sendToken').value = '';
        document.getElementById('sendTo').value = '';
        document.getElementById('sendAmount').value = '';

        // Refresh wallet data immediately then retry for confirmation
        await loadWalletData();
        // Additional refresh after short delay for blockchain propagation
        setTimeout(() => loadWalletData(), 1000);
    } catch (error) {
        console.error('Error sending transaction:', error);
        showToast('Transaction failed: ' + (error.message || 'Unknown error'), 'error');
    }
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
