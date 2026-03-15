import React, { useState, useCallback } from 'react';
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
import { submitPledge, verifyBtcPayment, downloadPledgePdf } from '../services/api';

// BTC Pledge Entry — The gateway to Thronos Network
// Users send min BTC fee to the pledge address, watcher verifies,
// then a THR wallet + encrypted PDF contract is generated.

type Step = 'intro' | 'send_btc' | 'verify' | 'complete';

export default function PledgeScreen({ navigation }: any) {
  const [step, setStep] = useState<Step>('intro');
  const [btcAddress, setBtcAddress] = useState('');
  const [pledgeText, setPledgeText] = useState('');
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [thrAddress, setThrAddress] = useState<string | null>(null);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);

  const copyPledgeAddress = async () => {
    await Clipboard.setStringAsync(CONFIG.BTC_PLEDGE_ADDRESS);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleSubmitPledge = useCallback(async () => {
    if (!btcAddress.trim()) {
      Alert.alert('Required', 'Enter your BTC address used for the payment');
      return;
    }
    setLoading(true);
    try {
      const res = await submitPledge({
        btc_address: btcAddress.trim(),
        pledge_text: pledgeText.trim() || 'I pledge to the Thronos Network',
      });
      if (res.success && res.thr_address) {
        setThrAddress(res.thr_address);
        setStep('verify');
      } else {
        Alert.alert('Error', res.error || 'Pledge submission failed');
      }
    } catch (err: any) {
      Alert.alert('Error', err.message || 'Network error');
    } finally {
      setLoading(false);
    }
  }, [btcAddress, pledgeText]);

  const handleVerify = useCallback(async () => {
    if (!btcAddress) return;
    setLoading(true);
    try {
      const res = await verifyBtcPayment(btcAddress);
      if (res.verified) {
        // Fetch PDF
        if (thrAddress) {
          const pdf = await downloadPledgePdf(thrAddress);
          setPdfUrl(pdf.pdf_url);
        }
        setStep('complete');
      } else {
        Alert.alert('Not Yet', 'BTC payment not detected yet. The watcher checks every few minutes. Please wait and try again.');
      }
    } catch (err: any) {
      Alert.alert('Error', err.message || 'Verification failed');
    } finally {
      setLoading(false);
    }
  }, [btcAddress, thrAddress]);

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={styles.title}>BTC Pledge</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView style={styles.scroll} showsVerticalScrollIndicator={false}>
        {/* Step: Intro */}
        {step === 'intro' && (
          <>
            <LinearGradient colors={['#1A0A00', '#0D0500']} style={styles.introCard}>
              <Ionicons name="shield-checkmark" size={48} color={COLORS.gold} />
              <Text style={styles.introTitle}>Enter the Thronos Network</Text>
              <Text style={styles.introDesc}>
                To activate your THR wallet, send the minimum BTC fee to our pledge address.
                The watcher will verify your payment and generate your THR wallet with an
                encrypted PDF contract.
              </Text>
            </LinearGradient>

            <View style={styles.rateBox}>
              <Text style={styles.rateText}>1 THR = 0.0001 BTC</Text>
              <Text style={styles.rateLabel}>Fixed Exchange Rate</Text>
            </View>

            <View style={styles.stepsBox}>
              <View style={styles.stepItem}>
                <View style={styles.stepNum}><Text style={styles.stepNumText}>1</Text></View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.stepTitle}>Send BTC</Text>
                  <Text style={styles.stepDesc}>Send minimum {CONFIG.MIN_BTC_PLEDGE} BTC to the pledge address</Text>
                </View>
              </View>
              <View style={styles.stepItem}>
                <View style={styles.stepNum}><Text style={styles.stepNumText}>2</Text></View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.stepTitle}>Watcher Verifies</Text>
                  <Text style={styles.stepDesc}>Our BTC watcher detects and approves your payment</Text>
                </View>
              </View>
              <View style={styles.stepItem}>
                <View style={styles.stepNum}><Text style={styles.stepNumText}>3</Text></View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.stepTitle}>Get THR Wallet</Text>
                  <Text style={styles.stepDesc}>Receive your THR address + encrypted PDF contract with steganography</Text>
                </View>
              </View>
              <View style={styles.stepItem}>
                <View style={styles.stepNum}><Text style={styles.stepNumText}>4</Text></View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.stepTitle}>Phantom Node</Text>
                  <Text style={styles.stepDesc}>Your mobile becomes a phantom node on the parallel chain</Text>
                </View>
              </View>
            </View>

            <TouchableOpacity style={styles.primaryBtn} onPress={() => setStep('send_btc')}>
              <Ionicons name="shield-checkmark" size={20} color={COLORS.background} />
              <Text style={styles.primaryBtnText}>Start Pledge</Text>
            </TouchableOpacity>
          </>
        )}

        {/* Step: Send BTC */}
        {step === 'send_btc' && (
          <>
            <Text style={styles.sectionTitle}>Send BTC to Pledge Address</Text>

            <TouchableOpacity style={styles.addressCard} onPress={copyPledgeAddress}>
              <Ionicons name="logo-bitcoin" size={24} color="#F7931A" />
              <View style={{ flex: 1 }}>
                <Text style={styles.addressLabel}>Pledge Address</Text>
                <Text style={styles.addressValue} numberOfLines={1}>
                  {CONFIG.BTC_PLEDGE_ADDRESS}
                </Text>
              </View>
              <View style={styles.copyBadge}>
                <Text style={styles.copyBadgeText}>{copied ? 'Copied!' : 'Copy'}</Text>
              </View>
            </TouchableOpacity>

            <View style={styles.minBox}>
              <Ionicons name="information-circle" size={20} color={COLORS.info} />
              <Text style={styles.minText}>
                Minimum: {CONFIG.MIN_BTC_PLEDGE} BTC
              </Text>
            </View>

            <Text style={styles.inputLabel}>Your BTC Address (sender)</Text>
            <TextInput
              style={styles.input}
              value={btcAddress}
              onChangeText={setBtcAddress}
              placeholder="Enter your BTC address..."
              placeholderTextColor={COLORS.textMuted}
              autoCapitalize="none"
              autoCorrect={false}
            />

            <Text style={styles.inputLabel}>Pledge Message (optional)</Text>
            <TextInput
              style={[styles.input, styles.textArea]}
              value={pledgeText}
              onChangeText={setPledgeText}
              placeholder="I pledge to the Thronos Network..."
              placeholderTextColor={COLORS.textMuted}
              multiline
              numberOfLines={3}
            />

            <TouchableOpacity
              style={[styles.primaryBtn, loading && styles.btnDisabled]}
              onPress={handleSubmitPledge}
              disabled={loading}
            >
              {loading ? (
                <ActivityIndicator color={COLORS.background} />
              ) : (
                <>
                  <Ionicons name="send" size={18} color={COLORS.background} />
                  <Text style={styles.primaryBtnText}>Submit Pledge</Text>
                </>
              )}
            </TouchableOpacity>
          </>
        )}

        {/* Step: Verify */}
        {step === 'verify' && (
          <>
            <LinearGradient colors={['#0A1A0A', '#0D0D00']} style={styles.verifyCard}>
              <Ionicons name="time" size={48} color={COLORS.gold} />
              <Text style={styles.verifyTitle}>Waiting for BTC Confirmation</Text>
              <Text style={styles.verifyDesc}>
                The watcher is monitoring for your BTC payment. This usually takes a few minutes
                after the BTC transaction confirms on the Bitcoin network.
              </Text>
              {thrAddress && (
                <View style={styles.thrPreview}>
                  <Text style={styles.thrPreviewLabel}>Your THR Address (pending)</Text>
                  <Text style={styles.thrPreviewAddr}>{thrAddress}</Text>
                </View>
              )}
            </LinearGradient>

            <TouchableOpacity
              style={[styles.primaryBtn, loading && styles.btnDisabled]}
              onPress={handleVerify}
              disabled={loading}
            >
              {loading ? (
                <ActivityIndicator color={COLORS.background} />
              ) : (
                <>
                  <Ionicons name="checkmark-circle" size={20} color={COLORS.background} />
                  <Text style={styles.primaryBtnText}>Check Verification</Text>
                </>
              )}
            </TouchableOpacity>
          </>
        )}

        {/* Step: Complete */}
        {step === 'complete' && (
          <>
            <LinearGradient colors={['#001A00', '#000D05']} style={styles.completeCard}>
              <Ionicons name="checkmark-circle" size={56} color={COLORS.success} />
              <Text style={styles.completeTitle}>Welcome to Thronos!</Text>
              <Text style={styles.completeDesc}>
                Your pledge has been verified. Your THR wallet is now active and your mobile
                device has been registered as a Phantom Network node.
              </Text>
              {thrAddress && (
                <View style={styles.thrFinal}>
                  <Text style={styles.thrFinalLabel}>THR Address</Text>
                  <Text style={styles.thrFinalAddr}>{thrAddress}</Text>
                </View>
              )}
            </LinearGradient>

            {pdfUrl && (
              <TouchableOpacity
                style={styles.pdfBtn}
                onPress={() => Linking.openURL(pdfUrl)}
              >
                <Ionicons name="document" size={20} color={COLORS.gold} />
                <Text style={styles.pdfBtnText}>Download Encrypted PDF Contract</Text>
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

  // Intro
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

  // Send BTC
  sectionTitle: { fontSize: FONT_SIZES.xl, fontWeight: '700', color: COLORS.text, marginBottom: SPACING.md },
  addressCard: {
    flexDirection: 'row', alignItems: 'center', gap: SPACING.md,
    backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.lg,
    padding: SPACING.md, marginBottom: SPACING.md,
    borderWidth: 1, borderColor: '#F7931A30',
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
  textArea: { minHeight: 80, textAlignVertical: 'top' },

  // Verify
  verifyCard: {
    borderRadius: BORDER_RADIUS.xl, padding: SPACING.xl,
    alignItems: 'center', gap: SPACING.md, marginBottom: SPACING.lg,
    borderWidth: 1, borderColor: COLORS.gold + '30',
  },
  verifyTitle: { fontSize: FONT_SIZES.xl, fontWeight: '700', color: COLORS.gold, textAlign: 'center' },
  verifyDesc: { fontSize: FONT_SIZES.md, color: COLORS.textSecondary, textAlign: 'center', lineHeight: 22 },
  thrPreview: {
    backgroundColor: COLORS.background, borderRadius: BORDER_RADIUS.md,
    padding: SPACING.md, width: '100%', marginTop: SPACING.sm,
  },
  thrPreviewLabel: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, marginBottom: 4 },
  thrPreviewAddr: { fontSize: FONT_SIZES.sm, color: COLORS.gold, fontFamily: 'monospace' },

  // Complete
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

  // Buttons
  primaryBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: SPACING.sm,
    backgroundColor: COLORS.gold, borderRadius: BORDER_RADIUS.lg,
    paddingVertical: SPACING.md, marginBottom: SPACING.md,
  },
  primaryBtnText: { fontSize: FONT_SIZES.lg, fontWeight: '700', color: COLORS.background },
  btnDisabled: { opacity: 0.6 },
});
