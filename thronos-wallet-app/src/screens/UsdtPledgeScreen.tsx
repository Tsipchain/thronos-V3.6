import React, { useState, useCallback, useEffect } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  TextInput, ActivityIndicator, Alert, Linking,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import * as Clipboard from 'expo-clipboard';
import { COLORS, SPACING, FONT_SIZES, BORDER_RADIUS } from '../constants/theme';
import { CONFIG } from '../constants/config';
import { getBnbPledgeQuote, registerBnbAddress, pledgeMigrate } from '../services/api';
import { useStore } from '../store/useStore';

// USDT-on-BNB-Chain Pledge — gateway to Thronos Network.
//
// Two modes:
//  - Existing wallet: registers BNB address so the watcher can credit THR
//  - New user (no wallet): generates THR address + send_secret + PDF, then
//    creates V1 wallet inline via pledge-migrate (same as BTC pledge flow).

type Step = 'intro' | 'register' | 'setup_v1' | 'v1_ready' | 'done';

export default function UsdtPledgeScreen({ navigation }: any) {
  const { wallet } = useStore();
  const isNewUser = !wallet.address;

  const [step, setStep] = useState<Step>('intro');
  const [bnbAddress, setBnbAddress] = useState('');
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [quote, setQuote] = useState<{ vault_address?: string; token_contract?: string; min_usdt?: number; usdt_thr_rate?: number } | null>(null);

  // new-user state
  const [secretSeed, setSecretSeed] = useState<string | null>(null);
  const [pendingThrAddress, setPendingThrAddress] = useState<string | null>(null);
  const [pin, setPin] = useState('');
  const [pinConfirm, setPinConfirm] = useState('');
  const [v1Address, setV1Address] = useState<string | null>(null);
  const [v1PdfUrl, setV1PdfUrl] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const q = await getBnbPledgeQuote();
        if (q.ok !== false) setQuote(q);
      } catch {}
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
    setLoading(true);
    try {
      const params = isNewUser
        ? { bnb_address: bnbAddress.trim() }
        : { thr_address: wallet.address!, bnb_address: bnbAddress.trim() };

      const res = await registerBnbAddress(params);
      if (!res.ok) {
        Alert.alert('Error', res.error || 'Registration failed');
        return;
      }

      if (isNewUser && res.secret_seed) {
        setSecretSeed(res.secret_seed);
        setPendingThrAddress(res.thr_address || null);
        setStep('setup_v1');
      } else {
        setStep('done');
      }
    } catch (err: any) {
      Alert.alert('Error', err.message || 'Network error');
    } finally {
      setLoading(false);
    }
  }, [bnbAddress, wallet.address, isNewUser]);

  const handleCreateV1 = useCallback(async () => {
    if (!pin || pin.length < 4) {
      Alert.alert('PIN Required', 'Enter a PIN of at least 4 digits');
      return;
    }
    if (pin !== pinConfirm) {
      Alert.alert('PIN Mismatch', 'PINs do not match — please re-enter');
      return;
    }
    if (!secretSeed) {
      Alert.alert('Error', 'No pledge secret — please re-register your BNB address');
      return;
    }
    setLoading(true);
    try {
      const res = await pledgeMigrate({ send_secret: secretSeed, pin });
      if (res.ok && res.canonical_v1_address) {
        setV1Address(res.canonical_v1_address);
        if (res.pdf_url) setV1PdfUrl(`${CONFIG.API_URL}${res.pdf_url}`);
        setStep('v1_ready');
      } else {
        Alert.alert('Error', res.error || 'V1 wallet creation failed');
      }
    } catch (err: any) {
      Alert.alert('Error', err.message || 'Network error');
    } finally {
      setLoading(false);
    }
  }, [pin, pinConfirm, secretSeed]);

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
                {isNewUser
                  ? 'Send USDT (BEP20) to our vault to create your THR wallet. You\'ll get a V1 address, Recovery Kit, and PDF contract with your secret embedded via LSB steganography.'
                  : 'Send USDT (BEP20) on Binance Smart Chain to our vault. The watcher detects your transfer and credits the THR equivalent to your wallet — half is paired into the THR/USDT liquidity pool.'}
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
                  <Text style={styles.stepTitle}>Register Your BNB Address</Text>
                  <Text style={styles.stepDesc}>Link the BNB address you'll send USDT from (KYC for the watcher)</Text>
                </View>
              </View>
              {isNewUser && (
                <View style={styles.stepItem}>
                  <View style={styles.stepNum}><Text style={styles.stepNumText}>2</Text></View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.stepTitle}>Create V1 Wallet</Text>
                    <Text style={styles.stepDesc}>Set a PIN — generates your Recovery Kit + PDF with embedded secret</Text>
                  </View>
                </View>
              )}
              <View style={styles.stepItem}>
                <View style={styles.stepNum}><Text style={styles.stepNumText}>{isNewUser ? '3' : '2'}</Text></View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.stepTitle}>Send USDT</Text>
                  <Text style={styles.stepDesc}>Send minimum {minUsdt} USDT (BEP20) to the vault</Text>
                </View>
              </View>
              <View style={styles.stepItem}>
                <View style={styles.stepNum}><Text style={styles.stepNumText}>{isNewUser ? '4' : '3'}</Text></View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.stepTitle}>THR Credited Automatically</Text>
                  <Text style={styles.stepDesc}>Our BSC watcher detects your transfer and credits THR (~5 min)</Text>
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

        {/* Step: Setup V1 Wallet (new users only) */}
        {step === 'setup_v1' && (
          <>
            <LinearGradient colors={['#001A0A', '#000D05']} style={styles.completeCard}>
              <Ionicons name="key" size={48} color={COLORS.gold} />
              <Text style={styles.completeTitle}>Address Registered!</Text>
              <Text style={styles.completeDesc}>
                Set a PIN to create your V1 wallet. Your Recovery Kit and a PDF contract
                (with your secret embedded via LSB steganography) will be generated.
              </Text>
              {pendingThrAddress && (
                <View style={styles.thrFinal}>
                  <Text style={styles.thrFinalLabel}>Reserved THR Address</Text>
                  <Text style={styles.thrFinalAddr}>{pendingThrAddress}</Text>
                </View>
              )}
            </LinearGradient>

            <Text style={styles.inputLabel}>New PIN (4-8 digits)</Text>
            <TextInput
              style={styles.input}
              value={pin}
              onChangeText={setPin}
              placeholder="Enter PIN..."
              placeholderTextColor={COLORS.textMuted}
              secureTextEntry
              keyboardType="numeric"
              maxLength={8}
            />

            <Text style={styles.inputLabel}>Confirm PIN</Text>
            <TextInput
              style={styles.input}
              value={pinConfirm}
              onChangeText={setPinConfirm}
              placeholder="Re-enter PIN..."
              placeholderTextColor={COLORS.textMuted}
              secureTextEntry
              keyboardType="numeric"
              maxLength={8}
            />

            <TouchableOpacity
              style={[styles.primaryBtn, loading && styles.btnDisabled]}
              onPress={handleCreateV1}
              disabled={loading}
            >
              {loading ? (
                <ActivityIndicator color={COLORS.background} />
              ) : (
                <>
                  <Ionicons name="shield-checkmark" size={20} color={COLORS.background} />
                  <Text style={styles.primaryBtnText}>Create V1 Wallet</Text>
                </>
              )}
            </TouchableOpacity>
          </>
        )}

        {/* Step: V1 Ready (new users) */}
        {step === 'v1_ready' && (
          <>
            <LinearGradient colors={['#001A00', '#000D05']} style={styles.completeCard}>
              <Ionicons name="shield-checkmark" size={56} color={COLORS.success} />
              <Text style={styles.completeTitle}>Welcome to Thronos!</Text>
              <Text style={styles.completeDesc}>
                Your V1 wallet is ready. Now send at least {minUsdt} USDT from your registered
                BNB address to the vault — THR will be credited automatically once confirmed.
              </Text>
              {v1Address && (
                <View style={styles.thrFinal}>
                  <Text style={styles.thrFinalLabel}>Your V1 THR Address</Text>
                  <Text style={styles.thrFinalAddr}>{v1Address}</Text>
                </View>
              )}
            </LinearGradient>

            {v1PdfUrl && (
              <TouchableOpacity
                style={styles.pdfBtn}
                onPress={() => Linking.openURL(v1PdfUrl!)}
              >
                <Ionicons name="document" size={20} color={COLORS.gold} />
                <Text style={styles.pdfBtnText}>Download PDF Contract (LSB)</Text>
              </TouchableOpacity>
            )}

            <TouchableOpacity
              style={styles.primaryBtn}
              onPress={() => navigation.navigate('MainTabs')}
            >
              <Ionicons name="wallet" size={20} color={COLORS.background} />
              <Text style={styles.primaryBtnText}>Go to Wallet</Text>
            </TouchableOpacity>
          </>
        )}

        {/* Step: Done (existing users) */}
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

  thrFinal: {
    backgroundColor: COLORS.background, borderRadius: BORDER_RADIUS.md,
    padding: SPACING.md, width: '100%', marginTop: SPACING.sm,
  },
  thrFinalLabel: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, marginBottom: 4 },
  thrFinalAddr: { fontSize: FONT_SIZES.md, color: COLORS.gold, fontFamily: 'monospace', fontWeight: '600' },

  pdfBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: SPACING.sm,
    backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.lg,
    padding: SPACING.md, marginBottom: SPACING.md,
    borderWidth: 1, borderColor: COLORS.gold + '30',
  },
  pdfBtnText: { fontSize: FONT_SIZES.md, color: COLORS.gold, fontWeight: '600' },

  primaryBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: SPACING.sm,
    backgroundColor: COLORS.gold, borderRadius: BORDER_RADIUS.lg,
    paddingVertical: SPACING.md, marginBottom: SPACING.md,
  },
  primaryBtnText: { fontSize: FONT_SIZES.lg, fontWeight: '700', color: COLORS.background },
  btnDisabled: { opacity: 0.6 },
});
