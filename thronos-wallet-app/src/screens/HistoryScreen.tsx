import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, FlatList, RefreshControl, ActivityIndicator,
  TouchableOpacity, Modal, ScrollView, Dimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { COLORS, SPACING, FONT_SIZES, BORDER_RADIUS } from '../constants/theme';
import { useStore } from '../store/useStore';
import { getTransactionHistory, getTransactionsByCategory } from '../services/api';

const { width: SCREEN_W } = Dimensions.get('window');

// ── Types ────────────────────────────────────────────────────────────────────

interface Transaction {
  id: string;
  hash: string;
  type: string;
  category: string;
  from: string;
  to: string;
  amount: number;
  token: string;
  fee: number;
  timestamp: string;       // ISO 8601 string
  timestampMs: number;     // Unix ms for sorting/formatting
  status: 'confirmed' | 'pending' | 'failed';
  chain: string;
  service: string;
  description: string;
  direction: 'sent' | 'received' | 'related';
  metadata?: Record<string, any>;
}

// ── Category Definitions ─────────────────────────────────────────────────────

interface CategoryDef {
  key: string;
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
  core: boolean;
  description: string;
}

const TX_CATEGORIES: CategoryDef[] = [
  { key: 'all', label: 'All', icon: 'apps', color: COLORS.gold, core: true, description: 'All transactions' },
  { key: 'thr', label: 'THR', icon: 'diamond', color: COLORS.gold, core: true, description: 'Native THR transfers' },
  { key: 'tokens', label: 'Tokens', icon: 'layers', color: COLORS.primary, core: true, description: 'Custom token transfers' },
  { key: 'mining', label: 'Mining', icon: 'hardware-chip', color: '#10B981', core: true, description: 'Mining rewards' },
  { key: 'swaps', label: 'Swaps', icon: 'swap-horizontal', color: '#3B82F6', core: true, description: 'Token swaps' },
  { key: 'liquidity', label: 'Liquidity', icon: 'water', color: '#06B6D4', core: true, description: 'Pool operations' },
  { key: 'gateway', label: 'Gateway', icon: 'git-network', color: '#8B5CF6', core: true, description: 'Gateway operations' },
  { key: 'l2e', label: 'L2E', icon: 'school', color: '#F59E0B', core: true, description: 'Learn-to-Earn' },
  { key: 'ai_credits', label: 'AI Credits', icon: 'sparkles', color: '#EC4899', core: true, description: 'Pytheia AI credits' },
  { key: 'bridge', label: 'Bridge', icon: 'link', color: '#14B8A6', core: false, description: 'Cross-chain bridge' },
  { key: 'music', label: 'Music', icon: 'musical-notes', color: '#A855F7', core: false, description: 'Music tips & royalties' },
  { key: 'iot', label: 'IoT', icon: 'radio', color: '#EAB308', core: false, description: 'IoT & telemetry' },
  { key: 'staking', label: 'Staking', icon: 'trending-up', color: '#22C55E', core: false, description: 'Pledge & staking' },
  { key: 'nft', label: 'NFTs', icon: 'image', color: '#F97316', core: false, description: 'NFT operations' },
  { key: 'governance', label: 'Governance', icon: 'people', color: '#64748B', core: false, description: 'Governance' },
];

// ── Chain Info ────────────────────────────────────────────────────────────────

const CHAIN_INFO: Record<string, { label: string; color: string; icon: keyof typeof Ionicons.glyphMap }> = {
  thronos: { label: 'Thronos', color: COLORS.gold, icon: 'diamond' },
  bitcoin: { label: 'Bitcoin', color: '#F7931A', icon: 'logo-bitcoin' },
  ethereum: { label: 'Ethereum', color: '#627EEA', icon: 'logo-web-component' },
  bsc: { label: 'BSC', color: '#F3BA2F', icon: 'cube' },
  polygon: { label: 'Polygon', color: '#8247E5', icon: 'triangle' },
  arbitrum: { label: 'Arbitrum', color: '#28A0F0', icon: 'layers' },
  avalanche: { label: 'Avalanche', color: '#E84142', icon: 'snow' },
  base: { label: 'Base', color: '#0052FF', icon: 'ellipse' },
};

