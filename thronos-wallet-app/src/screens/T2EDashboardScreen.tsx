import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT_SIZES, BORDER_RADIUS } from '../constants/theme';
import { useStore } from '../store/useStore';
import { getT2EBalance, getT2EHistory } from '../services/api';
import { CONFIG } from '../constants/config';

// ── Types ───────────────────────────────────────────────────────────────────────

interface EarningEntry {
  id: string;
  type: 'training' | 'rating' | 'data' | 'bonus' | 'contribution' | 'architect';
  amount: number;
  description: string;
  timestamp: string;
}

interface ArchitectProject {
  id: string;
  name: string;
  status: 'active' | 'completed' | 'pending';
  earned: number;
  contributions: number;
  progress?: number;
  completedAt?: string;
}

// No mock data — all data fetched from chain API

// ── Helpers ─────────────────────────────────────────────────────────────────────

const EARNING_TYPE_META: Record<EarningEntry['type'], { icon: keyof typeof Ionicons.glyphMap; color: string; label: string }> = {
  training: { icon: 'hardware-chip', color: COLORS.primary, label: 'Training' },
  rating: { icon: 'star', color: COLORS.gold, label: 'Rating' },
  data: { icon: 'cloud-upload', color: COLORS.info, label: 'Data' },
  bonus: { icon: 'gift', color: COLORS.success, label: 'Bonus' },
};

