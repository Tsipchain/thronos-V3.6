import React from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Switch, Alert, Linking,
} from 'react-native';
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

        {/* Wallet Info */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Wallet</Text>
          <View style={styles.card}>
            <Ionicons name="planet" size={24} color={COLORS.gold} />
            <View style={styles.cardInfo}>
              <Text style={styles.cardTitle}>{wallet.address ? shortenAddress(wallet.address) : 'Not connected'}</Text>
              <Text style={styles.cardSub}>Thronos Chain</Text>
            </View>
          </View>
        </View>

        {/* Security */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Security</Text>

          <TouchableOpacity style={styles.settingRow} onPress={handleExportKey}>
            <Ionicons name="key" size={20} color={COLORS.warning} />
            <Text style={styles.settingText}>Export Secret Key</Text>
            <Ionicons name="chevron-forward" size={20} color={COLORS.textMuted} />
          </TouchableOpacity>
        </View>

        {/* Preferences */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Preferences</Text>

          <View style={styles.settingRow}>
            <Ionicons name="notifications" size={20} color={COLORS.info} />
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
            <Ionicons name="globe" size={20} color={COLORS.primary} />
            <Text style={styles.settingText}>Website</Text>
            <Ionicons name="chevron-forward" size={20} color={COLORS.textMuted} />
          </TouchableOpacity>

          <TouchableOpacity style={styles.settingRow} onPress={() => Linking.openURL(`mailto:${CONFIG.SUPPORT_EMAIL}`)}>
            <Ionicons name="mail" size={20} color={COLORS.info} />
            <Text style={styles.settingText}>Support</Text>
            <Ionicons name="chevron-forward" size={20} color={COLORS.textMuted} />
          </TouchableOpacity>

          <View style={styles.settingRow}>
            <Ionicons name="information-circle" size={20} color={COLORS.textMuted} />
            <Text style={styles.settingText}>Version</Text>
            <Text style={styles.versionText}>{CONFIG.APP_VERSION}</Text>
          </View>
        </View>

        {/* Danger Zone */}
        <TouchableOpacity style={styles.deleteBtn} onPress={handleDisconnect}>
          <Ionicons name="trash" size={20} color={COLORS.error} />
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
  title: { fontSize: FONT_SIZES.xxl, fontWeight: '700', color: COLORS.text, paddingVertical: SPACING.md },
  section: { marginBottom: SPACING.lg },
  sectionTitle: { fontSize: FONT_SIZES.sm, fontWeight: '600', color: COLORS.textMuted, marginBottom: SPACING.sm, textTransform: 'uppercase' },
  card: {
    flexDirection: 'row', alignItems: 'center', backgroundColor: COLORS.surface,
    borderRadius: BORDER_RADIUS.lg, padding: SPACING.md, gap: SPACING.md,
    borderWidth: 1, borderColor: COLORS.gold + '30',
  },
  cardInfo: { flex: 1 },
  cardTitle: { fontSize: FONT_SIZES.md, fontWeight: '600', color: COLORS.text },
  cardSub: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted },
  settingRow: {
    flexDirection: 'row', alignItems: 'center', backgroundColor: COLORS.surface,
    borderRadius: BORDER_RADIUS.lg, padding: SPACING.md, marginBottom: SPACING.sm,
    gap: SPACING.md, borderWidth: 1, borderColor: COLORS.border,
  },
  settingText: { flex: 1, fontSize: FONT_SIZES.md, color: COLORS.text },
  versionText: { fontSize: FONT_SIZES.md, color: COLORS.textMuted },
  deleteBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    backgroundColor: COLORS.error + '15', borderRadius: BORDER_RADIUS.lg,
    padding: SPACING.md, gap: SPACING.sm, borderWidth: 1, borderColor: COLORS.error + '30',
  },
  deleteText: { fontSize: FONT_SIZES.md, fontWeight: '600', color: COLORS.error },
});