// ── API → Frontend Category Mapping ──────────────────────────────────────────
// The backend returns raw categories like 'token_transfer', 'music_tip', etc.
// We map them to our frontend category keys.

const CATEGORY_MAP: Record<string, string> = {
  thr: 'thr',
  transfer: 'thr',
  token_transfer: 'tokens',
  tokens: 'tokens',
  mining: 'mining',
  mining_reward: 'mining',
  swaps: 'swaps',
  swap: 'swaps',
  liquidity: 'liquidity',
  bridge: 'bridge',
  music_tip: 'music',
  music_stream: 'music',
  music_royalty: 'music',
  music: 'music',
  ai_credits: 'ai_credits',
  ai_reward: 'ai_credits',
  architect: 'ai_credits',
  architect_job: 'ai_credits',
  t2e: 'l2e',
  t2e_reward_thr: 'l2e',
  l2e: 'l2e',
  iot: 'iot',
  iot_telemetry: 'iot',
  iot_reward: 'iot',
  iot_mining_reward: 'iot',
  gps_mining: 'iot',
  music_gps_telemetry: 'iot',
  pledge: 'staking',
  staking: 'staking',
  nft: 'nft',
  nft_mint: 'nft',
  nft_buy: 'nft',
  verifyid: 'gateway',
  gateway: 'gateway',
  fiat_buy: 'gateway',
  fiat_deposit: 'gateway',
  other: 'thr',
};

// ── Helpers ──────────────────────────────────────────────────────────────────

function safeFloat(v: any): number {
  if (v === null || v === undefined || v === '') return 0;
  const n = typeof v === 'number' ? v : parseFloat(String(v));
  return isNaN(n) ? 0 : n;
}

function parseTimestamp(ts: any): number {
  if (!ts) return 0;
  // Unix seconds (number)
  if (typeof ts === 'number') {
    return ts > 1e12 ? ts : ts * 1000; // seconds → ms
  }
  const s = String(ts);
  // ISO 8601 string
  const d = new Date(s);
  if (!isNaN(d.getTime())) return d.getTime();
  // Try replacing Z
  const d2 = new Date(s.replace('Z', '+00:00'));
  if (!isNaN(d2.getTime())) return d2.getTime();
  return 0;
}

