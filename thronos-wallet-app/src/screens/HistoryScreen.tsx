import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  View, Text, StyleSheet, FlatList, RefreshControl, ActivityIndicator,
  TouchableOpacity, Modal, ScrollView, Animated, Dimensions,
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
  id?: string;
  hash?: string;
  type: string;         // 'send' | 'receive' | 'swap' | 'bridge' | 'stake' | 'mining' | 'music' | ...
  category: string;     // Service category
  from: string;
  to: string;
  amount: number;
  token: string;
  fee?: number;
  timestamp: string;
  status: 'confirmed' | 'pending' | 'failed';
  chain?: string;       // 'thronos' | 'bitcoin' | 'ethereum' | 'bsc' | 'polygon'
  service?: string;     // Which service generated the tx
  description?: string; // Human-readable description
  metadata?: Record<string, any>;
}

// ── Category Definitions (Core + Non-Core Services) ─────────────────────────

interface CategoryDef {
  key: string;
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
  core: boolean;  // core service or external
  description: string;
}

const TX_CATEGORIES: CategoryDef[] = [
  // ── Core Services ──
  { key: 'all', label: 'All', icon: 'apps', color: COLORS.gold, core: true, description: 'All transactions' },
  { key: 'thr', label: 'THR', icon: 'diamond', color: COLORS.gold, core: true, description: 'Native THR transfers' },
  { key: 'tokens', label: 'Tokens', icon: 'layers', color: COLORS.primary, core: true, description: 'Custom token transfers' },
  { key: 'mining', label: 'Mining', icon: 'hardware-chip', color: '#10B981', core: true, description: 'Mining rewards & payouts' },
  { key: 'swaps', label: 'Swaps', icon: 'swap-horizontal', color: '#3B82F6', core: true, description: 'Token swap operations' },
  { key: 'liquidity', label: 'Liquidity', icon: 'water', color: '#06B6D4', core: true, description: 'Liquidity pool operations' },
  { key: 'gateway', label: 'Gateway', icon: 'git-network', color: '#8B5CF6', core: true, description: 'Gateway node operations' },
  { key: 'l2e', label: 'L2E', icon: 'school', color: '#F59E0B', core: true, description: 'Learn-to-Earn rewards' },
  { key: 'ai_credits', label: 'AI Credits', icon: 'sparkles', color: '#EC4899', core: true, description: 'Pytheia AI credit usage' },

  // ── Non-Core / Extended Services ──
  { key: 'bridge', label: 'Bridge', icon: 'link', color: '#14B8A6', core: false, description: 'Cross-chain bridge transfers' },
  { key: 'music', label: 'Music', icon: 'musical-notes', color: '#A855F7', core: false, description: 'Decent Music tips & royalties' },
  { key: 'iot', label: 'IoT', icon: 'radio', color: '#EAB308', core: false, description: 'IoT vehicle & sensor data' },
  { key: 'staking', label: 'Staking', icon: 'trending-up', color: '#22C55E', core: false, description: 'Pledge & staking rewards' },
  { key: 'nft', label: 'NFTs', icon: 'image', color: '#F97316', core: false, description: 'NFT mints & transfers' },
  { key: 'governance', label: 'Governance', icon: 'people', color: '#64748B', core: false, description: 'Governance votes & proposals' },
];

// ── Cross-Chain Labels ──────────────────────────────────────────────────────

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

// ── Mock Data ────────────────────────────────────────────────────────────────

