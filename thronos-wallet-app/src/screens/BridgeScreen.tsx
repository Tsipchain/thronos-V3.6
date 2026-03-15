import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  Alert,
  ActivityIndicator,
  ScrollView,
  Animated,
  Modal,
  FlatList,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT_SIZES, BORDER_RADIUS } from '../constants/theme';
import { useStore } from '../store/useStore';
import {
  getTokenBalances,
  getBridgeQuote,
  executeBridge as executeBridgeAPI,
  getBridgeHistory,
} from '../services/api';
import { getWallet } from '../services/wallet';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ChainId = 'thronos' | 'bitcoin' | 'ethereum';

interface Chain {
  id: ChainId;
  name: string;
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
}

interface BridgeToken {
  symbol: string;
  name: string;
  icon: keyof typeof Ionicons.glyphMap;
  decimals: number;
}

type BridgeStatus = 'pending' | 'confirming' | 'completed' | 'failed';

interface BridgeTransfer {
  id: string;
  fromChain: ChainId;
  toChain: ChainId;
  token: string;
  amount: number;
  fee: number;
  status: BridgeStatus;
  txHash: string;
  timestamp: number;
  estimatedTime: number; // seconds
}

interface BridgePair {
  from: string;
  to: string;
  fee: number; // percentage
  estimatedMinutes: number;
  available: boolean;
}

// ---------------------------------------------------------------------------
// Static data
// ---------------------------------------------------------------------------

const CHAINS: Chain[] = [
  { id: 'thronos', name: 'Thronos', icon: 'diamond-outline', color: COLORS.gold },
  { id: 'bitcoin', name: 'Bitcoin', icon: 'logo-bitcoin', color: '#F7931A' },
  { id: 'ethereum', name: 'Ethereum', icon: 'logo-web-component', color: '#627EEA' },
];

const BRIDGE_TOKENS: Record<ChainId, BridgeToken[]> = {
  thronos: [
    { symbol: 'THR', name: 'Thronos', icon: 'diamond-outline', decimals: 8 },
    { symbol: 'WBTC', name: 'Wrapped Bitcoin', icon: 'logo-bitcoin', decimals: 8 },
  ],
  bitcoin: [
    { symbol: 'BTC', name: 'Bitcoin', icon: 'logo-bitcoin', decimals: 8 },
    { symbol: 'WBTC', name: 'Wrapped Bitcoin', icon: 'logo-bitcoin', decimals: 8 },
  ],
  ethereum: [
    { symbol: 'ETH', name: 'Ethereum', icon: 'logo-web-component', decimals: 18 },
  ],
};

const BRIDGE_PAIRS: BridgePair[] = [
  { from: 'THR', to: 'WBTC', fee: 0.1, estimatedMinutes: 5, available: true },
  { from: 'WBTC', to: 'THR', fee: 0.1, estimatedMinutes: 5, available: true },
  { from: 'WBTC', to: 'BTC', fee: 0.15, estimatedMinutes: 15, available: true },
  { from: 'BTC', to: 'WBTC', fee: 0.15, estimatedMinutes: 15, available: true },
  { from: 'THR', to: 'ETH', fee: 0.2, estimatedMinutes: 10, available: false },
  { from: 'ETH', to: 'THR', fee: 0.2, estimatedMinutes: 10, available: false },
];

// No mock data — all balances and transfers fetched from chain API

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getChain(id: ChainId): Chain {
  return CHAINS.find((c) => c.id === id)!;
}

function findBridgePair(fromToken: string, toToken: string): BridgePair | undefined {
  return BRIDGE_PAIRS.find((p) => p.from === fromToken && p.to === toToken);
}

function formatTime(minutes: number): string {
  if (minutes < 1) return '< 1 min';
  if (minutes === 1) return '1 min';
  return `~${minutes} min`;
}

function statusColor(status: BridgeStatus): string {
  switch (status) {
    case 'completed':
      return COLORS.success;
    case 'confirming':
      return COLORS.warning;
    case 'pending':
      return COLORS.info;
    case 'failed':
      return COLORS.error;
  }
}

function statusLabel(status: BridgeStatus): string {
  switch (status) {
    case 'completed':
      return 'Completed';
    case 'confirming':
      return 'Confirming';
    case 'pending':
      return 'Pending';
    case 'failed':
      return 'Failed';
  }
}

