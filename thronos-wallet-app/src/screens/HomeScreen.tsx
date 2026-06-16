import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, RefreshControl, ActivityIndicator,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import * as Clipboard from 'expo-clipboard';
import { COLORS, SPACING, FONT_SIZES, BORDER_RADIUS } from '../constants/theme';
import { useStore } from '../store/useStore';
import { getTokenBalances, getNetworkStatus, getTokenPrices } from '../services/api';
import { shortenAddress } from '../services/wallet';
import { CONFIG } from '../constants/config';
import type { RootStackParamList } from '../../App';

type Nav = NativeStackNavigationProp<RootStackParamList>;

// Token icon mapping — matches mainchain wallet widget
const TOKEN_ICONS: Record<string, keyof typeof Ionicons.glyphMap> = {
  THR: 'diamond',
  WBTC: 'logo-bitcoin',
  BTC: 'logo-bitcoin',
  L2E: 'school',
  T2E: 'sparkles',
  JAM: 'musical-note',
  ETH: 'logo-web-component',
  AIC: 'flash',
  CRYPT: 'game-controller',
};

const TOKEN_COLORS: Record<string, string> = {
  THR: COLORS.gold,
  WBTC: '#F7931A',
  BTC: '#F7931A',
  L2E: '#3B82F6',
  T2E: '#8B5CF6',
  JAM: '#EC4899',
  ETH: '#627EEA',
  AIC: '#EC4899',
  CRYPT: '#10B981',
};

const QUICK_ACTIONS: Array<{
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
  screen: keyof RootStackParamList;
}> = [
  { label: 'Send', icon: 'arrow-up-circle', color: COLORS.primary, screen: 'Send' },
  { label: 'Receive', icon: 'arrow-down-circle', color: COLORS.success, screen: 'Receive' },
  { label: 'Swap', icon: 'swap-horizontal', color: COLORS.info, screen: 'Swap' },
  { label: 'Bridge', icon: 'git-compare', color: COLORS.warning, screen: 'Bridge' },
  { label: 'Stake', icon: 'layers', color: COLORS.gold, screen: 'Stake' },
  { label: 'Pledge', icon: 'shield-checkmark', color: '#FF6B6B', screen: 'Pledge' },
  { label: 'Pools', icon: 'water', color: COLORS.info, screen: 'Pools' },
  { label: 'New Token', icon: 'add-circle', color: COLORS.success, screen: 'CreateToken' },
  { label: 'NFTs', icon: 'image', color: COLORS.primary, screen: 'NFT' },
  { label: 'Epoch', icon: 'hourglass', color: COLORS.warning, screen: 'Epoch' },
];

// USD price per THR (derived from 1 THR = 0.0001 BTC)
const THR_USD_RATE = 7.14; // approximate, updated from chain

