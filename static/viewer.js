/**
 * Thronos Blockchain Viewer - Client-Side Implementation
 *
 * Clean IIFE structure to avoid global conflicts
 * Provides viewer functionality for blocks and transfers
 */

(function() {
  'use strict';

  // ===== Configuration =====
  const API_BASE = window.TH_API_BASE_URL || window.location.origin;

  // ===== State =====
  let currentBlocksOffset = 0;
  let currentTransfersOffset = 0;
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
  async function loadStats() {
    try {
      const response = await fetch(`${API_BASE}/api/dashboard`);
      if (!response.ok) throw new Error(`Dashboard API error: ${response.status}`);

      const data = await response.json();
      if (!data.ok) throw new Error('Dashboard returned ok=false');

      dashboardStats = data.stats;

      // Update counters with correct IDs
      if (el('stat-block-count')) {
        el('stat-block-count').textContent = formatNumber(dashboardStats.block_count);
      }
      if (el('stat-fees-burned')) {
        el('stat-fees-burned').textContent = formatTHR(dashboardStats.burned_total_thr || 0);
      }
      if (el('stat-total-rewards')) {
        el('stat-total-rewards').textContent = formatTHR(dashboardStats.total_rewards_thr || 0);
      }
      if (el('stat-avg-reward')) {
        const avgReward = dashboardStats.block_count > 0 ?
          (dashboardStats.total_rewards_thr || 0) / dashboardStats.block_count : 0;
        el('stat-avg-reward').textContent = formatTHR(avgReward);
      }

      // Also update old IDs for compatibility
      if (el('blocksTotalCount')) {
        el('blocksTotalCount').textContent = formatNumber(dashboardStats.block_count);
      }
      if (el('blocksTotalBurned')) {
        el('blocksTotalBurned').textContent = formatTHR(dashboardStats.burned_total_thr || 0);
      }
      if (el('blocksTotalRewards')) {
        el('blocksTotalRewards').textContent = formatTHR(dashboardStats.total_rewards_thr || 0);
      }
      if (el('blocksAvgReward')) {
        const avgReward = dashboardStats.block_count > 0 ?
          (dashboardStats.total_rewards_thr || 0) / dashboardStats.block_count : 0;
        el('blocksAvgReward').textContent = formatTHR(avgReward);
      }

      return dashboardStats;
    } catch (error) {
      console.error('[Viewer] Failed to load dashboard stats:', error);
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

  // ===== Initialization =====
  function init() {
    console.log('[Viewer] Initializing...');

    // Load dashboard stats first
    loadStats();

    // Initialize blocks tab
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
    initBlocksTab
  };

})();
