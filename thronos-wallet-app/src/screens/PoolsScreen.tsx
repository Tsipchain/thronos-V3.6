import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  Alert,
  ActivityIndicator,
  ScrollView,
  Modal,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT_SIZES, BORDER_RADIUS } from '../constants/theme';
import { useStore } from '../store/useStore';
import { getLiquidityPools, getLPPositions, addLiquidity, getTokenBalances } from '../services/api';
import { getWallet, getPrivateKey } from '../services/wallet';

interface Pool {
  id: string;
  token_a: string;
  token_b: string;
  total_liquidity: number;
  apy: number;
  volume_24h: number;
}

interface Position {
  pool_id: string;
  token_a: string;
  token_b: string;
  liquidity_share: number;
  value: number;
  pending_rewards: number;
}

export default function PoolsScreen({ navigation }: { navigation: any }) {
  const { wallet } = useStore();
  const [pools, setPools] = useState<Pool[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [balances, setBalances] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [selectedPool, setSelectedPool] = useState<Pool | null>(null);
  const [amountA, setAmountA] = useState('');
  const [amountB, setAmountB] = useState('');

  const loadData = useCallback(async () => {
    if (!wallet.address) return;
    try {
      const [poolsRes, posRes, balRes] = await Promise.allSettled([
        getLiquidityPools(),
        getLPPositions(wallet.address),
        getTokenBalances(wallet.address),
      ]);
      if (poolsRes.status === 'fulfilled') setPools(poolsRes.value.pools || []);
      if (posRes.status === 'fulfilled') setPositions(posRes.value.positions || []);
      if (balRes.status === 'fulfilled' && balRes.value?.tokens) {
        const bals: Record<string, number> = {};
        for (const t of balRes.value.tokens) bals[t.symbol] = t.balance;
        setBalances(bals);
      }
    } catch (err) {
      console.warn('Pools: failed to load', err);
    } finally {
      setLoading(false);
    }
  }, [wallet.address]);

  useEffect(() => { loadData(); }, [loadData]);

  const openAddLiquidity = (pool: Pool) => {
    setSelectedPool(pool);
    setAmountA('');
    setAmountB('');
  };

  const handleAddLiquidity = useCallback(async () => {
    if (!selectedPool) return;
    const a = parseFloat(amountA) || 0;
    const b = parseFloat(amountB) || 0;
    if (a <= 0 || b <= 0) {
      Alert.alert('Invalid amount', 'Enter amounts greater than zero for both tokens.');
      return;
    }
    setSubmitting(true);
    try {
      const creds = await getWallet();
      const privHex = await getPrivateKey();
      if (!creds?.address || !privHex) {
        Alert.alert('Error', 'Wallet credentials not found.');
        return;
      }
      const result = await addLiquidity({
        from: creds.address,
        pool_id: selectedPool.id,
        amount_a: a,
        amount_b: b,
        private_key_hex: privHex,
      });
      if (result.ok) {
        Alert.alert('Liquidity Added', `Added ${a} ${selectedPool.token_a} + ${b} ${selectedPool.token_b}.`);
        setSelectedPool(null);
        loadData();
      } else {
        Alert.alert('Failed', result.error || 'Add liquidity failed.');
      }
    } catch (error: any) {
      Alert.alert('Failed', error.message || 'An unexpected error occurred.');
    } finally {
      setSubmitting(false);
    }
  }, [selectedPool, amountA, amountB, loadData]);

  return (
    <SafeAreaView style={styles.container}>
      <LinearGradient colors={[COLORS.background, COLORS.backgroundLight]} style={styles.gradient}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
            <Ionicons name="arrow-back" size={24} color={COLORS.text} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Liquidity Pools</Text>
          <View style={{ width: 24 }} />
        </View>

        <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
          {loading ? (
            <ActivityIndicator color={COLORS.gold} style={{ marginTop: SPACING.xl }} />
          ) : (
            <>
              {positions.length > 0 && (
                <>
                  <Text style={styles.sectionLabel}>Your Positions</Text>
                  {positions.map((pos) => (
                    <View key={pos.pool_id} style={styles.posCard}>
                      <Text style={styles.posPair}>{pos.token_a}/{pos.token_b}</Text>
                      <View style={styles.posRow}>
                        <Text style={styles.posLabel}>Your Value</Text>
                        <Text style={styles.posValue}>{pos.value.toLocaleString(undefined, { maximumFractionDigits: 6 })}</Text>
                      </View>
                      <View style={styles.posRow}>
                        <Text style={styles.posLabel}>Pending Rewards</Text>
                        <Text style={[styles.posValue, { color: COLORS.gold }]}>{pos.pending_rewards.toLocaleString(undefined, { maximumFractionDigits: 6 })}</Text>
                      </View>
                    </View>
                  ))}
                </>
              )}

              <Text style={styles.sectionLabel}>All Pools</Text>
              {pools.length === 0 ? (
                <View style={styles.emptyBox}>
                  <Ionicons name="water-outline" size={40} color={COLORS.textMuted} />
                  <Text style={styles.emptyText}>No pools available</Text>
                </View>
              ) : (
                pools.map((pool) => (
                  <TouchableOpacity key={pool.id} style={styles.poolCard} onPress={() => openAddLiquidity(pool)} activeOpacity={0.8}>
                    <View style={styles.poolHeader}>
                      <Text style={styles.poolPair}>{pool.token_a}/{pool.token_b}</Text>
                      <View style={styles.apyBadge}>
                        <Text style={styles.apyText}>{pool.apy?.toFixed(2) ?? '0.00'}% APY</Text>
                      </View>
                    </View>
                    <View style={styles.poolRow}>
                      <Text style={styles.poolLabel}>Total Liquidity</Text>
                      <Text style={styles.poolValue}>{pool.total_liquidity?.toLocaleString(undefined, { maximumFractionDigits: 2 })}</Text>
                    </View>
                    <View style={styles.poolRow}>
                      <Text style={styles.poolLabel}>24h Volume</Text>
                      <Text style={styles.poolValue}>{pool.volume_24h?.toLocaleString(undefined, { maximumFractionDigits: 2 })}</Text>
                    </View>
                    <View style={styles.addBtnRow}>
                      <Ionicons name="add-circle-outline" size={16} color={COLORS.gold} />
                      <Text style={styles.addBtnText}>Add Liquidity</Text>
                    </View>
                  </TouchableOpacity>
                ))
              )}
            </>
          )}
          <View style={{ height: SPACING.xxl }} />
        </ScrollView>
      </LinearGradient>

      <Modal visible={!!selectedPool} transparent animationType="slide">
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>Add Liquidity</Text>
            {selectedPool && (
              <>
                <Text style={styles.modalSubtitle}>{selectedPool.token_a}/{selectedPool.token_b} Pool</Text>

                <Text style={styles.inputLabel}>{selectedPool.token_a} Amount</Text>
                <TextInput
                  style={styles.input}
                  placeholder="0.00"
                  placeholderTextColor={COLORS.textMuted}
                  value={amountA}
                  onChangeText={setAmountA}
                  keyboardType="decimal-pad"
                />
                <Text style={styles.balanceHint}>Available: {(balances[selectedPool.token_a] ?? 0).toLocaleString(undefined, { maximumFractionDigits: 6 })} {selectedPool.token_a}</Text>

                <Text style={styles.inputLabel}>{selectedPool.token_b} Amount</Text>
                <TextInput
                  style={styles.input}
                  placeholder="0.00"
                  placeholderTextColor={COLORS.textMuted}
                  value={amountB}
                  onChangeText={setAmountB}
                  keyboardType="decimal-pad"
                />
                <Text style={styles.balanceHint}>Available: {(balances[selectedPool.token_b] ?? 0).toLocaleString(undefined, { maximumFractionDigits: 6 })} {selectedPool.token_b}</Text>

                <View style={styles.modalActions}>
                  <TouchableOpacity style={styles.modalCancelBtn} onPress={() => setSelectedPool(null)} disabled={submitting}>
                    <Text style={styles.modalCancelText}>Cancel</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={styles.modalConfirmBtn} onPress={handleAddLiquidity} disabled={submitting} activeOpacity={0.8}>
                    <LinearGradient colors={[COLORS.gold, COLORS.goldDark]} style={styles.modalConfirmGradient}>
                      {submitting ? <ActivityIndicator color={COLORS.background} /> : <Text style={styles.modalConfirmText}>Add Liquidity</Text>}
                    </LinearGradient>
                  </TouchableOpacity>
                </View>
              </>
            )}
          </View>
        </View>
      </Modal>
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
  sectionLabel: { fontSize: FONT_SIZES.sm, fontWeight: '600', color: COLORS.textSecondary, marginTop: SPACING.lg, marginBottom: SPACING.sm, textTransform: 'uppercase', letterSpacing: 0.8 },
  emptyBox: { alignItems: 'center', padding: SPACING.xl, backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.xl, gap: SPACING.sm },
  emptyText: { fontSize: FONT_SIZES.md, color: COLORS.textMuted },

  posCard: { backgroundColor: COLORS.backgroundCard, borderRadius: BORDER_RADIUS.lg, padding: SPACING.md, marginBottom: SPACING.sm, borderWidth: 1, borderColor: COLORS.gold + '25' },
  posPair: { fontSize: FONT_SIZES.lg, fontWeight: '700', color: COLORS.text, marginBottom: SPACING.xs },
  posRow: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 2 },
  posLabel: { fontSize: FONT_SIZES.sm, color: COLORS.textSecondary },
  posValue: { fontSize: FONT_SIZES.sm, fontWeight: '600', color: COLORS.text },

  poolCard: { backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.xl, padding: SPACING.md, marginBottom: SPACING.sm, borderWidth: 1, borderColor: COLORS.border },
  poolHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: SPACING.sm },
  poolPair: { fontSize: FONT_SIZES.lg, fontWeight: '700', color: COLORS.text },
  apyBadge: { backgroundColor: COLORS.success + '20', paddingHorizontal: SPACING.sm, paddingVertical: 4, borderRadius: BORDER_RADIUS.full },
  apyText: { fontSize: FONT_SIZES.xs, fontWeight: '700', color: COLORS.success },
  poolRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 2 },
  poolLabel: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted },
  poolValue: { fontSize: FONT_SIZES.xs, fontWeight: '600', color: COLORS.textSecondary },
  addBtnRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: SPACING.sm },
  addBtnText: { fontSize: FONT_SIZES.sm, fontWeight: '700', color: COLORS.gold },

  modalOverlay: { flex: 1, backgroundColor: COLORS.overlay, justifyContent: 'center', alignItems: 'center', padding: SPACING.lg },
  modalContent: { width: '100%', backgroundColor: COLORS.backgroundCard, borderRadius: BORDER_RADIUS.xl, padding: SPACING.lg, borderWidth: 1, borderColor: COLORS.gold + '30' },
  modalTitle: { fontSize: FONT_SIZES.xxl, fontWeight: '700', color: COLORS.text, marginBottom: SPACING.xs },
  modalSubtitle: { fontSize: FONT_SIZES.sm, color: COLORS.textSecondary, marginBottom: SPACING.lg },
  inputLabel: { fontSize: FONT_SIZES.sm, fontWeight: '600', color: COLORS.textSecondary, marginBottom: SPACING.xs },
  input: { backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.lg, borderWidth: 1, borderColor: COLORS.border, padding: SPACING.md, fontSize: FONT_SIZES.lg, color: COLORS.text, marginBottom: SPACING.xs },
  balanceHint: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, marginBottom: SPACING.md },
  modalActions: { flexDirection: 'row', gap: SPACING.md, marginTop: SPACING.md },
  modalCancelBtn: { flex: 1, paddingVertical: SPACING.md, borderRadius: BORDER_RADIUS.lg, borderWidth: 1, borderColor: COLORS.border, alignItems: 'center', justifyContent: 'center' },
  modalCancelText: { fontSize: FONT_SIZES.md, fontWeight: '600', color: COLORS.textSecondary },
  modalConfirmBtn: { flex: 1.5, borderRadius: BORDER_RADIUS.lg, overflow: 'hidden' },
  modalConfirmGradient: { paddingVertical: SPACING.md, alignItems: 'center', justifyContent: 'center' },
  modalConfirmText: { fontSize: FONT_SIZES.md, fontWeight: '700', color: COLORS.background },
});
