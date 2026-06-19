import React, { useState, useEffect } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, TextInput,
  ActivityIndicator, Alert, ScrollView, KeyboardAvoidingView, Platform,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT_SIZES, BORDER_RADIUS } from '../constants/theme';
import { getThrUsdtPoolInfo, requestWithdrawal, ThrUsdtPoolInfo } from '../services/api';
import { getPledgeStatus, getBnbPledgeStatus } from '../services/api';
import { useStore } from '../store/useStore';
import { getAuthSecret, getMnemonic } from '../services/wallet';
import type { RootStackParamList } from '../../App';

type Nav = NativeStackNavigationProp<RootStackParamList>;
type DestChain = 'bsc' | 'base' | 'arbitrum';
type Token = 'USDT' | 'USDC';

const CHAIN_OPTIONS: { value: DestChain; label: string; icon: string }[] = [
  { value: 'bsc',      label: 'BNB Chain (BSC)',  icon: '🔶' },
  { value: 'base',     label: 'Base',              icon: '⬛' },
  { value: 'arbitrum', label: 'Arbitrum',          icon: '🔵' },
];
const TOKEN_OPTIONS: { value: Token; label: string }[] = [
  { value: 'USDT', label: 'USDT' },
  { value: 'USDC', label: 'USDC' },
];

