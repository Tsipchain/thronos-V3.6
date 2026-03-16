import React, { useState } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, TextInput, Alert, ActivityIndicator,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT_SIZES, BORDER_RADIUS } from '../constants/theme';
import { useStore } from '../store/useStore';
import { getSwapQuote, executeSwap } from '../services/api';
import { getWallet } from '../services/wallet';

export default function SwapScreen() {
  const navigation = useNavigation();
  const { tokens } = useStore();
  const [fromToken, setFromToken] = useState('THR');
  const [toToken, setToToken] = useState('WBTC');
  const [amount, setAmount] = useState('');
  const [quote, setQuote] = useState<{ rate: number; amount_out: number; fee: number } | null>(null);
  const [loading, setLoading] = useState(false);

  const availableTokens = tokens.filter((t) => t.balance > 0).map((t) => t.symbol);
  if (!availableTokens.includes('THR')) availableTokens.unshift('THR');

  const handleGetQuote = async () => {
    const amt = parseFloat(amount);
    if (!amt || amt <= 0) { Alert.alert('Error', 'Enter a valid amount.'); return; }
    setLoading(true);
    try {
      const q = await getSwapQuote(fromToken, toToken, amt);
      setQuote(q);
    } catch (error: any) {
      Alert.alert('Error', error.message || 'Failed to get quote.');
    } finally {
      setLoading(false);
    }
  };

  const handleSwap = async () => {
    if (!quote) return;
    const creds = await getWallet();
    if (!creds) { Alert.alert('Error', 'Wallet not found.'); return; }

    setLoading(true);
    try {
      const result = await executeSwap({
        from_token: fromToken, to_token: toToken,
        amount: parseFloat(amount), address: creds.address, secret: creds.secret,
      });
      if (result.success) {
        Alert.alert('Success', `Swapped ${amount} ${fromToken} to ${toToken}!`, [
          { text: 'OK', onPress: () => navigation.goBack() },
        ]);
      } else {
        Alert.alert('Failed', 'Swap failed.');
      }
    } catch (error: any) {
      Alert.alert('Error', error.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <LinearGradient colors={[COLORS.background, COLORS.backgroundLight]} style={styles.gradient}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()}>
            <Ionicons name="arrow-back" size={24} color={COLORS.text} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Swap</Text>
          <View style={{ width: 24 }} />
        </View>

        <View style={styles.content}>
          <Text style={styles.label}>From</Text>
          <View style={styles.tokenRow}>
            {availableTokens.slice(0, 4).map((sym) => (
              <TouchableOpacity key={sym} style={[styles.chip, fromToken === sym && styles.chipActive]} onPress={() => setFromToken(sym)}>
                <Text style={[styles.chipText, fromToken === sym && styles.chipTextActive]}>{sym}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <TextInput
            style={styles.input}
            placeholder="Amount"
            placeholderTextColor={COLORS.textMuted}
            value={amount}
            onChangeText={setAmount}
            keyboardType="decimal-pad"
          />

          <View style={styles.swapIcon}>
            <Ionicons name="swap-vertical" size={28} color={COLORS.gold} />
          </View>

          <Text style={styles.label}>To</Text>
          <View style={styles.tokenRow}>
            {['THR', 'WBTC', 'L2E', 'USDT'].filter((s) => s !== fromToken).map((sym) => (
              <TouchableOpacity key={sym} style={[styles.chip, toToken === sym && styles.chipActive]} onPress={() => setToToken(sym)}>
                <Text style={[styles.chipText, toToken === sym && styles.chipTextActive]}>{sym}</Text>
              </TouchableOpacity>
            ))}
          </View>

          {quote && (
            <View style={styles.quoteBox}>
              <Text style={styles.quoteText}>Rate: 1 {fromToken} = {(quote.rate ?? 0).toFixed(6)} {toToken}</Text>
              <Text style={styles.quoteText}>You receive: {(quote.amount_out ?? 0).toFixed(6)} {toToken}</Text>
              <Text style={styles.quoteText}>Fee: {quote.fee ?? 0} THR</Text>
            </View>
          )}

          <TouchableOpacity style={styles.actionBtn} onPress={quote ? handleSwap : handleGetQuote} disabled={loading}>
            <LinearGradient colors={[COLORS.gold, COLORS.goldDark]} style={styles.btnGradient}>
              {loading ? <ActivityIndicator color={COLORS.background} /> : (
                <Text style={styles.btnText}>{quote ? 'Confirm Swap' : 'Get Quote'}</Text>
              )}
            </LinearGradient>
          </TouchableOpacity>
        </View>
      </LinearGradient>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.background },
  gradient: { flex: 1 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.lg, paddingVertical: SPACING.md },
  headerTitle: { fontSize: FONT_SIZES.xl, fontWeight: '600', color: COLORS.text },
  content: { flex: 1, paddingHorizontal: SPACING.lg },
  label: { fontSize: FONT_SIZES.sm, color: COLORS.textSecondary, fontWeight: '600', marginTop: SPACING.lg, marginBottom: SPACING.xs },
  tokenRow: { flexDirection: 'row', gap: SPACING.sm, flexWrap: 'wrap' },
  chip: { paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderRadius: BORDER_RADIUS.full, borderWidth: 1, borderColor: COLORS.border, backgroundColor: COLORS.surface },
  chipActive: { borderColor: COLORS.gold, backgroundColor: COLORS.gold + '20' },
  chipText: { fontSize: FONT_SIZES.sm, color: COLORS.textSecondary, fontWeight: '600' },
  chipTextActive: { color: COLORS.gold },
  input: { backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.lg, padding: SPACING.md, fontSize: FONT_SIZES.xxl, color: COLORS.text, borderWidth: 1, borderColor: COLORS.border, marginTop: SPACING.md, textAlign: 'center' },
  swapIcon: { alignItems: 'center', marginVertical: SPACING.md },
  quoteBox: { backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.lg, padding: SPACING.md, marginTop: SPACING.md, borderWidth: 1, borderColor: COLORS.gold + '30' },
  quoteText: { fontSize: FONT_SIZES.sm, color: COLORS.textSecondary, marginBottom: SPACING.xs },
  actionBtn: { borderRadius: BORDER_RADIUS.lg, overflow: 'hidden', marginTop: SPACING.xl },
  btnGradient: { alignItems: 'center', justifyContent: 'center', paddingVertical: SPACING.md },
  btnText: { fontSize: FONT_SIZES.lg, fontWeight: '700', color: COLORS.background },
});
