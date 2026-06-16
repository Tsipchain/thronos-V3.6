import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  ScrollView,
  RefreshControl,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT_SIZES, BORDER_RADIUS } from '../constants/theme';
import { getCurrentEpoch, getHalvingSchedule, getMiningEcosystemStats, CurrentEpochInfo, HalvingEntry } from '../services/api';

export default function EpochScreen({ navigation }: { navigation: any }) {
  const [epoch, setEpoch] = useState<CurrentEpochInfo | null>(null);
  const [halvings, setHalvings] = useState<HalvingEntry[]>([]);
  const [stats, setStats] = useState<{ halving_interval_months: number; estimated_full_circulation_years: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [epochRes, schedRes, statsRes] = await Promise.allSettled([
        getCurrentEpoch(),
        getHalvingSchedule(),
        getMiningEcosystemStats(),
      ]);
      if (epochRes.status === 'fulfilled') setEpoch(epochRes.value);
      if (schedRes.status === 'fulfilled') setHalvings(schedRes.value.halvings || []);
      if (statsRes.status === 'fulfilled') setStats(statsRes.value as any);
    } catch (err) {
      console.warn('Epoch: failed to load', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }, [load]);

  const nextHalving = halvings.find((h) => epoch && h.epoch >= epoch.epoch) ?? halvings[0];

  return (
    <SafeAreaView style={styles.container}>
      <LinearGradient colors={[COLORS.background, COLORS.backgroundLight]} style={styles.gradient}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
            <Ionicons name="arrow-back" size={24} color={COLORS.text} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Epoch & Halving</Text>
          <View style={{ width: 24 }} />
        </View>

        {loading ? (
          <ActivityIndicator color={COLORS.gold} style={{ marginTop: SPACING.xl }} />
        ) : (
          <ScrollView
            style={styles.scroll}
            contentContainerStyle={styles.scrollContent}
            refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.gold} />}
            showsVerticalScrollIndicator={false}
          >
            <LinearGradient colors={['#221600', '#140F00', '#0D0D1A']} style={styles.epochCard}>
              <Text style={styles.epochLabel}>CURRENT EPOCH</Text>
              <Text style={styles.epochNumber}>{epoch?.epoch ?? '—'}</Text>
              <Text style={styles.epochSub}>Block {epoch?.current_block?.toLocaleString() ?? '—'} · range {epoch?.block_range ?? '—'}</Text>
              <View style={styles.epochRow}>
                <View style={styles.epochStat}>
                  <Text style={styles.epochStatValue}>{epoch?.current_reward ?? '—'}</Text>
                  <Text style={styles.epochStatLabel}>Reward/Block</Text>
                </View>
                <View style={styles.epochStat}>
                  <Text style={styles.epochStatValue}>{epoch?.blocks_until_halving?.toLocaleString() ?? '—'}</Text>
                  <Text style={styles.epochStatLabel}>Blocks to Halving</Text>
                </View>
              </View>
              <Text style={styles.haldingDate}>
                Est. halving: {epoch?.halving_date_estimate ? new Date(epoch.halving_date_estimate).toLocaleDateString() : '—'}
              </Text>
            </LinearGradient>

            <View style={styles.supplyCard}>
              <View style={styles.supplyRow}>
                <Text style={styles.supplyLabel}>Circulating Supply</Text>
                <Text style={styles.supplyValue}>{epoch?.supply_circulating?.toLocaleString() ?? '—'} THR</Text>
              </View>
              <View style={styles.supplyRow}>
                <Text style={styles.supplyLabel}>Max Supply</Text>
                <Text style={styles.supplyValue}>{epoch?.supply_max?.toLocaleString() ?? '21,000,001'} THR</Text>
              </View>
              {stats && (
                <>
                  <View style={styles.supplyRow}>
                    <Text style={styles.supplyLabel}>Halving Interval</Text>
                    <Text style={styles.supplyValue}>{stats.halving_interval_months} months</Text>
                  </View>
                  <View style={styles.supplyRow}>
                    <Text style={styles.supplyLabel}>Full Circulation (est.)</Text>
                    <Text style={styles.supplyValue}>~{stats.estimated_full_circulation_years} years</Text>
                  </View>
                </>
              )}
            </View>

            <Text style={styles.sectionLabel}>Halving Schedule</Text>
            {halvings.slice(0, 8).map((h) => {
              const isNext = nextHalving?.epoch === h.epoch;
              return (
                <View key={h.epoch} style={[styles.haveRow, isNext && styles.haveRowActive]}>
                  <View style={styles.haveLeft}>
                    <Text style={[styles.haveEpoch, isNext && { color: COLORS.gold }]}>Epoch {h.epoch}</Text>
                    <Text style={styles.haveDate}>{new Date(h.halving_date).toLocaleDateString()}</Text>
                  </View>
                  <View style={styles.haveRight}>
                    <Text style={styles.haveReward}>{h.reward_before} → {h.reward_after}</Text>
                    <Text style={styles.haveSupply}>{h.supply_at_halving.toLocaleString()} THR</Text>
                  </View>
                </View>
              );
            })}

            <View style={{ height: SPACING.xxl }} />
          </ScrollView>
        )}
      </LinearGradient>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.background },
  gradient: { flex: 1 },
  scroll: { flex: 1 },
  scrollContent: { paddingHorizontal: SPACING.lg, paddingBottom: SPACING.xxl },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.lg, paddingVertical: SPACING.md },
  headerTitle: { fontSize: FONT_SIZES.xl, fontWeight: '700', color: COLORS.text },

  epochCard: { borderRadius: BORDER_RADIUS.xxl, padding: SPACING.lg, alignItems: 'center', borderWidth: 1, borderColor: COLORS.gold + '50', marginBottom: SPACING.md },
  epochLabel: { fontSize: FONT_SIZES.xs, color: COLORS.gold + 'AA', letterSpacing: 3, fontWeight: '700' },
  epochNumber: { fontSize: 48, fontWeight: '800', color: COLORS.gold, marginTop: SPACING.xs },
  epochSub: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, marginTop: 4 },
  epochRow: { flexDirection: 'row', gap: SPACING.xl, marginTop: SPACING.md },
  epochStat: { alignItems: 'center' },
  epochStatValue: { fontSize: FONT_SIZES.lg, fontWeight: '700', color: COLORS.text },
  epochStatLabel: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, marginTop: 2 },
  haldingDate: { fontSize: FONT_SIZES.sm, color: COLORS.textSecondary, marginTop: SPACING.md },

  supplyCard: { backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.xl, padding: SPACING.md, borderWidth: 1, borderColor: COLORS.border, marginBottom: SPACING.md },
  supplyRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: SPACING.xs },
  supplyLabel: { fontSize: FONT_SIZES.sm, color: COLORS.textSecondary },
  supplyValue: { fontSize: FONT_SIZES.sm, fontWeight: '700', color: COLORS.text },

  sectionLabel: { fontSize: FONT_SIZES.xs, fontWeight: '700', color: COLORS.textMuted, letterSpacing: 2, marginBottom: SPACING.sm, marginTop: SPACING.md, textTransform: 'uppercase' },
  haveRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', backgroundColor: COLORS.backgroundCard, borderRadius: BORDER_RADIUS.lg, padding: SPACING.md, marginBottom: SPACING.xs, borderWidth: 1, borderColor: COLORS.border },
  haveRowActive: { borderColor: COLORS.gold + '50', backgroundColor: COLORS.gold + '08' },
  haveLeft: {},
  haveEpoch: { fontSize: FONT_SIZES.md, fontWeight: '700', color: COLORS.text },
  haveDate: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, marginTop: 2 },
  haveRight: { alignItems: 'flex-end' },
  haveReward: { fontSize: FONT_SIZES.sm, fontWeight: '600', color: COLORS.textSecondary },
  haveSupply: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, marginTop: 2 },
});
