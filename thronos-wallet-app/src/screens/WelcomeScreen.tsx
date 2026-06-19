import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT_SIZES, BORDER_RADIUS } from '../constants/theme';
import type { RootStackParamList } from '../../App';

type Nav = NativeStackNavigationProp<RootStackParamList, 'Welcome'>;

const FEATURES = [
  { icon: 'shield-checkmark', text: 'Secure & Self-Custodial', color: COLORS.success },
  { icon: 'swap-horizontal', text: 'Send, Receive & Swap THR', color: COLORS.info },
  { icon: 'layers', text: 'Multi-Token & Multi-Chain', color: COLORS.primary },
  { icon: 'flash', text: 'ACIC — Instant Finality', color: COLORS.gold },
] as const;

export default function WelcomeScreen() {
  const navigation = useNavigation<Nav>();

  return (
    <SafeAreaView style={styles.container}>
      <LinearGradient colors={['#0D0D1A', '#0D0A00', '#0D0D1A']} style={styles.gradient}>
        <View style={styles.content}>
          {/* Logo area */}
          <View style={styles.logoArea}>
            {/* Outer glow ring */}
            <View style={styles.logoOuter}>
              <View style={styles.logoMiddle}>
                <View style={styles.logoCircle}>
                  <Ionicons name="planet" size={64} color={COLORS.gold} />
                </View>
              </View>
            </View>
            <Text style={styles.title}>THRONOS</Text>
            <Text style={styles.subtitle}>Secure · Fast · Decentralized</Text>
          </View>

          {/* Features */}
          <View style={styles.features}>
            {FEATURES.map((f, i) => (
              <View key={i} style={styles.featureRow}>
                <View style={[styles.featureIconWrap, { backgroundColor: f.color + '20' }]}>
                  <Ionicons name={f.icon} size={18} color={f.color} />
                </View>
                <Text style={styles.featureText}>{f.text}</Text>
              </View>
            ))}
          </View>

          {/* Actions */}
          <View style={styles.actions}>
            {/* Create New Wallet button is hidden — new users enter via BTC or USDT pledge only */}
            {false && (
            <TouchableOpacity
              style={styles.createButton}
              onPress={() => navigation.navigate('CreateWallet')}
            >
              <LinearGradient colors={[COLORS.gold, COLORS.goldDark]} style={styles.buttonGradient}>
                <Ionicons name="add-circle" size={24} color={COLORS.background} />
                <Text style={styles.createButtonText}>Create New Wallet</Text>
              </LinearGradient>
            </TouchableOpacity>
            )}

            <View style={styles.pledgeRow}>
              <TouchableOpacity
                style={styles.pledgeBtn}
                onPress={() => navigation.navigate('Pledge')}
              >
                <Ionicons name="logo-bitcoin" size={18} color="#F7931A" />
                <Text style={styles.pledgeBtnText}>BTC Pledge</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.pledgeBtn, { borderColor: '#26A17B40' }]}
                onPress={() => navigation.navigate('UsdtPledge')}
              >
                <Ionicons name="cash" size={18} color="#26A17B" />
                <Text style={[styles.pledgeBtnText, { color: '#26A17B' }]}>USDT Pledge</Text>
              </TouchableOpacity>
            </View>

            <TouchableOpacity
              style={styles.importButton}
              onPress={() => navigation.navigate('ImportWallet')}
            >
              <Ionicons name="download" size={20} color={COLORS.gold} />
              <Text style={styles.importButtonText}>Import Existing Wallet</Text>
            </TouchableOpacity>
          </View>

          <Text style={styles.version}>Thronos Wallet v1.1.0 · Mainnet</Text>
        </View>
      </LinearGradient>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.background },
  gradient: { flex: 1 },
  content: { flex: 1, paddingHorizontal: SPACING.lg, justifyContent: 'space-between', paddingBottom: SPACING.xl },

  // Logo
  logoArea: { alignItems: 'center', marginTop: SPACING.xxl },
  logoOuter: {
    width: 152, height: 152, borderRadius: 76,
    borderWidth: 1, borderColor: COLORS.gold + '18',
    justifyContent: 'center', alignItems: 'center',
    marginBottom: SPACING.md,
  },
  logoMiddle: {
    width: 136, height: 136, borderRadius: 68,
    borderWidth: 1.5, borderColor: COLORS.gold + '30',
    justifyContent: 'center', alignItems: 'center',
  },
  logoCircle: {
    width: 116, height: 116, borderRadius: 58,
    backgroundColor: COLORS.gold + '15',
    justifyContent: 'center', alignItems: 'center',
    borderWidth: 2, borderColor: COLORS.gold + '50',
  },
  title: { fontSize: FONT_SIZES.display, fontWeight: '800', color: COLORS.gold, letterSpacing: 6 },
  subtitle: { fontSize: FONT_SIZES.sm, fontWeight: '400', color: COLORS.textMuted, marginTop: SPACING.xs, letterSpacing: 1 },

  // Features
  features: { gap: SPACING.md },
  featureRow: { flexDirection: 'row', alignItems: 'center', gap: SPACING.md },
  featureIconWrap: {
    width: 36, height: 36, borderRadius: BORDER_RADIUS.md,
    justifyContent: 'center', alignItems: 'center',
  },
  featureText: { fontSize: FONT_SIZES.md, color: COLORS.textSecondary, fontWeight: '500' },

  // Actions
  actions: { gap: SPACING.md },
  createButton: { borderRadius: BORDER_RADIUS.xl, overflow: 'hidden' },
  buttonGradient: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    paddingVertical: SPACING.md + 2, gap: SPACING.sm,
  },
  createButtonText: { fontSize: FONT_SIZES.lg, fontWeight: '700', color: COLORS.background },
  pledgeRow: { flexDirection: 'row', gap: SPACING.sm },
  pledgeBtn: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    paddingVertical: SPACING.md - 2, gap: SPACING.xs,
    borderWidth: 1, borderColor: '#F7931A40', borderRadius: BORDER_RADIUS.xl,
    backgroundColor: COLORS.surface,
  },
  pledgeBtnText: { fontSize: FONT_SIZES.md, fontWeight: '600', color: '#F7931A' },

  importButton: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    paddingVertical: SPACING.md, gap: SPACING.sm,
    borderWidth: 1, borderColor: COLORS.gold + '40', borderRadius: BORDER_RADIUS.xl,
    backgroundColor: COLORS.gold + '05',
  },
  importButtonText: { fontSize: FONT_SIZES.lg, fontWeight: '600', color: COLORS.gold },
  version: { textAlign: 'center', fontSize: FONT_SIZES.xs, color: COLORS.textMuted, letterSpacing: 1 },
});