function formatRelativeTime(timestamp: string): string {
  const now = Date.now();
  const then = new Date(timestamp).getTime();
  const diffMs = now - then;
  const diffMins = Math.floor(diffMs / 60_000);
  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

function formatNumber(n: number, decimals = 2): string {
  return n.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

// ── Component ───────────────────────────────────────────────────────────────────

interface Props {
  navigation: any;
}

export default function T2EDashboardScreen({ navigation }: Props) {
  const { wallet, t2e, setT2E } = useStore();

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [recentEarnings, setRecentEarnings] = useState<EarningEntry[]>([]);
  const [projects, setProjects] = useState<ArchitectProject[]>([]);

  const fetchDashboardData = useCallback(async () => {
    if (!wallet.address) return;
    try {
      const [balanceRes, earningsRes, projectsRes] = await Promise.allSettled([
        getT2EBalance(wallet.address),
        getT2EHistory(wallet.address, 20),
        fetch(`${CONFIG.API_URL}/api/t2e/projects/${wallet.address}`, {
          headers: { 'Content-Type': 'application/json' },
        }).then((r) => r.ok ? r.json() : { projects: [] }),
      ]);

      if (balanceRes.status === 'fulfilled' && balanceRes.value) {
        const b = balanceRes.value;
        setT2E({
          balance: b.balance ?? 0,
          totalEarned: b.total_earned ?? 0,
          multiplier: b.multiplier ?? 1.0,
          projectsCompleted: b.projects_completed ?? 0,
        });
      }

      if (earningsRes.status === 'fulfilled' && earningsRes.value?.earnings) {
        setRecentEarnings(earningsRes.value.earnings.map((e: any) => ({
          id: e.id,
          type: e.type || 'training',
          amount: e.amount,
          description: e.description,
          timestamp: e.timestamp,
        })));
      }

      if (projectsRes.status === 'fulfilled' && projectsRes.value?.projects) {
        setProjects(projectsRes.value.projects);
      }
    } catch (error) {
      console.warn('T2E Dashboard: Failed to load data', error);
    } finally {
      setLoading(false);
    }
  }, [wallet.address, setT2E]);

  useEffect(() => {
    fetchDashboardData();
  }, [fetchDashboardData]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await fetchDashboardData();
    setRefreshing(false);
  }, [fetchDashboardData]);

  const activeProjects = projects.filter((p) => p.status === 'active');
  const completedProjects = projects.filter((p) => p.status === 'completed');

  // ── Render ──────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <SafeAreaView style={styles.container} edges={['top']}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={COLORS.gold} />
          <Text style={styles.loadingText}>Loading T2E Dashboard...</Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView
        style={styles.scroll}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={COLORS.gold}
          />
        }
      >
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
            <Ionicons name="arrow-back" size={24} color={COLORS.text} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Train to Earn</Text>
          <TouchableOpacity style={styles.historyBtn}>
            <Ionicons name="time-outline" size={24} color={COLORS.textSecondary} />
          </TouchableOpacity>
        </View>

        {/* ── T2E Balance Card ─────────────────────────────────────────────── */}
        <View style={styles.balanceCard}>
          <View style={styles.balanceCardHeader}>
            <View style={styles.balanceBadge}>
              <Ionicons name="flash" size={14} color={COLORS.gold} />
              <Text style={styles.balanceBadgeText}>T2E Tokens</Text>
            </View>
            <View style={styles.multiplierBadge}>
              <Ionicons name="trending-up" size={14} color={COLORS.background} />
              <Text style={styles.multiplierText}>{t2e.multiplier}x</Text>
            </View>
          </View>

          <Text style={styles.balanceAmount}>{formatNumber(t2e.balance)}</Text>
          <Text style={styles.balanceLabel}>Available Balance</Text>

          <View style={styles.balanceStatsRow}>
            <View style={styles.balanceStat}>
              <Text style={styles.balanceStatValue}>{formatNumber(t2e.totalEarned)}</Text>
              <Text style={styles.balanceStatLabel}>Total Earned</Text>
            </View>
            <View style={styles.balanceStatDivider} />
            <View style={styles.balanceStat}>
              <Text style={styles.balanceStatValue}>{t2e.multiplier}x</Text>
              <Text style={styles.balanceStatLabel}>Multiplier</Text>
            </View>
            <View style={styles.balanceStatDivider} />
            <View style={styles.balanceStat}>
              <Text style={styles.balanceStatValue}>{t2e.projectsCompleted}</Text>
              <Text style={styles.balanceStatLabel}>Projects</Text>
            </View>
          </View>
        </View>

        {/* ── Earn More Actions ────────────────────────────────────────────── */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Start Earning</Text>
          <View style={styles.actionsGrid}>
            <TouchableOpacity style={styles.actionCard} activeOpacity={0.7}>
              <View style={[styles.actionIconWrap, { backgroundColor: COLORS.primary + '20' }]}>
                <Ionicons name="hardware-chip" size={28} color={COLORS.primary} />
              </View>
              <Text style={styles.actionTitle}>Train AI</Text>
              <Text style={styles.actionSubtitle}>Fine-tune models</Text>
              <View style={styles.actionReward}>
                <Ionicons name="flash" size={12} color={COLORS.gold} />
                <Text style={styles.actionRewardText}>25-100 T2E</Text>
              </View>
            </TouchableOpacity>

            <TouchableOpacity style={styles.actionCard} activeOpacity={0.7}>
              <View style={[styles.actionIconWrap, { backgroundColor: COLORS.gold + '20' }]}>
                <Ionicons name="star" size={28} color={COLORS.gold} />
              </View>
              <Text style={styles.actionTitle}>Rate Responses</Text>
              <Text style={styles.actionSubtitle}>Quality feedback</Text>
              <View style={styles.actionReward}>
                <Ionicons name="flash" size={12} color={COLORS.gold} />
                <Text style={styles.actionRewardText}>5-25 T2E</Text>
              </View>
            </TouchableOpacity>

            <TouchableOpacity style={styles.actionCard} activeOpacity={0.7}>
              <View style={[styles.actionIconWrap, { backgroundColor: COLORS.info + '20' }]}>
                <Ionicons name="cloud-upload" size={28} color={COLORS.info} />
              </View>
              <Text style={styles.actionTitle}>Contribute Data</Text>
              <Text style={styles.actionSubtitle}>Share datasets</Text>
              <View style={styles.actionReward}>
                <Ionicons name="flash" size={12} color={COLORS.gold} />
                <Text style={styles.actionRewardText}>50-200 T2E</Text>
              </View>
            </TouchableOpacity>
          </View>
        </View>

        {/* ── Recent Earnings ──────────────────────────────────────────────── */}
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Recent Earnings</Text>
            <TouchableOpacity>
              <Text style={styles.seeAllText}>See All</Text>
            </TouchableOpacity>
          </View>

          {recentEarnings.length === 0 ? (
            <View style={styles.emptyBox}>
              <Ionicons name="wallet-outline" size={40} color={COLORS.textMuted} />
              <Text style={styles.emptyText}>No earnings yet</Text>
              <Text style={styles.emptySubtext}>Complete tasks above to start earning T2E tokens</Text>
            </View>
          ) : (
            recentEarnings.map((entry) => {
              const meta = EARNING_TYPE_META[entry.type];
              return (
                <View key={entry.id} style={styles.earningRow}>
                  <View style={[styles.earningIcon, { backgroundColor: meta.color + '15' }]}>
                    <Ionicons name={meta.icon} size={20} color={meta.color} />
                  </View>
                  <View style={styles.earningInfo}>
                    <Text style={styles.earningDescription} numberOfLines={1}>
                      {entry.description}
                    </Text>
                    <View style={styles.earningMeta}>
                      <Text style={styles.earningType}>{meta.label}</Text>
                      <Text style={styles.earningDot}> · </Text>
                      <Text style={styles.earningTime}>{formatRelativeTime(entry.timestamp)}</Text>
                    </View>
                  </View>
                  <Text style={styles.earningAmount}>+{formatNumber(entry.amount)}</Text>
                </View>
              );
            })
          )}
        </View>

        {/* ── Architect Projects ───────────────────────────────────────────── */}
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Architect Projects</Text>
            <View style={styles.projectCountBadge}>
              <Text style={styles.projectCountText}>
                {activeProjects.length} Active
              </Text>
            </View>
          </View>

          {activeProjects.map((project) => (
            <TouchableOpacity key={project.id} style={styles.projectCard} activeOpacity={0.7}>
              <View style={styles.projectHeader}>
                <View style={styles.projectStatusDot} />
                <Text style={styles.projectName} numberOfLines={1}>{project.name}</Text>
              </View>
              <View style={styles.projectStats}>
                <View style={styles.projectStatItem}>
                  <Ionicons name="flash" size={14} color={COLORS.gold} />
                  <Text style={styles.projectStatValue}>{formatNumber(project.earned)} T2E</Text>
                </View>
                <View style={styles.projectStatItem}>
                  <Ionicons name="git-commit" size={14} color={COLORS.textSecondary} />
                  <Text style={styles.projectStatLabel}>{project.contributions} contributions</Text>
                </View>
              </View>
              <View style={styles.projectProgressBar}>
                <View style={[styles.projectProgressFill, { width: `${Math.min(project.progress ?? 0, 100)}%` }]} />
              </View>
            </TouchableOpacity>
          ))}

          {completedProjects.length > 0 && (
            <>
              <Text style={styles.completedLabel}>Completed</Text>
              {completedProjects.map((project) => (
                <View key={project.id} style={styles.completedProjectRow}>
                  <View style={styles.completedDot}>
                    <Ionicons name="checkmark" size={12} color={COLORS.success} />
                  </View>
                  <View style={styles.completedInfo}>
                    <Text style={styles.completedName} numberOfLines={1}>{project.name}</Text>
                    <Text style={styles.completedDate}>{project.completedAt}</Text>
                  </View>
                  <Text style={styles.completedEarned}>{formatNumber(project.earned)} T2E</Text>
                </View>
              ))}
            </>
          )}
        </View>

        <View style={{ height: SPACING.xxl }} />
      </ScrollView>
    </SafeAreaView>
  );
}

