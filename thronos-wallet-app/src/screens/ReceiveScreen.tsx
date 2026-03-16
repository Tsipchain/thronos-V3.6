import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ActivityIndicator, ScrollView, Alert,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import * as Clipboard from 'expo-clipboard';
import QRCode from 'react-native-qrcode-svg';
import { Audio } from 'expo-av';
import { COLORS, SPACING, FONT_SIZES, BORDER_RADIUS } from '../constants/theme';
import { useStore } from '../store/useStore';
import { CONFIG } from '../constants/config';

// ── Types ────────────────────────────────────────────────────────────────────

type Network = 'thronos' | 'bitcoin' | 'ethereum' | 'bnb' | 'xrp';

interface NetworkInfo {
  key: Network;
  label: string;
  icon: string;
  color: string;
  wrappedToken: string;
  hint: string;
}

const NETWORKS: NetworkInfo[] = [
  { key: 'thronos', label: 'Thronos', icon: '⚡', color: COLORS.gold, wrappedToken: 'THR', hint: 'Scan QR to receive THR.' },
  { key: 'bitcoin', label: 'Bitcoin', icon: '₿', color: '#F7931A', wrappedToken: 'WBTC', hint: 'Deposit BTC to receive WBTC on Thronos.' },
  { key: 'ethereum', label: 'Ethereum', icon: 'Ξ', color: '#627EEA', wrappedToken: 'WETH', hint: 'Deposit ETH to receive WETH on Thronos.' },
  { key: 'bnb', label: 'BNB', icon: '🔶', color: '#F3BA2F', wrappedToken: 'WBNB', hint: 'Deposit BNB to receive WBNB on Thronos.' },
  { key: 'xrp', label: 'XRP', icon: '◆', color: '#23292F', wrappedToken: 'WXRP', hint: 'Deposit XRP to receive WXRP on Thronos.' },
];

// ── Component ────────────────────────────────────────────────────────────────

