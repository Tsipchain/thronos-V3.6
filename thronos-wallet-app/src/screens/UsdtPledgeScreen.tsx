import React, { useState, useCallback, useEffect } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  TextInput, ActivityIndicator, Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import * as Clipboard from 'expo-clipboard';
import { COLORS, SPACING, FONT_SIZES, BORDER_RADIUS } from '../constants/theme';
import { CONFIG } from '../constants/config';
import { getBnbPledgeQuote, registerBnbAddress } from '../services/api';
import { useStore } from '../store/useStore';

// USDT-on-BNB-Chain Pledge — alternate gateway to Thronos Network.
// User sends USDT (BEP20) to the vault, registers the sending BNB
// address so the watcher can resolve it, and is credited THR once
// the transfer confirms (half the THR equivalent is paired into the
// THR/USDT liquidity pool).

type Step = 'intro' | 'register' | 'done';

export default function UsdtPledgeScreen({ navigation }: any) {
  const { wallet } = useStore();
  const [step, setStep] = useState<Step>('intro');
  const [bnbAddress, setBnbAddress] = useState('');
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [quote, setQuote] = useState<{ vault_address?: string; token_contract?: string; chain?: string; min_usdt?: number; usdt_thr_rate?: number } | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const q = await getBnbPledgeQuote();
        if (q.ok !== false) setQuote(q);
      } catch (err) {
        // keep defaults from CONFIG if quote fails to load
      }
    })();
  }, []);

  const vaultAddress = quote?.vault_address || '';
  const minUsdt = quote?.min_usdt ?? CONFIG.MIN_USDT_PLEDGE;
  const rate = quote?.usdt_thr_rate ?? CONFIG.USDT_THR_RATE;

  const copyVaultAddress = async () => {
    if (!vaultAddress) return;
    await Clipboard.setStringAsync(vaultAddress);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleRegister = useCallback(async () => {
    if (!bnbAddress.trim() || !/^0x[a-fA-F0-9]{40}$/.test(bnbAddress.trim())) {
      Alert.alert('Required', 'Enter a valid BNB (0x...) sending address');
      return;
    }
    if (!wallet.address) {
      Alert.alert('Error', 'No THR wallet found');
      return;
    }
    setLoading(true);
    try {
      const res = await registerBnbAddress({ thr_address: wallet.address, bnb_address: bnbAddress.trim() });
      if (res.ok) {
        setStep('done');
      } else {
        Alert.alert('Error', res.error || 'Registration failed');
      }
    } catch (err: any) {
      Alert.alert('Error', err.message || 'Network error');
    } finally {
      setLoading(false);
    }
  }, [bnbAddress, wallet.address]);

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={styles.title}>USDT Pledge</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView style={styles.scroll} showsVerticalScrollIndicator={false}>
        {/* Step: Intro */}
        {step === 'intro' && (
          <>
            <LinearGradient colors={['#001A14', '#000D0A']} style={styles.introCard}>
              <Ionicons name="cash" size={48} color={COLORS.gold} />
              <Text style={styles.introTitle}>Pledge USDT on BNB Chain</Text>
              <Text style={styles.introDesc}>
                Send USDT (BEP20) on Binance Smart Chain to our vault. The watcher detects your
                transfer and credits the THR equivalent to your wallet — half is paired into the
                THR/USDT liquidity pool.
              </Text>
            </LinearGradient>

            <View style={styles.rateBox}>
              <Text style={styles.rateText}>1 USDT ≈ {rate} THR</Text>
              <Text style={styles.rateLabel}>Minimum pledge: {minUsdt} USDT</Text>
            </View>

            <View style={styles.stepsBox}>
              <View style={styles.stepItem}>
                <View style={styles.stepNum}><Text style={styles.stepNumText}>1</Text></View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.stepTitle}>Register Your Address</Text>
                  <Text style={styles.stepDesc}>Link the BNB address you'll send USDT from</Text>
                </View>
              </View>
              <View style={styles.stepItem}>
                <View style={styles.stepNum}><Text style={styles.stepNumText}>2</Text></View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.stepTitle}>Send USDT</Text>
                  <Text style={styles.stepDesc}>Send minimum {minUsdt} USDT (BEP20) to the vault</Text>
                </View>
              </View>
              <View style={styles.stepItem}>
                <View style={styles.stepNum}><Text style={styles.stepNumText}>3</Text></View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.stepTitle}>Watcher Verifies</Text>
                  <Text style={styles.stepDesc}>Our BSC watcher detects your transfer (~5 min)</Text>
                </View>
              </View>
              <View style={styles.stepItem}>
                <View style={styles.stepNum}><Text style={styles.stepNumText}>4</Text></View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.stepTitle}>Get THR Credited</Text>
                  <Text style={styles.stepDesc}>THR equivalent lands in your wallet automatically</Text>
                </View>
              </View>
            </View>

            <TouchableOpacity style={styles.primaryBtn} onPress={() => setStep('register')}>
              <Ionicons name="cash" size={20} color={COLORS.background} />
              <Text style={styles.primaryBtnText}>Start Pledge</Text>
            </TouchableOpacity>
          </>
        )}

        {/* Step: Register address + show vault */}
        {step === 'register' && (
          <>
            <Text style={styles.sectionTitle}>Send USDT to Vault</Text>

            <TouchableOpacity style={styles.addressCard} onPress={copyVaultAddress}>
              <Ionicons name="logo-usd" size={24} color="#26A17B" />
              <View style={{ flex: 1 }}>
                <Text style={styles.addressLabel}>Vault Address (BEP20)</Text>
                <Text style={styles.addressValue} numberOfLines={1}>
                  {vaultAddress || 'Loading…'}
                </Text>
              </View>
              <View style={styles.copyBadge}>
                <Text style={styles.copyBadgeText}>{copied ? 'Copied!' : 'Copy'}</Text>
              </View>
            </TouchableOpacity>

            <View style={styles.minBox}>
              <Ionicons name="information-circle" size={20} color={COLORS.info} />
              <Text style={styles.minText}>
                Minimum: {minUsdt} USDT · Network: BNB Smart Chain (BEP20)
              </Text>
            </View>

            <Text style={styles.inputLabel}>Your BNB Sending Address</Text>
            <TextInput
              style={styles.input}
              value={bnbAddress}
              onChangeText={setBnbAddress}
              placeholder="0x... (the address you'll send USDT from)"
              placeholderTextColor={COLORS.textMuted}
              autoCapitalize="none"
              autoCorrect={false}
            />

            <TouchableOpacity
              style={[styles.primaryBtn, loading && styles.btnDisabled]}
              onPress={handleRegister}
              disabled={loading}
            >
              {loading ? (
                <ActivityIndicator color={COLORS.background} />
              ) : (
                <>
                  <Ionicons name="link" size={18} color={COLORS.background} />
                  <Text style={styles.primaryBtnText}>Register Address</Text>
                </>
              )}
            </TouchableOpacity>
          </>
        )}

        {/* Step: Done */}
        {step === 'done' && (
          <>
            <LinearGradient colors={['#001A00', '#000D05']} style={styles.completeCard}>
              <Ionicons name="checkmark-circle" size={56} color={COLORS.success} />
              <Text style={styles.completeTitle}>Address Registered!</Text>
              <Text style={styles.completeDesc}>
                Send USDT (BEP20) from {bnbAddress.slice(0, 8)}…{bnbAddress.slice(-6)} to the vault
                address. THR will be credited to your wallet automatically once the watcher
                detects and confirms your transfer (usually within 5 minutes).
              </Text>
            </LinearGradient>

            <TouchableOpacity
              style={styles.primaryBtn}
              onPress={() => navigation.navigate('MainTabs')}
            >
              <Ionicons name="wallet" size={20} color={COLORS.background} />
              <Text style={styles.primaryBtnText}>Go to Wallet</Text>
            </TouchableOpacity>
          </>
        )}

        <View style={{ height: SPACING.xxl }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.background },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: SPACING.lg, paddingVertical: SPACING.md,
  },
  backBtn: { padding: SPACING.xs },
  title: { fontSize: FONT_SIZES.xl, fontWeight: '700', color: COLORS.gold },
  scroll: { flex: 1, paddingHorizontal: SPACING.lg },

  introCard: {
    borderRadius: BORDER_RADIUS.xl, padding: SPACING.xl,
    alignItems: 'center', gap: SPACING.md, marginBottom: SPACING.lg,
    borderWidth: 1, borderColor: COLORS.gold + '30',
  },
  introTitle: { fontSize: FONT_SIZES.xxl, fontWeight: '800', color: COLORS.gold, textAlign: 'center' },
  introDesc: { fontSize: FONT_SIZES.md, color: COLORS.textSecondary, textAlign: 'center', lineHeight: 22 },

  rateBox: {
    backgroundColor: COLORS.gold + '10', borderRadius: BORDER_RADIUS.md,
    padding: SPACING.md, alignItems: 'center', marginBottom: SPACING.lg,
    borderWidth: 1, borderColor: COLORS.gold + '25',
  },
  rateText: { fontSize: FONT_SIZES.lg, fontWeight: '800', color: COLORS.gold, fontFamily: 'monospace' },
  rateLabel: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, marginTop: 4 },

  stepsBox: { marginBottom: SPACING.lg, gap: SPACING.md },
  stepItem: { flexDirection: 'row', alignItems: 'flex-start', gap: SPACING.md },
  stepNum: {
    width: 28, height: 28, borderRadius: 14, backgroundColor: COLORS.gold,
    justifyContent: 'center', alignItems: 'center',
  },
  stepNumText: { fontSize: FONT_SIZES.sm, fontWeight: '700', color: COLORS.background },
  stepTitle: { fontSize: FONT_SIZES.md, fontWeight: '600', color: COLORS.text },
  stepDesc: { fontSize: FONT_SIZES.sm, color: COLORS.textMuted, marginTop: 2 },

  sectionTitle: { fontSize: FONT_SIZES.xl, fontWeight: '700', color: COLORS.text, marginBottom: SPACING.md },
  addressCard: {
    flexDirection: 'row', alignItems: 'center', gap: SPACING.md,
    backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.lg,
    padding: SPACING.md, marginBottom: SPACING.md,
    borderWidth: 1, borderColor: '#26A17B30',
  },
  addressLabel: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted },
  addressValue: { fontSize: FONT_SIZES.sm, color: COLORS.text, fontFamily: 'monospace', marginTop: 2 },
  copyBadge: { backgroundColor: COLORS.gold + '20', paddingHorizontal: SPACING.sm, paddingVertical: 4, borderRadius: BORDER_RADIUS.sm },
  copyBadgeText: { fontSize: FONT_SIZES.xs, color: COLORS.gold, fontWeight: '700' },

  minBox: {
    flexDirection: 'row', alignItems: 'center', gap: SPACING.sm,
    backgroundColor: COLORS.info + '10', borderRadius: BORDER_RADIUS.md,
    padding: SPACING.sm, marginBottom: SPACING.lg,
  },
  minText: { fontSize: FONT_SIZES.sm, color: COLORS.info, fontWeight: '500' },

  inputLabel: { fontSize: FONT_SIZES.sm, color: COLORS.textSecondary, fontWeight: '600', marginBottom: SPACING.xs },
  input: {
    backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.md,
    padding: SPACING.md, fontSize: FONT_SIZES.md, color: COLORS.text,
    borderWidth: 1, borderColor: COLORS.border, marginBottom: SPACING.md,
  },

  completeCard: {
    borderRadius: BORDER_RADIUS.xl, padding: SPACING.xl,
    alignItems: 'center', gap: SPACING.md, marginBottom: SPACING.lg,
    borderWidth: 1, borderColor: COLORS.success + '30',
  },
  completeTitle: { fontSize: FONT_SIZES.xxl, fontWeight: '800', color: COLORS.success, textAlign: 'center' },
  completeDesc: { fontSize: FONT_SIZES.md, color: COLORS.textSecondary, textAlign: 'center', lineHeight: 22 },

  primaryBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: SPACING.sm,
    backgroundColor: COLORS.gold, borderRadius: BORDER_RADIUS.lg,
    paddingVertical: SPACING.md, marginBottom: SPACING.md,
  },
  primaryBtnText: { fontSize: FONT_SIZES.lg, fontWeight: '700', color: COLORS.background },
  btnDisabled: { opacity: 0.6 },
});
