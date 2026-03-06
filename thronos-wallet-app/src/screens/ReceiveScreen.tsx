import React, { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import * as Clipboard from 'expo-clipboard';
import { COLORS, SPACING, FONT_SIZES, BORDER_RADIUS } from '../constants/theme';
import { useStore } from '../store/useStore';

export default function ReceiveScreen() {
  const navigation = useNavigation();
  const { wallet } = useStore();
  const [copied, setCopied] = useState(false);

  const copyAddress = async () => {
    if (wallet.address) {
      await Clipboard.setStringAsync(wallet.address);
      setCopied(true);
      setTimeout(() => setCopied(false), 3000);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <LinearGradient colors={[COLORS.background, COLORS.backgroundLight]} style={styles.gradient}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()}>
            <Ionicons name="arrow-back" size={24} color={COLORS.text} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Receive</Text>
          <View style={{ width: 24 }} />
        </View>

        <View style={styles.content}>
          {/* QR Code placeholder - in production use react-native-qrcode-svg */}
          <View style={styles.qrBox}>
            <View style={styles.qrPlaceholder}>
              <Ionicons name="qr-code" size={120} color={COLORS.gold} />
            </View>
            <Text style={styles.qrHint}>Scan this QR code to send tokens to this wallet</Text>
          </View>

          {/* Address */}
          <View style={styles.addressBox}>
            <Text style={styles.addressLabel}>Your Thronos Address</Text>
            <Text style={styles.addressValue} selectable>{wallet.address || '...'}</Text>
          </View>

          <TouchableOpacity style={styles.copyBtn} onPress={copyAddress}>
            <LinearGradient colors={[COLORS.gold, COLORS.goldDark]} style={styles.btnGradient}>
              <Ionicons name={copied ? 'checkmark-circle' : 'copy'} size={20} color={COLORS.background} />
              <Text style={styles.btnText}>{copied ? 'Copied!' : 'Copy Address'}</Text>
            </LinearGradient>
          </TouchableOpacity>

          <View style={styles.note}>
            <Ionicons name="information-circle" size={16} color={COLORS.info} />
            <Text style={styles.noteText}>
              Only send Thronos chain tokens (THR, WBTC, L2E, etc.) to this address. Sending tokens from other blockchains may result in permanent loss.
            </Text>
          </View>
        </View>
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
  content: { flex: 1, paddingHorizontal: SPACING.lg, alignItems: 'center', paddingTop: SPACING.xl },
  qrBox: { alignItems: 'center', marginBottom: SPACING.xl },
  qrPlaceholder: {
    width: 200, height: 200, backgroundColor: COLORS.text, borderRadius: BORDER_RADIUS.xl,
    justifyContent: 'center', alignItems: 'center', marginBottom: SPACING.md,
  },
  qrHint: { fontSize: FONT_SIZES.sm, color: COLORS.textMuted, textAlign: 'center' },
  addressBox: {
    width: '100%', backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.lg,
    padding: SPACING.md, marginBottom: SPACING.lg, borderWidth: 1, borderColor: COLORS.border,
  },
  addressLabel: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, marginBottom: SPACING.xs },
  addressValue: { fontSize: FONT_SIZES.sm, color: COLORS.text, fontFamily: 'monospace' },
  copyBtn: { borderRadius: BORDER_RADIUS.lg, overflow: 'hidden', width: '100%' },
  btnGradient: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    paddingVertical: SPACING.md, gap: SPACING.sm,
  },
  btnText: { fontSize: FONT_SIZES.lg, fontWeight: '700', color: COLORS.background },
  note: {
    flexDirection: 'row', backgroundColor: COLORS.info + '12', borderRadius: BORDER_RADIUS.lg,
    padding: SPACING.md, marginTop: SPACING.xl, gap: SPACING.sm,
    borderWidth: 1, borderColor: COLORS.info + '30',
  },
  noteText: { flex: 1, fontSize: FONT_SIZES.sm, color: COLORS.textSecondary, lineHeight: 20 },
});
