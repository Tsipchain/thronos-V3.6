import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT_SIZES, BORDER_RADIUS } from '../constants/theme';

export default function ScanScreen() {
  const navigation = useNavigation();

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Ionicons name="close" size={28} color={COLORS.text} />
        </TouchableOpacity>
      </View>
      <View style={styles.center}>
        <View style={styles.scanFrame}>
          <Ionicons name="scan" size={80} color={COLORS.gold} />
        </View>
        <Text style={styles.text}>Point camera at a Thronos QR code</Text>
        <Text style={styles.sub}>Camera permission required for scanning</Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.background },
  header: { paddingHorizontal: SPACING.lg, paddingVertical: SPACING.md },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', gap: SPACING.lg },
  scanFrame: {
    width: 200, height: 200, borderWidth: 3, borderColor: COLORS.gold + '50',
    borderRadius: BORDER_RADIUS.xl, justifyContent: 'center', alignItems: 'center',
  },
  text: { fontSize: FONT_SIZES.lg, color: COLORS.text, fontWeight: '600' },
  sub: { fontSize: FONT_SIZES.sm, color: COLORS.textMuted },
});
