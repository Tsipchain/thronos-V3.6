import React, { useCallback, useEffect, useRef, useState } from 'react';
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
import {
  getLiquidityPools,
  getLPPositions,
  addLiquidity,
  getAvailablePools,
  quoteAddLiquidity,
  addLiquidityCrossChain,
  type AvailablePool,
  type ExternalChainInfo,
} from '../services/api';
import { getWallet, getPrivateKey, getAuthSecret } from '../services/wallet';

interface Pool {
  id: string;
  token_a: string;
  token_b: string;
  total_liquidity: number;
  apy: number;
  volume_24h: number;
  reserves_a?: number;
  reserves_b?: number;
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
  const [availablePools, setAvailablePools] = useState<AvailablePool[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  // Modal state for selected pool
  const [selectedPool, setSelectedPool] = useState<Pool | null>(null);
  const [selectedAvailable, setSelectedAvailable] = useState<AvailablePool | null>(null);

  // Cross-chain form state
  const [selectedChainIdx, setSelectedChainIdx] = useState(0);
  const [evmAddress, setEvmAddress] = useState('');
  const [amountA, setAmountA] = useState('');
  const [amountB, setAmountB] = useState('');
  const [manualSecret, setManualSecret] = useState('');
  const [quoteInfo, setQuoteInfo] = useState<string>('');
  const [cachedSecret, setCachedSecret] = useState<string | null>(null);

  const quoteTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadData = useCallback(async () => {
    if (!wallet.address) return;
    try {
      const [poolsRes, posRes, availRes, secret] = await Promise.allSettled([
        getLiquidityPools(),
        getLPPositions(wallet.address),
        getAvailablePools(),
        getAuthSecret(),
      ]);
      if (poolsRes.status === 'fulfilled') setPools(poolsRes.value.pools || []);
      if (posRes.status === 'fulfilled') setPositions(posRes.value.positions || []);
      if (availRes.status === 'fulfilled') setAvailablePools(availRes.value.pools || []);
      if (secret.status === 'fulfilled') setCachedSecret(secret.value);
    } catch (err) {
      console.warn('Pools: failed to load', err);
    } finally {
      setLoading(false);
    }
  }, [wallet.address]);

  useEffect(() => { loadData(); }, [loadData]);

  const isCrossChainPool = (pool: Pool) =>
    pool.token_a === 'THR' && (pool.token_b === 'USDT' || pool.token_b === 'USDC');

  const openAddLiquidity = (pool: Pool) => {
    setSelectedPool(pool);
    setAmountA('');
    setAmountB('');
    setEvmAddress('');
    setManualSecret('');
    setQuoteInfo('');
    setSelectedChainIdx(0);
    const avail = availablePools.find(p => p.pool_id === pool.id) || null;
    setSelectedAvailable(avail);
  };

  const getLocalRatio = (): number | null => {
    const src = selectedAvailable || null;
    const resA = src?.reserves_a ?? selectedPool?.reserves_a ?? 0;
    const resB = src?.reserves_b ?? selectedPool?.reserves_b ?? 0;
    return resA > 0 && resB > 0 ? resB / resA : null;
  };

  const fetchQuote = async (poolId: string, amtA: string) => {
    const a = parseFloat(amtA);
    if (!a || a <= 0) { setQuoteInfo(''); return; }
    try {
      const q = await quoteAddLiquidity(poolId, a);
      if (q.ok && q.amount_b !== undefined) {
        setAmountB(String(q.amount_b));
        const tolMin = (q.amount_b * 0.98).toFixed(6);
        const tolMax = (q.amount_b * 1.02).toFixed(6);
        setQuoteInfo(
          `Required: ${q.amount_b} ${selectedPool?.token_b} (±2%: ${tolMin}–${tolMax})\n` +
          `Est. LP: ${q.lp_shares_estimate} shares · Pool share: ${q.share_pct}%`
        );
      }
    } catch {}
  };

  const handleAmountAChange = (val: string) => {
    setAmountA(val);
    const ratio = getLocalRatio();
    if (ratio) {
      const a = parseFloat(val);
      if (a > 0) setAmountB((a * ratio).toFixed(6));
    }
    if (selectedPool) {
      if (quoteTimer.current) clearTimeout(quoteTimer.current);
      quoteTimer.current = setTimeout(() => fetchQuote(selectedPool.id, val), 400);
    }
  };

  const handleAmountBChange = (val: string) => {
    setAmountB(val);
    const ratio = getLocalRatio();
    if (ratio) {
      const b = parseFloat(val);
      if (b > 0) setAmountA((b / ratio).toFixed(6));
    }
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
      if (isCrossChainPool(selectedPool) && selectedAvailable) {
        // Cross-chain path: THR + USDT/USDC
        const chainInfo: ExternalChainInfo = selectedAvailable.external_chains[selectedChainIdx];
        if (!chainInfo) {
          Alert.alert('Error', 'No external chain selected.');
          return;
        }
        if (!evmAddress.trim()) {
          Alert.alert('Error', `Enter your EVM address holding ${selectedPool.token_b}.`);
          return;
        }
        const secret = cachedSecret || manualSecret.trim();
        if (!secret) {
          Alert.alert('Error', 'Auth secret required. Enter your pledge send_secret.');
          return;
        }
        if (!wallet.address) {
          Alert.alert('Error', 'No active wallet.');
          return;
        }
        const result = await addLiquidityCrossChain({
          pool_id: selectedPool.id,
          amount_a: a,
          amount_b: b,
          chain: chainInfo.chain,
          token_contract: chainInfo.token_contract,
          decimals: chainInfo.decimals,
          provider_thr: wallet.address,
          evm_address: evmAddress.trim(),
          auth_secret: secret,
        });
        if (result.ok) {
          Alert.alert(
            'Intent Created',
            `Send ${b} ${selectedPool.token_b} to:\n\n${result.vault_address}\n\non ${chainInfo.label}\n\nIntent expires: ${new Date(result.expires_at * 1000).toLocaleString()}`,
            [
              { text: 'Copy Address', onPress: () => { /* TODO: clipboard */ } },
              { text: 'OK', onPress: () => { setSelectedPool(null); loadData(); } },
            ]
          );
        } else {
          Alert.alert('Failed', result.message || result.error || 'Add liquidity failed.');
        }
      } else {
        // Legacy internal path (WBTC/L2E pairs)
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
      }
    } catch (error: any) {
      Alert.alert('Failed', error.message || 'An unexpected error occurred.');
    } finally {
      setSubmitting(false);
    }
  }, [selectedPool, selectedAvailable, selectedChainIdx, amountA, amountB, evmAddress, manualSecret, cachedSecret, wallet.address, loadData]);

  const renderChainPicker = (chains: ExternalChainInfo[]) => (
    <View style={styles.chainRow}>
      {chains.map((c, i) => (
        <TouchableOpacity
          key={c.chain}
          style={[styles.chainChip, selectedChainIdx === i && styles.chainChipActive]}
          onPress={() => setSelectedChainIdx(i)}
        >
          <Text style={[styles.chainChipText, selectedChainIdx === i && styles.chainChipTextActive]}>
            {c.label}
          </Text>
        </TouchableOpacity>
      ))}
    </View>
  );

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
                      <View style={{ flexDirection: 'row', gap: SPACING.xs, alignItems: 'center' }}>
                        {isCrossChainPool(pool) && (
                          <View style={styles.crossChainBadge}>
                            <Text style={styles.crossChainBadgeText}>Cross-Chain</Text>
                          </View>
                        )}
                        <View style={styles.apyBadge}>
                          <Text style={styles.apyText}>{pool.apy?.toFixed(2) ?? '0.00'}% APY</Text>
                        </View>
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
          <ScrollView contentContainerStyle={{ flexGrow: 1, justifyContent: 'center', padding: SPACING.lg }}>
            <View style={styles.modalContent}>
              <Text style={styles.modalTitle}>Add Liquidity</Text>
              {selectedPool && (
                <>
                  <Text style={styles.modalSubtitle}>{selectedPool.token_a}/{selectedPool.token_b} Pool</Text>

                  {/* Pool reserves panel */}
                  {(() => {
                    const resA = selectedAvailable?.reserves_a ?? selectedPool.reserves_a ?? 0;
                    const resB = selectedAvailable?.reserves_b ?? selectedPool.reserves_b ?? 0;
                    const ratio = selectedAvailable?.pool_ratio ?? (resA > 0 && resB > 0 ? resB / resA : null);
                    if (!resA) return null;
                    return (
                      <View style={styles.reservesPanel}>
                        <View style={styles.reservesRow}>
                          <Text style={styles.reservesLabel}>Pool Reserves</Text>
                          <Text style={styles.reservesLabel}>Ratio</Text>
                        </View>
                        <View style={styles.reservesRow}>
                          <Text style={styles.reservesValue}>
                            {resA.toLocaleString(undefined, { maximumFractionDigits: 4 })} {selectedPool.token_a} / {resB.toLocaleString(undefined, { maximumFractionDigits: 4 })} {selectedPool.token_b}
                          </Text>
                          <Text style={styles.reservesRatio}>
                            1 {selectedPool.token_a} = {ratio ? ratio.toFixed(4) : '—'} {selectedPool.token_b}
                          </Text>
                        </View>
                      </View>
                    );
                  })()}

                  {/* Cross-chain UI: chain picker + EVM address */}
                  {isCrossChainPool(selectedPool) && selectedAvailable?.external_chains.length ? (
                    <>
                      <Text style={styles.inputLabel}>External Chain for {selectedPool.token_b}</Text>
                      {renderChainPicker(selectedAvailable.external_chains)}

                      <Text style={styles.inputLabel}>Your EVM Address (holding {selectedPool.token_b})</Text>
                      <TextInput
                        style={[styles.input, { fontFamily: 'monospace', fontSize: FONT_SIZES.sm }]}
                        placeholder="0x..."
                        placeholderTextColor={COLORS.textMuted}
                        value={evmAddress}
                        onChangeText={setEvmAddress}
                        autoCapitalize="none"
                        autoCorrect={false}
                      />
                    </>
                  ) : null}

                  <Text style={styles.inputLabel}>THR Amount</Text>
                  <TextInput
                    style={styles.input}
                    placeholder="0.00"
                    placeholderTextColor={COLORS.textMuted}
                    value={amountA}
                    onChangeText={handleAmountAChange}
                    keyboardType="decimal-pad"
                  />

                  <Text style={styles.inputLabel}>{selectedPool.token_b} Amount</Text>
                  <TextInput
                    style={styles.input}
                    placeholder="0.00"
                    placeholderTextColor={COLORS.textMuted}
                    value={amountB}
                    onChangeText={handleAmountBChange}
                    keyboardType="decimal-pad"
                  />

                  {!!quoteInfo && (
                    <Text style={styles.quoteText}>{quoteInfo}</Text>
                  )}

                  {isCrossChainPool(selectedPool) && (
                    <View style={styles.gasWarning}>
                      <Ionicons name="warning-outline" size={14} color={COLORS.warning} />
                      <Text style={styles.gasWarningText}>
                        Gas required on external chain to send {selectedPool.token_b}.
                      </Text>
                    </View>
                  )}

                  {/* Auth secret — only shown if not cached */}
                  {isCrossChainPool(selectedPool) && !cachedSecret && (
                    <>
                      <Text style={styles.inputLabel}>Auth Secret (send_secret from pledge)</Text>
                      <TextInput
                        style={styles.input}
                        placeholder="Enter your auth secret"
                        placeholderTextColor={COLORS.textMuted}
                        value={manualSecret}
                        onChangeText={setManualSecret}
                        secureTextEntry
                        autoCapitalize="none"
                        autoCorrect={false}
                      />
                    </>
                  )}

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
          </ScrollView>
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
  crossChainBadge: { backgroundColor: COLORS.info + '20', paddingHorizontal: SPACING.sm, paddingVertical: 4, borderRadius: BORDER_RADIUS.full },
  crossChainBadgeText: { fontSize: FONT_SIZES.xs, fontWeight: '700', color: COLORS.info },
  poolRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 2 },
  poolLabel: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted },
  poolValue: { fontSize: FONT_SIZES.xs, fontWeight: '600', color: COLORS.textSecondary },
  addBtnRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: SPACING.sm },
  addBtnText: { fontSize: FONT_SIZES.sm, fontWeight: '700', color: COLORS.gold },

  chainRow: { flexDirection: 'row', flexWrap: 'wrap', gap: SPACING.xs, marginBottom: SPACING.md },
  chainChip: { paddingVertical: 6, paddingHorizontal: SPACING.sm, borderRadius: BORDER_RADIUS.full, borderWidth: 1, borderColor: COLORS.border, backgroundColor: COLORS.surface },
  chainChipActive: { borderColor: COLORS.gold, backgroundColor: COLORS.gold + '18' },
  chainChipText: { fontSize: FONT_SIZES.xs, color: COLORS.textSecondary, fontWeight: '600' },
  chainChipTextActive: { color: COLORS.gold },

  reservesPanel: { backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.md, padding: SPACING.sm, marginBottom: SPACING.md, borderWidth: 1, borderColor: COLORS.border },
  reservesRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 2 },
  reservesLabel: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted },
  reservesValue: { fontSize: FONT_SIZES.xs, color: COLORS.text, flex: 1, marginRight: SPACING.sm },
  reservesRatio: { fontSize: FONT_SIZES.xs, color: COLORS.info, fontWeight: '600' },

  quoteText: { fontSize: FONT_SIZES.xs, color: COLORS.textSecondary, marginBottom: SPACING.sm, fontStyle: 'italic' },
  gasWarning: { flexDirection: 'row', alignItems: 'center', gap: SPACING.xs, backgroundColor: COLORS.warning + '12', borderRadius: BORDER_RADIUS.md, padding: SPACING.sm, marginBottom: SPACING.md, borderWidth: 1, borderColor: COLORS.warning + '30' },
  gasWarningText: { fontSize: FONT_SIZES.xs, color: COLORS.warning, flex: 1 },

  modalOverlay: { flex: 1, backgroundColor: COLORS.overlay },
  modalContent: { width: '100%', backgroundColor: COLORS.backgroundCard, borderRadius: BORDER_RADIUS.xl, padding: SPACING.lg, borderWidth: 1, borderColor: COLORS.gold + '30' },
  modalTitle: { fontSize: FONT_SIZES.xxl, fontWeight: '700', color: COLORS.text, marginBottom: SPACING.xs },
  modalSubtitle: { fontSize: FONT_SIZES.sm, color: COLORS.textSecondary, marginBottom: SPACING.lg },
  inputLabel: { fontSize: FONT_SIZES.sm, fontWeight: '600', color: COLORS.textSecondary, marginBottom: SPACING.xs },
  input: { backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.lg, borderWidth: 1, borderColor: COLORS.border, padding: SPACING.md, fontSize: FONT_SIZES.lg, color: COLORS.text, marginBottom: SPACING.md },
  modalActions: { flexDirection: 'row', gap: SPACING.md, marginTop: SPACING.md },
  modalCancelBtn: { flex: 1, paddingVertical: SPACING.md, borderRadius: BORDER_RADIUS.lg, borderWidth: 1, borderColor: COLORS.border, alignItems: 'center', justifyContent: 'center' },
  modalCancelText: { fontSize: FONT_SIZES.md, fontWeight: '600', color: COLORS.textSecondary },
  modalConfirmBtn: { flex: 1.5, borderRadius: BORDER_RADIUS.lg, overflow: 'hidden' },
  modalConfirmGradient: { paddingVertical: SPACING.md, alignItems: 'center', justifyContent: 'center' },
  modalConfirmText: { fontSize: FONT_SIZES.md, fontWeight: '700', color: COLORS.background },
});
