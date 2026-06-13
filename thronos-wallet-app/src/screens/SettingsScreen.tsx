import React from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Switch, Alert, Linking,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT_SIZES, BORDER_RADIUS } from '../constants/theme';
import { useStore } from '../store/useStore';
import { deleteWallet, getWallet, shortenAddress } from '../services/wallet';
import { CONFIG } from '../constants/config';
import type { RootStackParamList } from '../../App';

type Nav = NativeStackNavigationProp<RootStackParamList>;

export default function SettingsScreen() {
  const navigation = useNavigation<Nav>();
  const { wallet, settings, updateSettings, disconnect } = useStore();

  const handleExportKey = async () => {
    const creds = await getWallet();
    if (!creds) { Alert.alert('Error', 'No wallet found.'); return; }

    Alert.alert(
      'Export Secret Key',
      'Your secret key will be displayed. Make sure no one is watching your screen.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Show Key',
          style: 'destructive',
          onPress: () => {
            Alert.alert('Secret Key', creds.secret, [{ text: 'OK' }]);
          },
        },
      ],
    );
  };

  const handleDisconnect = () => {
    Alert.alert(
      'Delete Wallet',
      'This will remove the wallet from this device. Make sure you have your secret key backed up!',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            await deleteWallet();
            disconnect();
            navigation.reset({ index: 0, routes: [{ name: 'Welcome' }] });
          },
        },
      ],
    );
  };

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView style={styles.scroll} showsVerticalScrollIndicator={false}>
        <Text style={styles.title}>Settings</Text>

        {/* Wallet Info Card */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Wallet</Text>
          <LinearGradient colors={['#1E1400', '#1A1A33']} style={styles.walletCard}>
            <View style={styles.walletCardIcon}>
              <Ionicons name="planet" size={28} color={COLORS.gold} />
            </View>
            <View style={styles.cardInfo}>
              <Text style={styles.cardTitle}>
                {wallet.address ? shortenAddress(wallet.address) : 'Not connected'}
              </Text>
              <View style={styles.cardBadgeRow}>
                <View style={styles.networkBadge}>
                  <View style={styles.networkDot} />
                  <Text style={styles.cardSub}>Thronos Mainnet</Text>
                </View>
              </View>
            </View>
            <View style={styles.acicBadge}>
              <Ionicons name="flash" size={10} color={COLORS.gold} />
              <Text style={styles.acicText}>ACIC</Text>
            </View>
          </LinearGradient>
        </View>

        {/* Security */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Security</Text>

          <TouchableOpacity style={styles.settingRow} onPress={handleExportKey}>
            <View style={[styles.settingIcon, { backgroundColor: COLORS.warning + '20' }]}>
              <Ionicons name="key" size={18} color={COLORS.warning} />
            </View>
            <Text style={styles.settingText}>Export Secret Key</Text>
            <Ionicons name="chevron-forward" size={18} color={COLORS.textMuted} />
          </TouchableOpacity>
        </View>

        {/* Preferences */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Preferences</Text>

          <View style={styles.settingRow}>
            <View style={[styles.settingIcon, { backgroundColor: COLORS.info + '20' }]}>
              <Ionicons name="notifications" size={18} color={COLORS.info} />
            </View>
            <Text style={styles.settingText}>Notifications</Text>
            <Switch
              value={settings.notifications}
              onValueChange={(v) => updateSettings({ notifications: v })}
              trackColor={{ false: COLORS.border, true: COLORS.gold + '60' }}
              thumbColor={settings.notifications ? COLORS.gold : COLORS.textMuted}
            />
          </View>
        </View>

        {/* About */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>About</Text>

          <TouchableOpacity style={styles.settingRow} onPress={() => Linking.openURL('https://api.thronoschain.org')}>
            <View style={[styles.settingIcon, { backgroundColor: COLORS.primary + '20' }]}>
              <Ionicons name="globe" size={18} color={COLORS.primary} />
            </View>
            <Text style={styles.settingText}>Website</Text>
            <Ionicons name="chevron-forward" size={18} color={COLORS.textMuted} />
          </TouchableOpacity>

          <TouchableOpacity style={styles.settingRow} onPress={() => Linking.openURL(`mailto:${CONFIG.SUPPORT_EMAIL}`)}>
            <View style={[styles.settingIcon, { backgroundColor: COLORS.info + '20' }]}>
              <Ionicons name="mail" size={18} color={COLORS.info} />
            </View>
            <Text style={styles.settingText}>Support</Text>
            <Ionicons name="chevron-forward" size={18} color={COLORS.textMuted} />
          </TouchableOpacity>

          <View style={styles.settingRow}>
            <View style={[styles.settingIcon, { backgroundColor: COLORS.textMuted + '30' }]}>
              <Ionicons name="information-circle" size={18} color={COLORS.textMuted} />
            </View>
            <Text style={styles.settingText}>Version</Text>
            <View style={styles.versionBadge}>
              <Text style={styles.versionText}>{CONFIG.APP_VERSION}</Text>
            </View>
          </View>
        </View>

        {/* Danger Zone */}
        <TouchableOpacity style={styles.deleteBtn} onPress={handleDisconnect}>
          <Ionicons name="trash" size={18} color={COLORS.error} />
          <Text style={styles.deleteText}>Delete Wallet from Device</Text>
        </TouchableOpacity>

        <View style={{ height: SPACING.xxl }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.background },
  scroll: { flex: 1, paddingHorizontal: SPACING.lg },
  title: { fontSize: FONT_SIZES.xxl, fontWeight: '800', color: COLORS.text, paddingVertical: SPACING.md },
  section: { marginBottom: SPACING.lg },
  sectionTitle: {
    fontSize: FONT_SIZES.xs, fontWeight: '700', color: COLORS.textMuted,
    marginBottom: SPACING.sm, textTransform: 'uppercase', letterSpacing: 2,
  },

  // Wallet card
  walletCard: {
    flexDirection: 'row', alignItems: 'center',
    borderRadius: BORDER_RADIUS.xl, padding: SPACING.md, gap: SPACING.md,
    borderWidth: 1, borderColor: COLORS.gold + '40',
  },
  walletCardIcon: {
    width: 48, height: 48, borderRadius: BORDER_RADIUS.md,
    backgroundColor: COLORS.gold + '15', justifyContent: 'center', alignItems: 'center',
    borderWidth: 1, borderColor: COLORS.gold + '30',
  },
  cardInfo: { flex: 1 },
  cardTitle: { fontSize: FONT_SIZES.md, fontWeight: '700', color: COLORS.text },
  cardBadgeRow: { flexDirection: 'row', alignItems: 'center', marginTop: 4 },
  networkBadge: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  networkDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: COLORS.success },
  cardSub: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted },
  acicBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 2,
    backgroundColor: COLORS.gold + '20', paddingHorizontal: 6, paddingVertical: 2,
    borderRadius: BORDER_RADIUS.sm, borderWidth: 1, borderColor: COLORS.gold + '30',
  },
  acicText: { fontSize: 9, fontWeight: '800', color: COLORS.gold },

  // Setting rows
  settingRow: {
    flexDirection: 'row', alignItems: 'center', backgroundColor: COLORS.surface,
    borderRadius: BORDER_RADIUS.lg, padding: SPACING.md, marginBottom: SPACING.sm,
    gap: SPACING.md, borderWidth: 1, borderColor: COLORS.border,
  },
  settingIcon: { width: 34, height: 34, borderRadius: BORDER_RADIUS.sm, justifyContent: 'center', alignItems: 'center' },
  settingText: { flex: 1, fontSize: FONT_SIZES.md, color: COLORS.text },
  versionBadge: {
    backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.sm,
    paddingHorizontal: SPACING.sm, paddingVertical: 2, borderWidth: 1, borderColor: COLORS.border,
  },
  versionText: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, fontWeight: '600' },

  // Delete
  deleteBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    backgroundColor: COLORS.error + '12', borderRadius: BORDER_RADIUS.lg,
    padding: SPACING.md, gap: SPACING.sm, borderWidth: 1, borderColor: COLORS.error + '30',
  },
  deleteText: { fontSize: FONT_SIZES.md, fontWeight: '600', color: COLORS.error },
});