function formatTime(ms: number): string {
  if (ms <= 0) return '';
  const now = Date.now();
  const diff = now - ms;
  const mins = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (diff < 0) return 'Just now';
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 7) return `${days}d ago`;
  const d = new Date(ms);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatFullDate(ms: number): string {
  if (ms <= 0) return 'N/A';
  const d = new Date(ms);
  return d.toLocaleDateString('en-US', {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

function formatAmount(amount: number): string {
  if (amount === 0) return '0';
  if (Math.abs(amount) >= 1000) return amount.toLocaleString('en-US', { maximumFractionDigits: 2 });
  if (Math.abs(amount) >= 1) return amount.toFixed(2);
  if (Math.abs(amount) >= 0.01) return amount.toFixed(4);
  return amount.toFixed(6);
}

function describeTransaction(tx: any, walletAddr: string): string {
  const kind = (tx.kind || tx.type || '').toLowerCase();
  const cat = (tx.category || '').toLowerCase();
  const dir = tx.direction || (tx.to === walletAddr ? 'received' : tx.from === walletAddr ? 'sent' : 'related');

  if (kind === 'mining_reward' || cat === 'mining') return 'Mining Reward';
  if (cat === 'music_tip' || kind === 'music_tip') return dir === 'received' ? 'Music Tip Received' : 'Music Tip Sent';
  if (cat === 'music_stream' || kind === 'music_stream') return 'Music Stream Earning';
  if (cat === 'music_royalty' || kind === 'music_royalty') return 'Music Royalty';
  if (kind.includes('music')) return 'Music Earning';
  if (kind === 'swap' || cat === 'swaps' || cat === 'swap') {
    const pair = tx.meta?.pair || tx.pair;
    return pair ? `Swap ${pair}` : 'Token Swap';
  }
  if (kind === 'liquidity' || cat === 'liquidity') {
    return kind.includes('remove') ? 'Remove Liquidity' : 'Add Liquidity';
  }
  if (cat === 'bridge' || kind === 'bridge') return 'Bridge Transfer';
  if (cat === 'ai_credits' || kind === 'ai_credits') return 'AI Credits';
  if (cat === 'iot' || kind.includes('iot') || kind.includes('gps')) return 'IoT Telemetry';
  if (cat === 'pledge' || kind === 'pledge') return 'Pledge';
  if (cat === 'nft' || kind.includes('nft')) return 'NFT Transfer';
  if (cat === 'l2e' || cat === 't2e' || kind.includes('t2e')) return 'Learn-to-Earn Reward';
  if (kind === 'token_transfer' || cat === 'token_transfer') {
    const sym = tx.symbol || tx.token_symbol || tx.asset_symbol || 'Token';
    return dir === 'received' ? `Received ${sym}` : `Sent ${sym}`;
  }
  // Default: THR transfer
  return dir === 'received' ? 'Received' : dir === 'sent' ? 'Sent' : 'Transfer';
}

// ── Normalize raw API transaction into our format ────────────────────────────

function normalizeTx(raw: any, walletAddr: string): Transaction {
  const addrLower = walletAddr.toLowerCase();
  const from = raw.from || raw.sender || '';
  const to = raw.to || raw.recipient || '';
  const isFromWallet = from.toLowerCase() === addrLower;
  const isToWallet = to.toLowerCase() === addrLower;
  const direction = raw.direction || (isToWallet ? 'received' : isFromWallet ? 'sent' : 'related');

  const kind = (raw.kind || raw.type || '').toLowerCase();
  const rawCategory = (raw.category || raw.source || kind).toLowerCase();
  const category = CATEGORY_MAP[rawCategory] || CATEGORY_MAP[kind] || 'thr';

  const symbol = (raw.symbol || raw.asset_symbol || raw.token_symbol || raw.token || 'THR').toUpperCase();
  const amount = safeFloat(raw.display_amount ?? raw.amount);
  const fee = safeFloat(raw.fee_burned ?? raw.fee ?? raw.meta?.fee ?? raw.meta?.fee_burned);
  const hash = raw.tx_id || raw.hash || raw.id || raw.bridge_id || '';
  const tsMs = parseTimestamp(raw.timestamp);
  const status = raw.pending ? 'pending' : (raw.status || 'confirmed');
  const chain = raw.chain || raw.network || 'thronos';

  // Determine service label from category/kind
  let service = '';
  if (kind === 'mining_reward') service = 'Mining';
  else if (rawCategory.includes('music')) service = 'Decent Music';
  else if (rawCategory.includes('swap')) service = 'DEX';
  else if (rawCategory.includes('liquidity')) service = 'Liquidity Pool';
  else if (rawCategory.includes('bridge')) service = 'Bridge';
  else if (rawCategory.includes('ai') || rawCategory.includes('architect')) service = 'Pytheia AI';
  else if (rawCategory.includes('iot') || rawCategory.includes('gps')) service = 'IoT';
  else if (rawCategory.includes('nft')) service = 'NFT Market';
  else if (rawCategory.includes('pledge') || rawCategory.includes('staking')) service = 'Staking';
  else if (rawCategory.includes('l2e') || rawCategory.includes('t2e')) service = 'Learn2Earn';
  else if (rawCategory.includes('gateway') || rawCategory.includes('fiat')) service = 'Fiat Gateway';
  else if (rawCategory === 'token_transfer' || rawCategory === 'tokens') service = 'Tokens';
  else service = 'THR';

  return {
    id: hash || `${from}-${to}-${tsMs}`,
    hash,
    type: direction === 'received' ? 'receive' : 'send',
    category,
    from,
    to,
    amount,
    token: symbol,
    fee,
    timestamp: raw.timestamp || '',
    timestampMs: tsMs,
    status: status as any,
    chain: chain.toLowerCase(),
    service,
    description: raw.description || describeTransaction(raw, walletAddr),
    direction: direction as any,
    metadata: raw.meta || raw.metadata || {},
  };
}

function getCategoryDef(key: string): CategoryDef {
  return TX_CATEGORIES.find((c) => c.key === key) || TX_CATEGORIES[0];
}

// ── Component ────────────────────────────────────────────────────────────────

export default function HistoryScreen() {
  const { wallet, recentTxs, setRecentTxs } = useStore();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [activeCategory, setActiveCategory] = useState('all');
  const [activeChainFilter, setActiveChainFilter] = useState<string | null>(null);
  const [txDetailVisible, setTxDetailVisible] = useState(false);
  const [selectedTx, setSelectedTx] = useState<Transaction | null>(null);
  const [allTxs, setAllTxs] = useState<Transaction[]>([]);
  const [stats, setStats] = useState({ total: 0, volume: 0, services: 0 });

  const load = useCallback(async () => {
    if (!wallet.address) return;
    setLoading(true);
    try {
      const result = activeCategory === 'all'
        ? await getTransactionHistory(wallet.address, 200)
        : await getTransactionsByCategory(wallet.address, activeCategory, 200);

      // Handle various API response shapes
      const rawList: any[] = Array.isArray(result)
        ? result
        : (result as any)?.transactions || (result as any)?.history || [];

      // Normalize every transaction
      const normalized = rawList
        .map((raw: any) => normalizeTx(raw, wallet.address))
        .sort((a, b) => b.timestampMs - a.timestampMs);

      setAllTxs(normalized);
      setRecentTxs(normalized.slice(0, 50));
    } catch (err) {
      console.warn('Failed to load transaction history:', err);
    } finally {
      setLoading(false);
    }
  }, [wallet.address, activeCategory]);

  useEffect(() => { load(); }, [load]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }, [load]);

  // Calculate stats
  useEffect(() => {
    const uniqueServices = new Set(allTxs.map((t) => t.service).filter(Boolean));
    const totalVolume = allTxs.reduce((sum, t) => sum + Math.abs(t.amount), 0);
    setStats({ total: allTxs.length, volume: totalVolume, services: uniqueServices.size });
  }, [allTxs]);

  // Filter transactions
  const filteredTxs = allTxs.filter((tx) => {
    const catMatch = activeCategory === 'all' || tx.category === activeCategory;
    const chainMatch = !activeChainFilter || tx.chain === activeChainFilter;
    return catMatch && chainMatch;
  });

  const openDetail = (tx: Transaction) => {
    setSelectedTx(tx);
    setTxDetailVisible(true);
  };

  // ── Render ──────────────────────────────────────────────────────────────────

  const renderCategoryChip = (cat: CategoryDef) => {
    const isActive = activeCategory === cat.key;
    const count = cat.key === 'all' ? allTxs.length : allTxs.filter((t) => t.category === cat.key).length;

    return (
      <TouchableOpacity
        key={cat.key}
        style={[styles.categoryChip, isActive && { backgroundColor: cat.color + '25', borderColor: cat.color }]}
        onPress={() => setActiveCategory(cat.key)}
      >
        <Ionicons name={cat.icon} size={14} color={isActive ? cat.color : COLORS.textMuted} />
        <Text style={[styles.categoryChipText, isActive && { color: cat.color }]}>{cat.label}</Text>
        {count > 0 && (
          <View style={[styles.categoryBadge, isActive && { backgroundColor: cat.color }]}>
            <Text style={styles.categoryBadgeText}>{count}</Text>
          </View>
        )}
      </TouchableOpacity>
    );
  };

  const renderTx = ({ item }: { item: Transaction }) => {
    const isSend = item.direction === 'sent';
    const catDef = getCategoryDef(item.category);
    const chainInfo = CHAIN_INFO[item.chain] || CHAIN_INFO.thronos;

    return (
      <TouchableOpacity style={styles.txRow} onPress={() => openDetail(item)} activeOpacity={0.7}>
        <View style={[styles.txIcon, { backgroundColor: catDef.color + '20' }]}>
          <Ionicons name={catDef.icon} size={20} color={catDef.color} />
          {item.status === 'pending' && <View style={styles.pendingDot} />}
        </View>
        <View style={styles.txInfo}>
          <Text style={styles.txType} numberOfLines={1}>{item.description}</Text>
          <View style={styles.txMetaRow}>
            <Text style={styles.txService}>{item.service}</Text>
            {item.chain && item.chain !== 'thronos' && (
              <View style={[styles.chainBadge, { backgroundColor: chainInfo.color + '20' }]}>
                <Text style={[styles.chainBadgeText, { color: chainInfo.color }]}>{chainInfo.label}</Text>
              </View>
            )}
            {item.timestampMs > 0 && (
              <Text style={styles.txTime}>{formatTime(item.timestampMs)}</Text>
            )}
          </View>
        </View>
        <View style={styles.txAmount}>
          <Text style={[styles.txAmountText, { color: isSend ? COLORS.error : COLORS.success }]}>
            {isSend ? '-' : '+'}{formatAmount(item.amount)} {item.token}
          </Text>
          {item.fee > 0 && (
            <Text style={styles.txFee}>Fee: {item.fee} THR</Text>
          )}
          {item.status === 'pending' && (
            <Text style={styles.txPending}>Pending</Text>
          )}
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>History</Text>
        <View style={styles.headerActions}>
          <TouchableOpacity style={styles.filterBtn}>
            <Ionicons name="funnel-outline" size={18} color={COLORS.textSecondary} />
          </TouchableOpacity>
        </View>
      </View>

      {/* Stats Bar */}
      <View style={styles.statsBar}>
        <View style={styles.stat}>
          <Text style={styles.statVal}>{stats.total}</Text>
          <Text style={styles.statLabel}>Transactions</Text>
        </View>
        <View style={styles.statDivider} />
        <View style={styles.stat}>
          <Text style={styles.statVal}>{formatAmount(stats.volume)}</Text>
          <Text style={styles.statLabel}>Volume</Text>
        </View>
        <View style={styles.statDivider} />
        <View style={styles.stat}>
          <Text style={styles.statVal}>{stats.services}</Text>
          <Text style={styles.statLabel}>Services</Text>
        </View>
        <View style={styles.statDivider} />
        <View style={styles.stat}>
          <View style={styles.acicBadge}>
            <Ionicons name="flash" size={10} color={COLORS.gold} />
            <Text style={styles.acicText}>ACIC</Text>
          </View>
          <Text style={styles.statLabel}>Speed</Text>
        </View>
      </View>

      {/* Cross-Chain Filter */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chainFilterRow} contentContainerStyle={{ paddingHorizontal: SPACING.lg, gap: SPACING.xs }}>
        <TouchableOpacity
          style={[styles.chainChip, !activeChainFilter && styles.chainChipActive]}
          onPress={() => setActiveChainFilter(null)}
        >
          <Text style={[styles.chainChipText, !activeChainFilter && styles.chainChipTextActive]}>All Chains</Text>
        </TouchableOpacity>
        {Object.entries(CHAIN_INFO).map(([key, info]) => (
          <TouchableOpacity
            key={key}
            style={[styles.chainChip, activeChainFilter === key && { backgroundColor: info.color + '20', borderColor: info.color }]}
            onPress={() => setActiveChainFilter(activeChainFilter === key ? null : key)}
          >
            <Ionicons name={info.icon} size={12} color={activeChainFilter === key ? info.color : COLORS.textMuted} />
            <Text style={[styles.chainChipText, activeChainFilter === key && { color: info.color }]}>{info.label}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      {/* Category Filter */}
      <View style={styles.categoriesSection}>
        <Text style={styles.categorySectionLabel}>Core Services</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: SPACING.lg, gap: SPACING.xs }}>
          {TX_CATEGORIES.filter((c) => c.core).map(renderCategoryChip)}
        </ScrollView>
        <Text style={[styles.categorySectionLabel, { marginTop: SPACING.sm }]}>Extended Services</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: SPACING.lg, gap: SPACING.xs }}>
          {TX_CATEGORIES.filter((c) => !c.core).map(renderCategoryChip)}
        </ScrollView>
      </View>

      {/* Transaction List */}
      {loading ? (
        <View style={styles.center}><ActivityIndicator color={COLORS.gold} size="large" /></View>
      ) : filteredTxs.length === 0 ? (
        <View style={styles.center}>
          <Ionicons name="time-outline" size={56} color={COLORS.textMuted} />
          <Text style={styles.emptyText}>No transactions found</Text>
          <Text style={styles.emptySubText}>
            {activeCategory !== 'all' ? `No ${getCategoryDef(activeCategory).label} transactions yet` : 'Your transaction history will appear here'}
          </Text>
        </View>
      ) : (
        <FlatList
          data={filteredTxs}
          keyExtractor={(item, i) => item.id || String(i)}
          renderItem={renderTx}
          contentContainerStyle={styles.list}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.gold} />}
        />
      )}

      {/* Transaction Detail Modal */}
      <Modal visible={txDetailVisible} transparent animationType="slide">
        <View style={styles.modalOverlay}>
          <View style={styles.detailModal}>
            <View style={styles.detailHeader}>
              <Text style={styles.detailTitle}>Transaction Detail</Text>
              <TouchableOpacity onPress={() => setTxDetailVisible(false)}>
                <Ionicons name="close" size={24} color={COLORS.text} />
              </TouchableOpacity>
            </View>

            {selectedTx && (
              <ScrollView style={styles.detailContent}>
                {/* Status */}
                <View style={[styles.detailStatus, {
                  backgroundColor: selectedTx.status === 'confirmed' ? COLORS.success + '15' :
                    selectedTx.status === 'pending' ? COLORS.warning + '15' : COLORS.error + '15',
                }]}>
                  <Ionicons
                    name={selectedTx.status === 'confirmed' ? 'checkmark-circle' : selectedTx.status === 'pending' ? 'time' : 'close-circle'}
                    size={20}
                    color={selectedTx.status === 'confirmed' ? COLORS.success : selectedTx.status === 'pending' ? COLORS.warning : COLORS.error}
                  />
                  <Text style={[styles.detailStatusText, {
                    color: selectedTx.status === 'confirmed' ? COLORS.success : selectedTx.status === 'pending' ? COLORS.warning : COLORS.error,
                  }]}>{selectedTx.status.charAt(0).toUpperCase() + selectedTx.status.slice(1)}</Text>
                </View>

                {/* Amount */}
                <View style={styles.detailAmountSection}>
                  <Text style={styles.detailAmountLabel}>{selectedTx.description}</Text>
                  <Text style={[styles.detailAmount, {
                    color: selectedTx.direction === 'sent' ? COLORS.error : COLORS.success,
                  }]}>
                    {selectedTx.direction === 'sent' ? '-' : '+'}{formatAmount(selectedTx.amount)}
                  </Text>
                  <Text style={styles.detailTokenLabel}>{selectedTx.token}</Text>
                </View>

                {/* Detail Rows */}
                {[
                  { label: 'Description', value: selectedTx.description },
                  { label: 'Service', value: selectedTx.service },
                  { label: 'Category', value: getCategoryDef(selectedTx.category).label },
                  { label: 'Chain', value: CHAIN_INFO[selectedTx.chain]?.label || 'Thronos' },
                  { label: 'From', value: selectedTx.from || 'N/A', mono: true },
                  { label: 'To', value: selectedTx.to || 'N/A', mono: true },
                  { label: 'Fee', value: selectedTx.fee > 0 ? `${selectedTx.fee} THR` : 'Free' },
                  { label: 'Time', value: formatFullDate(selectedTx.timestampMs) },
                  { label: 'TX Hash', value: selectedTx.hash || 'Pending...', mono: true },
                ].map((row) => (
                  <View key={row.label} style={styles.detailRow}>
                    <Text style={styles.detailRowLabel}>{row.label}</Text>
                    <Text style={[styles.detailRowValue, row.mono && styles.monoText]} numberOfLines={1}>
                      {row.value}
                    </Text>
                  </View>
                ))}

                {/* ACIC Speed Badge */}
                <View style={styles.acicSection}>
                  <LinearGradient colors={['#2A1A0A', '#1A1A33']} style={styles.acicCard}>
                    <Ionicons name="flash" size={20} color={COLORS.gold} />
                    <View style={{ flex: 1, marginLeft: SPACING.sm }}>
                      <Text style={styles.acicCardTitle}>ACIC Accelerated</Text>
                      <Text style={styles.acicCardDesc}>
                        This transaction was routed through Thronos ACIC nodes for maximum speed and finality.
                      </Text>
                    </View>
                  </LinearGradient>
                </View>
              </ScrollView>
            )}
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

// ── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.background },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.lg, paddingVertical: SPACING.sm },
  title: { fontSize: FONT_SIZES.xxl, fontWeight: '700', color: COLORS.text },
  headerActions: { flexDirection: 'row', gap: SPACING.sm },
  filterBtn: { padding: SPACING.xs },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', gap: SPACING.md, paddingHorizontal: SPACING.xl },
  emptyText: { fontSize: FONT_SIZES.lg, color: COLORS.textMuted, fontWeight: '600' },
  emptySubText: { fontSize: FONT_SIZES.sm, color: COLORS.textMuted, textAlign: 'center' },
  list: { paddingHorizontal: SPACING.lg, paddingBottom: 20 },

  // Stats Bar
  statsBar: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-around',
    marginHorizontal: SPACING.lg, marginBottom: SPACING.sm,
    backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.lg,
    padding: SPACING.md, borderWidth: 1, borderColor: COLORS.border,
  },
  stat: { alignItems: 'center' },
  statVal: { fontSize: FONT_SIZES.lg, fontWeight: '700', color: COLORS.text },
  statLabel: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, marginTop: 2 },
  statDivider: { width: 1, height: 28, backgroundColor: COLORS.border },
  acicBadge: { flexDirection: 'row', alignItems: 'center', gap: 2, backgroundColor: COLORS.gold + '20', paddingHorizontal: 6, paddingVertical: 2, borderRadius: BORDER_RADIUS.sm },
  acicText: { fontSize: FONT_SIZES.xs, fontWeight: '700', color: COLORS.gold },

  // Chain Filter
  chainFilterRow: { marginBottom: SPACING.sm, maxHeight: 36 },
  chainChip: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: SPACING.sm, paddingVertical: 4,
    borderRadius: BORDER_RADIUS.full, backgroundColor: COLORS.surface,
    borderWidth: 1, borderColor: COLORS.border,
  },
  chainChipActive: { backgroundColor: COLORS.gold + '15', borderColor: COLORS.gold },
  chainChipText: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, fontWeight: '500' },
  chainChipTextActive: { color: COLORS.gold },

  // Category Filter
  categoriesSection: { marginBottom: SPACING.sm },
  categorySectionLabel: {
    fontSize: FONT_SIZES.xs, color: COLORS.textMuted, fontWeight: '600',
    paddingHorizontal: SPACING.lg, marginBottom: 4, textTransform: 'uppercase', letterSpacing: 1,
  },
  categoryChip: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: SPACING.sm, paddingVertical: 4,
    borderRadius: BORDER_RADIUS.full, backgroundColor: COLORS.surface,
    borderWidth: 1, borderColor: COLORS.border,
  },
  categoryChipText: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, fontWeight: '500' },
  categoryBadge: {
    backgroundColor: COLORS.textMuted, borderRadius: BORDER_RADIUS.full,
    minWidth: 16, height: 16, justifyContent: 'center', alignItems: 'center', paddingHorizontal: 4,
  },
  categoryBadgeText: { fontSize: 9, color: '#FFF', fontWeight: '700' },

  // Transaction Row
  txRow: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.lg,
    padding: SPACING.md, marginBottom: SPACING.sm,
    borderWidth: 1, borderColor: COLORS.border,
  },
  txIcon: {
    width: 40, height: 40, borderRadius: BORDER_RADIUS.md,
    justifyContent: 'center', alignItems: 'center', marginRight: SPACING.md,
  },
  pendingDot: {
    position: 'absolute', top: -2, right: -2,
    width: 8, height: 8, borderRadius: 4,
    backgroundColor: COLORS.warning, borderWidth: 1.5, borderColor: COLORS.surface,
  },
  txInfo: { flex: 1 },
  txType: { fontSize: FONT_SIZES.sm, fontWeight: '600', color: COLORS.text },
  txMetaRow: { flexDirection: 'row', alignItems: 'center', gap: SPACING.xs, marginTop: 3 },
  txService: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted },
  chainBadge: { paddingHorizontal: 4, paddingVertical: 1, borderRadius: BORDER_RADIUS.sm },
  chainBadgeText: { fontSize: 9, fontWeight: '600' },
  txTime: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted },
  txAmount: { alignItems: 'flex-end', marginLeft: SPACING.sm },
  txAmountText: { fontSize: FONT_SIZES.md, fontWeight: '700' },
  txFee: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, marginTop: 2 },
  txPending: { fontSize: FONT_SIZES.xs, color: COLORS.warning, fontWeight: '600', marginTop: 2 },

  // Detail Modal
  modalOverlay: { flex: 1, backgroundColor: COLORS.overlay, justifyContent: 'flex-end' },
  detailModal: {
    backgroundColor: COLORS.backgroundCard, borderTopLeftRadius: BORDER_RADIUS.xl,
    borderTopRightRadius: BORDER_RADIUS.xl, maxHeight: '85%',
    borderWidth: 1, borderColor: COLORS.border, borderBottomWidth: 0,
  },
  detailHeader: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: SPACING.lg, paddingVertical: SPACING.md,
    borderBottomWidth: 1, borderBottomColor: COLORS.border,
  },
  detailTitle: { fontSize: FONT_SIZES.xl, fontWeight: '700', color: COLORS.text },
  detailContent: { padding: SPACING.lg },
  detailStatus: {
    flexDirection: 'row', alignItems: 'center', gap: SPACING.sm,
    padding: SPACING.md, borderRadius: BORDER_RADIUS.lg, marginBottom: SPACING.lg,
  },
  detailStatusText: { fontSize: FONT_SIZES.md, fontWeight: '600' },
  detailAmountSection: { alignItems: 'center', marginBottom: SPACING.lg },
  detailAmountLabel: { fontSize: FONT_SIZES.sm, color: COLORS.textSecondary },
  detailAmount: { fontSize: FONT_SIZES.xxxl, fontWeight: '800', marginTop: SPACING.xs },
  detailTokenLabel: { fontSize: FONT_SIZES.md, color: COLORS.textSecondary, marginTop: 2 },
  detailRow: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.border,
  },
  detailRowLabel: { fontSize: FONT_SIZES.sm, color: COLORS.textMuted, flex: 1 },
  detailRowValue: { fontSize: FONT_SIZES.sm, color: COLORS.text, flex: 2, textAlign: 'right' },
  monoText: { fontFamily: 'monospace', fontSize: FONT_SIZES.xs },

  // ACIC Section
  acicSection: { marginTop: SPACING.lg },
  acicCard: {
    flexDirection: 'row', alignItems: 'center',
    padding: SPACING.md, borderRadius: BORDER_RADIUS.lg,
    borderWidth: 1, borderColor: COLORS.gold + '30',
  },
  acicCardTitle: { fontSize: FONT_SIZES.md, fontWeight: '600', color: COLORS.gold },
  acicCardDesc: { fontSize: FONT_SIZES.xs, color: COLORS.textSecondary, marginTop: 2, lineHeight: 16 },
});
