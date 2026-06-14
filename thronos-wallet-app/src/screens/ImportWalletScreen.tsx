import React, { useState } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, TextInput,
  ActivityIndicator, Alert, ScrollView,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import * as DocumentPicker from 'expo-document-picker';
import { COLORS, SPACING, FONT_SIZES, BORDER_RADIUS } from '../constants/theme';
import {
  importWallet, importWalletFromRecoveryJson,
  isBiometricAvailable, authenticateWithBiometrics, setBiometricEnabled,
} from '../services/wallet';
import { useStore } from '../store/useStore';
import type { RootStackParamList } from '../../App';

type Nav = NativeStackNavigationProp<RootStackParamList>;
type Tab = 'recovery' | 'secret';

export default function ImportWalletScreen() {
  const navigation = useNavigation<Nav>();
  const { setWallet } = useStore();
  const [tab, setTab]               = useState<Tab>('recovery');
  const [loading, setLoading]       = useState(false);
  const [recoveryFile, setRecoveryFile] = useState<{ name: string; uri: string } | null>(null);
  const [recoveryPin, setRecoveryPin]   = useState('');
  const [address, setAddress]       = useState('');
  const [secret, setSecret]         = useState('');

  const pickFile = async () => {
    try {
      const r = await DocumentPicker.getDocumentAsync({
        type: 'application/json',
        copyToCacheDirectory: true,
      });
      if (!r.canceled && r.assets?.[0]) {
        setRecoveryFile({ name: r.assets[0].name, uri: r.assets[0].uri });
      }
    } catch {
      Alert.alert('Error', 'Could not open file picker');
    }
  };

  const afterImport = async (addr: string) => {
    setWallet({ isConnected: true, address: addr, backedUp: true });
    const hasBio = await isBiometricAvailable();
    if (hasBio) {
      Alert.alert(
        'Enable Face ID / Biometrics',
        'Use biometrics to unlock your wallet quickly?',
        [
          {
            text: 'Enable',
            onPress: async () => {
              const ok = await authenticateWithBiometrics('Set up biometric unlock');
              if (ok) await setBiometricEnabled(true);
              navigation.reset({ index: 0, routes: [{ name: 'MainTabs' }] });
            },
          },
          {
            text: 'Skip',
            style: 'cancel',
            onPress: () => navigation.reset({ index: 0, routes: [{ name: 'MainTabs' }] }),
          },
        ],
      );
    } else {
      navigation.reset({ index: 0, routes: [{ name: 'MainTabs' }] });
    }
  };

  const handleRecovery = async () => {
    if (!recoveryFile) return Alert.alert('No File', 'Select your recovery kit JSON file first.');
    if (!recoveryPin.trim()) return Alert.alert('PIN Required', 'Enter your wallet PIN.');
    setLoading(true);
    try {
      const resp = await fetch(recoveryFile.uri);
      const text = await resp.text();
      const result = await importWalletFromRecoveryJson(text, recoveryPin.trim());
      await afterImport(result.address);
    } catch (e: any) {
      const m = e.message || '';
      if (m === 'wrong_pin') {
        Alert.alert('Wrong PIN', 'Decryption failed. Check your PIN and try again.');
      } else if (m.includes('Unrecognized')) {
        Alert.alert('Invalid File', 'This is not a recognised Thronos recovery kit.');
      } else {
        Alert.alert('Import Failed', m || 'Could not import wallet.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSecret = async () => {
    if (!address.trim() || !secret.trim())
      return Alert.alert('Missing Fields', 'Enter both your address and secret key.');
    setLoading(true);
    try {
      const result = await importWallet(address.trim(), secret.trim());
      await afterImport(result.address);
    } catch (e: any) {
      Alert.alert('Import Failed', e.message || 'Invalid credentials.');
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
          <Text style={styles.title}>Import Wallet</Text>
          <View style={{ width: 24 }} />
        </View>

        {/* Tab switcher */}
        <View style={styles.tabRow}>
          <TouchableOpacity
            style={[styles.tab, tab === 'recovery' && styles.tabActive]}
            onPress={() => setTab('recovery')}
          >
            <Ionicons name="document-text" size={15} color={tab === 'recovery' ? COLORS.background : COLORS.textMuted} />
            <Text style={[styles.tabLabel, tab === 'recovery' && styles.tabLabelActive]}>Recovery JSON</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.tab, tab === 'secret' && styles.tabActive]}
            onPress={() => setTab('secret')}
          >
            <Ionicons name="key" size={15} color={tab === 'secret' ? COLORS.background : COLORS.textMuted} />
            <Text style={[styles.tabLabel, tab === 'secret' && styles.tabLabelActive]}>Address + Secret</Text>
          </TouchableOpacity>
        </View>

        <ScrollView style={styles.scroll} contentContainerStyle={styles.content}>
          {tab === 'recovery' ? (
            <>
              <Text style={styles.desc}>
                Import using your{' '}
                <Text style={{ color: COLORS.gold }}>wallet-recovery-kit-THR*.json</Text>
                {' '}file and the PIN you set when creating your wallet.
              </Text>

              <TouchableOpacity style={styles.filePicker} onPress={pickFile}>
                <Ionicons name="folder-open" size={22} color={COLORS.gold} />
                <Text style={styles.filePickerText} numberOfLines={1}>
                  {recoveryFile ? recoveryFile.name : 'Select recovery kit JSON file…'}
                </Text>
              </TouchableOpacity>

              <Text style={styles.label}>Wallet PIN</Text>
              <TextInput
                style={styles.input}
                placeholder="Enter your wallet PIN"
                placeholderTextColor={COLORS.textMuted}
                value={recoveryPin}
                onChangeText={setRecoveryPin}
                secureTextEntry
                autoCapitalize="none"
              />

              <TouchableOpacity style={styles.btn} onPress={handleRecovery} disabled={loading}>
                <LinearGradient colors={[COLORS.gold, COLORS.goldDark]} style={styles.btnInner}>
                  {loading
                    ? <ActivityIndicator color={COLORS.background} />
                    : (<><Ionicons name="lock-open" size={22} color={COLORS.background} />
                        <Text style={styles.btnText}>Unlock &amp; Import</Text></>)
                  }
                </LinearGradient>
              </TouchableOpacity>
            </>
          ) : (
            <>
              <Text style={styles.desc}>
                Enter your Thronos address and send secret to connect your wallet.
              </Text>

              <Text style={styles.label}>Thronos Address</Text>
              <TextInput
                style={styles.input}
                placeholder="THR…"
                placeholderTextColor={COLORS.textMuted}
                value={address}
                onChangeText={setAddress}
                autoCapitalize="characters"
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

              <TouchableOpacity style={styles.btn} onPress={handleSecret} disabled={loading}>
                <LinearGradient colors={[COLORS.gold, COLORS.goldDark]} style={styles.btnInner}>
                  {loading
                    ? <ActivityIndicator color={COLORS.background} />
                    : (<><Ionicons name="download" size={22} color={COLORS.background} />
                        <Text style={styles.btnText}>Import Wallet</Text></>)
                  }
                </LinearGradient>
              </TouchableOpacity>
            </>
          )}

          <View style={styles.note}>
            <Ionicons name="shield-checkmark" size={16} color={COLORS.success} />
            <Text style={styles.noteText}>
              Your keys are encrypted and stored only on this device. They never leave your phone.
            </Text>
          </View>
        </ScrollView>
      </LinearGradient>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container:      { flex: 1, backgroundColor: COLORS.background },
  gradient:       { flex: 1 },
  header:         { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
                    paddingHorizontal: SPACING.lg, paddingVertical: SPACING.md },
  title:          { fontSize: FONT_SIZES.xl, fontWeight: '600', color: COLORS.text },
  tabRow:         { flexDirection: 'row', marginHorizontal: SPACING.lg, marginBottom: SPACING.md,
                    backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.lg, padding: 4 },
  tab:            { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
                    paddingVertical: SPACING.sm, borderRadius: BORDER_RADIUS.md, gap: 6 },
  tabActive:      { backgroundColor: COLORS.gold },
  tabLabel:       { fontSize: FONT_SIZES.sm, fontWeight: '600', color: COLORS.textMuted },
  tabLabelActive: { color: COLORS.background },
  scroll:         { flex: 1 },
  content:        { paddingHorizontal: SPACING.lg, paddingBottom: SPACING.xl },
  desc:           { fontSize: FONT_SIZES.md, color: COLORS.textSecondary, lineHeight: 22, marginBottom: SPACING.lg },
  filePicker:     { flexDirection: 'row', alignItems: 'center', gap: SPACING.sm,
                    backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.lg,
                    padding: SPACING.md, borderWidth: 1, borderColor: COLORS.gold + '40',
                    borderStyle: 'dashed', marginBottom: SPACING.md },
  filePickerText: { flex: 1, fontSize: FONT_SIZES.md, color: COLORS.textSecondary },
  label:          { fontSize: FONT_SIZES.sm, color: COLORS.textSecondary, fontWeight: '600',
                    marginBottom: SPACING.xs, marginTop: SPACING.md },
  input:          { backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.lg,
                    padding: SPACING.md, fontSize: FONT_SIZES.md, color: COLORS.text,
                    borderWidth: 1, borderColor: COLORS.border },
  btn:            { borderRadius: BORDER_RADIUS.lg, overflow: 'hidden', marginTop: SPACING.xl },
  btnInner:       { flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
                    paddingVertical: SPACING.md, gap: SPACING.sm },
  btnText:        { fontSize: FONT_SIZES.lg, fontWeight: '700', color: COLORS.background },
  note:           { flexDirection: 'row', backgroundColor: COLORS.success + '12',
                    borderRadius: BORDER_RADIUS.lg, padding: SPACING.md, marginTop: SPACING.xl,
                    gap: SPACING.sm, borderWidth: 1, borderColor: COLORS.success + '30' },
  noteText:       { flex: 1, fontSize: FONT_SIZES.sm, color: COLORS.textSecondary, lineHeight: 20 },
});
