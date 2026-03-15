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
import { getTokenBalances, getNetworkStatus } from '../services/api';
import { shortenAddress } from '../services/wallet';
import { CONFIG } from '../constants/config';
import type { RootStackParamList } from '../../App';

type Nav = NativeStackNavigationProp<RootStackParamList>;

// Token icon mapping
const TOKEN_ICONS: Record<string, keyof typeof Ionicons.glyphMap> = {
  THR: 'diamond',
  WBTC: 'logo-bitcoin',
  BTC: 'logo-bitcoin',
  L2E: 'school',
  T2E: 'sparkles',
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
  ETH: '#627EEA',
  AIC: '#EC4899',
  CRYPT: '#10B981',
};

export default function HomeScreen() {
  const navigation = useNavigation<Nav>();
  const { wallet, tokens, setTokens } = useStore();
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const [networkInfo, setNetworkInfo] = useState<any>(null);

  const loadBalances = useCallback(async () => {
    if (!wallet.address) return;
    try {
      const [balData, netData] = await Promise.allSettled([
        getTokenBalances(wallet.address),
        getNetworkStatus(),
      ]);
      if (balData.status === 'fulfilled') {
        setTokens(balData.value.tokens || []);
      }
      if (netData.status === 'fulfilled') {
        setNetworkInfo(netData.value);
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

  const thrToken = tokens.find((t) => t.symbol === 'THR');
  const thrBalance = thrToken?.balance ?? 0;
  const otherTokens = tokens.filter((t) => t.symbol !== 'THR' && t.balance > 0);

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView
        style={styles.scroll}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.gold} />}
      >
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.title}>Thronos Wallet</Text>
          <TouchableOpacity style={styles.scanBtn} onPress={() => navigation.navigate('Scan')}>
            <Ionicons name="scan" size={24} color={COLORS.text} />
          </TouchableOpacity>
        </View>

        {/* Main Balance Card */}
        <LinearGradient colors={[COLORS.gold, COLORS.goldDark]} style={styles.balanceCard}>
          <TouchableOpacity onPress={copyAddress} style={styles.addressRow}>
            <Text style={styles.addressLabel}>
              {wallet.address ? shortenAddress(wallet.address) : '...'}
            </Text>
            <Ionicons name={copied ? 'checkmark' : 'copy-outline'} size={16} color={COLORS.background} />
          </TouchableOpacity>

          <View style={styles.balanceArea}>
            <Text style={styles.balanceLabel}>THR Balance</Text>
            {loading ? (
              <ActivityIndicator color={COLORS.background} size="large" />
            ) : (
              <>
                <Text style={styles.balanceValue}>{thrBalance.toLocaleString(undefined, { maximumFractionDigits: 4 })}</Text>
                <Text style={styles.btcValue}>
                  {(thrBalance * CONFIG.THR_BTC_RATE).toFixed(8)} BTC
                </Text>
              </>
            )}
            <Text style={styles.balanceSub}>THRONOS</Text>
          </View>
        </LinearGradient>

        {/* Network Status */}
        {networkInfo && (
          <View style={styles.networkBar}>
            <View style={styles.networkDot} />
            <Text style={styles.networkText}>
              Block #{networkInfo.block_height?.toLocaleString() ?? '—'}
            </Text>
            <Text style={styles.networkText}>|</Text>
            <Text style={styles.networkText}>
              {networkInfo.tps ?? '—'} TPS
            </Text>
            {networkInfo.acic_enabled && (
              <>
                <Text style={styles.networkText}>|</Text>
                <View style={styles.acicBadge}>
                  <Text style={styles.acicText}>ACIC</Text>
                </View>
              </>
            )}
          </View>
        )}

        {/* Multi-Chain Selector */}
        <View style={styles.chainSelector}>
          {(['thronos', 'bitcoin', 'ethereum'] as const).map((chain) => {
            const active = wallet.activeChain === chain;
            const labels = { thronos: 'THR', bitcoin: 'BTC', ethereum: 'ETH' };
            const icons: Record<string, keyof typeof Ionicons.glyphMap> = { thronos: 'planet', bitcoin: 'logo-bitcoin', ethereum: 'diamond' };
            return (
              <TouchableOpacity
                key={chain}
                style={[styles.chainChip, active && styles.chainChipActive]}
                onPress={() => useStore.getState().setActiveChain(chain)}
              >
                <Ionicons name={icons[chain]} size={16} color={active ? COLORS.gold : COLORS.textMuted} />
                <Text style={[styles.chainChipText, active && styles.chainChipTextActive]}>
                  {labels[chain]}
                </Text>
              </TouchableOpacity>
            );
          })}
        </View>

        {/* Quick Actions */}
        <View style={styles.quickActions}>
          <TouchableOpacity style={styles.quickAction} onPress={() => navigation.navigate('Send')}>
            <View style={styles.qaIcon}><Ionicons name="arrow-up" size={24} color={COLORS.primary} /></View>
            <Text style={styles.qaText}>Send</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.quickAction} onPress={() => navigation.navigate('Receive')}>
            <View style={styles.qaIcon}><Ionicons name="arrow-down" size={24} color={COLORS.success} /></View>
            <Text style={styles.qaText}>Receive</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.quickAction} onPress={() => navigation.navigate('Swap')}>
            <View style={styles.qaIcon}><Ionicons name="swap-horizontal" size={24} color={COLORS.info} /></View>
            <Text style={styles.qaText}>Swap</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.quickAction} onPress={() => navigation.navigate('Bridge')}>
            <View style={styles.qaIcon}><Ionicons name="git-compare" size={24} color={COLORS.warning} /></View>
            <Text style={styles.qaText}>Bridge</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.quickAction} onPress={() => navigation.navigate('Stake')}>
            <View style={styles.qaIcon}><Ionicons name="layers" size={24} color={COLORS.gold} /></View>
            <Text style={styles.qaText}>Stake</Text>
          </TouchableOpacity>
        </View>

        {/* Token List */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Tokens</Text>
          {loading ? (
            <View style={styles.emptyBox}><ActivityIndicator color={COLORS.gold} /><Text style={styles.emptyText}>Loading...</Text></View>
          ) : tokens.length === 0 ? (
            <View style={styles.emptyBox}><Ionicons name="wallet-outline" size={40} color={COLORS.textMuted} /><Text style={styles.emptyText}>No tokens yet</Text></View>
          ) : (
            tokens.filter((t) => t.balance > 0 || t.symbol === 'THR').map((token, i) => {
              const iconName = TOKEN_ICONS[token.symbol] || 'cube';
              const iconColor = TOKEN_COLORS[token.symbol] || COLORS.primary;
              return (
                <View key={i} style={styles.tokenRow}>
                  <View style={[styles.tokenIcon, { backgroundColor: iconColor + '20' }]}>
                    <Ionicons name={iconName} size={24} color={iconColor} />
                  </View>
                  <View style={styles.tokenInfo}>
                    <Text style={styles.tokenName}>{token.name || token.symbol}</Text>
                    <Text style={styles.tokenCategory}>{token.category || 'Token'}</Text>
                  </View>
                  <View style={styles.tokenRight}>
                    <Text style={styles.tokenBalance}>
                      {token.balance.toLocaleString(undefined, { maximumFractionDigits: 4 })} {token.symbol}
                    </Text>
                    {token.symbol === 'THR' && (
                      <Text style={styles.tokenBtcVal}>
                        {(token.balance * CONFIG.THR_BTC_RATE).toFixed(8)} BTC
                      </Text>
                    )}
                  </View>
                </View>
              );
            })
          )}
        </View>

        <View style={{ height: SPACING.xxl }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.background },
  scroll: { flex: 1, paddingHorizontal: SPACING.lg },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: SPACING.md },
  title: { fontSize: FONT_SIZES.xxl, fontWeight: '700', color: COLORS.gold },
  scanBtn: { width: 44, height: 44, borderRadius: BORDER_RADIUS.md, backgroundColor: COLORS.surface, justifyContent: 'center', alignItems: 'center' },
  balanceCard: { borderRadius: BORDER_RADIUS.xl, padding: SPACING.lg, marginBottom: SPACING.lg },
  addressRow: { flexDirection: 'row', alignItems: 'center', gap: SPACING.xs, marginBottom: SPACING.md },
  addressLabel: { fontSize: FONT_SIZES.sm, color: COLORS.background, fontWeight: '500', fontFamily: 'monospace' },
  balanceArea: { alignItems: 'center', paddingVertical: SPACING.lg },
  balanceLabel: { fontSize: FONT_SIZES.sm, color: 'rgba(0,0,0,0.6)' },
  balanceValue: { fontSize: FONT_SIZES.display, fontWeight: '700', color: COLORS.background },
  btcValue: { fontSize: FONT_SIZES.sm, color: 'rgba(0,0,0,0.5)', fontWeight: '500', marginTop: 2 },
  balanceSub: { fontSize: FONT_SIZES.md, color: 'rgba(0,0,0,0.5)', fontWeight: '600' },
  chainSelector: { flexDirection: 'row', gap: SPACING.sm, marginBottom: SPACING.md },
  chainChip: {
    flexDirection: 'row', alignItems: 'center', gap: SPACING.xs,
    paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm,
    borderRadius: BORDER_RADIUS.full, backgroundColor: COLORS.surface,
    borderWidth: 1, borderColor: COLORS.border,
  },
  chainChipActive: { borderColor: COLORS.gold, backgroundColor: COLORS.gold + '15' },
  chainChipText: { fontSize: FONT_SIZES.sm, color: COLORS.textMuted, fontWeight: '600' },
  chainChipTextActive: { color: COLORS.gold },
  quickActions: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: SPACING.lg },
  quickAction: { alignItems: 'center' },
  qaIcon: {
    width: 56, height: 56, borderRadius: BORDER_RADIUS.lg,
    backgroundColor: COLORS.surface, justifyContent: 'center', alignItems: 'center',
    marginBottom: SPACING.xs, borderWidth: 1, borderColor: COLORS.border,
  },
  qaText: { fontSize: FONT_SIZES.sm, color: COLORS.textSecondary, fontWeight: '500' },
  section: { marginBottom: SPACING.lg },
  sectionTitle: { fontSize: FONT_SIZES.lg, fontWeight: '600', color: COLORS.text, marginBottom: SPACING.md },
  emptyBox: { alignItems: 'center', padding: SPACING.xl, backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.lg, gap: SPACING.sm },
  emptyText: { fontSize: FONT_SIZES.md, color: COLORS.textMuted },
  tokenRow: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.lg,
    padding: SPACING.md, marginBottom: SPACING.sm,
    borderWidth: 1, borderColor: COLORS.border,
  },
  tokenIcon: { width: 44, height: 44, borderRadius: BORDER_RADIUS.md, justifyContent: 'center', alignItems: 'center', marginRight: SPACING.md },
  tokenInfo: { flex: 1 },
  tokenName: { fontSize: FONT_SIZES.md, fontWeight: '600', color: COLORS.text },
  tokenCategory: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted },
  tokenRight: { alignItems: 'flex-end' as const },
  tokenBalance: { fontSize: FONT_SIZES.md, fontWeight: '600', color: COLORS.text },
  tokenBtcVal: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, marginTop: 2 },
  networkBar: {
    flexDirection: 'row' as const, alignItems: 'center' as const, gap: SPACING.xs,
    paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm,
    backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.md,
    marginBottom: SPACING.md, borderWidth: 1, borderColor: COLORS.border,
  },
  networkDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: COLORS.success },
  networkText: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, fontWeight: '500' },
  acicBadge: {
    backgroundColor: COLORS.gold + '20', paddingHorizontal: SPACING.xs,
    paddingVertical: 2, borderRadius: BORDER_RADIUS.sm,
  },
  acicText: { fontSize: FONT_SIZES.xs, color: COLORS.gold, fontWeight: '700' },
});