export default function HomeScreen() {
  const navigation = useNavigation<Nav>();
  const { wallet, tokens, setTokens } = useStore();
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const [networkInfo, setNetworkInfo] = useState<any>(null);
  const [prices, setPrices] = useState<Record<string, { thr: number; usd: number }>>({});

  const loadBalances = useCallback(async () => {
    if (!wallet.address) return;
    try {
      const [balData, netData, priceData] = await Promise.allSettled([
        getTokenBalances(wallet.address),
        getNetworkStatus(),
        getTokenPrices(),
      ]);
      if (balData.status === 'fulfilled') {
        setTokens(balData.value.tokens || []);
      }
      if (netData.status === 'fulfilled') {
        setNetworkInfo(netData.value);
      }
      if (priceData.status === 'fulfilled' && priceData.value) {
        setPrices(priceData.value);
      }
    } catch (error) {
      console.warn('Failed to load balances:', error);
    } finally {
      setLoading(false);
    }
  }, [wallet.address]);

  useEffect(() => { loadBalances(); }, [loadBalances]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await loadBalances();
    setRefreshing(false);
  }, [loadBalances]);

  const copyAddress = async () => {
    if (wallet.address) {
      await Clipboard.setStringAsync(wallet.address);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  // Calculate total value in THR (like mainchain widget)
  const totalThr = tokens.reduce((sum, t) => {
    if (t.symbol === 'THR') return sum + t.balance;
    const price = prices[t.symbol];
    if (price?.thr) return sum + t.balance * price.thr;
    return sum + t.balance;
  }, 0);
  const totalBtc = totalThr * CONFIG.THR_BTC_RATE;
  const totalUsd = totalThr * THR_USD_RATE;

  const thrToken = tokens.find((t) => t.symbol === 'THR');
  const thrBalance = thrToken?.balance ?? 0;

  // Token row helper — shows THR equivalent + USD like mainchain
  const getThrEquiv = (token: { symbol: string; balance: number }) => {
    if (token.symbol === 'THR') return null;
    const price = prices[token.symbol];
    return price?.thr ? token.balance * price.thr : null;
  };

  const getUsdValue = (token: { symbol: string; balance: number }) => {
    if (token.symbol === 'THR') return token.balance * THR_USD_RATE;
    const price = prices[token.symbol];
    return price?.usd ? token.balance * price.usd : null;
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView
        style={styles.scroll}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.gold} />}
      >
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.title}>THRONOS WALLET</Text>
          <TouchableOpacity style={styles.scanBtn} onPress={() => navigation.navigate('Scan')}>
            <Ionicons name="scan" size={24} color={COLORS.text} />
          </TouchableOpacity>
        </View>

        {/* Address Row */}
        <TouchableOpacity onPress={copyAddress} style={styles.addressBar}>
          <Ionicons name="wallet" size={16} color={COLORS.gold} />
          <Text style={styles.addressText}>
            {wallet.address ? shortenAddress(wallet.address) : 'No wallet connected'}
          </Text>
          <TouchableOpacity style={styles.copyBtn}>
            <Text style={styles.copyBtnText}>{copied ? 'Copied' : 'Copy'}</Text>
          </TouchableOpacity>
        </TouchableOpacity>

        {/* Total Value Card */}
        <LinearGradient
          colors={['#221600', '#140F00', '#0D0D1A']}
          style={styles.totalCard}
        >
          <View style={styles.totalCardInner}>
            <Text style={styles.totalLabel}>PORTFOLIO VALUE</Text>
            {loading ? (
              <ActivityIndicator color={COLORS.gold} size="large" style={{ marginVertical: SPACING.lg }} />
            ) : (
              <>
                <Text style={styles.totalThr}>
                  {totalThr.toLocaleString(undefined, { maximumFractionDigits: 4 })}
                  <Text style={styles.totalThrUnit}> THR</Text>
                </Text>
                <View style={styles.totalConversions}>
                  <View style={styles.totalConversionItem}>
                    <Text style={styles.totalUsd}>
                      ${totalUsd.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                    </Text>
                    <Text style={styles.totalConversionLabel}>USD</Text>
                  </View>
                  <View style={styles.totalConversionDivider} />
                  <View style={styles.totalConversionItem}>
                    <Text style={styles.totalBtc}>
                      {totalBtc.toFixed(8)}
                    </Text>
                    <Text style={styles.totalConversionLabel}>BTC</Text>
                  </View>
                </View>
              </>
            )}
          </View>
        </LinearGradient>

        {/* Network Status */}
        <View style={styles.networkBar}>
          <View style={[styles.networkDot, { backgroundColor: networkInfo ? COLORS.success : COLORS.textMuted }]} />
          <Text style={styles.networkText}>
            Block #{networkInfo?.block_height?.toLocaleString() ?? '—'}
          </Text>
          <Text style={styles.networkSep}>|</Text>
          <Text style={styles.networkText}>
            {networkInfo?.tps ?? '—'} TPS
          </Text>
          <Text style={styles.networkSep}>|</Text>
          <View style={styles.acicBadge}>
            <Text style={styles.acicText}>ACIC</Text>
          </View>
          <View style={{ flex: 1 }} />
          <Text style={styles.networkText}>
            {networkInfo?.peers ?? '—'} peers
          </Text>
        </View>

        {/* Multi-Chain Selector */}
        <View style={styles.chainSelector}>
          {(['thronos', 'bitcoin', 'ethereum', 'bsc', 'solana'] as const).map((chain) => {
            const active = wallet.activeChain === chain;
            const labels: Record<string, string> = { thronos: 'THR', bitcoin: 'BTC', ethereum: 'ETH', bsc: 'BSC', solana: 'SOL' };
            const icons: Record<string, keyof typeof Ionicons.glyphMap> = {
              thronos: 'planet', bitcoin: 'logo-bitcoin', ethereum: 'diamond', bsc: 'cube', solana: 'flash',
            };
            return (
              <TouchableOpacity
                key={chain}
                style={[styles.chainChip, active && styles.chainChipActive]}
                onPress={() => useStore.getState().setActiveChain(chain)}
              >
                <Ionicons name={icons[chain]} size={14} color={active ? COLORS.gold : COLORS.textMuted} />
                <Text style={[styles.chainChipText, active && styles.chainChipTextActive]}>
                  {labels[chain]}
                </Text>
              </TouchableOpacity>
            );
          })}
        </View>

        {/* Token List — matches mainchain ΠΕΡΙΟΥΣΙΑΚΑ ΣΤΟΙΧΕΙΑ */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>ASSETS</Text>
          {loading ? (
            <View style={styles.emptyBox}>
              <ActivityIndicator color={COLORS.gold} />
              <Text style={styles.emptyText}>Loading...</Text>
            </View>
          ) : tokens.length === 0 ? (
            <View style={styles.emptyBox}>
              <Ionicons name="wallet-outline" size={40} color={COLORS.textMuted} />
              <Text style={styles.emptyText}>No tokens yet</Text>
            </View>
          ) : (
            tokens.filter((t) => t.balance > 0 || t.symbol === 'THR').map((token, i) => {
              const iconName = TOKEN_ICONS[token.symbol] || 'cube';
              const iconColor = TOKEN_COLORS[token.symbol] || COLORS.primary;
              const thrEquiv = getThrEquiv(token);
              const usdVal = getUsdValue(token);
              return (
                <View key={i} style={styles.tokenRow}>
                  <View style={[styles.tokenIcon, { backgroundColor: iconColor + '20' }]}>
                    <Ionicons name={iconName} size={24} color={iconColor} />
                  </View>
                  <View style={styles.tokenInfo}>
                    <View style={styles.tokenNameRow}>
                      <Text style={styles.tokenName}>{token.name || token.symbol}</Text>
                      <View style={[styles.tokenBadge, { backgroundColor: iconColor + '25' }]}>
                        <Text style={[styles.tokenBadgeText, { color: iconColor }]}>{token.symbol}</Text>
                      </View>
                    </View>
                    {thrEquiv != null && (
                      <Text style={styles.tokenEquiv}>
                        ≈ {thrEquiv.toLocaleString(undefined, { maximumFractionDigits: 4 })} THR
                      </Text>
                    )}
                  </View>
                  <View style={styles.tokenRight}>
                    <Text style={styles.tokenBalance}>
                      {token.balance.toLocaleString(undefined, { maximumFractionDigits: token.symbol === 'WBTC' ? 8 : 6 })} {token.symbol}
                    </Text>
                    {usdVal != null && (
                      <Text style={styles.tokenUsdVal}>
                        ≈ ${usdVal.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                      </Text>
                    )}
                  </View>
                </View>
              );
            })
          )}
        </View>

        {/* Quick Actions Grid */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>QUICK ACTIONS</Text>
          <View style={styles.actionsGrid}>
            {QUICK_ACTIONS.map((action) => (
              <TouchableOpacity
                key={action.label}
                style={[styles.actionCard, { borderColor: action.color + '45', backgroundColor: action.color + '12' }]}
                onPress={() => navigation.navigate(action.screen)}
              >
                <View style={[styles.actionIconWrap, { backgroundColor: action.color + '25' }]}>
                  <Ionicons name={action.icon} size={26} color={action.color} />
                </View>
                <Text style={[styles.actionText, { color: action.color }]}>{action.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        {/* Exchange Rate */}
        <View style={styles.rateBar}>
          <Ionicons name="swap-vertical" size={16} color={COLORS.gold} />
          <Text style={styles.rateText}>1 THR = 0.0001 BTC</Text>
          <View style={{ flex: 1 }} />
          <Text style={styles.rateLabel}>Fixed Rate</Text>
        </View>

        <View style={{ height: SPACING.xxl }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.background },
  scroll: { flex: 1, paddingHorizontal: SPACING.lg },

  // Header
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: SPACING.md },
  title: { fontSize: FONT_SIZES.xl, fontWeight: '800', color: COLORS.gold, letterSpacing: 3 },
  scanBtn: {
    width: 44, height: 44, borderRadius: BORDER_RADIUS.md,
    backgroundColor: COLORS.surface, justifyContent: 'center', alignItems: 'center',
    borderWidth: 1, borderColor: COLORS.border,
  },

  // Address
  addressBar: {
    flexDirection: 'row', alignItems: 'center', gap: SPACING.sm,
    backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.lg,
    paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm,
    marginBottom: SPACING.md, borderWidth: 1, borderColor: COLORS.gold + '20',
  },
  addressText: { flex: 1, fontSize: FONT_SIZES.sm, color: COLORS.textSecondary, fontFamily: 'monospace' },
  copyBtn: {
    backgroundColor: COLORS.gold + '25', paddingHorizontal: SPACING.sm,
    paddingVertical: 4, borderRadius: BORDER_RADIUS.sm, borderWidth: 1, borderColor: COLORS.gold + '40',
  },
  copyBtnText: { fontSize: FONT_SIZES.xs, color: COLORS.gold, fontWeight: '700' },

  // Total Value Card
  totalCard: {
    borderRadius: BORDER_RADIUS.xxl, padding: 2,
    marginBottom: SPACING.md, borderWidth: 1, borderColor: COLORS.gold + '50',
  },
  totalCardInner: {
    borderRadius: BORDER_RADIUS.xxl - 2, padding: SPACING.lg,
    alignItems: 'center',
  },
  totalLabel: { fontSize: FONT_SIZES.xs, color: COLORS.gold + 'AA', letterSpacing: 3, fontWeight: '700' },
  totalThr: { fontSize: 40, fontWeight: '800', color: COLORS.gold, marginTop: SPACING.sm, letterSpacing: -1 },
  totalThrUnit: { fontSize: 22, fontWeight: '600', color: COLORS.gold + 'BB' },
  totalConversions: {
    flexDirection: 'row', alignItems: 'center', marginTop: SPACING.md,
    gap: SPACING.lg,
  },
  totalConversionItem: { alignItems: 'center' },
  totalConversionDivider: { width: 1, height: 28, backgroundColor: COLORS.gold + '30' },
  totalUsd: { fontSize: FONT_SIZES.lg, color: COLORS.textSecondary, fontWeight: '600' },
  totalBtc: { fontSize: FONT_SIZES.lg, color: '#F7931A', fontWeight: '600' },
  totalConversionLabel: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, marginTop: 2, fontWeight: '600', letterSpacing: 1 },

  // Network
  networkBar: {
    flexDirection: 'row', alignItems: 'center', gap: SPACING.xs,
    paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm,
    backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.md,
    marginBottom: SPACING.md, borderWidth: 1, borderColor: COLORS.border,
  },
  networkDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: COLORS.success },
  networkText: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, fontWeight: '500' },
  networkSep: { fontSize: FONT_SIZES.xs, color: COLORS.border },
  acicBadge: {
    backgroundColor: COLORS.gold + '20', paddingHorizontal: SPACING.xs,
    paddingVertical: 2, borderRadius: BORDER_RADIUS.sm,
  },
  acicText: { fontSize: FONT_SIZES.xs, color: COLORS.gold, fontWeight: '700' },

  // Chain Selector
  chainSelector: { flexDirection: 'row', gap: SPACING.xs, marginBottom: SPACING.md },
  chainChip: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: SPACING.sm, paddingVertical: 6,
    borderRadius: BORDER_RADIUS.full, backgroundColor: COLORS.surface,
    borderWidth: 1, borderColor: COLORS.border,
  },
  chainChipActive: { borderColor: COLORS.gold, backgroundColor: COLORS.gold + '15' },
  chainChipText: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, fontWeight: '600' },
  chainChipTextActive: { color: COLORS.gold },

  // Sections
  section: { marginBottom: SPACING.lg },
  sectionTitle: {
    fontSize: FONT_SIZES.xs, fontWeight: '700', color: COLORS.textMuted,
    letterSpacing: 2, marginBottom: SPACING.sm, textTransform: 'uppercase',
  },

  // Token rows
  emptyBox: { alignItems: 'center', padding: SPACING.xl, backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.xl, gap: SPACING.sm },
  emptyText: { fontSize: FONT_SIZES.md, color: COLORS.textMuted },
  tokenRow: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.xl,
    padding: SPACING.md, marginBottom: SPACING.sm,
    borderWidth: 1, borderColor: COLORS.border,
  },
  tokenIcon: { width: 46, height: 46, borderRadius: BORDER_RADIUS.lg, justifyContent: 'center', alignItems: 'center', marginRight: SPACING.md },
  tokenInfo: { flex: 1 },
  tokenNameRow: { flexDirection: 'row', alignItems: 'center', gap: SPACING.xs },
  tokenName: { fontSize: FONT_SIZES.md, fontWeight: '600', color: COLORS.text },
  tokenBadge: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: BORDER_RADIUS.sm },
  tokenBadgeText: { fontSize: 10, fontWeight: '700' },
  tokenEquiv: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, marginTop: 2 },
  tokenRight: { alignItems: 'flex-end' },
  tokenBalance: { fontSize: FONT_SIZES.md, fontWeight: '600', color: COLORS.text },
  tokenUsdVal: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, marginTop: 2 },

  // Actions Grid — 3x2
  actionsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: SPACING.sm },
  actionCard: {
    width: '31%' as any, aspectRatio: 1,
    borderRadius: BORDER_RADIUS.xl,
    justifyContent: 'center', alignItems: 'center', gap: 6,
    borderWidth: 1,
  },
  actionIconWrap: {
    width: 48, height: 48, borderRadius: BORDER_RADIUS.lg,
    justifyContent: 'center', alignItems: 'center',
  },
  actionText: { fontSize: FONT_SIZES.xs, fontWeight: '700', letterSpacing: 0.5 },

  // Rate Bar
  rateBar: {
    flexDirection: 'row', alignItems: 'center', gap: SPACING.sm,
    backgroundColor: COLORS.gold + '08', borderRadius: BORDER_RADIUS.md,
    paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm,
    borderWidth: 1, borderColor: COLORS.gold + '20',
    marginBottom: SPACING.md,
  },
  rateText: { fontSize: FONT_SIZES.sm, color: COLORS.gold, fontWeight: '700', fontFamily: 'monospace' },
  rateLabel: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted },
});
