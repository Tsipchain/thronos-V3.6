import React, { useState } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, TextInput, Alert, ActivityIndicator, ScrollView,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT_SIZES, BORDER_RADIUS } from '../constants/theme';
import { useStore } from '../store/useStore';
import { getWallet, isValidAddress } from '../services/wallet';
import { sendTHR, sendToken } from '../services/api';

export default function SendScreen() {
  const navigation = useNavigation();
  const { wallet, tokens } = useStore();
  const [recipient, setRecipient] = useState('');
  const [amount, setAmount] = useState('');
  const [selectedToken, setSelectedToken] = useState('THR');
  const [sending, setSending] = useState(false);

  const currentToken = tokens.find((t) => t.symbol === selectedToken);
  const availableBalance = currentToken?.balance ?? 0;

  const handleSend = async () => {
    if (!recipient.trim()) {
      Alert.alert('Error', 'Please enter a recipient address.');
      return;
    }
    if (!isValidAddress(recipient.trim())) {
      Alert.alert('Error', 'Invalid Thronos address. Must start with THR.');
      return;
    }
    const amt = parseFloat(amount);
    if (!amt || amt <= 0) {
      Alert.alert('Error', 'Please enter a valid amount.');
      return;
    }
    if (amt > availableBalance) {
      Alert.alert('Insufficient Balance', `You only have ${availableBalance} ${selectedToken}.`);
      return;
    }

    const creds = await getWallet();
    if (!creds) {
      Alert.alert('Error', 'Wallet not found. Please re-import.');
      return;
    }

    Alert.alert(
      'Confirm Transaction',
      `Send ${amt} ${selectedToken} to ${recipient.slice(0, 12)}...?`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Send',
          onPress: async () => {
            setSending(true);
            try {
              const result = selectedToken === 'THR'
                ? await sendTHR({ from: creds.address, to: recipient.trim(), amount: amt, secret: creds.secret })
                : await sendToken({ symbol: selectedToken, from: creds.address, to: recipient.trim(), amount: amt, secret: creds.secret });

              if (result.success) {
                Alert.alert('Success', `${amt} ${selectedToken} sent successfully!`, [
                  { text: 'OK', onPress: () => navigation.goBack() },
                ]);
              } else {
                Alert.alert('Failed', result.error || 'Transaction failed.');
              }
            } catch (error: any) {
              Alert.alert('Error', error.message || 'Transaction failed.');
            } finally {
              setSending(false);
            }
          },
        },
      ],
    );
  };

  return (
    <SafeAreaView style={styles.container}>
      <LinearGradient colors={[COLORS.background, COLORS.backgroundLight]} style={styles.gradient}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()}>
            <Ionicons name="arrow-back" size={24} color={COLORS.text} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Send</Text>
          <View style={{ width: 24 }} />
        </View>

        <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
          {/* Token selector */}
          <Text style={styles.label}>Token</Text>
          <View style={styles.tokenRow}>
            {['THR', ...tokens.filter((t) => t.symbol !== 'THR' && t.balance > 0).map((t) => t.symbol)].map((sym) => (
              <TouchableOpacity
                key={sym}
                style={[styles.tokenChip, selectedToken === sym && styles.tokenChipActive]}
                onPress={() => setSelectedToken(sym)}
              >
                <Text style={[styles.tokenChipText, selectedToken === sym && styles.tokenChipTextActive]}>{sym}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <Text style={styles.balanceInfo}>Available: {availableBalance.toLocaleString()} {selectedToken}</Text>

          {/* Recipient */}
          <Text style={styles.label}>Recipient Address</Text>
          <TextInput
            style={styles.input}
            placeholder="THR..."
            placeholderTextColor={COLORS.textMuted}
            value={recipient}
            onChangeText={setRecipient}
            autoCapitalize="none"
            autoCorrect={false}
          />

          {/* Amount */}
          <Text style={styles.label}>Amount</Text>
          <View style={styles.amountRow}>
            <TextInput
              style={[styles.input, { flex: 1 }]}
              placeholder="0.00"
              placeholderTextColor={COLORS.textMuted}
              value={amount}
              onChangeText={setAmount}
              keyboardType="decimal-pad"
            />
            <TouchableOpacity
              style={styles.maxBtn}
              onPress={() => setAmount(String(availableBalance))}
            >
              <Text style={styles.maxText}>MAX</Text>
            </TouchableOpacity>
          </View>

          {/* Send button */}
          <TouchableOpacity style={styles.sendBtn} onPress={handleSend} disabled={sending}>
            <LinearGradient colors={[COLORS.gold, COLORS.goldDark]} style={styles.btnGradient}>
              {sending ? (
                <ActivityIndicator color={COLORS.background} />
              ) : (
                <>
                  <Ionicons name="send" size={20} color={COLORS.background} />
                  <Text style={styles.btnText}>Send {selectedToken}</Text>
                </>
              )}
            </LinearGradient>
          </TouchableOpacity>
        </ScrollView>
      </LinearGradient>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.background },
  gradient: { flex: 1 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.lg, paddingVertical: SPACING.md },
  headerTitle: { fontSize: FONT_SIZES.xl, fontWeight: '600', color: COLORS.text },
  content: { flex: 1, paddingHorizontal: SPACING.lg },
  label: { fontSize: FONT_SIZES.sm, color: COLORS.textSecondary, fontWeight: '600', marginBottom: SPACING.xs, marginTop: SPACING.lg },
  tokenRow: { flexDirection: 'row', flexWrap: 'wrap', gap: SPACING.sm },
  tokenChip: {
    paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm,
    borderRadius: BORDER_RADIUS.full, borderWidth: 1, borderColor: COLORS.border,
    backgroundColor: COLORS.surface,
  },
  tokenChipActive: { borderColor: COLORS.gold, backgroundColor: COLORS.gold + '20' },
  tokenChipText: { fontSize: FONT_SIZES.sm, color: COLORS.textSecondary, fontWeight: '600' },
  tokenChipTextActive: { color: COLORS.gold },
  balanceInfo: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, marginTop: SPACING.xs },
  input: {
    backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.lg, padding: SPACING.md,
    fontSize: FONT_SIZES.md, color: COLORS.text, borderWidth: 1, borderColor: COLORS.border,
  },
  amountRow: { flexDirection: 'row', gap: SPACING.sm, alignItems: 'center' },
  maxBtn: { backgroundColor: COLORS.gold + '20', paddingHorizontal: SPACING.md, paddingVertical: SPACING.md, borderRadius: BORDER_RADIUS.lg },
  maxText: { fontSize: FONT_SIZES.sm, color: COLORS.gold, fontWeight: '700' },
  sendBtn: { borderRadius: BORDER_RADIUS.lg, overflow: 'hidden', marginTop: SPACING.xl },
  btnGradient: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: SPACING.md, gap: SPACING.sm },
  btnText: { fontSize: FONT_SIZES.lg, fontWeight: '700', color: COLORS.background },
});
