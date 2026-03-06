import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, StyleSheet, FlatList, RefreshControl, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT_SIZES, BORDER_RADIUS } from '../constants/theme';
import { useStore } from '../store/useStore';
import { getTransactionHistory } from '../services/api';

export default function HistoryScreen() {
  const { wallet, recentTxs, setRecentTxs } = useStore();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    if (!wallet.address) return;
    try {
      const txs = await getTransactionHistory(wallet.address, 50);
      setRecentTxs(Array.isArray(txs) ? txs : []);
    } catch {
      // Keep existing
    } finally {
      setLoading(false);
    }
  }, [wallet.address]);

  useEffect(() => { load(); }, [load]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }, [load]);

  const renderItem = ({ item }: { item: any }) => {
    const isSend = item.from === wallet.address || item.type === 'send';
    return (
      <View style={styles.txRow}>
        <View style={[styles.txIcon, { backgroundColor: isSend ? COLORS.error + '20' : COLORS.success + '20' }]}>
          <Ionicons name={isSend ? 'arrow-up' : 'arrow-down'} size={20} color={isSend ? COLORS.error : COLORS.success} />
        </View>
        <View style={styles.txInfo}>
          <Text style={styles.txType}>{isSend ? 'Sent' : 'Received'}</Text>
          <Text style={styles.txAddr}>{(isSend ? item.to : item.from)?.slice(0, 14)}...</Text>
        </View>
        <View style={styles.txAmount}>
          <Text style={[styles.txAmountText, { color: isSend ? COLORS.error : COLORS.success }]}>
            {isSend ? '-' : '+'}{item.amount} {item.token || 'THR'}
          </Text>
        </View>
      </View>
    );
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.title}>History</Text>
      </View>

      {loading ? (
        <View style={styles.center}><ActivityIndicator color={COLORS.gold} /></View>
      ) : recentTxs.length === 0 ? (
        <View style={styles.center}>
          <Ionicons name="time-outline" size={56} color={COLORS.textMuted} />
          <Text style={styles.emptyText}>No transactions yet</Text>
        </View>
      ) : (
        <FlatList
          data={recentTxs}
          keyExtractor={(_, i) => String(i)}
          renderItem={renderItem}
          contentContainerStyle={styles.list}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.gold} />}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.background },
  header: { paddingHorizontal: SPACING.lg, paddingVertical: SPACING.md },
  title: { fontSize: FONT_SIZES.xxl, fontWeight: '700', color: COLORS.text },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', gap: SPACING.md },
  emptyText: { fontSize: FONT_SIZES.md, color: COLORS.textMuted },
  list: { paddingHorizontal: SPACING.lg },
  txRow: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.lg,
    padding: SPACING.md, marginBottom: SPACING.sm, borderWidth: 1, borderColor: COLORS.border,
  },
  txIcon: { width: 40, height: 40, borderRadius: BORDER_RADIUS.md, justifyContent: 'center', alignItems: 'center', marginRight: SPACING.md },
  txInfo: { flex: 1 },
  txType: { fontSize: FONT_SIZES.md, fontWeight: '600', color: COLORS.text },
  txAddr: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, fontFamily: 'monospace' },
  txAmount: { alignItems: 'flex-end' },
  txAmountText: { fontSize: FONT_SIZES.md, fontWeight: '600' },
});
