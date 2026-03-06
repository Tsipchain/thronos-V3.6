import React, { useState } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, TextInput, ActivityIndicator, Alert,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT_SIZES, BORDER_RADIUS } from '../constants/theme';
import { importWallet } from '../services/wallet';
import { useStore } from '../store/useStore';
import type { RootStackParamList } from '../../App';

type Nav = NativeStackNavigationProp<RootStackParamList>;

export default function ImportWalletScreen() {
  const navigation = useNavigation<Nav>();
  const { setWallet } = useStore();
  const [address, setAddress] = useState('');
  const [secret, setSecret] = useState('');
  const [loading, setLoading] = useState(false);

  const handleImport = async () => {
    if (!address.trim() || !secret.trim()) {
      Alert.alert('Missing Fields', 'Please enter both your address and secret key.');
      return;
    }

    setLoading(true);
    try {
      const result = await importWallet(address.trim(), secret.trim());
      setWallet({ isConnected: true, address: result.address, backedUp: true });
      navigation.reset({ index: 0, routes: [{ name: 'MainTabs' }] });
    } catch (error: any) {
      Alert.alert('Import Failed', error.message || 'Invalid credentials.');
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
          <Text style={styles.headerTitle}>Import Wallet</Text>
          <View style={{ width: 24 }} />
        </View>

        <View style={styles.content}>
          <Text style={styles.desc}>
            Enter your Thronos wallet address and secret key to restore your wallet on this device.
          </Text>

          <Text style={styles.label}>Thronos Address</Text>
          <TextInput
            style={styles.input}
            placeholder="THR..."
            placeholderTextColor={COLORS.textMuted}
            value={address}
            onChangeText={setAddress}
            autoCapitalize="none"
            autoCorrect={false}
          />

          <Text style={styles.label}>Secret Key</Text>
          <TextInput
            style={styles.input}
            placeholder="Enter your secret key"
            placeholderTextColor={COLORS.textMuted}
            value={secret}
            onChangeText={setSecret}
            autoCapitalize="none"
            autoCorrect={false}
            secureTextEntry
          />

          <View style={styles.securityNote}>
            <Ionicons name="lock-closed" size={16} color={COLORS.success} />
            <Text style={styles.securityText}>
              Your secret key is encrypted and stored locally on your device. It never leaves your phone.
            </Text>
          </View>

          <TouchableOpacity style={styles.importBtn} onPress={handleImport} disabled={loading}>
            <LinearGradient colors={[COLORS.gold, COLORS.goldDark]} style={styles.btnGradient}>
              {loading ? (
                <ActivityIndicator color={COLORS.background} />
              ) : (
                <>
                  <Ionicons name="download" size={24} color={COLORS.background} />
                  <Text style={styles.btnText}>Import Wallet</Text>
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
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: SPACING.lg, paddingVertical: SPACING.md,
  },
  headerTitle: { fontSize: FONT_SIZES.xl, fontWeight: '600', color: COLORS.text },
  content: { flex: 1, paddingHorizontal: SPACING.lg, paddingTop: SPACING.lg },
  desc: { fontSize: FONT_SIZES.md, color: COLORS.textSecondary, lineHeight: 22, marginBottom: SPACING.xl },
  label: { fontSize: FONT_SIZES.sm, color: COLORS.textSecondary, fontWeight: '600', marginBottom: SPACING.xs, marginTop: SPACING.md },
  input: {
    backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.lg, padding: SPACING.md,
    fontSize: FONT_SIZES.md, color: COLORS.text, borderWidth: 1, borderColor: COLORS.border,
  },
  securityNote: {
    flexDirection: 'row', backgroundColor: COLORS.success + '12',
    borderRadius: BORDER_RADIUS.lg, padding: SPACING.md, marginTop: SPACING.xl, gap: SPACING.sm,
    borderWidth: 1, borderColor: COLORS.success + '30',
  },
  securityText: { flex: 1, fontSize: FONT_SIZES.sm, color: COLORS.textSecondary, lineHeight: 20 },
  importBtn: { borderRadius: BORDER_RADIUS.lg, overflow: 'hidden', marginTop: SPACING.xl },
  btnGradient: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    paddingVertical: SPACING.md, gap: SPACING.sm,
  },
  btnText: { fontSize: FONT_SIZES.lg, fontWeight: '700', color: COLORS.background },
});
