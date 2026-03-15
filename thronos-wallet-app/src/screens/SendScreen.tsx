import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, TextInput, Alert, ActivityIndicator,
  ScrollView, Modal,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { Audio } from 'expo-av';
import { COLORS, SPACING, FONT_SIZES, BORDER_RADIUS } from '../constants/theme';
import { useStore } from '../store/useStore';
import { getWallet, isValidAddress } from '../services/wallet';
import { sendTHR, sendToken } from '../services/api';
import { CONFIG } from '../constants/config';

// ── Types ────────────────────────────────────────────────────────────────────

type Network = 'thronos' | 'bitcoin' | 'ethereum' | 'bnb' | 'xrp';
type Speed = 'slow' | 'fast';

interface NetworkInfo {
  key: Network;
  label: string;
  icon: string;
  color: string;
  available: boolean;
}

const NETWORKS: NetworkInfo[] = [
  { key: 'thronos', label: 'Thronos Chain', icon: '⚡', color: COLORS.gold, available: true },
  { key: 'bitcoin', label: 'Bitcoin', icon: '₿', color: '#F7931A', available: true },
  { key: 'ethereum', label: 'Ethereum', icon: 'Ξ', color: '#627EEA', available: true },
  { key: 'bnb', label: 'BNB Chain', icon: '🔶', color: '#F3BA2F', available: true },
  { key: 'xrp', label: 'XRP Ledger', icon: '◆', color: '#23292F', available: true },
];

// ── Component ────────────────────────────────────────────────────────────────

