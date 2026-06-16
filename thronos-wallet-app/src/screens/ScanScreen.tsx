import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, Alert,
  ActivityIndicator, Vibration,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { COLORS, SPACING, FONT_SIZES, BORDER_RADIUS } from '../constants/theme';
import { useStore } from '../store/useStore';
import { CONFIG } from '../constants/config';

// ── Types ────────────────────────────────────────────────────────────────────

interface ThrConnectURI {
  sessionId: string;
  relay: string;
  dapp: string;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function parseThrConnect(uri: string): ThrConnectURI | null {
  try {
    if (!uri.startsWith('thrconnect://')) return null;
    const withoutScheme = uri.slice('thrconnect://'.length);
    const queryIdx = withoutScheme.indexOf('?');
    const sessionId = queryIdx >= 0 ? withoutScheme.slice(0, queryIdx) : withoutScheme;
    const params = new URLSearchParams(queryIdx >= 0 ? withoutScheme.slice(queryIdx + 1) : '');
    return {
      sessionId,
      relay: params.get('relay') || CONFIG.API_URL,
      dapp: params.get('dapp') || 'ThronosBuilder',
    };
  } catch {
    return null;
  }
}

function isThrAddress(value: string): boolean {
  return /^THR[A-Za-z0-9]{30,60}$/.test(value.trim());
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function ScanScreen() {
  const navigation = useNavigation<any>();
  const { address: walletAddress } = useStore();
  const [permission, requestPermission] = useCameraPermissions();
  const [scanned, setScanned] = useState(false);
  const [pairing, setPairing] = useState(false);
  const processingRef = useRef(false);

  // Reset scan lock when screen gains focus (so user can scan again after going back)
  useEffect(() => {
    const unsubscribe = navigation.addListener('focus', () => {
      setScanned(false);
      processingRef.current = false;
    });
    return unsubscribe;
  }, [navigation]);

  const handleScannedData = useCallback(async (data: string) => {
    if (processingRef.current) return;
    processingRef.current = true;
    setScanned(true);
    Vibration.vibrate(80);

    const thrConnect = parseThrConnect(data);
    if (thrConnect) {
      await handleWalletConnect(thrConnect);
      return;
    }

    if (isThrAddress(data.trim())) {
      navigation.navigate('Send', { toAddress: data.trim() });
      return;
    }

    // Unknown QR — show alert with raw value
    Alert.alert(
      'QR Code Scanned',
      data.length > 120 ? data.slice(0, 120) + '…' : data,
      [
        { text: 'OK', onPress: () => { processingRef.current = false; setScanned(false); } },
      ],
    );
  }, [navigation, walletAddress]);

  const handleWalletConnect = async (parsed: ThrConnectURI) => {
    if (!walletAddress) {
      Alert.alert('No Wallet', 'Please unlock your wallet first.', [
        { text: 'OK', onPress: () => navigation.goBack() },
      ]);
      return;
    }
    setPairing(true);
    try {
      const relayBase = parsed.relay.replace(/\/$/, '');
      const resp = await fetch(`${relayBase}/api/wallet/wc/pair`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: parsed.sessionId,
          address: walletAddress,
          dapp: parsed.dapp,
        }),
      });
      const json = await resp.json().catch(() => ({}));
      if (resp.ok && json.ok) {
        Alert.alert(
          '✅ Connected',
          `Your wallet is now connected to ${parsed.dapp}.\n\nYou can approve transaction requests from the builder.`,
          [{ text: 'Done', onPress: () => navigation.goBack() }],
        );
      } else {
        throw new Error(json.error || `HTTP ${resp.status}`);
      }
    } catch (err: any) {
      Alert.alert(
        'Connection Failed',
        err?.message || 'Could not connect to the dApp. Please try again.',
        [
          { text: 'Retry', onPress: () => { processingRef.current = false; setScanned(false); setPairing(false); } },
          { text: 'Cancel', onPress: () => navigation.goBack() },
        ],
      );
    } finally {
      setPairing(false);
    }
  };

  // ── Permission not yet determined ──
  if (!permission) {
    return (
      <SafeAreaView style={styles.container}>
        <ActivityIndicator color={COLORS.gold} style={{ flex: 1 }} />
      </SafeAreaView>
    );
  }

  // ── Permission denied ──
  if (!permission.granted) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()}>
            <Ionicons name="close" size={28} color={COLORS.text} />
          </TouchableOpacity>
        </View>
        <View style={styles.center}>
          <Ionicons name="camera-off-outline" size={64} color={COLORS.textMuted} />
          <Text style={styles.title}>Camera Access Required</Text>
          <Text style={styles.sub}>
            Thronos Wallet needs camera permission to scan QR codes.
          </Text>
          <TouchableOpacity style={styles.primaryBtn} onPress={requestPermission}>
            <Text style={styles.primaryBtnText}>Grant Camera Access</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  // ── Camera view ──
  return (
    <View style={styles.fullscreen}>
      <CameraView
        style={StyleSheet.absoluteFill}
        facing="back"
        barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
        onBarcodeScanned={scanned ? undefined : ({ data }) => handleScannedData(data)}
      />

      {/* Dark overlay with scan window cut-out */}
      <View style={styles.overlay}>
        {/* Top */}
        <View style={[styles.overlaySegment, { flex: 1 }]} />
        {/* Middle row */}
        <View style={styles.overlayMiddleRow}>
          <View style={[styles.overlaySegment, { width: SPACING.xxl * 2 }]} />
          <View style={styles.scanWindow}>
            {/* Corner marks */}
            <View style={[styles.corner, styles.cornerTL]} />
            <View style={[styles.corner, styles.cornerTR]} />
            <View style={[styles.corner, styles.cornerBL]} />
            <View style={[styles.corner, styles.cornerBR]} />
          </View>
          <View style={[styles.overlaySegment, { width: SPACING.xxl * 2 }]} />
        </View>
        {/* Bottom */}
        <View style={[styles.overlaySegment, { flex: 1, alignItems: 'center', justifyContent: 'flex-start', paddingTop: SPACING.xl }]}>
          <Text style={styles.scanLabel}>Scan a Thronos QR code</Text>
          <Text style={styles.scanSub}>thrconnect:// or THR address</Text>
        </View>
      </View>

      {/* Header */}
      <SafeAreaView style={styles.headerAbsolute} pointerEvents="box-none">
        <View style={styles.header}>
          <TouchableOpacity style={styles.closeBtn} onPress={() => navigation.goBack()}>
            <Ionicons name="close" size={24} color="#fff" />
          </TouchableOpacity>
        </View>
      </SafeAreaView>

      {/* Pairing overlay */}
      {pairing && (
        <View style={styles.pairingOverlay}>
          <ActivityIndicator size="large" color={COLORS.gold} />
          <Text style={styles.pairingText}>Connecting to dApp…</Text>
        </View>
      )}
    </View>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const SCAN_WINDOW = 260;
const CORNER = 28;
const CORNER_W = 3;

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.background },
  fullscreen: { flex: 1, backgroundColor: '#000' },

  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: SPACING.lg,
    paddingVertical: SPACING.md,
  },
  headerAbsolute: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
  },
  closeBtn: {
    backgroundColor: 'rgba(0,0,0,0.55)',
    borderRadius: 20,
    padding: 6,
  },
  overlay: { ...StyleSheet.absoluteFillObject, flexDirection: 'column' },
  overlaySegment: { backgroundColor: 'rgba(0,0,0,0.6)' },
  overlayMiddleRow: { flexDirection: 'row', height: SCAN_WINDOW },
  scanWindow: { width: SCAN_WINDOW, height: SCAN_WINDOW, position: 'relative' },
  corner: { position: 'absolute', width: CORNER, height: CORNER, borderColor: COLORS.gold, borderRadius: 4 },
  cornerTL: { top: 0, left: 0, borderTopWidth: CORNER_W, borderLeftWidth: CORNER_W },
  cornerTR: { top: 0, right: 0, borderTopWidth: CORNER_W, borderRightWidth: CORNER_W },
  cornerBL: { bottom: 0, left: 0, borderBottomWidth: CORNER_W, borderLeftWidth: CORNER_W },
  cornerBR: { bottom: 0, right: 0, borderBottomWidth: CORNER_W, borderRightWidth: CORNER_W },

  scanLabel: { color: '#fff', fontSize: FONT_SIZES.md, fontWeight: '700', textAlign: 'center' },
  scanSub: { color: 'rgba(255,255,255,0.6)', fontSize: FONT_SIZES.sm, marginTop: 4, textAlign: 'center' },

  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: SPACING.xl,
    gap: SPACING.lg,
  },
  title: { fontSize: FONT_SIZES.xl, color: COLORS.text, fontWeight: '700', textAlign: 'center' },
  sub: { fontSize: FONT_SIZES.sm, color: COLORS.textMuted, textAlign: 'center', lineHeight: 20 },

  primaryBtn: {
    backgroundColor: COLORS.gold,
    paddingHorizontal: SPACING.xl,
    paddingVertical: SPACING.md,
    borderRadius: BORDER_RADIUS.lg,
    alignItems: 'center',
    width: '100%',
  },
  primaryBtnText: { color: '#000', fontWeight: '700', fontSize: FONT_SIZES.md },
  pairingOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.75)',
    justifyContent: 'center',
    alignItems: 'center',
    gap: SPACING.md,
  },
  pairingText: { color: '#fff', fontSize: FONT_SIZES.lg, fontWeight: '600' },
});
