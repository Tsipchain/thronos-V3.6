import React, { useState } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ActivityIndicator, ScrollView, Alert,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import * as Clipboard from 'expo-clipboard';
import { COLORS, SPACING, FONT_SIZES, BORDER_RADIUS } from '../constants/theme';
import { createNewWallet, markBackedUp, generateMnemonic } from '../services/wallet';
import { useStore } from '../store/useStore';
import type { RootStackParamList } from '../../App';

type Nav = NativeStackNavigationProp<RootStackParamList>;

export default function CreateWalletScreen() {
  const navigation = useNavigation<Nav>();
  const { setWallet } = useStore();
  const [loading, setLoading] = useState(false);
  const [wallet, setCreatedWallet] = useState<{ address: string; secret: string; mnemonic?: string } | null>(null);
  const [secretCopied, setSecretCopied] = useState(false);
  const [addressCopied, setAddressCopied] = useState(false);
  const [mnemonicCopied, setMnemonicCopied] = useState(false);

  const handleCreate = async () => {
    setLoading(true);
    try {
      const mnemonic = generateMnemonic();
      const result = await createNewWallet(mnemonic);
      setCreatedWallet(result);
    } catch (error: any) {
      Alert.alert('Error', error.message || 'Failed to create wallet. Check your connection.');
    } finally {
      setLoading(false);
    }
  };

  const copyMnemonic = async () => {
    if (wallet?.mnemonic) {
      await Clipboard.setStringAsync(wallet.mnemonic);
      setMnemonicCopied(true);
      setTimeout(() => setMnemonicCopied(false), 3000);
    }
  };

  const copySecret = async () => {
    if (wallet) {
      await Clipboard.setStringAsync(wallet.secret);
      setSecretCopied(true);
      setTimeout(() => setSecretCopied(false), 3000);
    }
  };

  const copyAddress = async () => {
    if (wallet) {
      await Clipboard.setStringAsync(wallet.address);
      setAddressCopied(true);
      setTimeout(() => setAddressCopied(false), 3000);
    }
  };

  const handleContinue = async () => {
    if (!wallet) return;
    await markBackedUp();
    setWallet({
      isConnected: true,
      address: wallet.address,
      backedUp: true,
      hasMnemonic: !!wallet.mnemonic,
      activeChain: 'thronos',
      chainAddresses: { thronos: wallet.address, bitcoin: null, ethereum: null },
    });
    navigation.reset({ index: 0, routes: [{ name: 'MainTabs' }] });
  };

  if (!wallet) {
    return (
      <SafeAreaView style={styles.container}>
        <LinearGradient colors={[COLORS.background, COLORS.backgroundLight]} style={styles.gradient}>
          <View style={styles.header}>
            <TouchableOpacity onPress={() => navigation.goBack()}>
              <Ionicons name="arrow-back" size={24} color={COLORS.text} />
            </TouchableOpacity>
            <Text style={styles.headerTitle}>Create Wallet</Text>
            <View style={{ width: 24 }} />
          </View>

          <View style={styles.centerContent}>
            <View style={styles.iconCircle}>
              <Ionicons name="planet" size={56} color={COLORS.gold} />
            </View>
            <Text style={styles.title}>Create Your Thronos Wallet</Text>
            <Text style={styles.desc}>
              Your wallet will be created on the Thronos blockchain. You'll receive a unique address and a secret key that you must keep safe.
            </Text>

            <TouchableOpacity style={styles.createBtn} onPress={handleCreate} disabled={loading}>
              <LinearGradient colors={[COLORS.gold, COLORS.goldDark]} style={styles.btnGradient}>
                {loading ? (
                  <ActivityIndicator color={COLORS.background} />
                ) : (
                  <>
                    <Ionicons name="add-circle" size={24} color={COLORS.background} />
                    <Text style={styles.btnText}>Generate Wallet</Text>
                  </>
                )}
              </LinearGradient>
            </TouchableOpacity>
          </View>
        </LinearGradient>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <LinearGradient colors={[COLORS.background, COLORS.backgroundLight]} style={styles.gradient}>
        <View style={styles.header}>
          <View style={{ width: 24 }} />
          <Text style={styles.headerTitle}>Wallet Created</Text>
          <View style={{ width: 24 }} />
        </View>

        <ScrollView style={styles.scrollContent} showsVerticalScrollIndicator={false}>
          <View style={styles.successIcon}>
            <Ionicons name="checkmark-circle" size={64} color={COLORS.success} />
          </View>
          <Text style={styles.successText}>Your wallet is ready!</Text>

          {/* Address */}
          <TouchableOpacity style={styles.credBox} onPress={copyAddress}>
            <Text style={styles.credLabel}>Address</Text>
            <Text style={styles.credValue} selectable>{wallet.address}</Text>
            <View style={styles.copyRow}>
              <Ionicons name={addressCopied ? 'checkmark' : 'copy-outline'} size={16} color={COLORS.gold} />
              <Text style={styles.copyText}>{addressCopied ? 'Copied!' : 'Tap to copy'}</Text>
            </View>
          </TouchableOpacity>

          {/* Secret */}
          <TouchableOpacity style={[styles.credBox, styles.secretBox]} onPress={copySecret}>
            <Text style={styles.credLabel}>
              <Ionicons name="key" size={14} color={COLORS.warning} /> Secret Key
            </Text>
            <Text style={styles.credValue} selectable>{wallet.secret}</Text>
            <View style={styles.copyRow}>
              <Ionicons name={secretCopied ? 'checkmark' : 'copy-outline'} size={16} color={COLORS.warning} />
              <Text style={[styles.copyText, { color: COLORS.warning }]}>{secretCopied ? 'Copied!' : 'Tap to copy'}</Text>
            </View>
          </TouchableOpacity>

          {/* Recovery Phrase */}
          {wallet.mnemonic && (
            <TouchableOpacity style={[styles.credBox, styles.mnemonicBox]} onPress={copyMnemonic}>
              <Text style={styles.credLabel}>
                <Ionicons name="shield-checkmark" size={14} color={COLORS.primary} /> Recovery Phrase (12 words)
              </Text>
              <View style={styles.mnemonicGrid}>
                {wallet.mnemonic.split(' ').map((word, i) => (
                  <View key={i} style={styles.mnemonicWord}>
                    <Text style={styles.mnemonicIndex}>{i + 1}.</Text>
                    <Text style={styles.mnemonicText}>{word}</Text>
                  </View>
                ))}
              </View>
              <View style={styles.copyRow}>
                <Ionicons name={mnemonicCopied ? 'checkmark' : 'copy-outline'} size={16} color={COLORS.primary} />
                <Text style={[styles.copyText, { color: COLORS.primary }]}>{mnemonicCopied ? 'Copied!' : 'Tap to copy'}</Text>
              </View>
            </TouchableOpacity>
          )}

          {/* Warning */}
          <View style={styles.warningBox}>
            <Ionicons name="alert-circle" size={24} color={COLORS.error} />
            <View style={{ flex: 1 }}>
              <Text style={styles.warningTitle}>IMPORTANT - Save Your Recovery Phrase!</Text>
              <Text style={styles.warningText}>
                Write down your 12-word recovery phrase on paper and store it safely. This is the ONLY way to recover your wallet. We do NOT store your keys or phrase.
              </Text>
            </View>
          </View>

          <TouchableOpacity style={styles.continueBtn} onPress={handleContinue}>
            <LinearGradient colors={[COLORS.success, '#059669']} style={styles.btnGradient}>
              <Ionicons name="checkmark-circle" size={24} color={COLORS.text} />
              <Text style={[styles.btnText, { color: COLORS.text }]}>I've Saved My Key - Continue</Text>
            </LinearGradient>
          </TouchableOpacity>

          <View style={{ height: SPACING.xxl }} />
        </ScrollView>
      </LinearGradient>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.background },
  gradient: { flex: 1 },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: SPACING.lg, paddingVertical: SPACING.md,
  },
  headerTitle: { fontSize: FONT_SIZES.xl, fontWeight: '600', color: COLORS.text },
  centerContent: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingHorizontal: SPACING.lg },
  iconCircle: {
    width: 100, height: 100, borderRadius: 50,
    backgroundColor: COLORS.gold + '15', justifyContent: 'center', alignItems: 'center',
    borderWidth: 2, borderColor: COLORS.gold + '30', marginBottom: SPACING.lg,
  },
  title: { fontSize: FONT_SIZES.xxl, fontWeight: '700', color: COLORS.text, textAlign: 'center' },
  desc: { fontSize: FONT_SIZES.md, color: COLORS.textSecondary, textAlign: 'center', marginTop: SPACING.md, lineHeight: 22 },
  createBtn: { borderRadius: BORDER_RADIUS.lg, overflow: 'hidden', marginTop: SPACING.xl, width: '100%' },
  btnGradient: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    paddingVertical: SPACING.md, gap: SPACING.sm,
  },
  btnText: { fontSize: FONT_SIZES.lg, fontWeight: '700', color: COLORS.background },
  scrollContent: { flex: 1, paddingHorizontal: SPACING.lg },
  successIcon: { alignItems: 'center', marginTop: SPACING.lg, marginBottom: SPACING.sm },
  successText: { fontSize: FONT_SIZES.xxl, fontWeight: '700', color: COLORS.success, textAlign: 'center', marginBottom: SPACING.xl },
  credBox: {
    backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.lg,
    padding: SPACING.md, marginBottom: SPACING.md,
    borderWidth: 1, borderColor: COLORS.border,
  },
  secretBox: { borderColor: COLORS.warning + '50', backgroundColor: COLORS.warning + '08' },
  mnemonicBox: { borderColor: COLORS.primary + '50', backgroundColor: COLORS.primary + '08' },
  mnemonicGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: SPACING.xs, marginTop: SPACING.sm },
  mnemonicWord: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.sm,
    paddingHorizontal: SPACING.sm, paddingVertical: SPACING.xs,
    borderWidth: 1, borderColor: COLORS.border,
  },
  mnemonicIndex: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, fontWeight: '600' },
  mnemonicText: { fontSize: FONT_SIZES.sm, color: COLORS.text, fontWeight: '500' },
  credLabel: { fontSize: FONT_SIZES.sm, color: COLORS.textSecondary, fontWeight: '600', marginBottom: SPACING.xs },
  credValue: { fontSize: FONT_SIZES.md, color: COLORS.text, fontFamily: 'monospace' },
  copyRow: { flexDirection: 'row', alignItems: 'center', gap: SPACING.xs, marginTop: SPACING.sm },
  copyText: { fontSize: FONT_SIZES.xs, color: COLORS.gold },
  warningBox: {
    flexDirection: 'row', backgroundColor: COLORS.error + '12',
    borderRadius: BORDER_RADIUS.lg, padding: SPACING.md, gap: SPACING.sm,
    borderWidth: 1, borderColor: COLORS.error + '30', marginBottom: SPACING.lg,
  },
  warningTitle: { fontSize: FONT_SIZES.md, fontWeight: '700', color: COLORS.error, marginBottom: SPACING.xs },
  warningText: { fontSize: FONT_SIZES.sm, color: COLORS.textSecondary, lineHeight: 20 },
  continueBtn: { borderRadius: BORDER_RADIUS.lg, overflow: 'hidden' },
});
