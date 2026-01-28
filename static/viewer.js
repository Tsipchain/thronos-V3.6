/**
 * Thronos Blockchain Viewer - Client-Side Implementation
 *
 * Clean IIFE structure to avoid global conflicts
 * Provides viewer functionality for blocks and transfers
 */

(function() {
  'use strict';

  // ===== Configuration =====
  const API_BASE = window.__API_BASE__ || window.TH_API_BASE_URL || window.location.origin;

  // ===== State =====
  let currentBlocksOffset = 0;
  let currentTransfersOffset = 0;
  let transfersCursor = null;
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

  const safeNumber = (value) => {
    const num = Number(value);
    return Number.isFinite(num) ? num : 0;
  };

  const setStatsBanner = (message) => {
    let banner = document.getElementById('viewerStatsBanner');
    if (!banner) {
      banner = document.createElement('div');
      banner.id = 'viewerStatsBanner';
      banner.style.cssText = 'margin: 12px 0; padding: 10px 12px; border: 1px solid rgba(255, 140, 0, 0.6); border-radius: 8px; color: #ff9b5f; background: rgba(255, 140, 0, 0.1); display: none;';
      const wrap = document.querySelector('.wrap');
      if (wrap) {
        wrap.insertBefore(banner, wrap.firstChild);
      } else {
        document.body.insertBefore(banner, document.body.firstChild);
      }
    }
    if (message) {
      banner.textContent = message;
      banner.style.display = 'block';
    } else {
      banner.textContent = '';
      banner.style.display = 'none';
    }
  };

  // ===== Dashboard Stats =====
  async function loadStats() {
    try {
      const response = await fetch(`${API_BASE}/api/dashboard`);
      if (!response.ok) throw new Error(`Dashboard API error: ${response.status}`);

      const data = await response.json();
      const stats = data?.stats || data?.data || data?.dashboard || data || {};
      if (data?.ok === false) throw new Error('Dashboard returned ok=false');

      dashboardStats = stats;
      setStatsBanner('');

      // Update counters with correct IDs
      if (el('stat-block-count')) {
        el('stat-block-count').textContent = formatNumber(safeNumber(dashboardStats.block_count));
      }
      if (el('stat-fees-burned')) {
        el('stat-fees-burned').textContent = formatTHR(safeNumber(dashboardStats.burned_total_thr));
      }
      if (el('stat-total-rewards')) {
        el('stat-total-rewards').textContent = formatTHR(safeNumber(dashboardStats.total_rewards_thr));
      }
      if (el('stat-avg-reward')) {
        const blockCount = safeNumber(dashboardStats.block_count);
        const avgReward = blockCount > 0
          ? safeNumber(dashboardStats.total_rewards_thr) / blockCount
          : 0;
        el('stat-avg-reward').textContent = formatTHR(avgReward);
      }

      // Also update old IDs for compatibility (blocks tab)
      if (el('blocksTotalCount')) {
        el('blocksTotalCount').textContent = formatNumber(safeNumber(dashboardStats.block_count));
      }
      if (el('blocksTotalBurned')) {
        el('blocksTotalBurned').textContent = formatTHR(safeNumber(dashboardStats.burned_total_thr));
      }
      if (el('blocksTotalRewards')) {
        el('blocksTotalRewards').textContent = formatTHR(safeNumber(dashboardStats.total_rewards_thr));
      }
      if (el('blocksAvgReward')) {
        const blockCount = safeNumber(dashboardStats.block_count);
        const avgReward = blockCount > 0
          ? safeNumber(dashboardStats.total_rewards_thr) / blockCount
          : 0;
        el('blocksAvgReward').textContent = formatTHR(avgReward);
      }

      return dashboardStats;
    } catch (error) {
      console.error('[Viewer] Failed to load dashboard stats:', error);
      setStatsBanner('Stats unavailable');
      if (el('stat-block-count')) el('stat-block-count').textContent = '—';
      if (el('stat-fees-burned')) el('stat-fees-burned').textContent = '—';
      if (el('stat-total-rewards')) el('stat-total-rewards').textContent = '—';
      if (el('stat-avg-reward')) el('stat-avg-reward').textContent = '—';
      if (el('blocksTotalCount')) el('blocksTotalCount').textContent = '—';
      if (el('blocksTotalBurned')) el('blocksTotalBurned').textContent = '—';
      if (el('blocksTotalRewards')) el('blocksTotalRewards').textContent = '—';
      if (el('blocksAvgReward')) el('blocksAvgReward').textContent = '—';
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
      console.error('[Viewer] Failed to load blocks:', error);
      return { ok: false, blocks: [], total: 0, has_more: false };
    }
  }

  function renderBlocks(blocks, append = false) {
    const tbody = el('blocks-tbody') || el('blocksTableBody');
    if (!tbody) return;

    if (!append) {
      tbody.innerHTML = '';
    }

    if (!blocks || blocks.length === 0) {
      if (!append) {
        tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;">No blocks found</td></tr>';
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

  async function handleLoadMoreBlocks() {
    const loadMoreBtn = el('load-more-blocks') || el('btnLoadMoreBlocks');
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
  }

  async function initBlocksTab() {
    const data = await loadBlocks(0, 100);
    renderBlocks(data.blocks, false);

    const loadMoreBtn = el('load-more-blocks') || el('btnLoadMoreBlocks');
    if (loadMoreBtn) {
      loadMoreBtn.disabled = !data.has_more;
      loadMoreBtn.textContent = data.has_more ? 'Load More Blocks' : 'All Blocks Loaded';
      loadMoreBtn.onclick = handleLoadMoreBlocks;
    }
  }

  // ===== Transfers Tab =====
  async function loadTransfersStats() {
    try {
      const response = await fetch(`${API_BASE}/api/dashboard`);
      if (!response.ok) throw new Error(`Dashboard API error: ${response.status}`);

      const data = await response.json();
      if (data?.ok === false) throw new Error('Dashboard returned ok=false');

      const stats = data?.stats || data?.data || data?.dashboard || data || {};
      setStatsBanner('');

      // Update transfers tab counters
      if (el('txsTotalCount')) {
        el('txsTotalCount').textContent = formatNumber(safeNumber(stats.total_transfers));
      }
      if (el('txsUniqueAddresses')) {
        el('txsUniqueAddresses').textContent = formatNumber(safeNumber(stats.unique_addresses));
      }
      if (el('stat-total-transfers')) {
        el('stat-total-transfers').textContent = formatNumber(safeNumber(stats.total_transfers));
      }
      if (el('stat-unique-addresses')) {
        el('stat-unique-addresses').textContent = formatNumber(safeNumber(stats.unique_addresses));
      }

      return stats;
    } catch (error) {
      console.error('[Viewer] Failed to load transfers stats:', error);
      setStatsBanner('Stats unavailable');
      if (el('txsTotalCount')) el('txsTotalCount').textContent = '—';
      if (el('txsUniqueAddresses')) el('txsUniqueAddresses').textContent = '—';
      if (el('stat-total-transfers')) el('stat-total-transfers').textContent = '—';
      if (el('stat-unique-addresses')) el('stat-unique-addresses').textContent = '—';
      return null;
    }
  }

  const TRANSFER_PAGE_SIZE = 200;
  const TRANSFER_KINDS = ['token_transfer', 'swap', 'bridge'];

  async function loadTransfers(limit = TRANSFER_PAGE_SIZE, cursor = null) {
    try {
      let url = `${API_BASE}/api/tx_feed?limit=${Math.min(limit, 500)}&kinds=${encodeURIComponent(TRANSFER_KINDS.join(','))}`;
      if (cursor !== null && cursor !== undefined) {
        url += `&cursor=${encodeURIComponent(cursor)}`;
      }

      const response = await fetch(url);
      if (!response.ok) throw new Error(`Transfers API error: ${response.status}`);

      const data = await response.json();
      if (Array.isArray(data)) {
        return { ok: true, items: data, has_more: false, cursor: null };
      }
      if (!data.ok) throw new Error('Transfers returned ok=false');

      return data;
    } catch (error) {
      console.error('[Viewer] Failed to load transfers:', error);
      return { ok: false, transfers: [], items: [], has_more: false, cursor: null };
    }
  }

  function renderTransfers(transfers, append = false) {
    const tbody = el('transfers-tbody') || el('transfersTableBody');
    if (!tbody) return;

    if (!append) {
      tbody.innerHTML = '';
    }

    if (!transfers || transfers.length === 0) {
      if (!append) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;">No transfers found</td></tr>';
      }
      return;
    }

    const allowedKinds = new Set(TRANSFER_KINDS);
    const onlyTransfers = (transfers || []).filter(tx =>
      tx
      && tx.type !== 'block'
      && tx.category !== 'block'
      && !['block'].includes(tx.kind)
      && (
        allowedKinds.has(tx.type)
        || allowedKinds.has(tx.kind)
        || tx.category === 'tokens'
      )
    );

    if (!onlyTransfers.length) {
      if (!append) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;">No transfers found</td></tr>';
      }
      return;
    }

    onlyTransfers.forEach(tx => {
      const row = document.createElement('tr');
      row.innerHTML = `
        <td><code>${truncateHash(tx.tx_id || tx.id)}</code></td>
        <td>${tx.type || tx.kind || '—'}</td>
        <td><code>${truncateHash(tx.from || '—')}</code></td>
        <td><code>${truncateHash(tx.to || '—')}</code></td>
        <td>${tx.asset_symbol || tx.asset || tx.symbol || 'THR'}</td>
        <td>${formatTHR(tx.amount || 0)}</td>
        <td>${formatTHR(tx.fee || 0)}</td>
        <td>${formatTimestamp(tx.timestamp)}</td>
      `;
      tbody.appendChild(row);
    });
  }

  async function handleLoadMoreTransfers() {
    const loadMoreBtn = el('load-more-transfers') || el('btnLoadMoreTxs');
    if (loadMoreBtn) {
      loadMoreBtn.disabled = true;
      loadMoreBtn.textContent = 'Loading...';
    }

    const data = await loadTransfers(TRANSFER_PAGE_SIZE, transfersCursor);

    // Support both 'transfers' and 'items' response keys
    const items = data.transfers || data.items || [];
    renderTransfers(items, true);

    // Update cursor for next page
    transfersCursor = data.cursor || data.next_cursor || null;

    if (loadMoreBtn) {
      loadMoreBtn.disabled = !data.has_more && !transfersCursor;
      loadMoreBtn.textContent = (data.has_more || transfersCursor) ? 'Load More Transfers' : 'All Transfers Loaded';
    }
  }

  async function handleRefreshTransfers() {
    const refreshBtn = el('refresh-transfers') || el('btnRefreshTxs');
    if (refreshBtn) {
      refreshBtn.disabled = true;
      refreshBtn.textContent = 'Refreshing...';
    }

    // Reset cursor
    transfersCursor = null;
    currentTransfersOffset = 0;

    // Reload stats
    await loadTransfersStats();

    // Reload transfers from beginning
    const data = await loadTransfers(TRANSFER_PAGE_SIZE, null);
    const items = data.transfers || data.items || [];
    renderTransfers(items, false);

    // Update cursor
    transfersCursor = data.cursor || data.next_cursor || null;

    const loadMoreBtn = el('load-more-transfers') || el('btnLoadMoreTxs');
    if (loadMoreBtn) {
      loadMoreBtn.disabled = !data.has_more && !transfersCursor;
      loadMoreBtn.textContent = (data.has_more || transfersCursor) ? 'Load More Transfers' : 'All Transfers Loaded';
    }

    if (refreshBtn) {
      refreshBtn.disabled = false;
      refreshBtn.textContent = 'Refresh Transfers';
    }
  }

  async function initTransfersTab() {
    // Load stats first
    await loadTransfersStats();

    // Load initial transfers
    const data = await loadTransfers(TRANSFER_PAGE_SIZE, null);
    const items = data.transfers || data.items || [];
    renderTransfers(items, false);

    // Update cursor
    transfersCursor = data.cursor || data.next_cursor || null;

    // Setup buttons
    const loadMoreBtn = el('load-more-transfers') || el('btnLoadMoreTxs');
    if (loadMoreBtn) {
      loadMoreBtn.disabled = !data.has_more && !transfersCursor;
      loadMoreBtn.textContent = (data.has_more || transfersCursor) ? 'Load More Transfers' : 'All Transfers Loaded';
      loadMoreBtn.onclick = handleLoadMoreTransfers;
    }

    const refreshBtn = el('refresh-transfers') || el('btnRefreshTxs');
    if (refreshBtn) {
      refreshBtn.onclick = handleRefreshTransfers;
    }
  }

  // ===== Initialization =====
  function init() {
    console.log('[Viewer] Initializing...');

    // Load dashboard stats first
    loadStats();

    // Initialize blocks tab by default
    initBlocksTab();

    console.log('[Viewer] Initialized');
  }

  // Auto-initialize on DOMContentLoaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Expose necessary functions globally for onclick handlers
  window.THROnosViewer = {
    loadStats,
    loadBlocks,
    renderBlocks,
    handleLoadMoreBlocks,
    initBlocksTab,
    loadTransfersStats,
    loadTransfers,
    renderTransfers,
    handleLoadMoreTransfers,
    handleRefreshTransfers,
    initTransfersTab
  };

})();
