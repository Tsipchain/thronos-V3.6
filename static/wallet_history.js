/**
 * Shared Wallet History Module
 * Used by both base.html wallet modal and wallet_viewer.html
 *
 * Provides:
 * - Wallet history with category filtering
 * - Mining statistics ("Mined Blocks" tab)
 * - Transaction categorization
 * - Category aggregations (Mining, AI Rewards, Music Tips, IoT)
 */

// API base configuration
const API_BASE = window.TH_API_BASE_URL || window.location.origin;

// Transaction category labels
const WALLET_CATEGORY_LABELS = {
  'token_transfer': 'THR Transfer',
  'music_tip': 'Music Tips',
  'ai_reward': 'AI Rewards',
  'iot_telemetry': 'IoT Telemetry',
  'bridge': 'Cross-Chain Bridge',
  'pledge': 'BTC Pledge',
  'mining': 'Mining Rewards',
  'swap': 'Token Swap',
  'liquidity': 'Liquidity Pool',
  'other': 'Other'
};

// Utility functions
const fmtNumber = (num) => {
  if (num == null) return '—';
  return Number(num).toLocaleString();
};

const fmtTHR = (amount) => {
  if (amount == null) return '0.000000';
  return Number(amount).toFixed(6);
};

const fmtTimestamp = (ts) => {
  if (!ts) return '—';
  try {
    const date = new Date(ts);
    return date.toLocaleString();
  } catch (e) {
    return ts;
  }
};

const truncHash = (hash) => {
  if (!hash) return '—';
  return hash.length > 16 ? `${hash.substring(0, 8)}...${hash.substring(hash.length - 8)}` : hash;
};

/**
 * Load wallet history from API
 */
async function loadWalletHistory(address, categoryFilter = '') {
  try {
    let url = `${API_BASE}/api/wallet/history?address=${encodeURIComponent(address)}`;
    if (categoryFilter) {
      url += `&category=${encodeURIComponent(categoryFilter)}`;
    }

    const response = await fetch(url);
    if (!response.ok) throw new Error(`Wallet history API error: ${response.status}`);

    const data = await response.json();
    if (!data.ok) throw new Error('Wallet history returned ok=false');

    return data;
  } catch (error) {
    console.error('[WalletHistory] Failed to load:', error);
    return { ok: false, transactions: [], summary: {} };
  }
}

/**
 * Load mining statistics from API
 */
async function loadMiningStats(address) {
  try {
    const response = await fetch(`${API_BASE}/api/wallet/mining_stats?address=${encodeURIComponent(address)}`);
    if (!response.ok) throw new Error(`Mining stats API error: ${response.status}`);

    const data = await response.json();
    if (!data.ok) throw new Error('Mining stats returned ok=false');

    return data;
  } catch (error) {
    console.error('[WalletHistory] Failed to load mining stats:', error);
    return { ok: false, blocks_mined: 0, total_block_reward: 0, recent_blocks: [] };
  }
}

/**
 * Render wallet summary cards
 */
function renderWalletSummary(summary, containerId = 'walletSummary') {
  if (!summary) return;

  const container = document.getElementById(containerId);
  if (!container) return;

  container.innerHTML = `
    <div class="row mb-3">
      <div class="col-md-3 col-sm-6 mb-3">
        <div class="card bg-dark text-white">
          <div class="card-body">
            <h6 class="card-subtitle mb-2 text-muted">Mining Rewards</h6>
            <h4 class="card-title text-success">${fmtTHR(summary.total_mining || 0)} THR</h4>
            <small class="text-muted">${fmtNumber(summary.mining_count || 0)} transactions</small>
          </div>
        </div>
      </div>
      <div class="col-md-3 col-sm-6 mb-3">
        <div class="card bg-dark text-white">
          <div class="card-body">
            <h6 class="card-subtitle mb-2 text-muted">AI Rewards</h6>
            <h4 class="card-title text-info">${fmtTHR(summary.total_ai_rewards || 0)} THR</h4>
            <small class="text-muted">${fmtNumber(summary.ai_reward_count || 0)} transactions</small>
          </div>
        </div>
      </div>
      <div class="col-md-3 col-sm-6 mb-3">
        <div class="card bg-dark text-white">
          <div class="card-body">
            <h6 class="card-subtitle mb-2 text-muted">Music Tips</h6>
            <h4 class="card-title text-warning">
              <small>+${fmtTHR(summary.total_music_tips_received || 0)}</small><br>
              <small>-${fmtTHR(summary.total_music_tips_sent || 0)}</small>
            </h4>
            <small class="text-muted">${fmtNumber(summary.music_tip_count || 0)} transactions</small>
          </div>
        </div>
      </div>
      <div class="col-md-3 col-sm-6 mb-3">
        <div class="card bg-dark text-white">
          <div class="card-body">
            <h6 class="card-subtitle mb-2 text-muted">IoT Rewards</h6>
            <h4 class="card-title text-primary">${fmtTHR(summary.total_iot_rewards || 0)} THR</h4>
            <small class="text-muted">${fmtNumber(summary.iot_count || 0)} submissions</small>
          </div>
        </div>
      </div>
    </div>
  `;
}

/**
 * Render transaction history table
 */
