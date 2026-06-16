import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  Alert,
  ActivityIndicator,
  FlatList,
  Image,
  Modal,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT_SIZES, BORDER_RADIUS } from '../constants/theme';
import { useStore } from '../store/useStore';
import { getNfts, mintNft, buyNft, ThronosNft } from '../services/api';
import { getWallet, getPrivateKey } from '../services/wallet';
import { CONFIG } from '../constants/config';

function shortenAddr(addr: string): string {
  return addr ? `${addr.slice(0, 6)}…${addr.slice(-4)}` : '';
}

export default function NFTScreen({ navigation }: { navigation: any }) {
  const { wallet } = useStore();
  const [nfts, setNfts] = useState<ThronosNft[]>([]);
  const [loading, setLoading] = useState(true);
  const [buyingId, setBuyingId] = useState<string | null>(null);
  const [showMint, setShowMint] = useState(false);
  const [minting, setMinting] = useState(false);

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [price, setPrice] = useState('');
  const [royalties, setRoyalties] = useState('10');

  const load = useCallback(async () => {
    try {
      const res = await getNfts();
      setNfts(res.nfts || []);
    } catch (err) {
      console.warn('NFTs: failed to load', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleBuy = useCallback((nft: ThronosNft) => {
    Alert.alert('Buy NFT', `Buy "${nft.name}" for ${nft.price} THR?`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Buy',
        onPress: async () => {
          setBuyingId(nft.id);
          try {
            const creds = await getWallet();
            const privHex = await getPrivateKey();
            if (!creds?.address || !privHex) {
              Alert.alert('Error', 'Wallet credentials not found.');
              return;
            }
            const result = await buyNft({ from: creds.address, nft_id: nft.id, private_key_hex: privHex });
            if (result.ok) {
              Alert.alert('Purchased', `You now own "${nft.name}".`);
              load();
            } else {
              Alert.alert('Failed', result.error || 'Purchase failed.');
            }
          } catch (error: any) {
            Alert.alert('Failed', error.message || 'An unexpected error occurred.');
          } finally {
            setBuyingId(null);
          }
        },
      },
    ]);
  }, [load]);

  const resetMintForm = () => {
    setName('');
    setDescription('');
    setPrice('');
    setRoyalties('10');
  };

  const handleMint = useCallback(async () => {
    if (!name.trim()) {
      Alert.alert('Invalid form', 'Enter a name for your NFT.');
      return;
    }
    setMinting(true);
    try {
      const creds = await getWallet();
      const privHex = await getPrivateKey();
      if (!creds?.address || !privHex) {
        Alert.alert('Error', 'Wallet credentials not found.');
        return;
      }
      const result = await mintNft({
        from: creds.address,
        name: name.trim(),
        description: description.trim(),
        price: parseFloat(price) || 0,
        royalties: parseInt(royalties, 10) || 0,
        private_key_hex: privHex,
      });
      if (result.ok) {
        setShowMint(false);
        resetMintForm();
        Alert.alert('NFT Minted', `"${name.trim()}" has been minted.`);
        load();
      } else {
        Alert.alert('Failed', result.error || 'Mint failed.');
      }
    } catch (error: any) {
      Alert.alert('Failed', error.message || 'An unexpected error occurred.');
    } finally {
      setMinting(false);
    }
  }, [name, description, price, royalties, load]);

  const renderItem = ({ item }: { item: ThronosNft }) => {
    const isMine = item.owner === wallet.address;
    const imageUri = item.image_url
      ? (item.image_url.startsWith('http') ? item.image_url : `${CONFIG.API_URL}${item.image_url}`)
      : null;
    return (
      <View style={styles.card}>
        {imageUri ? (
          <Image source={{ uri: imageUri }} style={styles.cardImage} />
        ) : (
          <View style={[styles.cardImage, styles.cardImagePlaceholder]}>
            <Ionicons name="image-outline" size={32} color={COLORS.textMuted} />
          </View>
        )}
        <Text style={styles.cardName} numberOfLines={1}>{item.name}</Text>
        {item.description ? <Text style={styles.cardDesc} numberOfLines={2}>{item.description}</Text> : null}
        <Text style={styles.cardOwner}>Owner: {isMine ? 'You' : shortenAddr(item.owner)}</Text>
        <View style={styles.cardFooter}>
          <Text style={styles.cardPrice}>
            {item.for_sale && item.price > 0 ? `${item.price} THR` : 'Not for sale'}
          </Text>
          {!isMine && item.for_sale && item.price > 0 && (
            <TouchableOpacity
              style={styles.buyBtn}
              onPress={() => handleBuy(item)}
              disabled={buyingId === item.id}
              activeOpacity={0.8}
            >
              {buyingId === item.id ? (
                <ActivityIndicator size="small" color={COLORS.background} />
              ) : (
                <Text style={styles.buyBtnText}>Buy</Text>
              )}
            </TouchableOpacity>
          )}
        </View>
      </View>
    );
  };

  return (
    <SafeAreaView style={styles.container}>
      <LinearGradient colors={[COLORS.background, COLORS.backgroundLight]} style={styles.gradient}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => navigation.goBack()} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
            <Ionicons name="arrow-back" size={24} color={COLORS.text} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>NFTs</Text>
          <TouchableOpacity onPress={() => setShowMint(true)} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
            <Ionicons name="add-circle-outline" size={26} color={COLORS.gold} />
          </TouchableOpacity>
        </View>

        {loading ? (
          <ActivityIndicator color={COLORS.gold} style={{ marginTop: SPACING.xl }} />
        ) : nfts.length === 0 ? (
          <View style={styles.emptyBox}>
            <Ionicons name="image-outline" size={40} color={COLORS.textMuted} />
            <Text style={styles.emptyText}>No NFTs yet — mint the first one</Text>
          </View>
        ) : (
          <FlatList
            data={nfts}
            keyExtractor={(item) => item.id}
            renderItem={renderItem}
            numColumns={2}
            columnWrapperStyle={{ gap: SPACING.sm }}
            contentContainerStyle={{ paddingHorizontal: SPACING.lg, paddingBottom: SPACING.xxl, gap: SPACING.sm }}
            showsVerticalScrollIndicator={false}
          />
        )}
      </LinearGradient>

      <Modal visible={showMint} transparent animationType="slide">
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>Mint NFT</Text>

            <Text style={styles.inputLabel}>Name</Text>
            <TextInput style={styles.input} placeholder="NFT name" placeholderTextColor={COLORS.textMuted} value={name} onChangeText={setName} maxLength={64} />

            <Text style={styles.inputLabel}>Description</Text>
            <TextInput style={[styles.input, { height: 70 }]} placeholder="Optional description" placeholderTextColor={COLORS.textMuted} value={description} onChangeText={setDescription} multiline maxLength={500} />

            <Text style={styles.inputLabel}>Price (THR, 0 = not for sale)</Text>
            <TextInput style={styles.input} placeholder="0" placeholderTextColor={COLORS.textMuted} value={price} onChangeText={setPrice} keyboardType="decimal-pad" />

            <Text style={styles.inputLabel}>Royalties %</Text>
            <TextInput style={styles.input} placeholder="10" placeholderTextColor={COLORS.textMuted} value={royalties} onChangeText={setRoyalties} keyboardType="number-pad" maxLength={2} />

            <View style={styles.modalActions}>
              <TouchableOpacity style={styles.modalCancelBtn} onPress={() => { setShowMint(false); resetMintForm(); }} disabled={minting}>
                <Text style={styles.modalCancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.modalConfirmBtn} onPress={handleMint} disabled={minting} activeOpacity={0.8}>
                <LinearGradient colors={[COLORS.gold, COLORS.goldDark]} style={styles.modalConfirmGradient}>
                  {minting ? <ActivityIndicator color={COLORS.background} /> : <Text style={styles.modalConfirmText}>Mint</Text>}
                </LinearGradient>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.background },
  gradient: { flex: 1 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.lg, paddingVertical: SPACING.md },
  headerTitle: { fontSize: FONT_SIZES.xl, fontWeight: '700', color: COLORS.text },
  emptyBox: { alignItems: 'center', padding: SPACING.xl, marginHorizontal: SPACING.lg, marginTop: SPACING.xl, backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.xl, gap: SPACING.sm },
  emptyText: { fontSize: FONT_SIZES.md, color: COLORS.textMuted, textAlign: 'center' },

  card: { flex: 1, backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.xl, padding: SPACING.sm, borderWidth: 1, borderColor: COLORS.border, marginBottom: SPACING.sm },
  cardImage: { width: '100%', height: 110, borderRadius: BORDER_RADIUS.lg, marginBottom: SPACING.xs },
  cardImagePlaceholder: { backgroundColor: COLORS.backgroundCard, alignItems: 'center', justifyContent: 'center' },
  cardName: { fontSize: FONT_SIZES.sm, fontWeight: '700', color: COLORS.text },
  cardDesc: { fontSize: FONT_SIZES.xs, color: COLORS.textSecondary, marginTop: 2 },
  cardOwner: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, marginTop: 4 },
  cardFooter: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: SPACING.sm },
  cardPrice: { fontSize: FONT_SIZES.xs, fontWeight: '700', color: COLORS.gold },
  buyBtn: { backgroundColor: COLORS.gold, paddingHorizontal: SPACING.sm, paddingVertical: 4, borderRadius: BORDER_RADIUS.md, minWidth: 44, alignItems: 'center' },
  buyBtnText: { fontSize: FONT_SIZES.xs, fontWeight: '700', color: COLORS.background },

  modalOverlay: { flex: 1, backgroundColor: COLORS.overlay, justifyContent: 'center', alignItems: 'center', padding: SPACING.lg },
  modalContent: { width: '100%', backgroundColor: COLORS.backgroundCard, borderRadius: BORDER_RADIUS.xl, padding: SPACING.lg, borderWidth: 1, borderColor: COLORS.gold + '30' },
  modalTitle: { fontSize: FONT_SIZES.xxl, fontWeight: '700', color: COLORS.text, marginBottom: SPACING.md },
  inputLabel: { fontSize: FONT_SIZES.sm, fontWeight: '600', color: COLORS.textSecondary, marginBottom: SPACING.xs, marginTop: SPACING.sm },
  input: { backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.lg, borderWidth: 1, borderColor: COLORS.border, padding: SPACING.md, fontSize: FONT_SIZES.md, color: COLORS.text },
  modalActions: { flexDirection: 'row', gap: SPACING.md, marginTop: SPACING.lg },
  modalCancelBtn: { flex: 1, paddingVertical: SPACING.md, borderRadius: BORDER_RADIUS.lg, borderWidth: 1, borderColor: COLORS.border, alignItems: 'center', justifyContent: 'center' },
  modalCancelText: { fontSize: FONT_SIZES.md, fontWeight: '600', color: COLORS.textSecondary },
  modalConfirmBtn: { flex: 1.5, borderRadius: BORDER_RADIUS.lg, overflow: 'hidden' },
  modalConfirmGradient: { paddingVertical: SPACING.md, alignItems: 'center', justifyContent: 'center' },
  modalConfirmText: { fontSize: FONT_SIZES.md, fontWeight: '700', color: COLORS.background },
});