function timeAgo(timestamp: number): string {
  const diff = Date.now() - timestamp;
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return 'Just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function BridgeScreen({ navigation }: { navigation: any }) {
  const { wallet, tokens, bridgeHistory, setBridgeHistory } = useStore();

  // State
  const [sourceChain, setSourceChain] = useState<ChainId>('thronos');
  const [destChain, setDestChain] = useState<ChainId>('bitcoin');
  const [selectedToken, setSelectedToken] = useState<string>('WBTC');
  const [amount, setAmount] = useState('');
  const [loading, setLoading] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [showTokenPicker, setShowTokenPicker] = useState(false);
  const [balances, setBalances] = useState<Record<string, number>>({});

  // Animated rotation for the swap button
  const rotateAnim = useRef(new Animated.Value(0)).current;

  // Load real balances and bridge history from chain
  useEffect(() => {
    async function loadData() {
      if (!wallet.address) return;
      try {
        const [balRes, histRes] = await Promise.allSettled([
          getTokenBalances(wallet.address),
          getBridgeHistory(wallet.address),
        ]);
        if (balRes.status === 'fulfilled' && balRes.value?.tokens) {
          const bals: Record<string, number> = {};
          for (const t of balRes.value.tokens) {
            bals[t.symbol] = t.balance;
          }
          setBalances(bals);
        }
        if (histRes.status === 'fulfilled' && histRes.value?.transfers) {
          setBridgeHistory(histRes.value.transfers.map((t: any) => ({
            id: t.id,
            fromChain: t.from_chain || 'thronos',
            toChain: t.to_chain || 'bitcoin',
            token: t.from_token || t.token || 'THR',
            amount: t.amount,
            fee: t.fee || 0,
            status: t.status || 'pending',
            txHash: t.tx_hash || '',
            timestamp: new Date(t.created_at || Date.now()).getTime(),
            estimatedTime: 300,
          })));
        }
      } catch (err) {
        console.warn('Bridge: Failed to load data', err);
      }
    }
    loadData();
  }, [wallet.address]);

  // Derived
  const sourceChainData = getChain(sourceChain);
  const destChainData = getChain(destChain);

  const availableTokens = useMemo(
    () => BRIDGE_TOKENS[sourceChain] || [],
    [sourceChain],
  );

  const currentPair = useMemo(() => {
    // Determine destination token based on selected token & dest chain
    const destTokens = BRIDGE_TOKENS[destChain] || [];
    for (const dt of destTokens) {
      const pair = findBridgePair(selectedToken, dt.symbol);
      if (pair) return pair;
    }
    return undefined;
  }, [selectedToken, destChain]);

  const balance = balances[selectedToken] ?? tokens.find((t) => t.symbol === selectedToken)?.balance ?? 0;

  const parsedAmount = parseFloat(amount) || 0;
  const feeAmount = currentPair ? parsedAmount * (currentPair.fee / 100) : 0;
  const receiveAmount = parsedAmount - feeAmount;

  const canBridge =
    currentPair?.available &&
    parsedAmount > 0 &&
    parsedAmount <= balance &&
    receiveAmount > 0;

  // Handlers ------------------------------------------------------------------

  const handleSwapDirection = useCallback(() => {
    Animated.timing(rotateAnim, {
      toValue: 1,
      duration: 300,
      useNativeDriver: true,
    }).start(() => {
      rotateAnim.setValue(0);
    });

    const newSource = destChain;
    const newDest = sourceChain;
    setSourceChain(newSource);
    setDestChain(newDest);

    // Pick a sensible default token for the new source chain
    const newTokens = BRIDGE_TOKENS[newSource] || [];
    if (newTokens.length > 0) {
      // Try to keep current token if available on new source chain
      const kept = newTokens.find((t) => t.symbol === selectedToken);
      setSelectedToken(kept ? kept.symbol : newTokens[0].symbol);
    }
  }, [sourceChain, destChain, selectedToken, rotateAnim]);

  const handleSelectSource = useCallback(
    (chain: ChainId) => {
      if (chain === destChain) {
        // Swap them
        setDestChain(sourceChain);
      }
      setSourceChain(chain);
      const tokens = BRIDGE_TOKENS[chain] || [];
      if (tokens.length > 0) {
        const kept = tokens.find((t) => t.symbol === selectedToken);
        setSelectedToken(kept ? kept.symbol : tokens[0].symbol);
      }
    },
    [destChain, sourceChain, selectedToken],
  );

  const handleSelectDest = useCallback(
    (chain: ChainId) => {
      if (chain === sourceChain) {
        setSourceChain(destChain);
      }
      setDestChain(chain);
    },
    [sourceChain, destChain],
  );

  const handleMax = useCallback(() => {
    setAmount(balance.toString());
  }, [balance]);

  const handleBridgePress = useCallback(() => {
    if (!canBridge) return;
    setShowConfirm(true);
  }, [canBridge]);

  const handleConfirmBridge = useCallback(async () => {
    setShowConfirm(false);
    setLoading(true);
    try {
      const creds = await getWallet();
      if (!creds) {
        Alert.alert('Error', 'Wallet credentials not found.');
        return;
      }

      const result = await executeBridgeAPI({
        from_chain: sourceChain,
        to_chain: destChain,
        token: selectedToken,
        amount: parsedAmount,
        from_address: creds.address,
        to_address: wallet.chainAddresses?.[destChain] || creds.address,
        secret: creds.secret,
      });

      if (result.success && result.transfer) {
        const newTransfer: BridgeTransfer = {
          id: result.transfer.id || `br_${Date.now()}`,
          fromChain: sourceChain,
          toChain: destChain,
          token: selectedToken,
          amount: parsedAmount,
          fee: feeAmount,
          status: 'pending',
          txHash: result.transfer.tx_hash || '',
          timestamp: Date.now(),
          estimatedTime: (currentPair?.estimatedMinutes ?? 5) * 60,
        };

        setBridgeHistory([newTransfer, ...(bridgeHistory || [])]);

        Alert.alert(
          'Bridge Initiated',
          `Bridging ${parsedAmount} ${selectedToken} from ${sourceChainData.name} to ${destChainData.name}.\n\nEstimated time: ${formatTime(currentPair?.estimatedMinutes ?? 5)}`,
          [{ text: 'OK' }],
        );
        setAmount('');
      } else {
        Alert.alert('Bridge Failed', result.error || 'Bridge operation failed.');
      }
    } catch (error: any) {
      Alert.alert('Bridge Failed', error.message || 'An unexpected error occurred.');
    } finally {
      setLoading(false);
    }
  }, [
    sourceChain,
    destChain,
    selectedToken,
    parsedAmount,
    feeAmount,
    currentPair,
    sourceChainData,
    destChainData,
    wallet,
    bridgeHistory,
    setBridgeHistory,
  ]);

  // Animated rotation value
  const spin = rotateAnim.interpolate({
    inputRange: [0, 1],
    outputRange: ['0deg', '180deg'],
  });

  // Render helpers ------------------------------------------------------------

  const transfers: BridgeTransfer[] =
    bridgeHistory && bridgeHistory.length > 0
      ? (bridgeHistory as BridgeTransfer[])
      : [];

  const renderChainChip = (
    chain: Chain,
    isSelected: boolean,
    onPress: () => void,
  ) => (
    <TouchableOpacity
      key={chain.id}
      style={[
        styles.chainChip,
        isSelected && { borderColor: chain.color, backgroundColor: chain.color + '18' },
      ]}
      onPress={onPress}
      activeOpacity={0.7}
    >
      <Ionicons
        name={chain.icon}
        size={16}
        color={isSelected ? chain.color : COLORS.textSecondary}
      />
      <Text
        style={[
          styles.chainChipText,
          isSelected && { color: chain.color },
        ]}
      >
        {chain.name}
      </Text>
    </TouchableOpacity>
  );

  const renderTransferItem = ({ item }: { item: BridgeTransfer }) => {
    const from = getChain(item.fromChain);
    const to = getChain(item.toChain);
    const color = statusColor(item.status);
    return (
      <View style={styles.transferCard}>
        <View style={styles.transferRow}>
          <View style={styles.transferChains}>
            <View style={[styles.transferChainDot, { backgroundColor: from.color }]} />
            <Text style={styles.transferChainLabel}>{from.name}</Text>
            <Ionicons name="arrow-forward" size={14} color={COLORS.textMuted} style={{ marginHorizontal: 4 }} />
            <View style={[styles.transferChainDot, { backgroundColor: to.color }]} />
            <Text style={styles.transferChainLabel}>{to.name}</Text>
          </View>
          <Text style={styles.transferTime}>{timeAgo(item.timestamp)}</Text>
        </View>
        <View style={styles.transferRow}>
          <Text style={styles.transferAmount}>
            {item.amount} {item.token}
          </Text>
          <View style={[styles.statusBadge, { backgroundColor: color + '20' }]}>
            <View style={[styles.statusDot, { backgroundColor: color }]} />
            <Text style={[styles.statusText, { color }]}>{statusLabel(item.status)}</Text>
          </View>
        </View>
        <Text style={styles.transferHash}>TX: {item.txHash}</Text>
      </View>
    );
  };

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <SafeAreaView style={styles.container}>
      <LinearGradient colors={[COLORS.background, COLORS.backgroundLight]} style={styles.gradient}>
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
            <Ionicons name="arrow-back" size={24} color={COLORS.text} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Bridge</Text>
          <TouchableOpacity hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
            <Ionicons name="information-circle-outline" size={24} color={COLORS.textSecondary} />
          </TouchableOpacity>
        </View>

        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          showsVerticalScrollIndicator={false}
          keyboardShouldPersistTaps="handled"
        >
          {/* Source Chain */}
          <Text style={styles.sectionLabel}>Source Chain</Text>
          <View style={styles.chipRow}>
            {CHAINS.map((c) =>
              renderChainChip(c, c.id === sourceChain, () => handleSelectSource(c.id)),
            )}
          </View>

          {/* Swap Direction Button */}
          <View style={styles.swapBtnContainer}>
            <TouchableOpacity onPress={handleSwapDirection} activeOpacity={0.7}>
              <Animated.View style={[styles.swapBtn, { transform: [{ rotate: spin }] }]}>
                <LinearGradient
                  colors={[COLORS.gold, COLORS.goldDark]}
                  style={styles.swapBtnGradient}
                >
                  <Ionicons name="swap-vertical" size={22} color={COLORS.background} />
                </LinearGradient>
              </Animated.View>
            </TouchableOpacity>
          </View>

          {/* Destination Chain */}
          <Text style={styles.sectionLabel}>Destination Chain</Text>
          <View style={styles.chipRow}>
            {CHAINS.filter((c) => c.id !== sourceChain).map((c) =>
              renderChainChip(c, c.id === destChain, () => handleSelectDest(c.id)),
            )}
          </View>

          {/* Token Selector */}
          <Text style={styles.sectionLabel}>Token</Text>
          <TouchableOpacity
            style={styles.tokenSelector}
            onPress={() => setShowTokenPicker(true)}
            activeOpacity={0.7}
          >
            <View style={styles.tokenSelectorLeft}>
              <Ionicons
                name={availableTokens.find((t) => t.symbol === selectedToken)?.icon ?? 'ellipse-outline'}
                size={24}
                color={COLORS.gold}
              />
              <View style={{ marginLeft: SPACING.sm }}>
                <Text style={styles.tokenSymbol}>{selectedToken}</Text>
                <Text style={styles.tokenName}>
                  {availableTokens.find((t) => t.symbol === selectedToken)?.name ?? selectedToken}
                </Text>
              </View>
            </View>
            <Ionicons name="chevron-down" size={20} color={COLORS.textSecondary} />
          </TouchableOpacity>

          {/* Amount Input */}
          <Text style={styles.sectionLabel}>Amount</Text>
          <View style={styles.amountContainer}>
            <TextInput
              style={styles.amountInput}
              placeholder="0.00"
              placeholderTextColor={COLORS.textMuted}
              value={amount}
              onChangeText={setAmount}
              keyboardType="decimal-pad"
              returnKeyType="done"
            />
            <TouchableOpacity style={styles.maxButton} onPress={handleMax} activeOpacity={0.7}>
              <Text style={styles.maxButtonText}>MAX</Text>
            </TouchableOpacity>
          </View>
          <View style={styles.balanceRow}>
            <Text style={styles.balanceLabel}>Available</Text>
            <Text style={styles.balanceValue}>
              {balance.toLocaleString(undefined, { maximumFractionDigits: 8 })} {selectedToken}
            </Text>
          </View>

          {/* Bridge Fee & Estimate */}
          {currentPair && parsedAmount > 0 && (
            <View style={styles.feeCard}>
              <View style={styles.feeRow}>
                <Text style={styles.feeLabel}>Bridge Fee ({currentPair.fee}%)</Text>
                <Text style={styles.feeValue}>
                  {feeAmount.toLocaleString(undefined, { maximumFractionDigits: 8 })} {selectedToken}
                </Text>
              </View>
              <View style={styles.feeRow}>
                <Text style={styles.feeLabel}>You Receive</Text>
                <Text style={[styles.feeValue, { color: COLORS.gold }]}>
                  {receiveAmount > 0
                    ? receiveAmount.toLocaleString(undefined, { maximumFractionDigits: 8 })
                    : '0'}{' '}
                  {selectedToken}
                </Text>
              </View>
              <View style={styles.feeDivider} />
              <View style={styles.feeRow}>
                <View style={styles.feeTimeRow}>
                  <Ionicons name="time-outline" size={14} color={COLORS.textSecondary} />
                  <Text style={[styles.feeLabel, { marginLeft: 4 }]}>Estimated Time</Text>
                </View>
                <Text style={styles.feeValue}>{formatTime(currentPair.estimatedMinutes)}</Text>
              </View>
              {!currentPair.available && (
                <View style={styles.comingSoonBadge}>
                  <Ionicons name="lock-closed-outline" size={12} color={COLORS.warning} />
                  <Text style={styles.comingSoonText}>Coming Soon</Text>
                </View>
              )}
            </View>
          )}

          {/* Bridge Button */}
          <TouchableOpacity
            style={[styles.bridgeBtn, !canBridge && styles.bridgeBtnDisabled]}
            onPress={handleBridgePress}
            disabled={!canBridge || loading}
            activeOpacity={0.8}
          >
            <LinearGradient
              colors={canBridge ? [COLORS.gold, COLORS.goldDark] : [COLORS.surfaceLight, COLORS.surface]}
              style={styles.bridgeBtnGradient}
            >
              {loading ? (
                <ActivityIndicator color={canBridge ? COLORS.background : COLORS.textMuted} />
              ) : (
                <>
                  <Ionicons
                    name="git-compare-outline"
                    size={20}
                    color={canBridge ? COLORS.background : COLORS.textMuted}
                    style={{ marginRight: SPACING.sm }}
                  />
                  <Text
                    style={[
                      styles.bridgeBtnText,
                      !canBridge && { color: COLORS.textMuted },
                    ]}
                  >
                    {currentPair && !currentPair.available
                      ? 'Bridge Unavailable'
                      : parsedAmount > balance
                        ? 'Insufficient Balance'
                        : 'Bridge Tokens'}
                  </Text>
                </>
              )}
            </LinearGradient>
          </TouchableOpacity>

          {/* Recent Bridge Transfers */}
          <View style={styles.recentHeader}>
            <Text style={styles.recentTitle}>Recent Transfers</Text>
            <TouchableOpacity activeOpacity={0.7}>
              <Text style={styles.viewAllText}>View All</Text>
            </TouchableOpacity>
          </View>

          {transfers.map((item) => (
            <React.Fragment key={item.id}>{renderTransferItem({ item })}</React.Fragment>
          ))}

          <View style={{ height: SPACING.xxl }} />
        </ScrollView>
      </LinearGradient>

      {/* Confirmation Modal */}
      <Modal visible={showConfirm} transparent animationType="fade">
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <View style={styles.modalIconWrapper}>
              <LinearGradient colors={[COLORS.gold, COLORS.goldDark]} style={styles.modalIcon}>
                <Ionicons name="git-compare-outline" size={32} color={COLORS.background} />
              </LinearGradient>
            </View>

            <Text style={styles.modalTitle}>Confirm Bridge</Text>
            <Text style={styles.modalSubtitle}>
              You are about to bridge tokens across chains. This action cannot be reversed.
            </Text>

            <View style={styles.modalDetailBox}>
              <View style={styles.modalDetailRow}>
                <Text style={styles.modalDetailLabel}>From</Text>
                <Text style={styles.modalDetailValue}>{sourceChainData.name}</Text>
              </View>
              <View style={styles.modalDetailRow}>
                <Text style={styles.modalDetailLabel}>To</Text>
                <Text style={styles.modalDetailValue}>{destChainData.name}</Text>
              </View>
              <View style={styles.modalDetailRow}>
                <Text style={styles.modalDetailLabel}>Amount</Text>
                <Text style={styles.modalDetailValue}>
                  {parsedAmount} {selectedToken}
                </Text>
              </View>
              <View style={styles.modalDetailRow}>
                <Text style={styles.modalDetailLabel}>Fee</Text>
                <Text style={styles.modalDetailValue}>
                  {feeAmount.toLocaleString(undefined, { maximumFractionDigits: 8 })} {selectedToken}
                </Text>
              </View>
              <View style={styles.modalDetailRow}>
                <Text style={styles.modalDetailLabel}>You Receive</Text>
                <Text style={[styles.modalDetailValue, { color: COLORS.gold }]}>
                  {receiveAmount.toLocaleString(undefined, { maximumFractionDigits: 8 })} {selectedToken}
                </Text>
              </View>
              <View style={styles.modalDetailRow}>
                <Text style={styles.modalDetailLabel}>Est. Time</Text>
                <Text style={styles.modalDetailValue}>
                  {formatTime(currentPair?.estimatedMinutes ?? 5)}
                </Text>
              </View>
            </View>

            <View style={styles.modalActions}>
              <TouchableOpacity
                style={styles.modalCancelBtn}
                onPress={() => setShowConfirm(false)}
                activeOpacity={0.7}
              >
                <Text style={styles.modalCancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.modalConfirmBtn}
                onPress={handleConfirmBridge}
                activeOpacity={0.8}
              >
                <LinearGradient
                  colors={[COLORS.gold, COLORS.goldDark]}
                  style={styles.modalConfirmGradient}
                >
                  <Text style={styles.modalConfirmText}>Confirm Bridge</Text>
                </LinearGradient>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* Token Picker Modal */}
      <Modal visible={showTokenPicker} transparent animationType="slide">
        <View style={styles.modalOverlay}>
          <View style={styles.pickerContent}>
            <View style={styles.pickerHeader}>
              <Text style={styles.pickerTitle}>Select Token</Text>
              <TouchableOpacity onPress={() => setShowTokenPicker(false)}>
                <Ionicons name="close" size={24} color={COLORS.text} />
              </TouchableOpacity>
            </View>
            {availableTokens.map((token) => {
              const isSelected = token.symbol === selectedToken;
              return (
                <TouchableOpacity
                  key={token.symbol}
                  style={[styles.pickerItem, isSelected && styles.pickerItemActive]}
                  onPress={() => {
                    setSelectedToken(token.symbol);
                    setShowTokenPicker(false);
                  }}
                  activeOpacity={0.7}
                >
                  <Ionicons
                    name={token.icon}
                    size={28}
                    color={isSelected ? COLORS.gold : COLORS.textSecondary}
                  />
                  <View style={{ marginLeft: SPACING.md, flex: 1 }}>
                    <Text style={[styles.pickerSymbol, isSelected && { color: COLORS.gold }]}>
                      {token.symbol}
                    </Text>
                    <Text style={styles.pickerName}>{token.name}</Text>
                  </View>
                  <View style={{ alignItems: 'flex-end' }}>
                    <Text style={styles.pickerBalance}>
                      {(balances[token.symbol] ?? tokens.find((t) => t.symbol === token.symbol)?.balance ?? 0).toLocaleString(undefined, {
                        maximumFractionDigits: 8,
                      })}
                    </Text>
                    <Text style={styles.pickerBalanceLabel}>Available</Text>
                  </View>
                  {isSelected && (
                    <Ionicons
                      name="checkmark-circle"
                      size={20}
                      color={COLORS.gold}
                      style={{ marginLeft: SPACING.sm }}
                    />
                  )}
                </TouchableOpacity>
              );
            })}
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  // Layout
  container: { flex: 1, backgroundColor: COLORS.background },
  gradient: { flex: 1 },
  scroll: { flex: 1 },
  scrollContent: { paddingHorizontal: SPACING.lg, paddingBottom: SPACING.xxl },

  // Header
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: SPACING.lg,
    paddingVertical: SPACING.md,
  },
  headerTitle: {
    fontSize: FONT_SIZES.xl,
    fontWeight: '700',
    color: COLORS.text,
    letterSpacing: 0.3,
  },

  // Section
  sectionLabel: {
    fontSize: FONT_SIZES.sm,
    fontWeight: '600',
    color: COLORS.textSecondary,
    marginTop: SPACING.lg,
    marginBottom: SPACING.sm,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },

  // Chain chips
  chipRow: { flexDirection: 'row', gap: SPACING.sm, flexWrap: 'wrap' },
  chainChip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: SPACING.md,
    paddingVertical: SPACING.sm + 2,
    borderRadius: BORDER_RADIUS.full,
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.surface,
    gap: SPACING.xs + 2,
  },
  chainChipText: {
    fontSize: FONT_SIZES.sm,
    fontWeight: '600',
    color: COLORS.textSecondary,
  },

  // Swap button
  swapBtnContainer: {
    alignItems: 'center',
    marginVertical: SPACING.sm,
  },
  swapBtn: {
    width: 44,
    height: 44,
    borderRadius: 22,
    overflow: 'hidden',
    elevation: 6,
    shadowColor: COLORS.gold,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.35,
    shadowRadius: 6,
  },
  swapBtnGradient: {
    width: 44,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
  },

  // Token selector
  tokenSelector: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: COLORS.surface,
    borderRadius: BORDER_RADIUS.lg,
    padding: SPACING.md,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  tokenSelectorLeft: { flexDirection: 'row', alignItems: 'center' },
  tokenSymbol: { fontSize: FONT_SIZES.lg, fontWeight: '700', color: COLORS.text },
  tokenName: { fontSize: FONT_SIZES.xs, color: COLORS.textSecondary, marginTop: 1 },

  // Amount input
  amountContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.surface,
    borderRadius: BORDER_RADIUS.lg,
    borderWidth: 1,
    borderColor: COLORS.border,
    overflow: 'hidden',
  },
  amountInput: {
    flex: 1,
    fontSize: FONT_SIZES.xxl,
    fontWeight: '700',
    color: COLORS.text,
    paddingHorizontal: SPACING.md,
    paddingVertical: SPACING.md,
  },
  maxButton: {
    backgroundColor: COLORS.gold + '20',
    paddingHorizontal: SPACING.md,
    paddingVertical: SPACING.sm,
    borderRadius: BORDER_RADIUS.md,
    marginRight: SPACING.sm,
  },
  maxButtonText: {
    fontSize: FONT_SIZES.xs,
    fontWeight: '800',
    color: COLORS.gold,
    letterSpacing: 1,
  },

  // Balance
  balanceRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: SPACING.xs,
    paddingHorizontal: SPACING.xs,
  },
  balanceLabel: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted },
  balanceValue: { fontSize: FONT_SIZES.xs, color: COLORS.textSecondary, fontWeight: '600' },

  // Fee card
  feeCard: {
    backgroundColor: COLORS.backgroundCard,
    borderRadius: BORDER_RADIUS.lg,
    padding: SPACING.md,
    marginTop: SPACING.lg,
    borderWidth: 1,
    borderColor: COLORS.gold + '25',
  },
  feeRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: SPACING.sm,
  },
  feeTimeRow: { flexDirection: 'row', alignItems: 'center' },
  feeLabel: { fontSize: FONT_SIZES.sm, color: COLORS.textSecondary },
  feeValue: { fontSize: FONT_SIZES.sm, fontWeight: '600', color: COLORS.text },
  feeDivider: {
    height: 1,
    backgroundColor: COLORS.border,
    marginVertical: SPACING.sm,
  },
  comingSoonBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    backgroundColor: COLORS.warning + '15',
    paddingHorizontal: SPACING.sm,
    paddingVertical: SPACING.xs,
    borderRadius: BORDER_RADIUS.full,
    gap: SPACING.xs,
    marginTop: SPACING.xs,
  },
  comingSoonText: {
    fontSize: FONT_SIZES.xs,
    fontWeight: '600',
    color: COLORS.warning,
  },

  // Bridge button
  bridgeBtn: {
    borderRadius: BORDER_RADIUS.lg,
    overflow: 'hidden',
    marginTop: SPACING.xl,
    elevation: 4,
    shadowColor: COLORS.gold,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
  },
  bridgeBtnDisabled: {
    elevation: 0,
    shadowOpacity: 0,
  },
  bridgeBtnGradient: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: SPACING.md + 2,
  },
  bridgeBtnText: {
    fontSize: FONT_SIZES.lg,
    fontWeight: '700',
    color: COLORS.background,
  },

  // Recent transfers
  recentHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: SPACING.xl,
    marginBottom: SPACING.md,
  },
  recentTitle: {
    fontSize: FONT_SIZES.lg,
    fontWeight: '700',
    color: COLORS.text,
  },
  viewAllText: {
    fontSize: FONT_SIZES.sm,
    fontWeight: '600',
    color: COLORS.gold,
  },

  // Transfer card
  transferCard: {
    backgroundColor: COLORS.backgroundCard,
    borderRadius: BORDER_RADIUS.lg,
    padding: SPACING.md,
    marginBottom: SPACING.sm,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  transferRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: SPACING.xs,
  },
  transferChains: { flexDirection: 'row', alignItems: 'center' },
  transferChainDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 4,
  },
  transferChainLabel: {
    fontSize: FONT_SIZES.sm,
    color: COLORS.textSecondary,
    fontWeight: '500',
  },
  transferTime: {
    fontSize: FONT_SIZES.xs,
    color: COLORS.textMuted,
  },
  transferAmount: {
    fontSize: FONT_SIZES.md,
    fontWeight: '700',
    color: COLORS.text,
  },
  statusBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: SPACING.sm,
    paddingVertical: SPACING.xs,
    borderRadius: BORDER_RADIUS.full,
    gap: SPACING.xs,
  },
  statusDot: { width: 6, height: 6, borderRadius: 3 },
  statusText: { fontSize: FONT_SIZES.xs, fontWeight: '600' },
  transferHash: {
    fontSize: FONT_SIZES.xs,
    color: COLORS.textMuted,
    fontFamily: 'monospace',
    marginTop: 2,
  },

  // Confirmation Modal
  modalOverlay: {
    flex: 1,
    backgroundColor: COLORS.overlay,
    justifyContent: 'center',
    alignItems: 'center',
    padding: SPACING.lg,
  },
  modalContent: {
    width: '100%',
    backgroundColor: COLORS.backgroundCard,
    borderRadius: BORDER_RADIUS.xl,
    padding: SPACING.lg,
    borderWidth: 1,
    borderColor: COLORS.gold + '30',
  },
  modalIconWrapper: { alignItems: 'center', marginBottom: SPACING.md },
  modalIcon: {
    width: 64,
    height: 64,
    borderRadius: 32,
    alignItems: 'center',
    justifyContent: 'center',
  },
  modalTitle: {
    fontSize: FONT_SIZES.xxl,
    fontWeight: '700',
    color: COLORS.text,
    textAlign: 'center',
    marginBottom: SPACING.xs,
  },
  modalSubtitle: {
    fontSize: FONT_SIZES.sm,
    color: COLORS.textSecondary,
    textAlign: 'center',
    marginBottom: SPACING.lg,
    lineHeight: 20,
  },
  modalDetailBox: {
    backgroundColor: COLORS.surface,
    borderRadius: BORDER_RADIUS.lg,
    padding: SPACING.md,
    marginBottom: SPACING.lg,
  },
  modalDetailRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: SPACING.sm,
  },
  modalDetailLabel: { fontSize: FONT_SIZES.sm, color: COLORS.textSecondary },
  modalDetailValue: { fontSize: FONT_SIZES.sm, fontWeight: '600', color: COLORS.text },
  modalActions: { flexDirection: 'row', gap: SPACING.md },
  modalCancelBtn: {
    flex: 1,
    paddingVertical: SPACING.md,
    borderRadius: BORDER_RADIUS.lg,
    borderWidth: 1,
    borderColor: COLORS.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  modalCancelText: { fontSize: FONT_SIZES.md, fontWeight: '600', color: COLORS.textSecondary },
  modalConfirmBtn: {
    flex: 1.5,
    borderRadius: BORDER_RADIUS.lg,
    overflow: 'hidden',
  },
  modalConfirmGradient: {
    paddingVertical: SPACING.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  modalConfirmText: { fontSize: FONT_SIZES.md, fontWeight: '700', color: COLORS.background },

  // Token picker modal
  pickerContent: {
    width: '100%',
    backgroundColor: COLORS.backgroundCard,
    borderRadius: BORDER_RADIUS.xl,
    padding: SPACING.lg,
    borderWidth: 1,
    borderColor: COLORS.border,
    maxHeight: '70%',
  },
  pickerHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: SPACING.lg,
  },
  pickerTitle: { fontSize: FONT_SIZES.xl, fontWeight: '700', color: COLORS.text },
  pickerItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: SPACING.md,
    paddingHorizontal: SPACING.sm,
    borderRadius: BORDER_RADIUS.lg,
    marginBottom: SPACING.xs,
  },
  pickerItemActive: {
    backgroundColor: COLORS.gold + '10',
    borderWidth: 1,
    borderColor: COLORS.gold + '30',
  },
  pickerSymbol: { fontSize: FONT_SIZES.lg, fontWeight: '700', color: COLORS.text },
  pickerName: { fontSize: FONT_SIZES.xs, color: COLORS.textSecondary, marginTop: 1 },
  pickerBalance: { fontSize: FONT_SIZES.sm, fontWeight: '600', color: COLORS.text },
  pickerBalanceLabel: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, marginTop: 1 },
});