const MOCK_TXS: Transaction[] = [
  { type: 'receive', category: 'mining', from: 'THR_Mining_Pool', to: 'THR...user', amount: 125.5, token: 'THR', timestamp: '2026-03-15T08:12:00Z', status: 'confirmed', chain: 'thronos', service: 'Micro Miner', description: 'Mining reward - Block #284901' },
  { type: 'send', category: 'music', from: 'THR...user', to: 'THR...artist', amount: 5.0, token: 'THR', timestamp: '2026-03-15T07:45:00Z', status: 'confirmed', chain: 'thronos', service: 'Decent Music', description: 'Tip to CryptoWave - "Decentralize"' },
  { type: 'receive', category: 'l2e', from: 'THR_T2E_Pool', to: 'THR...user', amount: 42.0, token: 'T2E', timestamp: '2026-03-15T06:30:00Z', status: 'confirmed', chain: 'thronos', service: 'Architect T2E', description: 'Pytheia Language Model training reward' },
  { type: 'send', category: 'bridge', from: 'THR...user', to: '0x...bridge', amount: 500.0, token: 'THR', fee: 0.5, timestamp: '2026-03-14T22:15:00Z', status: 'confirmed', chain: 'thronos', service: 'BTC Bridge', description: 'Bridge THR → WBTC' },
  { type: 'receive', category: 'bridge', from: '0x...bridge', to: 'THR...user', amount: 0.015, token: 'WBTC', timestamp: '2026-03-14T22:20:00Z', status: 'confirmed', chain: 'bitcoin', service: 'BTC Bridge', description: 'Bridge receive WBTC' },
  { type: 'send', category: 'swaps', from: 'THR...user', to: 'THR_Swap_Pool', amount: 200.0, token: 'THR', fee: 0.3, timestamp: '2026-03-14T18:00:00Z', status: 'confirmed', chain: 'thronos', service: 'Thronos DEX', description: 'Swap THR → WBTC' },
  { type: 'receive', category: 'gateway', from: 'THR_Gateway_Node', to: 'THR...user', amount: 15.8, token: 'THR', timestamp: '2026-03-14T14:00:00Z', status: 'confirmed', chain: 'thronos', service: 'Phantom Gateway', description: 'Gateway relay reward' },
  { type: 'send', category: 'ai_credits', from: 'THR...user', to: 'THR_Pytheia', amount: 10.0, token: 'AIC', timestamp: '2026-03-14T12:30:00Z', status: 'confirmed', chain: 'thronos', service: 'Pytheia AI', description: 'AI credit purchase - 100 credits' },
  { type: 'receive', category: 'liquidity', from: 'THR_LP_Pool', to: 'THR...user', amount: 8.2, token: 'THR', timestamp: '2026-03-14T10:00:00Z', status: 'confirmed', chain: 'thronos', service: 'Liquidity Pool', description: 'LP rewards THR/WBTC pool' },
  { type: 'send', category: 'thr', from: 'THR...user', to: 'THR9a3b...c4f2', amount: 50.0, token: 'THR', fee: 0.1, timestamp: '2026-03-13T20:00:00Z', status: 'confirmed', chain: 'thronos', description: 'Transfer to THR9a3b...c4f2' },
  { type: 'receive', category: 'iot', from: 'THR_IoT_Pool', to: 'THR...user', amount: 3.2, token: 'THR', timestamp: '2026-03-13T16:00:00Z', status: 'confirmed', chain: 'thronos', service: 'IoT Vehicle Node', description: 'GPS telemetry reward - 24h uptime' },
  { type: 'receive', category: 'staking', from: 'THR_Pledge', to: 'THR...user', amount: 22.5, token: 'THR', timestamp: '2026-03-13T12:00:00Z', status: 'confirmed', chain: 'thronos', service: 'Pledge System', description: 'Staking reward - Epoch 1847' },
  { type: 'send', category: 'governance', from: 'THR...user', to: 'THR_Governance', amount: 0.1, token: 'THR', timestamp: '2026-03-13T08:00:00Z', status: 'confirmed', chain: 'thronos', service: 'Governance', description: 'Vote: Proposal #47 - Fee reduction' },
  { type: 'receive', category: 'tokens', from: 'THR_Airdrop', to: 'THR...user', amount: 100.0, token: 'CRYPT', timestamp: '2026-03-12T18:00:00Z', status: 'confirmed', chain: 'thronos', service: 'Crypto Hunters', description: 'Crypto Hunters quest reward' },
  { type: 'send', category: 'bridge', from: 'THR...user', to: '0x...eth_bridge', amount: 1000.0, token: 'THR', fee: 2.0, timestamp: '2026-03-12T14:00:00Z', status: 'pending', chain: 'ethereum', service: 'ETH Bridge', description: 'Bridge THR → ETH (processing)' },
  { type: 'receive', category: 'mining', from: 'THR_Stratum', to: 'THR...user', amount: 87.3, token: 'THR', timestamp: '2026-03-12T08:00:00Z', status: 'confirmed', chain: 'thronos', service: 'Stratum Pool', description: 'Stratum mining payout' },
];

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatTime(ts: string): string {
  const d = new Date(ts);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  const mins = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
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
  const [allTxs, setAllTxs] = useState<Transaction[]>(MOCK_TXS);
  const [stats, setStats] = useState({ total: 0, volume: 0, services: 0 });

  const load = useCallback(async () => {
    if (!wallet.address) return;
    setLoading(true);
    try {
      const endpoint = activeCategory === 'all'
        ? await getTransactionHistory(wallet.address, 100)
        : await getTransactionsByCategory(wallet.address, activeCategory, 100);

      const txList = Array.isArray(endpoint) ? endpoint : (endpoint as any)?.transactions || [];
      if (txList.length > 0) {
        setAllTxs(txList);
        setRecentTxs(txList.slice(0, 50));
      }
    } catch {
      // Keep mock data
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
    const totalVolume = allTxs.reduce((sum, t) => sum + t.amount, 0);
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
    const isSend = item.type === 'send' || item.from === wallet.address;
    const catDef = getCategoryDef(item.category);
    const chainInfo = CHAIN_INFO[item.chain || 'thronos'];

    return (
      <TouchableOpacity style={styles.txRow} onPress={() => openDetail(item)} activeOpacity={0.7}>
        <View style={[styles.txIcon, { backgroundColor: catDef.color + '20' }]}>
          <Ionicons name={catDef.icon} size={20} color={catDef.color} />
          {item.status === 'pending' && (
            <View style={styles.pendingDot} />
          )}
        </View>
        <View style={styles.txInfo}>
          <View style={styles.txInfoRow}>
            <Text style={styles.txType} numberOfLines={1}>{item.description || (isSend ? 'Sent' : 'Received')}</Text>
          </View>
          <View style={styles.txMetaRow}>
            <Text style={styles.txService}>{item.service || catDef.label}</Text>
            {item.chain && item.chain !== 'thronos' && (
              <View style={[styles.chainBadge, { backgroundColor: chainInfo.color + '20' }]}>
                <Text style={[styles.chainBadgeText, { color: chainInfo.color }]}>{chainInfo.label}</Text>
              </View>
            )}
            <Text style={styles.txTime}>{formatTime(item.timestamp)}</Text>
          </View>
        </View>
        <View style={styles.txAmount}>
          <Text style={[styles.txAmountText, { color: isSend ? COLORS.error : COLORS.success }]}>
            {isSend ? '-' : '+'}{item.amount} {item.token}
          </Text>
          {item.fee !== undefined && item.fee > 0 && (
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

      {/* Stats Bar (ACIC Speed Indicator) */}
      <View style={styles.statsBar}>
        <View style={styles.stat}>
          <Text style={styles.statVal}>{stats.total}</Text>
          <Text style={styles.statLabel}>Transactions</Text>
        </View>
        <View style={styles.statDivider} />
        <View style={styles.stat}>
          <Text style={styles.statVal}>{stats.volume.toFixed(1)}</Text>
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
          keyExtractor={(_, i) => String(i)}
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
                  <Text style={styles.detailAmountLabel}>
                    {selectedTx.type === 'send' ? 'Sent' : 'Received'}
                  </Text>
                  <Text style={[styles.detailAmount, {
                    color: selectedTx.type === 'send' ? COLORS.error : COLORS.success,
                  }]}>
                    {selectedTx.type === 'send' ? '-' : '+'}{selectedTx.amount} {selectedTx.token}
                  </Text>
                </View>

                {/* Detail Rows */}
                {[
                  { label: 'Description', value: selectedTx.description },
                  { label: 'Service', value: selectedTx.service || getCategoryDef(selectedTx.category).label },
                  { label: 'Category', value: getCategoryDef(selectedTx.category).label },
                  { label: 'Chain', value: CHAIN_INFO[selectedTx.chain || 'thronos']?.label || 'Thronos' },
                  { label: 'From', value: selectedTx.from, mono: true },
                  { label: 'To', value: selectedTx.to, mono: true },
                  { label: 'Fee', value: selectedTx.fee ? `${selectedTx.fee} THR` : 'None' },
                  { label: 'Time', value: new Date(selectedTx.timestamp).toLocaleString() },
                  { label: 'TX Hash', value: selectedTx.hash || 'N/A', mono: true },
                ].map((row) => (
                  <View key={row.label} style={styles.detailRow}>
                    <Text style={styles.detailRowLabel}>{row.label}</Text>
                    <Text style={[styles.detailRowValue, row.mono && { fontFamily: 'monospace', fontSize: FONT_SIZES.xs }]} numberOfLines={1}>
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
  txInfoRow: { flexDirection: 'row', alignItems: 'center' },
  txType: { fontSize: FONT_SIZES.sm, fontWeight: '600', color: COLORS.text, flex: 1 },
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
  detailRow: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.border,
  },
  detailRowLabel: { fontSize: FONT_SIZES.sm, color: COLORS.textMuted, flex: 1 },
  detailRowValue: { fontSize: FONT_SIZES.sm, color: COLORS.text, flex: 2, textAlign: 'right' },

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
