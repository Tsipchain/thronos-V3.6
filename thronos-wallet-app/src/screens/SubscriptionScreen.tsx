import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, RefreshControl, ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT_SIZES, BORDER_RADIUS } from '../constants/theme';
import { useStore } from '../store/useStore';
import { getSentinelSubscription, type SentinelSubscription } from '../services/api';

const TIER_CONFIG: Record<string, { color: string; icon: keyof typeof Ionicons.glyphMap; label: string }> = {
  starter: { color: COLORS.textSecondary, icon: 'shield-outline', label: 'Starter' },
  pro: { color: COLORS.info, icon: 'shield-half', label: 'Pro' },
  elite: { color: COLORS.gold, icon: 'shield', label: 'Elite' },
  whale: { color: '#FF6B6B', icon: 'shield-checkmark', label: 'Whale' },
};

function TierCard({ tier, multiplier }: { tier: string; multiplier: number }) {
  const cfg = TIER_CONFIG[tier] || TIER_CONFIG.starter;
  return (
    <View style={[styles.tierCard, { borderColor: cfg.color + '40' }]}>
      <Ionicons name={cfg.icon} size={48} color={cfg.color} />
      <Text style={[styles.tierName, { color: cfg.color }]}>{cfg.label}</Text>
      <Text style={styles.multiplier}>{multiplier}x Rewards</Text>
    </View>
  );
}

function StatRow({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={styles.statRow}>
      <Text style={styles.statLabel}>{label}</Text>
      <Text style={[styles.statValue, color ? { color } : null]}>{value}</Text>
    </View>
  );
}

export default function SubscriptionScreen() {
  const { wallet } = useStore();
  const [sub, setSub] = useState<SentinelSubscription | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchSub = useCallback(async () => {
    if (!wallet.address) return;
    try {
      setError(null);
      const data = await getSentinelSubscription(wallet.address);
      setSub(data);
    } catch (err: any) {
      setError(err.message || 'Failed to load subscription');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [wallet.address]);

  useEffect(() => { fetchSub(); }, [fetchSub]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    fetchSub();
  }, [fetchSub]);

  if (loading) {
    return (
      <SafeAreaView style={styles.container}>
        <ActivityIndicator size="large" color={COLORS.gold} style={{ marginTop: 40 }} />
      </SafeAreaView>
    );
  }

  const expiresDate = sub?.expires_at
    ? new Date(sub.expires_at * 1000).toLocaleDateString()
    : '—';
  const isActive = sub?.active && sub?.expires_at && sub.expires_at * 1000 > Date.now();

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.gold} />}
        contentContainerStyle={styles.scroll}
      >
        <View style={styles.header}>
          <Ionicons name="ribbon" size={24} color={COLORS.gold} />
          <Text style={styles.title}>Subscription</Text>
        </View>

        {error ? (
          <View style={styles.errorBox}>
            <Ionicons name="warning" size={20} color={COLORS.error} />
            <Text style={styles.errorText}>{error}</Text>
          </View>
        ) : null}

        {!sub || !sub.active ? (
          <View style={styles.inactiveBox}>
            <Ionicons name="lock-closed" size={48} color={COLORS.textMuted} />
            <Text style={styles.inactiveTitle}>No Active Subscription</Text>
            <Text style={styles.inactiveDesc}>
              Hold THR tokens to unlock Sentinel trading signals and market reviews.
            </Text>
          </View>
        ) : (
          <>
            <TierCard tier={sub.tier} multiplier={sub.rewards_multiplier} />

            <View style={styles.statusCard}>
              <View style={styles.statusHeader}>
                <View style={[styles.statusDot, { backgroundColor: isActive ? COLORS.success : COLORS.error }]} />
                <Text style={styles.statusText}>{isActive ? 'Active' : 'Expired'}</Text>
              </View>

              <StatRow label="THR Balance" value={`${sub.thr_balance?.toFixed(2) ?? '0'} THR`} color={COLORS.gold} />
              <StatRow label="Tier" value={TIER_CONFIG[sub.tier]?.label || sub.tier} />
              <StatRow label="Rewards Multiplier" value={`${sub.rewards_multiplier}x`} />
              <StatRow label="Verified" value={sub.verified ? 'Yes' : 'No'} color={sub.verified ? COLORS.success : COLORS.error} />
              <StatRow label="Expires" value={expiresDate} />
            </View>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.background },
  scroll: { paddingHorizontal: SPACING.md, paddingBottom: SPACING.xxl },
  header: { flexDirection: 'row', alignItems: 'center', paddingVertical: SPACING.md, paddingHorizontal: SPACING.sm, gap: SPACING.sm },
  title: { fontSize: FONT_SIZES.xxl, fontWeight: '700', color: COLORS.text },
  tierCard: {
    backgroundColor: COLORS.backgroundCard,
    borderRadius: BORDER_RADIUS.xl,
    padding: SPACING.xl,
    alignItems: 'center',
    marginBottom: SPACING.lg,
    borderWidth: 1,
  },
  tierName: { fontSize: FONT_SIZES.xxl, fontWeight: '700', marginTop: SPACING.sm },
  multiplier: { fontSize: FONT_SIZES.md, color: COLORS.textSecondary, marginTop: SPACING.xs },
  statusCard: {
    backgroundColor: COLORS.backgroundCard,
    borderRadius: BORDER_RADIUS.lg,
    padding: SPACING.md,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  statusHeader: { flexDirection: 'row', alignItems: 'center', gap: SPACING.sm, marginBottom: SPACING.md },
  statusDot: { width: 10, height: 10, borderRadius: 5 },
  statusText: { fontSize: FONT_SIZES.lg, fontWeight: '600', color: COLORS.text },
  statRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.border },
  statLabel: { fontSize: FONT_SIZES.md, color: COLORS.textSecondary },
  statValue: { fontSize: FONT_SIZES.md, fontWeight: '600', color: COLORS.text },
  inactiveBox: { alignItems: 'center', paddingTop: 60, gap: SPACING.md },
  inactiveTitle: { fontSize: FONT_SIZES.xl, color: COLORS.textSecondary, fontWeight: '600' },
  inactiveDesc: { fontSize: FONT_SIZES.md, color: COLORS.textMuted, textAlign: 'center', paddingHorizontal: SPACING.xl },
  errorBox: { flexDirection: 'row', alignItems: 'center', gap: SPACING.sm, paddingHorizontal: SPACING.lg, paddingVertical: SPACING.sm, backgroundColor: COLORS.error + '15', borderRadius: BORDER_RADIUS.md, marginBottom: SPACING.md },
  errorText: { fontSize: FONT_SIZES.sm, color: COLORS.error, flex: 1 },
});
