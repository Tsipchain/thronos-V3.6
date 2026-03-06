import React, { useState, useEffect } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, TextInput, Alert, ActivityIndicator,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT_SIZES, BORDER_RADIUS } from '../constants/theme';
import { useStore } from '../store/useStore';
import { getPledgeInfo, pledgeTokens } from '../services/api';
import { getWallet } from '../services/wallet';

export default function StakeScreen() {
  const navigation = useNavigation();
  const { wallet, tokens } = useStore();
  const [amount, setAmount] = useState('');
  const [pledgeInfo, setPledgeInfo] = useState<{ pledged_amount: number; rewards: number; apr: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [staking, setStaking] = useState(false);

  const thrBalance = tokens.find((t) => t.symbol === 'THR')?.balance ?? 0;

  useEffect(() => {
    if (!wallet.address) return;
    getPledgeInfo(wallet.address)
      .then(setPledgeInfo)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [wallet.address]);

  const handleStake = async () => {
    const amt = parseFloat(amount);
    if (!amt || amt <= 0) { Alert.alert('Error', 'Enter a valid amount.'); return; }
    if (amt > thrBalance) { Alert.alert('Error', 'Insufficient THR balance.'); return; }

    const creds = await getWallet();
    if (!creds) { Alert.alert('Error', 'Wallet not found.'); return; }

    setStaking(true);
    try {
      const result = await pledgeTokens({ address: creds.address, amount: amt, secret: creds.secret });
      if (result.success) {
        Alert.alert('Success', `Staked ${amt} THR!`, [{ text: 'OK', onPress: () => navigation.goBack() }]);
      }
    } catch (error: any) {
      Alert.alert('Error', error.message);
    } finally {
      setStaking(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <LinearGradient colors={[COLORS.background, COLORS.backgroundLight]} style={styles.gradient}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()}>
            <Ionicons name="arrow-back" size={24} color={COLORS.text} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Stake THR</Text>
          <View style={{ width: 24 }} />
        </View>

        <View style={styles.content}>
          {/* Current staking info */}
          {loading ? (
            <ActivityIndicator color={COLORS.gold} />
          ) : pledgeInfo ? (
            <View style={styles.infoCard}>
              <View style={styles.infoRow}>
                <Text style={styles.infoLabel}>Staked</Text>
                <Text style={styles.infoValue}>{pledgeInfo.pledged_amount.toLocaleString()} THR</Text>
              </View>
              <View style={styles.infoRow}>
                <Text style={styles.infoLabel}>Rewards</Text>
                <Text style={[styles.infoValue, { color: COLORS.success }]}>{pledgeInfo.rewards.toFixed(4)} THR</Text>
              </View>
              <View style={styles.infoRow}>
                <Text style={styles.infoLabel}>APR</Text>
                <Text style={[styles.infoValue, { color: COLORS.gold }]}>{(pledgeInfo.apr * 100).toFixed(1)}%</Text>
              </View>
            </View>
          ) : null}

          <Text style={styles.label}>Amount to Stake</Text>
          <Text style={styles.balanceHint}>Available: {thrBalance.toLocaleString()} THR</Text>

          <View style={styles.amountRow}>
            <TextInput
              style={[styles.input, { flex: 1 }]}
              placeholder="0.00"
              placeholderTextColor={COLORS.textMuted}
              value={amount}
              onChangeText={setAmount}
              keyboardType="decimal-pad"
            />
            <TouchableOpacity style={styles.maxBtn} onPress={() => setAmount(String(thrBalance))}>
              <Text style={styles.maxText}>MAX</Text>
            </TouchableOpacity>
          </View>

          <TouchableOpacity style={styles.stakeBtn} onPress={handleStake} disabled={staking}>
            <LinearGradient colors={[COLORS.gold, COLORS.goldDark]} style={styles.btnGradient}>
              {staking ? <ActivityIndicator color={COLORS.background} /> : (
                <>
                  <Ionicons name="layers" size={20} color={COLORS.background} />
                  <Text style={styles.btnText}>Stake THR</Text>
                </>
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
  infoCard: { backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.lg, padding: SPACING.md, marginBottom: SPACING.lg, borderWidth: 1, borderColor: COLORS.gold + '30' },
  infoRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: SPACING.xs },
  infoLabel: { fontSize: FONT_SIZES.md, color: COLORS.textSecondary },
  infoValue: { fontSize: FONT_SIZES.md, fontWeight: '600', color: COLORS.text },
  label: { fontSize: FONT_SIZES.sm, color: COLORS.textSecondary, fontWeight: '600', marginTop: SPACING.lg },
  balanceHint: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, marginBottom: SPACING.sm },
  amountRow: { flexDirection: 'row', gap: SPACING.sm, alignItems: 'center' },
  input: { backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.lg, padding: SPACING.md, fontSize: FONT_SIZES.xxl, color: COLORS.text, borderWidth: 1, borderColor: COLORS.border, textAlign: 'center' },
  maxBtn: { backgroundColor: COLORS.gold + '20', paddingHorizontal: SPACING.md, paddingVertical: SPACING.md, borderRadius: BORDER_RADIUS.lg },
  maxText: { fontSize: FONT_SIZES.sm, color: COLORS.gold, fontWeight: '700' },
  stakeBtn: { borderRadius: BORDER_RADIUS.lg, overflow: 'hidden', marginTop: SPACING.xl },
  btnGradient: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: SPACING.md, gap: SPACING.sm },
  btnText: { fontSize: FONT_SIZES.lg, fontWeight: '700', color: COLORS.background },
});