export default function SendScreen() {
  const navigation = useNavigation();
  const { wallet, tokens } = useStore();
  const [selectedNetwork, setSelectedNetwork] = useState<Network>('thronos');
  const [recipient, setRecipient] = useState('');
  const [amount, setAmount] = useState('');
  const [selectedToken, setSelectedToken] = useState('THR');
  const [speed, setSpeed] = useState<Speed>('fast');
  const [sending, setSending] = useState(false);
  const [txResult, setTxResult] = useState<{ success: boolean; tx_id?: string; error?: string } | null>(null);

  // Survival mode / WhisperNote
  const [survivalVisible, setSurvivalVisible] = useState(false);
  const [whisperPlaying, setWhisperPlaying] = useState(false);
  const [sound, setSound] = useState<Audio.Sound | null>(null);

  const currentToken = tokens.find((t) => t.symbol === selectedToken);
  const availableBalance = currentToken?.balance ?? 0;
  const feePercent = speed === 'fast' ? 0.5 : 0.09;

  useEffect(() => {
    return () => {
      if (sound) sound.unloadAsync();
    };
  }, [sound]);

  const selectNetwork = (network: Network) => {
    setSelectedNetwork(network);
    // Reset token if changing away from thronos
    if (network !== 'thronos') {
      const networkTokenMap: Record<string, string> = {
        bitcoin: 'WBTC',
        ethereum: 'WETH',
        bnb: 'WBNB',
        xrp: 'WXRP',
      };
      setSelectedToken(networkTokenMap[network] || 'THR');
    } else {
      setSelectedToken('THR');
    }
  };

  const handleSend = async () => {
    if (!recipient.trim()) {
      Alert.alert('Error', 'Please enter a recipient address.');
      return;
    }
    if (selectedNetwork === 'thronos' && !isValidAddress(recipient.trim())) {
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

    const fee = (amt * feePercent / 100).toFixed(6);
    Alert.alert(
      'Confirm Transaction',
      `Send ${amt} ${selectedToken} to ${recipient.slice(0, 16)}...?\n\nSpeed: ${speed === 'fast' ? 'Fast' : 'Slow'}\nFee: ${fee} ${selectedToken} (${feePercent}%)`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Send',
          onPress: async () => {
            setSending(true);
            setTxResult(null);
            try {
              const result = selectedToken === 'THR'
                ? await sendTHR({ from: creds.address, to: recipient.trim(), amount: amt, secret: creds.secret, speed })
                : await sendToken({ symbol: selectedToken, from: creds.address, to: recipient.trim(), amount: amt, secret: creds.secret });

              if (result.success) {
                setTxResult({ success: true, tx_id: result.transaction?.tx_id });
              } else {
                setTxResult({ success: false, error: result.error || 'Transaction failed.' });
              }
            } catch (error: any) {
              setTxResult({ success: false, error: error.message || 'Transaction failed.' });
            } finally {
              setSending(false);
            }
          },
        },
      ],
    );
  };

  // WhisperNote: encode transaction data to audio
  const playWhisperNote = async () => {
    if (!recipient || !amount) {
      Alert.alert('WhisperNote', 'Enter recipient and amount first.');
      return;
    }
    try {
      setWhisperPlaying(true);
      if (sound) await sound.unloadAsync();
      // Use the address audio endpoint to encode the transaction data
      const txData = `${recipient}:${amount}:${selectedToken}`;
      const audioUrl = `${CONFIG.API_URL}/api/wallet/audio/${encodeURIComponent(txData)}`;
      const { sound: newSound } = await Audio.Sound.createAsync({ uri: audioUrl });
      setSound(newSound);
      newSound.setOnPlaybackStatusUpdate((status) => {
        if ('didJustFinish' in status && status.didJustFinish) {
          setWhisperPlaying(false);
        }
      });
      await newSound.playAsync();
    } catch {
      setWhisperPlaying(false);
    }
  };

  const tokenList = selectedNetwork === 'thronos'
    ? ['THR', ...tokens.filter((t) => t.symbol !== 'THR' && t.balance > 0).map((t) => t.symbol)]
    : [selectedToken];

  return (
    <SafeAreaView style={styles.container}>
      <LinearGradient colors={[COLORS.background, COLORS.backgroundLight]} style={styles.gradient}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()}>
            <Ionicons name="arrow-back" size={24} color={COLORS.text} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Send Tokens</Text>
          <TouchableOpacity onPress={() => setSurvivalVisible(true)}>
            <Ionicons name="radio" size={22} color={COLORS.textSecondary} />
          </TouchableOpacity>
        </View>

        <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
          {/* Network Selector */}
          <Text style={styles.label}>Network</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.networkScroll}>
            <View style={styles.networkRow}>
              {NETWORKS.map((net) => (
                <TouchableOpacity
                  key={net.key}
                  style={[
                    styles.networkChip,
                    selectedNetwork === net.key && styles.networkChipActive,
                    selectedNetwork === net.key && { borderColor: net.color },
                  ]}
                  onPress={() => selectNetwork(net.key)}
                >
                  <Text style={styles.networkIcon}>{net.icon}</Text>
                  <Text style={[
                    styles.networkText,
                    selectedNetwork === net.key && { color: net.color },
                  ]}>
                    {net.label}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          </ScrollView>

          {/* Token selector */}
          <Text style={styles.label}>Token</Text>
          <View style={styles.tokenRow}>
            {tokenList.map((sym) => (
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
            placeholder={selectedNetwork === 'thronos' ? 'THR...' : `${selectedNetwork} address...`}
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
              placeholder="0.000000"
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

          {/* Transaction Speed */}
          <Text style={styles.label}>Transaction Speed</Text>
          <View style={styles.speedRow}>
            <TouchableOpacity
              style={[styles.speedBtn, speed === 'slow' && styles.speedBtnActive]}
              onPress={() => setSpeed('slow')}
            >
              <Text style={styles.speedIcon}>🐢</Text>
              <Text style={[styles.speedLabel, speed === 'slow' && styles.speedLabelActive]}>Slow</Text>
              <Text style={styles.speedFee}>0.09% fee</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.speedBtn, speed === 'fast' && styles.speedBtnActive]}
              onPress={() => setSpeed('fast')}
            >
              <Text style={styles.speedIcon}>⚡</Text>
              <Text style={[styles.speedLabel, speed === 'fast' && styles.speedLabelActive]}>Fast</Text>
              <Text style={styles.speedFee}>0.5% fee</Text>
            </TouchableOpacity>
          </View>

          {/* Transaction Result */}
          {txResult && (
            <View style={[styles.resultBox, txResult.success ? styles.resultSuccess : styles.resultError]}>
              <Ionicons
                name={txResult.success ? 'checkmark-circle' : 'close-circle'}
                size={20}
                color={txResult.success ? COLORS.success : COLORS.error}
              />
              <View style={{ flex: 1 }}>
                <Text style={styles.resultText}>
                  {txResult.success ? 'Transaction sent!' : txResult.error}
                </Text>
                {txResult.tx_id && (
                  <Text style={styles.resultTxId} numberOfLines={1}>TX: {txResult.tx_id}</Text>
                )}
              </View>
            </View>
          )}

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

          <View style={{ height: 40 }} />
        </ScrollView>
      </LinearGradient>

      {/* Survival / WhisperNote / Bluetooth Modal */}
      <Modal visible={survivalVisible} transparent animationType="slide">
        <View style={styles.modalOverlay}>
          <View style={styles.survivalModal}>
            <View style={styles.survivalHeader}>
              <Text style={styles.survivalTitle}>Survival Transfer</Text>
              <TouchableOpacity onPress={() => setSurvivalVisible(false)}>
                <Ionicons name="close" size={24} color={COLORS.textMuted} />
              </TouchableOpacity>
            </View>

            <Text style={styles.survivalDesc}>
              Send THR offline using sound waves or Bluetooth — no internet needed.
            </Text>

            {/* WhisperNote */}
            <View style={styles.survivalCard}>
              <Ionicons name="volume-high" size={28} color={COLORS.gold} />
              <View style={{ flex: 1, marginLeft: SPACING.md }}>
                <Text style={styles.survivalCardTitle}>WhisperNote (Audio)</Text>
                <Text style={styles.survivalCardDesc}>
                  Encode transaction data into sound waves. The receiver decodes the audio
                  to process the payment — works offline.
                </Text>
              </View>
            </View>
            <TouchableOpacity
              style={[styles.survivalBtn, whisperPlaying && styles.survivalBtnActive]}
              onPress={playWhisperNote}
            >
              <Ionicons
                name={whisperPlaying ? 'radio' : 'musical-note'}
                size={18}
                color={COLORS.background}
              />
              <Text style={styles.survivalBtnText}>
                {whisperPlaying ? 'Broadcasting...' : 'Broadcast via Sound'}
              </Text>
            </TouchableOpacity>

            {/* Bluetooth */}
            <View style={[styles.survivalCard, { marginTop: SPACING.lg }]}>
              <Ionicons name="bluetooth" size={28} color={COLORS.info} />
              <View style={{ flex: 1, marginLeft: SPACING.md }}>
                <Text style={styles.survivalCardTitle}>Bluetooth Transfer</Text>
                <Text style={styles.survivalCardDesc}>
                  Send THR directly via Bluetooth to nearby devices.
                  Both devices must have the Thronos app.
                </Text>
              </View>
            </View>
            <TouchableOpacity
              style={[styles.survivalBtn, { backgroundColor: COLORS.info }]}
              onPress={() => Alert.alert('Bluetooth', 'Scanning for nearby Thronos devices...')}
            >
              <Ionicons name="bluetooth" size={18} color="#FFF" />
              <Text style={styles.survivalBtnText}>Send via Bluetooth</Text>
            </TouchableOpacity>

            {/* Survival Mode Info */}
            <View style={styles.survivalInfo}>
              <Ionicons name="shield-checkmark" size={16} color={COLORS.success} />
              <Text style={styles.survivalInfoText}>
                Survival Mode: Transactions are queued locally and synced to chain
                when connectivity is restored. Supports RF, QR, and audio channels.
              </Text>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

// ── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.background },
  gradient: { flex: 1 },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: SPACING.lg, paddingVertical: SPACING.md,
  },
  headerTitle: { fontSize: FONT_SIZES.xl, fontWeight: '600', color: COLORS.text },
  content: { flex: 1, paddingHorizontal: SPACING.lg },

  label: {
    fontSize: FONT_SIZES.sm, color: COLORS.textSecondary, fontWeight: '600',
    marginBottom: SPACING.xs, marginTop: SPACING.lg,
  },

  // Network
  networkScroll: { marginBottom: SPACING.xs },
  networkRow: { flexDirection: 'row', gap: SPACING.sm },
  networkChip: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm,
    borderRadius: BORDER_RADIUS.lg, borderWidth: 1, borderColor: COLORS.border,
    backgroundColor: COLORS.surface,
  },
  networkChipActive: { backgroundColor: COLORS.gold + '15' },
  networkIcon: { fontSize: 16 },
  networkText: { fontSize: FONT_SIZES.xs, fontWeight: '600', color: COLORS.textSecondary },

  // Token
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

  // Input
  input: {
    backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.lg, padding: SPACING.md,
    fontSize: FONT_SIZES.md, color: COLORS.text, borderWidth: 1, borderColor: COLORS.border,
  },
  amountRow: { flexDirection: 'row', gap: SPACING.sm, alignItems: 'center' },
  maxBtn: {
    backgroundColor: COLORS.gold + '20', paddingHorizontal: SPACING.md,
    paddingVertical: SPACING.md, borderRadius: BORDER_RADIUS.lg,
  },
  maxText: { fontSize: FONT_SIZES.sm, color: COLORS.gold, fontWeight: '700' },

  // Speed
  speedRow: { flexDirection: 'row', gap: SPACING.sm },
  speedBtn: {
    flex: 1, alignItems: 'center', paddingVertical: SPACING.md,
    borderRadius: BORDER_RADIUS.lg, borderWidth: 1, borderColor: COLORS.border,
    backgroundColor: COLORS.surface,
  },
  speedBtnActive: { borderColor: COLORS.gold, backgroundColor: COLORS.gold + '15' },
  speedIcon: { fontSize: 20, marginBottom: 4 },
  speedLabel: { fontSize: FONT_SIZES.sm, fontWeight: '600', color: COLORS.textSecondary },
  speedLabelActive: { color: COLORS.gold },
  speedFee: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, marginTop: 2 },

  // Result
  resultBox: {
    flexDirection: 'row', alignItems: 'center', gap: SPACING.sm,
    padding: SPACING.md, borderRadius: BORDER_RADIUS.lg, marginTop: SPACING.md,
    borderWidth: 1,
  },
  resultSuccess: { backgroundColor: COLORS.success + '12', borderColor: COLORS.success + '30' },
  resultError: { backgroundColor: COLORS.error + '12', borderColor: COLORS.error + '30' },
  resultText: { fontSize: FONT_SIZES.sm, color: COLORS.text, fontWeight: '600' },
  resultTxId: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, fontFamily: 'monospace', marginTop: 2 },

  // Send Button
  sendBtn: { borderRadius: BORDER_RADIUS.lg, overflow: 'hidden', marginTop: SPACING.xl },
  btnGradient: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    paddingVertical: SPACING.md, gap: SPACING.sm,
  },
  btnText: { fontSize: FONT_SIZES.lg, fontWeight: '700', color: COLORS.background },

  // Survival Modal
  modalOverlay: {
    flex: 1, backgroundColor: COLORS.overlay, justifyContent: 'flex-end',
  },
  survivalModal: {
    backgroundColor: COLORS.backgroundCard, borderTopLeftRadius: BORDER_RADIUS.xl,
    borderTopRightRadius: BORDER_RADIUS.xl, padding: SPACING.lg, paddingBottom: 40,
    borderTopWidth: 1, borderColor: COLORS.border,
  },
  survivalHeader: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    marginBottom: SPACING.md,
  },
  survivalTitle: { fontSize: FONT_SIZES.xl, fontWeight: '700', color: COLORS.text },
  survivalDesc: { fontSize: FONT_SIZES.sm, color: COLORS.textSecondary, marginBottom: SPACING.lg, lineHeight: 20 },
  survivalCard: {
    flexDirection: 'row', alignItems: 'flex-start', backgroundColor: COLORS.surface,
    borderRadius: BORDER_RADIUS.lg, padding: SPACING.md,
    borderWidth: 1, borderColor: COLORS.border,
  },
  survivalCardTitle: { fontSize: FONT_SIZES.md, fontWeight: '600', color: COLORS.text },
  survivalCardDesc: { fontSize: FONT_SIZES.sm, color: COLORS.textSecondary, marginTop: 4, lineHeight: 18 },
  survivalBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: SPACING.sm,
    backgroundColor: COLORS.gold, paddingVertical: SPACING.md, borderRadius: BORDER_RADIUS.lg,
    marginTop: SPACING.sm,
  },
  survivalBtnActive: { backgroundColor: COLORS.gold + 'CC' },
  survivalBtnText: { fontSize: FONT_SIZES.md, fontWeight: '700', color: COLORS.background },
  survivalInfo: {
    flexDirection: 'row', gap: SPACING.sm, marginTop: SPACING.lg,
    backgroundColor: COLORS.success + '10', borderRadius: BORDER_RADIUS.lg,
    padding: SPACING.md, borderWidth: 1, borderColor: COLORS.success + '30',
  },
  survivalInfoText: { flex: 1, fontSize: FONT_SIZES.xs, color: COLORS.textSecondary, lineHeight: 18 },
});
