/**
 * Thronos Blockchain Viewer - Client-Side Implementation
 *
 * Implements:
 * - Blocks tab with pagination (load more until height=1)
 * - Transfers tab with adaptive stats and category filters
 * - Wallet history with mined blocks tab
 * - Category aggregations and summaries
 * - Consistency between dashboard/blocks/transfers
 */

// ===== Configuration =====
const API_BASE = window.TH_API_BASE_URL || window.location.origin;

// Transaction category labels
const CATEGORY_LABELS = {
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

// State
let currentBlocksOffset = 0;
let currentTransfersOffset = 0;
let currentCategoryFilter = '';
let dashboardStats = null;

// ===== Utility Functions =====
const el = (id) => document.getElementById(id);

const formatNumber = (num) => {
  if (num == null) return '—';
  return Number(num).toLocaleString();
};

const formatTHR = (amount) => {
  if (amount == null) return '0.000000';
  return Number(amount).toFixed(6);
};

const formatTimestamp = (ts) => {
  if (!ts) return '—';
  try {
    const date = new Date(ts);
    return date.toLocaleString();
  } catch (e) {
    return ts;
  }
};

const truncateHash = (hash) => {
  if (!hash) return '—';
  return hash.length > 16 ? `${hash.substring(0, 8)}...${hash.substring(hash.length - 8)}` : hash;
};

// ===== Dashboard Stats =====
async function loadDashboardStats() {
  try {
    const response = await fetch(`${API_BASE}/api/dashboard`);
    if (!response.ok) throw new Error(`Dashboard API error: ${response.status}`);

    const data = await response.json();
    if (!data.ok) throw new Error('Dashboard returned ok=false');

    dashboardStats = data.stats;

    // Update blocks section counters
    if (el('blocksTotalCount')) {
      el('blocksTotalCount').textContent = formatNumber(dashboardStats.block_count);
    }
    if (el('blocksTotalRewards')) {
      el('blocksTotalRewards').textContent = formatTHR(dashboardStats.total_rewards_thr || 0);
    }
    if (el('blocksTotalBurned')) {
      el('blocksTotalBurned').textContent = formatTHR(dashboardStats.burned_total_thr || 0);
    }
    if (el('blocksAvgReward')) {
      const avgReward = dashboardStats.block_count > 0 ?
        (dashboardStats.total_rewards_thr || 0) / dashboardStats.block_count : 0;
      el('blocksAvgReward').textContent = formatTHR(avgReward);
    }

    // Update global counters (if they exist elsewhere on the page)
    if (el('totalBlocks')) {
      el('totalBlocks').textContent = formatNumber(dashboardStats.block_count);
    }
    if (el('totalTransfers')) {
      el('totalTransfers').textContent = formatNumber(dashboardStats.total_transfers);
    }
    if (el('uniqueAddresses')) {
      el('uniqueAddresses').textContent = formatNumber(dashboardStats.unique_addresses);
    }

    return dashboardStats;
  } catch (error) {
    console.error('Failed to load dashboard stats:', error);
    return null;
  }
}

// ===== Blocks Tab =====
async function loadBlocks(offset = 0, limit = 100) {
  try {
    const response = await fetch(`${API_BASE}/api/blocks?offset=${offset}&limit=${limit}`);
    if (!response.ok) throw new Error(`Blocks API error: ${response.status}`);

    const data = await response.json();
    if (!data.ok) throw new Error('Blocks returned ok=false');

    return data;
  } catch (error) {
    console.error('Failed to load blocks:', error);
    return { ok: false, blocks: [], total: 0, has_more: false };
  }
}

function renderBlocks(blocks, append = false) {
  const tbody = el('blocksTableBody');
  if (!tbody) return;

  if (!append) {
    tbody.innerHTML = '';
  }

  if (!blocks || blocks.length === 0) {
    if (!append) {
      tbody.innerHTML = '<tr><td colspan="7" class="text-center">No blocks found</td></tr>';
    }
    return;
  }

  blocks.forEach(block => {
    const row = document.createElement('tr');
    row.innerHTML = `
      <td><a href="/block/${block.index || block.height}">${block.index || block.height || '—'}</a></td>
      <td><code>${truncateHash(block.hash || block.block_hash)}</code></td>
      <td>${formatTHR(block.reward_to_miner || block.reward || 0)}</td>
      <td>${formatTHR(block.fee_burned || 0)}</td>
      <td>${formatTHR(block.reward_to_ai || 0)}</td>
      <td>${formatTimestamp(block.timestamp)}</td>
      <td><span class="badge ${block.is_stratum ? 'bg-success' : 'bg-secondary'}">${block.is_stratum ? 'Stratum' : 'CPU'}</span></td>
    `;
    tbody.appendChild(row);
  });
}

async function loadMoreBlocks() {
  const loadMoreBtn = el('btnLoadMoreBlocks');
  if (loadMoreBtn) {
    loadMoreBtn.disabled = true;
    loadMoreBtn.textContent = 'Loading...';
  }

  currentBlocksOffset += 100;
  const data = await loadBlocks(currentBlocksOffset, 100);

  renderBlocks(data.blocks, true);

  if (loadMoreBtn) {
    loadMoreBtn.disabled = !data.has_more;
    loadMoreBtn.textContent = data.has_more ? 'Load More Blocks' : 'All Blocks Loaded';
  }

  // Update counter if available
  if (el('blocksCount')) {
    el('blocksCount').textContent = formatNumber(data.total);
  }
}

async function initBlocksTab() {
  const data = await loadBlocks(0, 100);
  renderBlocks(data.blocks, false);

  const loadMoreBtn = el('btnLoadMoreBlocks');
  if (loadMoreBtn) {
    loadMoreBtn.disabled = !data.has_more;
    loadMoreBtn.textContent = data.has_more ? 'Load More Blocks' : 'All Blocks Loaded';
    loadMoreBtn.onclick = loadMoreBlocks;
  }

  // Update block count (if there's a separate counter for current view)
  if (el('blocksCount')) {
    el('blocksCount').textContent = formatNumber(data.total);
  }
  // Note: blocksTotalCount is updated from dashboard stats, not blocks API
}

// ===== Transfers Tab =====
async function loadTransfers(offset = 0, limit = 100, typeFilter = '', addressFilter = '') {
  try {
    let url = `${API_BASE}/api/transfers?offset=${offset}&limit=${limit}`;
    if (typeFilter) url += `&type=${encodeURIComponent(typeFilter)}`;
    if (addressFilter) url += `&address=${encodeURIComponent(addressFilter)}`;

    const response = await fetch(url);
    if (!response.ok) throw new Error(`Transfers API error: ${response.status}`);

    const data = await response.json();
    if (!data.ok) throw new Error('Transfers returned ok=false');

    return data;
  } catch (error) {
    console.error('Failed to load transfers:', error);
    return { ok: false, transfers: [], total: 0, has_more: false, stats: {} };
  }
}

function renderTransfers(transfers, append = false) {
  const tbody = el('transfersTableBody');
  if (!tbody) return;

  if (!append) {
    tbody.innerHTML = '';
  }

  if (!transfers || transfers.length === 0) {
    if (!append) {
      tbody.innerHTML = '<tr><td colspan="6" class="text-center">No transfers found</td></tr>';
    }
    return;
  }

  transfers.forEach(tx => {
    const row = document.createElement('tr');
    const category = tx.category || 'other';
    const categoryLabel = CATEGORY_LABELS[category] || category;

    row.innerHTML = `
      <td><code>${truncateHash(tx.tx_id || tx.id)}</code></td>
      <td><span class="badge bg-info">${categoryLabel}</span></td>
      <td><code>${truncateHash(tx.from || '—')}</code></td>
      <td><code>${truncateHash(tx.to || '—')}</code></td>
      <td>${formatTHR(tx.amount || 0)}</td>
      <td>${formatTimestamp(tx.timestamp)}</td>
    `;
    tbody.appendChild(row);
  });
}

function renderTransferStats(stats) {
  if (!stats) return;

  // Update stats counters
  if (el('transfersCount')) {
    el('transfersCount').textContent = formatNumber(stats.total_transfers);
  }
  if (el('uniqueAddressesCount')) {
    el('uniqueAddressesCount').textContent = formatNumber(stats.unique_addresses);
  }

  // Show period indicator
  if (el('statsPeriod')) {
    const periodText = stats.period === '24h' ? 'Last 24 hours' : 'All time';
    el('statsPeriod').textContent = periodText;
    el('statsPeriod').className = stats.period === '24h' ? 'badge bg-warning' : 'badge bg-success';
  }

  // Render category breakdown
  if (stats.by_category && el('categoryBreakdown')) {
    let html = '<div class="row">';

    Object.entries(stats.by_category).forEach(([category, count]) => {
      const label = CATEGORY_LABELS[category] || category;
      html += `
        <div class="col-md-3 col-sm-6 mb-2">
          <div class="card">
            <div class="card-body p-2">
              <small class="text-muted">${label}</small>
              <h5 class="mb-0">${formatNumber(count)}</h5>
            </div>
          </div>
        </div>
      `;
    });

    html += '</div>';
    el('categoryBreakdown').innerHTML = html;
  }
}

function renderCategoryFilters(stats) {
  if (!stats || !stats.by_category) return;

  const filtersContainer = el('categoryFilters');
  if (!filtersContainer) return;

  // Add "All" filter
  let html = `<button class="btn btn-sm ${currentCategoryFilter === '' ? 'btn-primary' : 'btn-outline-primary'} me-2 mb-2" onclick="filterByCategory('')">All</button>`;

  // Add category filters
  Object.keys(stats.by_category).forEach(category => {
    const label = CATEGORY_LABELS[category] || category;
    const isActive = currentCategoryFilter === category;
    html += `<button class="btn btn-sm ${isActive ? 'btn-primary' : 'btn-outline-primary'} me-2 mb-2" onclick="filterByCategory('${category}')">${label}</button>`;
  });

  filtersContainer.innerHTML = html;
}

async function filterByCategory(category) {
  currentCategoryFilter = category;
  currentTransfersOffset = 0;

  const data = await loadTransfers(0, 100, category);
  renderTransfers(data.transfers, false);
  renderTransferStats(data.stats);
  renderCategoryFilters(data.stats);

  const loadMoreBtn = el('loadMoreTransfers');
  if (loadMoreBtn) {
    loadMoreBtn.disabled = !data.has_more;
    loadMoreBtn.textContent = data.has_more ? 'Load More' : 'All Transfers Loaded';
  }
}

async function loadMoreTransfers() {
  const loadMoreBtn = el('btnLoadMoreTxs');
  if (loadMoreBtn) {
    loadMoreBtn.disabled = true;
    loadMoreBtn.textContent = 'Loading...';
  }

  currentTransfersOffset += 100;
  const data = await loadTransfers(currentTransfersOffset, 100, currentCategoryFilter);

  renderTransfers(data.transfers, true);

  if (loadMoreBtn) {
    loadMoreBtn.disabled = !data.has_more;
    loadMoreBtn.textContent = data.has_more ? 'Load More Transactions' : 'All Transfers Loaded';
  }
}

async function initTransfersTab() {
  const data = await loadTransfers(0, 100);
  renderTransfers(data.transfers, false);
  renderTransferStats(data.stats);
  renderCategoryFilters(data.stats);

  const loadMoreBtn = el('btnLoadMoreTxs');
  if (loadMoreBtn) {
    loadMoreBtn.disabled = !data.has_more;
    loadMoreBtn.textContent = data.has_more ? 'Load More Transactions' : 'All Transfers Loaded';
    loadMoreBtn.onclick = loadMoreTransfers;
  }
}

// ===== Wallet History with Mining Stats =====
async function loadWalletHistory(address) {
  try {
    const response = await fetch(`${API_BASE}/api/wallet/history?address=${encodeURIComponent(address)}`);
    if (!response.ok) throw new Error(`Wallet history API error: ${response.status}`);

    const data = await response.json();
    if (!data.ok) throw new Error('Wallet history returned ok=false');

    return data;
  } catch (error) {
    console.error('Failed to load wallet history:', error);
    return { ok: false, transactions: [], summary: {} };
  }
}

async function loadMiningStats(address) {
  try {
    const response = await fetch(`${API_BASE}/api/wallet/mining_stats?address=${encodeURIComponent(address)}`);
    if (!response.ok) throw new Error(`Mining stats API error: ${response.status}`);

    const data = await response.json();
    if (!data.ok) throw new Error('Mining stats returned ok=false');

    return data;
  } catch (error) {
    console.error('Failed to load mining stats:', error);
    return { ok: false, blocks_mined: 0, total_block_reward: 0, recent_blocks: [] };
  }
}

function renderWalletSummary(summary) {
  if (!summary) return;

  const summaryDiv = el('walletSummary');
  if (!summaryDiv) return;

  summaryDiv.innerHTML = `
    <div class="row">
      <div class="col-md-3 col-sm-6 mb-3">
        <div class="card">
          <div class="card-body">
            <h6 class="card-subtitle mb-2 text-muted">Mining Rewards</h6>
            <h4 class="card-title">${formatTHR(summary.total_mining)} THR</h4>
            <small class="text-muted">${summary.mining_count || 0} transactions</small>
          </div>
        </div>
      </div>
      <div class="col-md-3 col-sm-6 mb-3">
        <div class="card">
          <div class="card-body">
            <h6 class="card-subtitle mb-2 text-muted">AI Rewards</h6>
            <h4 class="card-title">${formatTHR(summary.total_ai_rewards)} THR</h4>
            <small class="text-muted">${summary.ai_reward_count || 0} transactions</small>
          </div>
        </div>
      </div>
      <div class="col-md-3 col-sm-6 mb-3">
        <div class="card">
          <div class="card-body">
            <h6 class="card-subtitle mb-2 text-muted">Music Tips</h6>
            <h4 class="card-title">+${formatTHR(summary.total_music_tips_received)} / -${formatTHR(summary.total_music_tips_sent)} THR</h4>
            <small class="text-muted">${summary.music_tip_count || 0} transactions</small>
          </div>
        </div>
      </div>
      <div class="col-md-3 col-sm-6 mb-3">
        <div class="card">
          <div class="card-body">
            <h6 class="card-subtitle mb-2 text-muted">IoT Rewards</h6>
            <h4 class="card-title">${formatTHR(summary.total_iot_rewards)} THR</h4>
            <small class="text-muted">${summary.iot_count || 0} submissions</small>
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderMinedBlocks(miningData) {
  const tbody = el('minedBlocksTableBody');
  if (!tbody) return;

  tbody.innerHTML = '';

  if (!miningData || !miningData.recent_blocks || miningData.recent_blocks.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="text-center">No blocks mined yet</td></tr>';
    return;
  }

  // Update summary
  if (el('totalBlocksMined')) {
    el('totalBlocksMined').textContent = formatNumber(miningData.blocks_mined);
  }
  if (el('totalMiningRewards')) {
    el('totalMiningRewards').textContent = formatTHR(miningData.total_block_reward);
  }

  // Render recent blocks
  miningData.recent_blocks.forEach(block => {
    const row = document.createElement('tr');
    row.innerHTML = `
      <td><a href="/block/${block.height}">${block.height}</a></td>
      <td><code>${truncateHash(block.hash)}</code></td>
      <td>${formatTHR(block.reward)}</td>
      <td>${formatTHR(block.fee_burned)}</td>
      <td>${formatTimestamp(block.timestamp)}</td>
    `;
    tbody.appendChild(row);
  });
}

async function openWalletModal(address) {
  // Load wallet history and mining stats
  const [history, miningStats] = await Promise.all([
    loadWalletHistory(address),
    loadMiningStats(address)
  ]);

  // Render summary
  renderWalletSummary(history.summary);

  // Store mining stats for tab switching
  window.currentMiningStats = miningStats;
  window.currentWalletHistory = history;

  // Show modal (assuming Bootstrap modal)
  const modal = new bootstrap.Modal(el('walletModal'));
  modal.show();

  // Show transactions tab by default
  showWalletTab('transactions');
}

function showWalletTab(tabName) {
  // Hide all tabs
  const tabs = ['transactions', 'minedBlocks', 'bridge'];
  tabs.forEach(tab => {
    const content = el(`${tab}Tab`);
    if (content) content.style.display = 'none';
  });

  // Show selected tab
  const selectedContent = el(`${tabName}Tab`);
  if (selectedContent) selectedContent.style.display = 'block';

  // Render content based on tab
  if (tabName === 'minedBlocks' && window.currentMiningStats) {
    renderMinedBlocks(window.currentMiningStats);
  }
}

// ===== IoT Mining Toggle =====
let iotMiningEnabled = false;
let gpsWatchId = null;
let gpsBuffer = [];
let telemetryInterval = null;

function toggleIoTMining() {
  const toggle = el('iotMiningToggle');
  if (!toggle) return;

  iotMiningEnabled = toggle.checked;

  if (iotMiningEnabled) {
    startIoTMining();
  } else {
    stopIoTMining();
  }
}

function startIoTMining() {
  if (!navigator.geolocation) {
    alert('Geolocation not supported on this device');
    if (el('iotMiningToggle')) el('iotMiningToggle').checked = false;
    return;
  }

  console.log('[IoT] Starting GPS tracking...');

  gpsWatchId = navigator.geolocation.watchPosition(
    position => {
      gpsBuffer.push({
        lat: position.coords.latitude,
        lng: position.coords.longitude,
        accuracy: position.coords.accuracy,
        timestamp: Date.now()
      });

      // Keep last 100 samples
      if (gpsBuffer.length > 100) {
        gpsBuffer.shift();
      }

      console.log(`[IoT] GPS sample collected: ${gpsBuffer.length} samples in buffer`);
    },
    error => {
      console.error('[IoT] GPS error:', error);
    },
    {
      enableHighAccuracy: true,
      timeout: 10000,
      maximumAge: 0
    }
  );

  // Submit telemetry every minute
  telemetryInterval = setInterval(submitTelemetry, 60000);

  console.log('[IoT] Mining enabled');
}

function stopIoTMining() {
  if (gpsWatchId !== null) {
    navigator.geolocation.clearWatch(gpsWatchId);
    gpsWatchId = null;
  }

  if (telemetryInterval !== null) {
    clearInterval(telemetryInterval);
    telemetryInterval = null;
  }

  gpsBuffer = [];
  console.log('[IoT] Mining disabled');
}

async function submitTelemetry() {
  if (gpsBuffer.length === 0) {
    console.log('[IoT] No GPS samples to submit');
    return;
  }

  const walletAddress = window.currentWalletAddress || localStorage.getItem('thronos_wallet_address');
  if (!walletAddress) {
    console.error('[IoT] No wallet address configured');
    return;
  }

  // Hash GPS path (simple concatenation for demo)
  const pathString = gpsBuffer.map(p => `${p.lat},${p.lng}`).join('|');
  const routeHash = await hashString(pathString);

  const payload = {
    address: walletAddress,
    device_id: getDeviceId(),
    route_hash: routeHash,
    samples: gpsBuffer.length
  };

  try {
    const response = await fetch(`${API_BASE}/api/iot/telemetry`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await response.json();

    if (data.ok) {
      console.log(`[IoT] Telemetry submitted: ${data.tx_id}`);
      // Clear buffer after successful submission
      gpsBuffer = [];
    } else {
      console.error('[IoT] Telemetry submission failed:', data.error);
    }
  } catch (error) {
    console.error('[IoT] Telemetry submission error:', error);
  }
}

async function hashString(str) {
  const encoder = new TextEncoder();
  const data = encoder.encode(str);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

function getDeviceId() {
  let deviceId = localStorage.getItem('thronos_device_id');
  if (!deviceId) {
    deviceId = `device-${Date.now()}-${Math.random().toString(36).substring(7)}`;
    localStorage.setItem('thronos_device_id', deviceId);
  }
  return deviceId;
}

// ===== Initialization =====
document.addEventListener('DOMContentLoaded', async () => {
  console.log('[Viewer] Initializing...');

  // Load dashboard stats first
  await loadDashboardStats();

  // Initialize based on current tab
  const currentTab = window.location.hash || '#blocks';

  if (currentTab === '#blocks' || currentTab === '') {
    await initBlocksTab();
  } else if (currentTab === '#transfers') {
    await initTransfersTab();
  }

  // Setup tab switching
  const tabLinks = document.querySelectorAll('[data-bs-toggle="tab"]');
  tabLinks.forEach(link => {
    link.addEventListener('shown.bs.tab', async (event) => {
      const target = event.target.getAttribute('data-bs-target');

      if (target === '#blocks') {
        await initBlocksTab();
      } else if (target === '#transfers') {
        await initTransfersTab();
      }
    });
  });

  // Setup IoT toggle
  const iotToggle = el('iotMiningToggle');
  if (iotToggle) {
    iotToggle.addEventListener('change', toggleIoTMining);
  }

  console.log('[Viewer] Initialized');
});

// Make functions globally available
window.filterByCategory = filterByCategory;
window.openWalletModal = openWalletModal;
window.showWalletTab = showWalletTab;
window.loadMoreBlocks = loadMoreBlocks;
window.loadMoreTransfers = loadMoreTransfers;
