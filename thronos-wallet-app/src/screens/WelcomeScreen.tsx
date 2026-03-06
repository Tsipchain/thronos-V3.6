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

export default function WelcomeScreen() {
  const navigation = useNavigation<Nav>();

  return (
    <SafeAreaView style={styles.container}>
      <LinearGradient colors={[COLORS.background, COLORS.backgroundLight]} style={styles.gradient}>
        <View style={styles.content}>
          {/* Logo area */}
          <View style={styles.logoArea}>
            <View style={styles.logoCircle}>
              <Ionicons name="planet" size={64} color={COLORS.gold} />
            </View>
            <Text style={styles.title}>Thronos</Text>
            <Text style={styles.subtitle}>Wallet</Text>
          </View>

          {/* Features */}
          <View style={styles.features}>
            {[
              { icon: 'shield-checkmark', text: 'Secure & Self-Custodial' },
              { icon: 'swap-horizontal', text: 'Send, Receive & Swap THR' },
              { icon: 'layers', text: 'Multi-Token Support' },
              { icon: 'flash', text: 'Fast Transactions' },
            ].map((f, i) => (
              <View key={i} style={styles.featureRow}>
                <Ionicons name={f.icon as any} size={20} color={COLORS.gold} />
                <Text style={styles.featureText}>{f.text}</Text>
              </View>
            ))}
          </View>

          {/* Actions */}
          <View style={styles.actions}>
            <TouchableOpacity
              style={styles.createButton}
              onPress={() => navigation.navigate('CreateWallet')}
            >
              <LinearGradient colors={[COLORS.gold, COLORS.goldDark]} style={styles.buttonGradient}>
                <Ionicons name="add-circle" size={24} color={COLORS.background} />
                <Text style={styles.createButtonText}>Create New Wallet</Text>
              </LinearGradient>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.importButton}
              onPress={() => navigation.navigate('ImportWallet')}
            >
              <Ionicons name="download" size={20} color={COLORS.gold} />
              <Text style={styles.importButtonText}>Import Existing Wallet</Text>
            </TouchableOpacity>
          </View>

          <Text style={styles.version}>Thronos Wallet v1.0.0</Text>
        </View>
      </LinearGradient>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.background },
  gradient: { flex: 1 },
  content: { flex: 1, paddingHorizontal: SPACING.lg, justifyContent: 'space-between', paddingBottom: SPACING.xl },
  logoArea: { alignItems: 'center', marginTop: SPACING.xxl },
  logoCircle: {
    width: 120, height: 120, borderRadius: 60,
    backgroundColor: COLORS.gold + '15',
    justifyContent: 'center', alignItems: 'center',
    borderWidth: 2, borderColor: COLORS.gold + '30',
    marginBottom: SPACING.md,
  },
  title: { fontSize: FONT_SIZES.display, fontWeight: '700', color: COLORS.gold },
  subtitle: { fontSize: FONT_SIZES.xxl, fontWeight: '300', color: COLORS.textSecondary, marginTop: -4 },
  features: { gap: SPACING.md },
  featureRow: { flexDirection: 'row', alignItems: 'center', gap: SPACING.md },
  featureText: { fontSize: FONT_SIZES.lg, color: COLORS.textSecondary },
  actions: { gap: SPACING.md },
  createButton: { borderRadius: BORDER_RADIUS.lg, overflow: 'hidden' },
  buttonGradient: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    paddingVertical: SPACING.md, gap: SPACING.sm,
  },
  createButtonText: { fontSize: FONT_SIZES.lg, fontWeight: '700', color: COLORS.background },
  importButton: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    paddingVertical: SPACING.md, gap: SPACING.sm,
    borderWidth: 1, borderColor: COLORS.gold + '40', borderRadius: BORDER_RADIUS.lg,
  },
  importButtonText: { fontSize: FONT_SIZES.lg, fontWeight: '600', color: COLORS.gold },
  version: { textAlign: 'center', fontSize: FONT_SIZES.xs, color: COLORS.textMuted },
});