export default function WithdrawScreen() {
  const navigation = useNavigation<Nav>();
  const { wallet } = useStore();
  const address = wallet?.address || '';

  const [loading, setLoading]         = useState(true);
  const [submitting, setSubmitting]   = useState(false);
  const [poolInfo, setPoolInfo]       = useState<ThrUsdtPoolInfo | null>(null);
  const [sendSecret, setSendSecret]   = useState<string | null>(null);
  const [amount, setAmount]           = useState('');
  const [token, setToken]             = useState<Token>('USDT');
  const [destChain, setDestChain]     = useState<DestChain>('bsc');
  const [destAddress, setDestAddress] = useState('');
  const [done, setDone]               = useState<any>(null);

  useEffect(() => {
    init();
  }, []);

  const init = async () => {
    setLoading(true);
    try {
      const [pi] = await Promise.all([getThrUsdtPoolInfo()]);
      if (pi.ok) setPoolInfo(pi);

      // Try to find send_secret from BTC or USDT pledge
      const secret = await getAuthSecret();
      if (secret) {
        setSendSecret(secret);
      } else {
        // No auth secret stored yet; we need a pledge send_seed
        // The pledge send_seed is stored as the wallet's send_secret
        // Try to get it from pledge status
        // (This path is taken if user came via pledge but hasn't cached send_seed locally)
      }
    } catch {}
    setLoading(false);
  };

  const maxWithdraw = poolInfo ? Math.min(150, poolInfo.max_withdraw_usdt) : 150;

  const feeInfo = () => {
    const amt = parseFloat(amount) || 0;
    if (!amt) return null;
    const feeTotalUsd = amt * 0.01;
    const feePoolUsdt = feeTotalUsd * 0.5;
    const feeThr      = poolInfo ? (feeTotalUsd * 0.5) / poolInfo.thr_price_usd : 0;
    const netAmount   = amt - feePoolUsdt;
    return { feeTotalUsd, feePoolUsdt, feeThr, netAmount };
  };

  const handleSubmit = async () => {
    if (!sendSecret) {
      Alert.alert('No Pledge', 'Complete a BTC or USDT pledge first to unlock withdrawals.');
      return;
    }
    const amt = parseFloat(amount) || 0;
    if (amt <= 0) return Alert.alert('Invalid Amount', 'Enter a valid amount.');
    if (amt > maxWithdraw) return Alert.alert('Limit Exceeded', `Maximum withdrawal is $${maxWithdraw.toFixed(2)}.`);
    if (!/^0x[0-9a-fA-F]{40}$/.test(destAddress.trim())) {
      return Alert.alert('Invalid Address', 'Enter a valid EVM destination address (0x…).');
    }

    setSubmitting(true);
    try {
      const res = await requestWithdrawal({
        address,
        send_secret: sendSecret,
        amount: amt,
        token,
        dest_chain: destChain,
        dest_address: destAddress.trim().toLowerCase(),
      });

      if (res.ok) {
        setDone(res);
      } else {
        let msg = res.error || 'Withdrawal failed.';
        if (res.error === 'insufficient_thr_for_fee') {
          msg = `Insufficient THR for fee.\nRequired: ${res.required_thr} THR\nBalance: ${res.thr_balance} THR`;
        } else if (res.error === 'insufficient_pool_liquidity') {
          msg = `Pool liquidity too low.\nAvailable: $${res.available_usdt?.toFixed(2)} USDT`;
        } else if (res.error === 'exceeds_max_withdrawal') {
          msg = `Exceeds max withdrawal of $${maxWithdraw.toFixed(2)}.`;
        } else if (res.error === 'invalid_credentials') {
          msg = 'Invalid pledge credentials. Please re-import your wallet.';
        }
        Alert.alert('Withdrawal Failed', msg);
      }
    } catch (e: any) {
      Alert.alert('Error', e.message || 'Network error.');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
          <ActivityIndicator color={COLORS.gold} size="large" />
        </View>
      </SafeAreaView>
    );
  }

  if (done) {
    return (
      <SafeAreaView style={styles.container}>
        <LinearGradient colors={[COLORS.background, COLORS.backgroundLight]} style={styles.gradient}>
          <View style={styles.header}>
            <TouchableOpacity onPress={() => navigation.goBack()}>
              <Ionicons name="arrow-back" size={24} color={COLORS.text} />
            </TouchableOpacity>
            <Text style={styles.title}>Withdrawal Submitted</Text>
            <View style={{ width: 24 }} />
          </View>
          <ScrollView contentContainerStyle={{ padding: SPACING.lg }}>
            <View style={[styles.card, { alignItems: 'center', padding: SPACING.xl }]}>
              <Text style={{ fontSize: 48, marginBottom: SPACING.md }}>✅</Text>
              <Text style={{ fontSize: FONT_SIZES.xl, fontWeight: '700', color: COLORS.success, marginBottom: SPACING.xs }}>Processing</Text>
              <Text style={{ fontSize: FONT_SIZES.sm, color: COLORS.textMuted, marginBottom: SPACING.lg }}>
                ID: {done.withdrawal_id}
              </Text>
              <View style={{ width: '100%', gap: 8 }}>
                {[
                  ['Token',       done.token],
                  ['Requested',   `${done.amount} ${done.token}`],
                  ['You receive', `${done.amount_net} ${done.token}`],
                  ['THR fee',     `${done.fee_thr} THR`],
                  ['Chain',       (done.dest_chain || '').toUpperCase()],
                  ['Destination', `${done.dest_address?.slice(0,10)}…${done.dest_address?.slice(-6)}`],
                ].map(([k, v]) => (
                  <View key={k} style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                    <Text style={{ color: COLORS.textMuted, fontSize: FONT_SIZES.sm }}>{k}</Text>
                    <Text style={{ color: k === 'You receive' ? COLORS.success : COLORS.text, fontSize: FONT_SIZES.sm, fontWeight: k === 'You receive' ? '700' : '400' }}>{v}</Text>
                  </View>
                ))}
              </View>
              <Text style={{ color: COLORS.textMuted, fontSize: FONT_SIZES.xs, marginTop: SPACING.lg, textAlign: 'center' }}>
                Estimated delivery: ~{done.estimated_minutes || 5} minutes
              </Text>
            </View>
            <TouchableOpacity style={styles.btn} onPress={() => navigation.goBack()}>
              <LinearGradient colors={[COLORS.gold, COLORS.goldDark]} style={styles.btnInner}>
                <Text style={styles.btnText}>Back to Wallet</Text>
              </LinearGradient>
            </TouchableOpacity>
          </ScrollView>
        </LinearGradient>
      </SafeAreaView>
    );
  }

  const fee = feeInfo();

  return (
    <SafeAreaView style={styles.container}>
      <LinearGradient colors={[COLORS.background, COLORS.backgroundLight]} style={styles.gradient}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()}>
            <Ionicons name="arrow-back" size={24} color={COLORS.text} />
          </TouchableOpacity>
          <Text style={styles.title}>Withdraw</Text>
          <View style={{ width: 24 }} />
        </View>

        <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <ScrollView contentContainerStyle={{ padding: SPACING.lg, paddingBottom: SPACING.xl * 2 }}>

            {/* Pool info */}
            {poolInfo && (
              <View style={[styles.card, { marginBottom: SPACING.md }]}>
                <Text style={styles.sectionLabel}>THR/USDT Pool</Text>
                <View style={{ gap: 6 }}>
                  {[
                    ['USDT Reserve',  `${poolInfo.usdt_reserve.toFixed(2)} USDT`],
                    ['THR Price',     `$${poolInfo.thr_price_usd.toFixed(4)}`],
                    ['Pledges',       `${poolInfo.pledge_count} (next level: ${poolInfo.next_level_at})`],
                    ['Max per TX',    `$${maxWithdraw.toFixed(2)}`],
                  ].map(([k, v]) => (
                    <View key={k} style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                      <Text style={{ color: COLORS.textMuted, fontSize: FONT_SIZES.sm }}>{k}</Text>
                      <Text style={{ color: k === 'THR Price' ? COLORS.success : COLORS.text, fontSize: FONT_SIZES.sm, fontWeight: k === 'THR Price' ? '700' : '400' }}>{v}</Text>
                    </View>
                  ))}
                </View>
              </View>
            )}

            {!sendSecret ? (
              <View style={[styles.card, { alignItems: 'center', padding: SPACING.xl }]}>
                <Ionicons name="lock-closed" size={40} color={COLORS.textMuted} style={{ marginBottom: SPACING.md }} />
                <Text style={{ color: COLORS.text, fontSize: FONT_SIZES.md, fontWeight: '600', marginBottom: SPACING.xs }}>Pledge Required</Text>
                <Text style={{ color: COLORS.textMuted, fontSize: FONT_SIZES.sm, textAlign: 'center', lineHeight: 20 }}>
                  Withdrawals are available after completing a BTC or USDT pledge. Complete your pledge first.
                </Text>
              </View>
            ) : (
              <View style={styles.card}>
                <Text style={styles.sectionLabel}>Withdrawal Details</Text>

                {/* Token */}
                <Text style={styles.label}>Token</Text>
                <View style={styles.chipRow}>
                  {TOKEN_OPTIONS.map(opt => (
                    <TouchableOpacity
                      key={opt.value}
                      style={[styles.chip, token === opt.value && styles.chipActive]}
                      onPress={() => setToken(opt.value)}
                    >
                      <Text style={[styles.chipText, token === opt.value && styles.chipTextActive]}>{opt.label}</Text>
                    </TouchableOpacity>
                  ))}
                </View>

                {/* Destination chain */}
                <Text style={styles.label}>Destination Chain</Text>
                <View style={styles.chipRow}>
                  {CHAIN_OPTIONS.map(opt => (
                    <TouchableOpacity
                      key={opt.value}
                      style={[styles.chip, destChain === opt.value && styles.chipActive]}
                      onPress={() => setDestChain(opt.value)}
                    >
                      <Text style={[styles.chipText, destChain === opt.value && styles.chipTextActive]}>{opt.icon} {opt.label}</Text>
                    </TouchableOpacity>
                  ))}
                </View>

                {/* Destination address */}
                <Text style={styles.label}>Destination Address (EVM)</Text>
                <TextInput
                  style={styles.input}
                  placeholder="0x..."
                  placeholderTextColor={COLORS.textMuted}
                  value={destAddress}
                  onChangeText={setDestAddress}
                  autoCapitalize="none"
                  autoCorrect={false}
                />

                {/* Amount */}
                <Text style={styles.label}>Amount (max ${maxWithdraw.toFixed(2)})</Text>
                <View style={{ flexDirection: 'row', gap: 8, marginBottom: SPACING.sm }}>
                  <TextInput
                    style={[styles.input, { flex: 1, marginBottom: 0 }]}
                    placeholder={`e.g. 50`}
                    placeholderTextColor={COLORS.textMuted}
                    value={amount}
                    onChangeText={setAmount}
                    keyboardType="decimal-pad"
                  />
                  <TouchableOpacity
                    style={[styles.chip, { alignSelf: 'stretch', paddingHorizontal: SPACING.md }]}
                    onPress={() => setAmount(maxWithdraw.toFixed(2))}
                  >
                    <Text style={styles.chipText}>MAX</Text>
                  </TouchableOpacity>
                </View>

                {/* Fee preview */}
                {fee && (
                  <View style={[styles.feeBox]}>
                    <Text style={styles.feeText}>
                      You receive:{' '}
                      <Text style={{ color: COLORS.success, fontWeight: '700' }}>
                        {fee.netAmount.toFixed(4)} {token}
                      </Text>
                    </Text>
                    <Text style={styles.feeText}>
                      Service fee: {fee.feePoolUsdt.toFixed(4)} {token} + {fee.feeThr.toFixed(6)} THR
                    </Text>
                  </View>
                )}

                <TouchableOpacity style={styles.btn} onPress={handleSubmit} disabled={submitting}>
                  <LinearGradient colors={[COLORS.gold, COLORS.goldDark]} style={styles.btnInner}>
                    {submitting
                      ? <ActivityIndicator color={COLORS.background} />
                      : <><Ionicons name="arrow-up-circle" size={22} color={COLORS.background} /><Text style={styles.btnText}>Submit Withdrawal</Text></>
                    }
                  </LinearGradient>
                </TouchableOpacity>

                <View style={styles.note}>
                  <Ionicons name="information-circle" size={16} color={COLORS.primary} />
                  <Text style={styles.noteText}>
                    1% service fee (0.5% from THR balance + 0.5% in-kind). Max $150 per transaction. Processed automatically within ~5 minutes.
                  </Text>
                </View>
              </View>
            )}
          </ScrollView>
        </KeyboardAvoidingView>
      </LinearGradient>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container:    { flex: 1, backgroundColor: COLORS.background },
  gradient:     { flex: 1 },
  header:       { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
                  paddingHorizontal: SPACING.lg, paddingVertical: SPACING.md },
  title:        { fontSize: FONT_SIZES.xl, fontWeight: '600', color: COLORS.text },
  card:         { backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.lg, padding: SPACING.md, marginBottom: SPACING.md },
  sectionLabel: { fontSize: FONT_SIZES.xs, textTransform: 'uppercase', letterSpacing: 1, color: COLORS.primary, marginBottom: SPACING.sm, fontWeight: '700' },
  label:        { fontSize: FONT_SIZES.sm, color: COLORS.textSecondary, fontWeight: '600', marginBottom: SPACING.xs, marginTop: SPACING.sm },
  input:        { backgroundColor: COLORS.backgroundCard, borderRadius: BORDER_RADIUS.md, padding: SPACING.md,
                  fontSize: FONT_SIZES.md, color: COLORS.text, borderWidth: 1, borderColor: COLORS.textMuted + '40', marginBottom: SPACING.sm },
  chipRow:      { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: SPACING.sm },
  chip:         { backgroundColor: COLORS.backgroundCard, borderRadius: BORDER_RADIUS.md, paddingVertical: 6, paddingHorizontal: 12,
                  borderWidth: 1, borderColor: COLORS.textMuted + '40' },
  chipActive:   { backgroundColor: COLORS.gold + '22', borderColor: COLORS.gold },
  chipText:     { fontSize: FONT_SIZES.sm, color: COLORS.textMuted },
  chipTextActive: { color: COLORS.gold, fontWeight: '700' },
  feeBox:       { backgroundColor: COLORS.backgroundCard, borderRadius: BORDER_RADIUS.md, padding: SPACING.sm,
                  marginBottom: SPACING.sm, borderWidth: 1, borderColor: COLORS.success + '30' },
  feeText:      { fontSize: FONT_SIZES.xs, color: COLORS.textSecondary, lineHeight: 18 },
  btn:          { borderRadius: BORDER_RADIUS.lg, overflow: 'hidden', marginTop: SPACING.md },
  btnInner:     { flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
                  paddingVertical: SPACING.md, gap: SPACING.sm },
  btnText:      { fontSize: FONT_SIZES.lg, fontWeight: '700', color: COLORS.background },
  note:         { flexDirection: 'row', backgroundColor: COLORS.primary + '12', borderRadius: BORDER_RADIUS.md,
                  padding: SPACING.sm, marginTop: SPACING.sm, gap: SPACING.xs,
                  borderWidth: 1, borderColor: COLORS.primary + '30' },
  noteText:     { flex: 1, fontSize: FONT_SIZES.xs, color: COLORS.textSecondary, lineHeight: 18 },
});