function renderTransactionHistory(transactions, tableBodyId = 'walletHistoryTableBody') {
  const tbody = document.getElementById(tableBodyId);
  if (!tbody) return;

  tbody.innerHTML = '';

  if (!transactions || transactions.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No transactions found</td></tr>';
    return;
  }

  transactions.forEach(tx => {
    const category = tx.category || 'other';
    const categoryLabel = WALLET_CATEGORY_LABELS[category] || category;
    const direction = tx.direction || 'related';
    const directionBadge = direction === 'received' ? '<span class="badge bg-success">↓ Received</span>' :
                           direction === 'sent' ? '<span class="badge bg-danger">↑ Sent</span>' :
                           '<span class="badge bg-secondary">↔</span>';

    const row = document.createElement('tr');
    row.innerHTML = `
      <td><code>${truncHash(tx.tx_id || tx.id)}</code></td>
      <td><span class="badge bg-info">${categoryLabel}</span></td>
      <td>${directionBadge}</td>
      <td><code>${truncHash(tx.from || '—')}</code></td>
      <td><code>${truncHash(tx.to || '—')}</code></td>
      <td class="${direction === 'received' ? 'text-success' : direction === 'sent' ? 'text-danger' : ''}">${fmtTHR(tx.amount || 0)} THR</td>
      <td>${fmtTimestamp(tx.timestamp)}</td>
    `;
    tbody.appendChild(row);
  });
}

/**
 * Render mined blocks statistics
 */
function renderMinedBlocksStats(miningData, containerId = 'minedBlocksStats') {
  const container = document.getElementById(containerId);
  if (!container) return;

  container.innerHTML = `
    <div class="row mb-3">
      <div class="col-md-3">
        <div class="stat-card">
          <h6 class="text-muted">Blocks Mined</h6>
          <h3 class="text-success">${fmtNumber(miningData.blocks_mined || 0)}</h3>
        </div>
      </div>
      <div class="col-md-3">
        <div class="stat-card">
          <h6 class="text-muted">Total Rewards</h6>
          <h3 class="text-success">${fmtTHR(miningData.total_block_reward || 0)} THR</h3>
        </div>
      </div>
      <div class="col-md-3">
        <div class="stat-card">
          <h6 class="text-muted">Fees Burned</h6>
          <h3 class="text-warning">${fmtTHR(miningData.total_pool_burn || 0)} THR</h3>
        </div>
      </div>
      <div class="col-md-3">
        <div class="stat-card">
          <h6 class="text-muted">AI Share</h6>
          <h3 class="text-info">${fmtTHR(miningData.total_ai_share || 0)} THR</h3>
        </div>
      </div>
    </div>
    <div class="row mb-2">
      <div class="col">
        <small class="text-muted">
          Last Block: #${fmtNumber(miningData.last_block_height || 0)} at ${fmtTimestamp(miningData.last_block_time)}
        </small>
      </div>
    </div>
  `;
}

/**
 * Render mined blocks table
 */
function renderMinedBlocksTable(miningData, tableBodyId = 'minedBlocksTableBody') {
  const tbody = document.getElementById(tableBodyId);
  if (!tbody) return;

  tbody.innerHTML = '';

  if (!miningData || !miningData.recent_blocks || miningData.recent_blocks.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No blocks mined yet</td></tr>';
    return;
  }

  miningData.recent_blocks.forEach(block => {
    const row = document.createElement('tr');
    row.innerHTML = `
      <td><a href="/block/${block.height}" target="_blank">${fmtNumber(block.height)}</a></td>
      <td><code>${truncHash(block.hash)}</code></td>
      <td class="text-success">${fmtTHR(block.reward)} THR</td>
      <td class="text-warning">${fmtTHR(block.fee_burned)} THR</td>
      <td>${fmtTimestamp(block.timestamp)}</td>
      <td><span class="badge ${block.is_stratum ? 'bg-success' : 'bg-secondary'}">${block.is_stratum ? 'Stratum' : 'CPU'}</span></td>
    `;
    tbody.appendChild(row);
  });
}

/**
 * Open wallet history modal with all tabs
 */
async function openWalletHistoryModal(address, modalId = 'walletHistoryModal') {
  console.log('[WalletHistory] Opening modal for:', address);

  if (!address) {
    console.error('[WalletHistory] No address provided');
    return;
  }

  // Show modal using send-modal pattern (classList.add('active'))
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.add('active');
  } else {
    console.error('[WalletHistory] Modal not found:', modalId);
    return;
  }

  // Load data in parallel
  const [historyData, miningData] = await Promise.all([
    loadWalletHistory(address),
    loadMiningStats(address)
  ]);

  // Render summary
  renderWalletSummary(historyData.summary);

  // Render transaction history
  renderTransactionHistory(historyData.transactions);

  // Render mining stats (if containers exist)
  if (document.getElementById('minedBlocksStatsContainer')) {
    renderMinedBlocksStats(miningData);
  }
  if (document.getElementById('minedBlocksTableBody')) {
    renderMinedBlocksTable(miningData);
  }

  // Store data for category filtering
  window.currentWalletAddress = address;
  window.currentWalletHistory = historyData;
  window.currentMiningData = miningData;

  console.log('[WalletHistory] Modal loaded successfully');
}

/**
 * Close wallet history modal
 */
function closeWalletHistoryModal(modalId = 'walletHistoryModal') {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.remove('active');
  }
}

/**
 * Filter wallet history by category
 */
async function filterWalletHistoryByCategory(category, tableBodyId = 'walletHistoryTableBody') {
  if (!window.currentWalletAddress) {
    console.error('[WalletHistory] No wallet address set');
    return;
  }

  const data = await loadWalletHistory(window.currentWalletAddress, category);
  renderTransactionHistory(data.transactions, tableBodyId);
}

/**
 * Export functions for global use
 */
window.WalletHistory = {
  loadWalletHistory,
  loadMiningStats,
  renderWalletSummary,
  renderTransactionHistory,
  renderMinedBlocksStats,
  renderMinedBlocksTable,
  openWalletHistoryModal,
  closeWalletHistoryModal,
  filterWalletHistoryByCategory,
  // Utility functions
  fmtNumber,
  fmtTHR,
  fmtTimestamp,
  truncHash
};

console.log('[WalletHistory] Module loaded');