export default function ReceiveScreen() {
  const navigation = useNavigation();
  const { wallet } = useStore();
  const [selectedNetwork, setSelectedNetwork] = useState<Network>('thronos');
  const [depositAddress, setDepositAddress] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [audioPlaying, setAudioPlaying] = useState(false);
  const [sound, setSound] = useState<Audio.Sound | null>(null);

  const networkInfo = NETWORKS.find(n => n.key === selectedNetwork)!;

  // Cleanup audio on unmount
  useEffect(() => {
    return () => {
      if (sound) sound.unloadAsync();
    };
  }, [sound]);

  const loadAddress = useCallback(async (network: Network) => {
    if (!wallet.address) return;

    if (network === 'thronos') {
      setDepositAddress(wallet.address);
      return;
    }

    setLoading(true);
    try {
      let endpoint: string;
      if (network === 'bitcoin') {
        endpoint = `/api/bridge/deposit?wallet=${encodeURIComponent(wallet.address)}`;
      } else {
        endpoint = `/api/bridge/deposit?network=${network}&thr_address=${encodeURIComponent(wallet.address)}`;
      }
      const res = await fetch(`${CONFIG.API_URL}${endpoint}`);
      const data = await res.json();

      if (network === 'bitcoin' && data.ok && data.btc_address) {
        setDepositAddress(data.btc_address);
      } else if (data.ok && data.deposit_address) {
        setDepositAddress(data.deposit_address);
      } else {
        setDepositAddress('');
      }
    } catch {
      setDepositAddress('');
    } finally {
      setLoading(false);
    }
  }, [wallet.address]);

  useEffect(() => {
    loadAddress(selectedNetwork);
  }, [selectedNetwork, loadAddress]);

  const selectNetwork = (network: Network) => {
    setSelectedNetwork(network);
    setCopied(false);
    setDepositAddress('');
  };

  const copyAddress = async () => {
    if (!depositAddress) return;
    await Clipboard.setStringAsync(depositAddress);
    setCopied(true);
    setTimeout(() => setCopied(false), 3000);
  };

  const playAudio = async () => {
    if (!depositAddress || selectedNetwork !== 'thronos') return;
    try {
      setAudioPlaying(true);
      if (sound) await sound.unloadAsync();
      const audioUrl = `${CONFIG.API_URL}/api/wallet/audio/${encodeURIComponent(depositAddress)}`;
      const { sound: newSound } = await Audio.Sound.createAsync({ uri: audioUrl });
      setSound(newSound);
      newSound.setOnPlaybackStatusUpdate((status) => {
        if ('didJustFinish' in status && status.didJustFinish) {
          setAudioPlaying(false);
        }
      });
      await newSound.playAsync();
    } catch {
      setAudioPlaying(false);
      Alert.alert('Error', 'Failed to play audio encoding.');
    }
  };

  const qrValue = depositAddress || 'empty';

  return (
    <SafeAreaView style={styles.container}>
      <LinearGradient colors={[COLORS.background, COLORS.backgroundLight]} style={styles.gradient}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()}>
            <Ionicons name="arrow-back" size={24} color={COLORS.text} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Receive Tokens</Text>
          <View style={{ width: 24 }} />
        </View>

        <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
          {/* Network Selector */}
          <Text style={styles.sectionLabel}>Network</Text>
          <View style={styles.networkGrid}>
            {NETWORKS.map((net) => (
              <TouchableOpacity
                key={net.key}
                style={[
                  styles.networkBtn,
                  selectedNetwork === net.key && styles.networkBtnActive,
                  selectedNetwork === net.key && { borderColor: net.color },
                ]}
                onPress={() => selectNetwork(net.key)}
              >
                <Text style={styles.networkIcon}>{net.icon}</Text>
                <Text style={[
                  styles.networkLabel,
                  selectedNetwork === net.key && { color: net.color },
                ]}>
                  {net.label}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          {/* Network Label */}
          <View style={styles.networkInfoRow}>
            <View style={[styles.networkDot, { backgroundColor: networkInfo.color }]} />
            <Text style={styles.networkInfoText}>
              Network: {networkInfo.label} {selectedNetwork !== 'thronos' ? 'Chain' : ''}
            </Text>
          </View>

          {/* Address Display */}
          <View style={styles.addressSection}>
            <Text style={styles.addressLabel}>Deposit Address</Text>
            {loading ? (
              <ActivityIndicator color={COLORS.gold} style={{ marginVertical: SPACING.lg }} />
            ) : depositAddress ? (
              <View style={styles.addressRow}>
                <Text style={styles.addressValue} selectable numberOfLines={2}>
                  {depositAddress}
                </Text>
                <TouchableOpacity style={styles.copySmall} onPress={copyAddress}>
                  <Ionicons name={copied ? 'checkmark' : 'copy'} size={16} color={COLORS.gold} />
                  <Text style={styles.copySmallText}>{copied ? 'Copied' : 'Copy'}</Text>
                </TouchableOpacity>
              </View>
            ) : (
              <Text style={styles.comingSoon}>
                {selectedNetwork === 'thronos'
                  ? 'Connect wallet to view address'
                  : `${networkInfo.label} bridge coming soon`}
              </Text>
            )}
          </View>

          {/* QR Code */}
          {depositAddress ? (
            <View style={styles.qrSection}>
              <View style={styles.qrContainer}>
                <QRCode
                  value={qrValue}
                  size={200}
                  backgroundColor="#FFFFFF"
                  color="#000000"
                />
              </View>
              <Text style={styles.qrHint}>{networkInfo.hint}</Text>
            </View>
          ) : null}

          {/* WhisperNote Audio Buttons */}
          {depositAddress && (
            <View style={styles.audioSection}>
              <TouchableOpacity
                style={[styles.audioBtn, audioPlaying && styles.audioBtnActive]}
                onPress={playAudio}
                disabled={selectedNetwork !== 'thronos'}
              >
                <Ionicons
                  name={audioPlaying ? 'volume-high' : 'volume-medium'}
                  size={20}
                  color={selectedNetwork === 'thronos' ? COLORS.gold : COLORS.textMuted}
                />
                <Text style={[
                  styles.audioBtnText,
                  selectedNetwork !== 'thronos' && { color: COLORS.textMuted },
                ]}>
                  Play Sound
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.audioBtn}
                disabled={selectedNetwork !== 'thronos'}
                onPress={() => {
                  if (selectedNetwork === 'thronos') {
                    Alert.alert('WhisperNote', 'Audio encoding of your address. Use this for offline sound-based transfers.');
                  }
                }}
              >
                <Ionicons
                  name="download"
                  size={20}
                  color={selectedNetwork === 'thronos' ? COLORS.gold : COLORS.textMuted}
                />
                <Text style={[
                  styles.audioBtnText,
                  selectedNetwork !== 'thronos' && { color: COLORS.textMuted },
                ]}>
                  Download WAV
                </Text>
              </TouchableOpacity>
            </View>
          )}

          {/* Copy Address Full Button */}
          {depositAddress ? (
            <TouchableOpacity style={styles.copyFullBtn} onPress={copyAddress}>
              <LinearGradient colors={[COLORS.gold, COLORS.goldDark]} style={styles.btnGradient}>
                <Ionicons name={copied ? 'checkmark-circle' : 'copy'} size={20} color={COLORS.background} />
                <Text style={styles.btnText}>{copied ? 'Copied!' : 'Copy Address'}</Text>
              </LinearGradient>
            </TouchableOpacity>
          ) : null}

          {/* Info Note */}
          <View style={styles.note}>
            <Ionicons name="information-circle" size={16} color={COLORS.info} />
            <Text style={styles.noteText}>
              {selectedNetwork === 'thronos'
                ? 'Only send Thronos chain tokens (THR, WBTC, L2E, etc.) to this address.'
                : `Send only ${networkInfo.label} to this deposit address. Tokens will be bridged to ${networkInfo.wrappedToken} on Thronos Chain.`}
            </Text>
          </View>

          <View style={{ height: 40 }} />
        </ScrollView>
      </LinearGradient>
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

  sectionLabel: {
    fontSize: FONT_SIZES.sm, fontWeight: '600', color: COLORS.textSecondary,
    marginBottom: SPACING.sm, marginTop: SPACING.sm,
  },

  // Network Selector
  networkGrid: {
    flexDirection: 'row', flexWrap: 'wrap', gap: SPACING.sm,
  },
  networkBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm,
    borderRadius: BORDER_RADIUS.lg, borderWidth: 1, borderColor: COLORS.border,
    backgroundColor: COLORS.surface,
  },
  networkBtnActive: {
    backgroundColor: COLORS.gold + '15',
  },
  networkIcon: { fontSize: 16 },
  networkLabel: { fontSize: FONT_SIZES.xs, fontWeight: '600', color: COLORS.textSecondary },

  networkInfoRow: {
    flexDirection: 'row', alignItems: 'center', gap: SPACING.xs,
    marginTop: SPACING.md, marginBottom: SPACING.sm,
  },
  networkDot: { width: 8, height: 8, borderRadius: 4 },
  networkInfoText: { fontSize: FONT_SIZES.xs, color: COLORS.info },

  // Address
  addressSection: {
    backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.lg,
    padding: SPACING.md, borderWidth: 1, borderColor: COLORS.border,
    marginBottom: SPACING.md,
  },
  addressLabel: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, marginBottom: SPACING.xs },
  addressRow: { flexDirection: 'row', alignItems: 'center', gap: SPACING.sm },
  addressValue: { flex: 1, fontSize: FONT_SIZES.sm, color: COLORS.gold, fontFamily: 'monospace' },
  copySmall: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: SPACING.sm, paddingVertical: 6,
    borderRadius: BORDER_RADIUS.sm, backgroundColor: COLORS.gold + '15',
  },
  copySmallText: { fontSize: FONT_SIZES.xs, color: COLORS.gold, fontWeight: '600' },
  comingSoon: { fontSize: FONT_SIZES.sm, color: COLORS.textMuted, fontStyle: 'italic', paddingVertical: SPACING.sm },

  // QR Code
  qrSection: { alignItems: 'center', marginBottom: SPACING.lg },
  qrContainer: {
    padding: SPACING.md, backgroundColor: '#FFFFFF', borderRadius: BORDER_RADIUS.xl,
    borderWidth: 2, borderColor: COLORS.gold + '40',
  },
  qrHint: { fontSize: FONT_SIZES.sm, color: COLORS.textMuted, marginTop: SPACING.sm, textAlign: 'center' },

  // Audio Buttons
  audioSection: {
    flexDirection: 'row', gap: SPACING.sm, marginBottom: SPACING.lg,
  },
  audioBtn: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: SPACING.xs,
    paddingVertical: SPACING.md, borderRadius: BORDER_RADIUS.lg,
    backgroundColor: COLORS.surface, borderWidth: 1, borderColor: COLORS.border,
  },
  audioBtnActive: { borderColor: COLORS.gold + '60', backgroundColor: COLORS.gold + '10' },
  audioBtnText: { fontSize: FONT_SIZES.sm, color: COLORS.gold, fontWeight: '600' },

  // Copy Button
  copyFullBtn: { borderRadius: BORDER_RADIUS.lg, overflow: 'hidden', marginBottom: SPACING.lg },
  btnGradient: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    paddingVertical: SPACING.md, gap: SPACING.sm,
  },
  btnText: { fontSize: FONT_SIZES.lg, fontWeight: '700', color: COLORS.background },

  // Info Note
  note: {
    flexDirection: 'row', backgroundColor: COLORS.info + '12', borderRadius: BORDER_RADIUS.lg,
    padding: SPACING.md, gap: SPACING.sm, borderWidth: 1, borderColor: COLORS.info + '30',
  },
  noteText: { flex: 1, fontSize: FONT_SIZES.sm, color: COLORS.textSecondary, lineHeight: 20 },
});
