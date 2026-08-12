import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, FlatList, TouchableOpacity, RefreshControl, ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT_SIZES, BORDER_RADIUS } from '../constants/theme';
import { useStore } from '../store/useStore';
import { getSentinelSignals, type SentinelSignal } from '../services/api';

const SIGNAL_COLORS: Record<string, string> = {
  LONG: COLORS.success,
  SHORT: COLORS.error,
  BUY: COLORS.success,
  SELL: COLORS.error,
  HOLD: COLORS.warning,
  ACCUMULATION: COLORS.info,
  DISTRIBUTION: COLORS.warning,
};

const RISK_COLORS: Record<string, string> = {
  LOW: COLORS.success,
  MEDIUM: COLORS.warning,
  HIGH: COLORS.error,
  EXTREME: '#FF0000',
};

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.min(100, Math.max(0, value));
  const color = pct >= 75 ? COLORS.success : pct >= 50 ? COLORS.warning : COLORS.error;
  return (
    <View style={styles.confBarBg}>
      <View style={[styles.confBarFill, { width: `${pct}%`, backgroundColor: color }]} />
    </View>
  );
}

function SignalCard({ signal }: { signal: SentinelSignal }) {
  const dirColor = SIGNAL_COLORS[signal.signal] || COLORS.textSecondary;
  const riskColor = RISK_COLORS[signal.risk] || COLORS.textSecondary;

  return (
    <View style={styles.card}>
      <View style={styles.cardHeader}>
        <View style={styles.symbolRow}>
          <Text style={styles.symbol}>{signal.symbol}</Text>
          <View style={[styles.badge, { backgroundColor: dirColor + '20', borderColor: dirColor }]}>
            <Text style={[styles.badgeText, { color: dirColor }]}>{signal.signal}</Text>
          </View>
        </View>
        <Text style={styles.timeframe}>{signal.timeframe}</Text>
      </View>

      <View style={styles.priceRow}>
        <View style={styles.priceItem}>
          <Text style={styles.priceLabel}>Entry</Text>
          <Text style={styles.priceValue}>${signal.entry?.toLocaleString() ?? '—'}</Text>
        </View>
        <View style={styles.priceItem}>
          <Text style={styles.priceLabel}>TP1</Text>
          <Text style={[styles.priceValue, { color: COLORS.success }]}>
            {signal.tp1 ? `$${signal.tp1.toLocaleString()}` : '—'}
          </Text>
        </View>
        <View style={styles.priceItem}>
          <Text style={styles.priceLabel}>SL</Text>
          <Text style={[styles.priceValue, { color: COLORS.error }]}>
            {signal.sl ? `$${signal.sl.toLocaleString()}` : '—'}
          </Text>
        </View>
      </View>

      <View style={styles.metaRow}>
        <View style={styles.confSection}>
          <Text style={styles.metaLabel}>Confidence</Text>
          <ConfidenceBar value={signal.confidence} />
          <Text style={styles.confText}>{signal.confidence}%</Text>
        </View>
        <View style={styles.riskSection}>
          <Text style={styles.metaLabel}>Risk</Text>
          <Text style={[styles.riskText, { color: riskColor }]}>{signal.risk}</Text>
        </View>
      </View>

      <Text style={styles.reason} numberOfLines={2}>{signal.reason}</Text>

      {signal.confirmations && signal.confirmations.length > 0 && (
        <View style={styles.confRow}>
          {signal.confirmations.map((c, i) => (
            <View key={i} style={styles.confChip}>
              <Text style={styles.confChipText}>{c}</Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

export default function SignalsScreen() {
  const { wallet } = useStore();
  const [signals, setSignals] = useState<SentinelSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchSignals = useCallback(async () => {
    if (!wallet.address) return;
    try {
      setError(null);
      const data = await getSentinelSignals(wallet.address, 20);
      setSignals(data.signals || []);
    } catch (err: any) {
      setError(err.message || 'Failed to load signals');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [wallet.address]);

  useEffect(() => { fetchSignals(); }, [fetchSignals]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    fetchSignals();
  }, [fetchSignals]);

  if (loading) {
    return (
      <SafeAreaView style={styles.container}>
        <ActivityIndicator size="large" color={COLORS.gold} style={{ marginTop: 40 }} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Ionicons name="analytics" size={24} color={COLORS.gold} />
        <Text style={styles.title}>Sentinel Signals</Text>
      </View>

      {error ? (
        <View style={styles.errorBox}>
          <Ionicons name="warning" size={20} color={COLORS.error} />
          <Text style={styles.errorText}>{error}</Text>
        </View>
      ) : null}

      <FlatList
        data={signals}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => <SignalCard signal={item} />}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.gold} />}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Ionicons name="radio-outline" size={48} color={COLORS.textMuted} />
            <Text style={styles.emptyText}>No signals yet</Text>
            <Text style={styles.emptySubtext}>Sentinel is watching the markets</Text>
          </View>
        }
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.background },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: SPACING.lg, paddingVertical: SPACING.md, gap: SPACING.sm },
  title: { fontSize: FONT_SIZES.xxl, fontWeight: '700', color: COLORS.text },
  list: { paddingHorizontal: SPACING.md, paddingBottom: SPACING.xxl },
  card: {
    backgroundColor: COLORS.backgroundCard,
    borderRadius: BORDER_RADIUS.lg,
    padding: SPACING.md,
    marginBottom: SPACING.md,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: SPACING.sm },
  symbolRow: { flexDirection: 'row', alignItems: 'center', gap: SPACING.sm },
  symbol: { fontSize: FONT_SIZES.lg, fontWeight: '700', color: COLORS.text },
  badge: { paddingHorizontal: SPACING.sm, paddingVertical: 2, borderRadius: BORDER_RADIUS.sm, borderWidth: 1 },
  badgeText: { fontSize: FONT_SIZES.sm, fontWeight: '700' },
  timeframe: { fontSize: FONT_SIZES.sm, color: COLORS.textSecondary },
  priceRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: SPACING.sm },
  priceItem: { alignItems: 'center', flex: 1 },
  priceLabel: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, marginBottom: 2 },
  priceValue: { fontSize: FONT_SIZES.md, fontWeight: '600', color: COLORS.text },
  metaRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: SPACING.sm },
  confSection: { flex: 1, marginRight: SPACING.md },
  metaLabel: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, marginBottom: 4 },
  confBarBg: { height: 6, backgroundColor: COLORS.surfaceLight, borderRadius: 3, overflow: 'hidden' },
  confBarFill: { height: '100%', borderRadius: 3 },
  confText: { fontSize: FONT_SIZES.xs, color: COLORS.textSecondary, marginTop: 2 },
  riskSection: { alignItems: 'flex-end' },
  riskText: { fontSize: FONT_SIZES.md, fontWeight: '700' },
  reason: { fontSize: FONT_SIZES.sm, color: COLORS.textSecondary, marginBottom: SPACING.sm },
  confRow: { flexDirection: 'row', flexWrap: 'wrap', gap: SPACING.xs },
  confChip: { backgroundColor: COLORS.surface, paddingHorizontal: SPACING.sm, paddingVertical: 2, borderRadius: BORDER_RADIUS.sm },
  confChipText: { fontSize: FONT_SIZES.xs, color: COLORS.textSecondary },
  errorBox: { flexDirection: 'row', alignItems: 'center', gap: SPACING.sm, paddingHorizontal: SPACING.lg, paddingVertical: SPACING.sm, backgroundColor: COLORS.error + '15', marginHorizontal: SPACING.md, borderRadius: BORDER_RADIUS.md },
  errorText: { fontSize: FONT_SIZES.sm, color: COLORS.error, flex: 1 },
  empty: { alignItems: 'center', paddingTop: 60, gap: SPACING.sm },
  emptyText: { fontSize: FONT_SIZES.lg, color: COLORS.textSecondary, fontWeight: '600' },
  emptySubtext: { fontSize: FONT_SIZES.sm, color: COLORS.textMuted },
});
