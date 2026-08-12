import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, FlatList, RefreshControl, ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT_SIZES, BORDER_RADIUS } from '../constants/theme';
import { useStore } from '../store/useStore';
import { getSentinelMilestones, type SentinelMilestone } from '../services/api';

const STATUS_CONFIG: Record<string, { color: string; icon: keyof typeof Ionicons.glyphMap }> = {
  pending: { color: COLORS.warning, icon: 'hourglass' },
  approved: { color: COLORS.info, icon: 'checkmark-circle' },
  submitted: { color: COLORS.primary, icon: 'paper-plane' },
  confirmed: { color: COLORS.success, icon: 'shield-checkmark' },
  failed: { color: COLORS.error, icon: 'close-circle' },
};

function MilestoneCard({ milestone }: { milestone: SentinelMilestone }) {
  const cfg = STATUS_CONFIG[milestone.status] || STATUS_CONFIG.pending;
  const date = new Date(milestone.created_at * 1000).toLocaleDateString();

  return (
    <View style={styles.card}>
      <View style={styles.cardLeft}>
        <Ionicons name={cfg.icon} size={28} color={cfg.color} />
      </View>
      <View style={styles.cardBody}>
        <Text style={styles.milestoneTitle}>{milestone.title || `Milestone #${milestone.id}`}</Text>
        <Text style={styles.milestoneAmount}>
          {milestone.amount?.toFixed(2) ?? '0'} THR
        </Text>
        <Text style={styles.milestoneDate}>{date}</Text>
      </View>
      <View style={[styles.statusBadge, { backgroundColor: cfg.color + '20' }]}>
        <Text style={[styles.statusText, { color: cfg.color }]}>
          {milestone.status.charAt(0).toUpperCase() + milestone.status.slice(1)}
        </Text>
      </View>
    </View>
  );
}

export default function MilestonesScreen() {
  const { wallet } = useStore();
  const [milestones, setMilestones] = useState<SentinelMilestone[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchMilestones = useCallback(async () => {
    if (!wallet.address) return;
    try {
      setError(null);
      const data = await getSentinelMilestones(wallet.address);
      setMilestones(data.milestones || []);
    } catch (err: any) {
      setError(err.message || 'Failed to load milestones');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [wallet.address]);

  useEffect(() => { fetchMilestones(); }, [fetchMilestones]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    fetchMilestones();
  }, [fetchMilestones]);

  if (loading) {
    return (
      <SafeAreaView style={styles.container}>
        <ActivityIndicator size="large" color={COLORS.gold} style={{ marginTop: 40 }} />
      </SafeAreaView>
    );
  }

  const totalEarned = milestones
    .filter((m) => m.status === 'confirmed')
    .reduce((sum, m) => sum + (m.amount || 0), 0);

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Ionicons name="trophy" size={24} color={COLORS.gold} />
        <Text style={styles.title}>Milestones</Text>
      </View>

      <View style={styles.summaryCard}>
        <Text style={styles.summaryLabel}>Total Earned</Text>
        <Text style={styles.summaryValue}>{totalEarned.toFixed(2)} THR</Text>
        <Text style={styles.summaryCount}>{milestones.length} milestones</Text>
      </View>

      {error ? (
        <View style={styles.errorBox}>
          <Ionicons name="warning" size={20} color={COLORS.error} />
          <Text style={styles.errorText}>{error}</Text>
        </View>
      ) : null}

      <FlatList
        data={milestones}
        keyExtractor={(item) => String(item.id)}
        renderItem={({ item }) => <MilestoneCard milestone={item} />}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.gold} />}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Ionicons name="medal-outline" size={48} color={COLORS.textMuted} />
            <Text style={styles.emptyText}>No milestones yet</Text>
            <Text style={styles.emptySubtext}>Complete tasks to earn THR rewards</Text>
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
  summaryCard: {
    backgroundColor: COLORS.backgroundCard,
    borderRadius: BORDER_RADIUS.lg,
    padding: SPACING.lg,
    marginHorizontal: SPACING.md,
    marginBottom: SPACING.md,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: COLORS.gold + '30',
  },
  summaryLabel: { fontSize: FONT_SIZES.sm, color: COLORS.textSecondary },
  summaryValue: { fontSize: FONT_SIZES.xxxl, fontWeight: '700', color: COLORS.gold, marginVertical: SPACING.xs },
  summaryCount: { fontSize: FONT_SIZES.sm, color: COLORS.textMuted },
  list: { paddingHorizontal: SPACING.md, paddingBottom: SPACING.xxl },
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.backgroundCard,
    borderRadius: BORDER_RADIUS.lg,
    padding: SPACING.md,
    marginBottom: SPACING.sm,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  cardLeft: { marginRight: SPACING.md },
  cardBody: { flex: 1 },
  milestoneTitle: { fontSize: FONT_SIZES.md, fontWeight: '600', color: COLORS.text },
  milestoneAmount: { fontSize: FONT_SIZES.sm, color: COLORS.gold, marginTop: 2 },
  milestoneDate: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, marginTop: 2 },
  statusBadge: { paddingHorizontal: SPACING.sm, paddingVertical: 4, borderRadius: BORDER_RADIUS.sm },
  statusText: { fontSize: FONT_SIZES.xs, fontWeight: '700' },
  errorBox: { flexDirection: 'row', alignItems: 'center', gap: SPACING.sm, paddingHorizontal: SPACING.lg, paddingVertical: SPACING.sm, backgroundColor: COLORS.error + '15', marginHorizontal: SPACING.md, marginBottom: SPACING.md, borderRadius: BORDER_RADIUS.md },
  errorText: { fontSize: FONT_SIZES.sm, color: COLORS.error, flex: 1 },
  empty: { alignItems: 'center', paddingTop: 60, gap: SPACING.sm },
  emptyText: { fontSize: FONT_SIZES.lg, color: COLORS.textSecondary, fontWeight: '600' },
  emptySubtext: { fontSize: FONT_SIZES.sm, color: COLORS.textMuted },
});