// ── Styles ──────────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  scroll: {
    flex: 1,
    paddingHorizontal: SPACING.lg,
  },

  // Loading
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: SPACING.md,
  },
  loadingText: {
    fontSize: FONT_SIZES.md,
    color: COLORS.textSecondary,
  },

  // Header
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: SPACING.md,
  },
  backBtn: {
    width: 44,
    height: 44,
    borderRadius: BORDER_RADIUS.md,
    backgroundColor: COLORS.surface,
    justifyContent: 'center',
    alignItems: 'center',
  },
  headerTitle: {
    fontSize: FONT_SIZES.xxl,
    fontWeight: '700',
    color: COLORS.gold,
  },
  historyBtn: {
    width: 44,
    height: 44,
    borderRadius: BORDER_RADIUS.md,
    backgroundColor: COLORS.surface,
    justifyContent: 'center',
    alignItems: 'center',
  },

  // Balance Card
  balanceCard: {
    backgroundColor: COLORS.surface,
    borderRadius: BORDER_RADIUS.xl,
    padding: SPACING.lg,
    marginBottom: SPACING.lg,
    borderWidth: 1,
    borderColor: COLORS.gold + '30',
  },
  balanceCardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: SPACING.md,
  },
  balanceBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: SPACING.xs,
  },
  balanceBadgeText: {
    fontSize: FONT_SIZES.sm,
    color: COLORS.gold,
    fontWeight: '600',
  },
  multiplierBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: SPACING.xs,
    backgroundColor: COLORS.gold,
    paddingHorizontal: SPACING.sm,
    paddingVertical: SPACING.xs,
    borderRadius: BORDER_RADIUS.full,
  },
  multiplierText: {
    fontSize: FONT_SIZES.sm,
    fontWeight: '700',
    color: COLORS.background,
  },
  balanceAmount: {
    fontSize: FONT_SIZES.display,
    fontWeight: '700',
    color: COLORS.text,
    textAlign: 'center',
  },
  balanceLabel: {
    fontSize: FONT_SIZES.sm,
    color: COLORS.textSecondary,
    textAlign: 'center',
    marginBottom: SPACING.lg,
  },
  balanceStatsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-around',
    borderTopWidth: 1,
    borderTopColor: COLORS.border,
    paddingTop: SPACING.md,
  },
  balanceStat: {
    alignItems: 'center',
    flex: 1,
  },
  balanceStatValue: {
    fontSize: FONT_SIZES.lg,
    fontWeight: '700',
    color: COLORS.gold,
  },
  balanceStatLabel: {
    fontSize: FONT_SIZES.xs,
    color: COLORS.textMuted,
    marginTop: 2,
  },
  balanceStatDivider: {
    width: 1,
    height: 28,
    backgroundColor: COLORS.border,
  },

  // Sections
  section: {
    marginBottom: SPACING.lg,
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: SPACING.md,
  },
  sectionTitle: {
    fontSize: FONT_SIZES.lg,
    fontWeight: '600',
    color: COLORS.text,
    marginBottom: SPACING.md,
  },
  seeAllText: {
    fontSize: FONT_SIZES.sm,
    color: COLORS.gold,
    fontWeight: '600',
    marginBottom: SPACING.md,
  },

  // Actions Grid
  actionsGrid: {
    flexDirection: 'row',
    gap: SPACING.sm,
  },
  actionCard: {
    flex: 1,
    backgroundColor: COLORS.surface,
    borderRadius: BORDER_RADIUS.lg,
    padding: SPACING.md,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  actionIconWrap: {
    width: 52,
    height: 52,
    borderRadius: BORDER_RADIUS.lg,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: SPACING.sm,
  },
  actionTitle: {
    fontSize: FONT_SIZES.sm,
    fontWeight: '600',
    color: COLORS.text,
    textAlign: 'center',
  },
  actionSubtitle: {
    fontSize: FONT_SIZES.xs,
    color: COLORS.textMuted,
    textAlign: 'center',
    marginBottom: SPACING.sm,
  },
  actionReward: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    backgroundColor: COLORS.gold + '15',
    paddingHorizontal: SPACING.sm,
    paddingVertical: 3,
    borderRadius: BORDER_RADIUS.full,
  },
  actionRewardText: {
    fontSize: FONT_SIZES.xs,
    color: COLORS.gold,
    fontWeight: '600',
  },

  // Earnings
  emptyBox: {
    alignItems: 'center',
    padding: SPACING.xl,
    backgroundColor: COLORS.surface,
    borderRadius: BORDER_RADIUS.lg,
    gap: SPACING.sm,
  },
  emptyText: {
    fontSize: FONT_SIZES.md,
    color: COLORS.textMuted,
    fontWeight: '500',
  },
  emptySubtext: {
    fontSize: FONT_SIZES.sm,
    color: COLORS.textMuted,
    textAlign: 'center',
  },
  earningRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.surface,
    borderRadius: BORDER_RADIUS.lg,
    padding: SPACING.md,
    marginBottom: SPACING.sm,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  earningIcon: {
    width: 40,
    height: 40,
    borderRadius: BORDER_RADIUS.md,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: SPACING.md,
  },
  earningInfo: {
    flex: 1,
    marginRight: SPACING.sm,
  },
  earningDescription: {
    fontSize: FONT_SIZES.md,
    fontWeight: '500',
    color: COLORS.text,
  },
  earningMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 2,
  },
  earningType: {
    fontSize: FONT_SIZES.xs,
    color: COLORS.textMuted,
  },
  earningDot: {
    fontSize: FONT_SIZES.xs,
    color: COLORS.textMuted,
  },
  earningTime: {
    fontSize: FONT_SIZES.xs,
    color: COLORS.textMuted,
  },
  earningAmount: {
    fontSize: FONT_SIZES.md,
    fontWeight: '700',
    color: COLORS.success,
  },

  // Projects
  projectCountBadge: {
    backgroundColor: COLORS.success + '20',
    paddingHorizontal: SPACING.sm,
    paddingVertical: SPACING.xs,
    borderRadius: BORDER_RADIUS.full,
    marginBottom: SPACING.md,
  },
  projectCountText: {
    fontSize: FONT_SIZES.xs,
    color: COLORS.success,
    fontWeight: '600',
  },
  projectCard: {
    backgroundColor: COLORS.surface,
    borderRadius: BORDER_RADIUS.lg,
    padding: SPACING.md,
    marginBottom: SPACING.sm,
    borderWidth: 1,
    borderColor: COLORS.primary + '30',
  },
  projectHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: SPACING.sm,
  },
  projectStatusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: COLORS.success,
    marginRight: SPACING.sm,
  },
  projectName: {
    fontSize: FONT_SIZES.md,
    fontWeight: '600',
    color: COLORS.text,
    flex: 1,
  },
  projectStats: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: SPACING.sm,
  },
  projectStatItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: SPACING.xs,
  },
  projectStatValue: {
    fontSize: FONT_SIZES.sm,
    color: COLORS.gold,
    fontWeight: '600',
  },
  projectStatLabel: {
    fontSize: FONT_SIZES.sm,
    color: COLORS.textSecondary,
  },
  projectProgressBar: {
    height: 4,
    backgroundColor: COLORS.border,
    borderRadius: 2,
    overflow: 'hidden',
  },
  projectProgressFill: {
    height: '100%',
    backgroundColor: COLORS.primary,
    borderRadius: 2,
  },

  // Completed Projects
  completedLabel: {
    fontSize: FONT_SIZES.sm,
    color: COLORS.textMuted,
    fontWeight: '600',
    marginTop: SPACING.md,
    marginBottom: SPACING.sm,
  },
  completedProjectRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.surface,
    borderRadius: BORDER_RADIUS.lg,
    padding: SPACING.md,
    marginBottom: SPACING.sm,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  completedDot: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: COLORS.success + '20',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: SPACING.md,
  },
  completedInfo: {
    flex: 1,
  },
  completedName: {
    fontSize: FONT_SIZES.md,
    fontWeight: '500',
    color: COLORS.text,
  },
  completedDate: {
    fontSize: FONT_SIZES.xs,
    color: COLORS.textMuted,
    marginTop: 2,
  },
  completedEarned: {
    fontSize: FONT_SIZES.sm,
    fontWeight: '600',
    color: COLORS.textSecondary,
  },
});
