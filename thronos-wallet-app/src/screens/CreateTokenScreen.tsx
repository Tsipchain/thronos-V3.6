import React, { useCallback, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  Alert,
  ActivityIndicator,
  ScrollView,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT_SIZES, BORDER_RADIUS } from '../constants/theme';
import { useStore } from '../store/useStore';
import { createToken } from '../services/api';
import { getWallet, getPrivateKey } from '../services/wallet';

export default function CreateTokenScreen({ navigation }: { navigation: any }) {
  const { wallet } = useStore();
  const [name, setName] = useState('');
  const [symbol, setSymbol] = useState('');
  const [totalSupply, setTotalSupply] = useState('');
  const [decimals, setDecimals] = useState('8');
  const [submitting, setSubmitting] = useState(false);

  const canSubmit =
    name.trim().length > 0 &&
    /^[A-Z0-9]{1,8}$/.test(symbol.trim()) &&
    parseFloat(totalSupply) > 0 &&
    !isNaN(parseInt(decimals, 10));

  const handleCreate = useCallback(async () => {
    if (!canSubmit) {
      Alert.alert('Invalid form', 'Fill in a name, a 1-8 char uppercase symbol, and a positive total supply.');
      return;
    }
    setSubmitting(true);
    try {
      const creds = await getWallet();
      const privHex = await getPrivateKey();
      if (!creds?.address || !privHex) {
        Alert.alert('Error', 'Wallet credentials not found.');
        return;
      }
      const result = await createToken({
        from: creds.address,
        name: name.trim(),
        symbol: symbol.trim().toUpperCase(),
        total_supply: parseFloat(totalSupply),
        decimals: parseInt(decimals, 10) || 8,
        private_key_hex: privHex,
      });
      if (result.ok) {
        Alert.alert('Token Created', `${symbol.trim().toUpperCase()} has been created on Thronos.`, [
          { text: 'OK', onPress: () => navigation.goBack() },
        ]);
      } else {
        Alert.alert('Failed', result.error || 'Token creation failed.');
      }
    } catch (error: any) {
      Alert.alert('Failed', error.message || 'An unexpected error occurred.');
    } finally {
      setSubmitting(false);
    }
  }, [canSubmit, name, symbol, totalSupply, decimals, navigation]);

  return (
    <SafeAreaView style={styles.container}>
      <LinearGradient colors={[COLORS.background, COLORS.backgroundLight]} style={styles.gradient}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
            <Ionicons name="arrow-back" size={24} color={COLORS.text} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Create Token</Text>
          <View style={{ width: 24 }} />
        </View>

        <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent} keyboardShouldPersistTaps="handled">
          <View style={styles.iconWrap}>
            <LinearGradient colors={[COLORS.gold, COLORS.goldDark]} style={styles.icon}>
              <Ionicons name="add-circle" size={32} color={COLORS.background} />
            </LinearGradient>
          </View>
          <Text style={styles.intro}>
            Launch your own experimental token on the Thronos network. Anyone can hold and trade it once created.
          </Text>

          <Text style={styles.label}>Token Name</Text>
          <TextInput
            style={styles.input}
            placeholder="e.g. My Awesome Token"
            placeholderTextColor={COLORS.textMuted}
            value={name}
            onChangeText={setName}
            maxLength={64}
          />

          <Text style={styles.label}>Symbol (1-8 chars)</Text>
          <TextInput
            style={styles.input}
            placeholder="e.g. MAT"
            placeholderTextColor={COLORS.textMuted}
            value={symbol}
            onChangeText={(t) => setSymbol(t.toUpperCase())}
            autoCapitalize="characters"
            maxLength={8}
          />

          <Text style={styles.label}>Total Supply</Text>
          <TextInput
            style={styles.input}
            placeholder="e.g. 1000000"
            placeholderTextColor={COLORS.textMuted}
            value={totalSupply}
            onChangeText={setTotalSupply}
            keyboardType="decimal-pad"
          />

          <Text style={styles.label}>Decimals</Text>
          <TextInput
            style={styles.input}
            placeholder="8"
            placeholderTextColor={COLORS.textMuted}
            value={decimals}
            onChangeText={setDecimals}
            keyboardType="number-pad"
            maxLength={2}
          />

          <TouchableOpacity
            style={[styles.createBtn, !canSubmit && styles.createBtnDisabled]}
            onPress={handleCreate}
            disabled={!canSubmit || submitting}
            activeOpacity={0.8}
          >
            <LinearGradient
              colors={canSubmit ? [COLORS.gold, COLORS.goldDark] : [COLORS.surfaceLight, COLORS.surface]}
              style={styles.createBtnGradient}
            >
              {submitting ? (
                <ActivityIndicator color={canSubmit ? COLORS.background : COLORS.textMuted} />
              ) : (
                <Text style={[styles.createBtnText, !canSubmit && { color: COLORS.textMuted }]}>Create Token</Text>
              )}
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
  scroll: { flex: 1 },
  scrollContent: { paddingHorizontal: SPACING.lg, paddingBottom: SPACING.xxl },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.lg, paddingVertical: SPACING.md },
  headerTitle: { fontSize: FONT_SIZES.xl, fontWeight: '700', color: COLORS.text },
  iconWrap: { alignItems: 'center', marginVertical: SPACING.lg },
  icon: { width: 64, height: 64, borderRadius: 32, alignItems: 'center', justifyContent: 'center' },
  intro: { fontSize: FONT_SIZES.sm, color: COLORS.textSecondary, textAlign: 'center', lineHeight: 20, marginBottom: SPACING.lg },
  label: { fontSize: FONT_SIZES.sm, fontWeight: '600', color: COLORS.textSecondary, marginBottom: SPACING.xs, marginTop: SPACING.sm, textTransform: 'uppercase', letterSpacing: 0.5 },
  input: { backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.lg, borderWidth: 1, borderColor: COLORS.border, padding: SPACING.md, fontSize: FONT_SIZES.lg, color: COLORS.text },
  createBtn: { borderRadius: BORDER_RADIUS.lg, overflow: 'hidden', marginTop: SPACING.xl },
  createBtnDisabled: { elevation: 0 },
  createBtnGradient: { paddingVertical: SPACING.md + 2, alignItems: 'center', justifyContent: 'center' },
  createBtnText: { fontSize: FONT_SIZES.lg, fontWeight: '700', color: COLORS.background },
});
