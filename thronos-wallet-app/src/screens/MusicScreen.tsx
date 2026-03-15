import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  View, Text, StyleSheet, FlatList, TouchableOpacity, ScrollView,
  RefreshControl, ActivityIndicator, Modal, Animated, Dimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { COLORS, SPACING, FONT_SIZES, BORDER_RADIUS } from '../constants/theme';
import { useStore } from '../store/useStore';
import { CONFIG } from '../constants/config';

const { width: SCREEN_W } = Dimensions.get('window');

// ── Types ────────────────────────────────────────────────────────────────────

interface Track {
  id: string;
  title: string;
  artist: string;
  album?: string;
  duration: number; // seconds
  genre?: string;
  plays: number;
  tips_earned: number;
  artwork_url?: string;
  stream_url?: string;
  is_offline?: boolean;
}

interface Playlist {
  id: string;
  name: string;
  track_count: number;
  total_duration: number;
  created_at: string;
}

interface ArtistEarnings {
  total_tips: number;
  total_plays: number;
  total_tracks: number;
  top_track?: string;
}

// ── API Helpers ──────────────────────────────────────────────────────────────

async function fetchJSON<T = any>(endpoint: string): Promise<T> {
  const res = await fetch(`${CONFIG.API_URL}${endpoint}`, {
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function postJSON<T = any>(endpoint: string, body: any): Promise<T> {
  const res = await fetch(`${CONFIG.API_URL}${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// No mock data — all music data fetched from chain API

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatDuration(s: number): string {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}:${sec.toString().padStart(2, '0')}`;
}

function formatNumber(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
}

// ── Component ────────────────────────────────────────────────────────────────

type TabType = 'tracks' | 'playlists' | 'earnings' | 'offline';

export default function MusicScreen({ navigation }: any) {
  const { wallet } = useStore();
  const [activeTab, setActiveTab] = useState<TabType>('tracks');
  const [tracks, setTracks] = useState<Track[]>([]);
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [currentTrack, setCurrentTrack] = useState<Track | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [tipModalVisible, setTipModalVisible] = useState(false);
  const [tipAmount, setTipAmount] = useState(1);
  const [tipTarget, setTipTarget] = useState<Track | null>(null);
  const [earnings, setEarnings] = useState<ArtistEarnings>({
    total_tips: 0, total_plays: 0, total_tracks: 0, top_track: undefined,
  });

  const progressAnim = useRef(new Animated.Value(0)).current;
  const pulseAnim = useRef(new Animated.Value(1)).current;

  // Pulse animation for now-playing indicator
  useEffect(() => {
    if (isPlaying) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, { toValue: 1.2, duration: 600, useNativeDriver: true }),
          Animated.timing(pulseAnim, { toValue: 1, duration: 600, useNativeDriver: true }),
        ]),
      ).start();
    } else {
      pulseAnim.setValue(1);
    }
  }, [isPlaying]);

  const loadData = useCallback(async () => {
    if (!wallet.address) return;
    setLoading(true);
    try {
      const [trackRes, playlistRes, earningsRes] = await Promise.allSettled([
        fetchJSON(`/api/v1/music/tracks?address=${wallet.address}`),
        fetchJSON(`/api/music/playlists?address=${wallet.address}`),
        fetchJSON(`/api/v1/music/earnings?address=${wallet.address}`),
      ]);
      if (trackRes.status === 'fulfilled' && trackRes.value?.tracks) {
        setTracks(trackRes.value.tracks);
      }
      if (playlistRes.status === 'fulfilled' && playlistRes.value?.playlists) {
        setPlaylists(playlistRes.value.playlists);
      }
      if (earningsRes.status === 'fulfilled' && earningsRes.value) {
        setEarnings(earningsRes.value);
      }
    } catch (err) {
      console.warn('Failed to load music data:', err);
    } finally {
      setLoading(false);
    }
  }, [wallet.address]);

  useEffect(() => { loadData(); }, [loadData]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await loadData();
    setRefreshing(false);
  }, [loadData]);

  const playTrack = (track: Track) => {
    setCurrentTrack(track);
    setIsPlaying(true);
    progressAnim.setValue(0);
    Animated.timing(progressAnim, {
      toValue: 1,
      duration: track.duration * 1000,
      useNativeDriver: false,
    }).start();
    // Record play
    postJSON('/api/v1/music/play/' + track.id, { address: wallet.address }).catch(() => {});
  };

  const togglePlayPause = () => setIsPlaying(!isPlaying);

  const openTipModal = (track: Track) => {
    setTipTarget(track);
    setTipAmount(1);
    setTipModalVisible(true);
  };

  const sendTip = async () => {
    if (!tipTarget || !wallet.address) return;
    try {
      await postJSON('/api/v1/music/tip', {
        address: wallet.address,
        track_id: tipTarget.id,
        artist: tipTarget.artist,
        amount: tipAmount,
      });
    } catch {
      // Silent fail for demo
    }
    setTipModalVisible(false);
  };

  // ── Render Helpers ───────────────────────────────────────────────────────────

  const renderTrack = ({ item, index }: { item: Track; index: number }) => {
    const isCurrent = currentTrack?.id === item.id;
    return (
      <TouchableOpacity
        style={[styles.trackRow, isCurrent && styles.trackRowActive]}
        onPress={() => playTrack(item)}
        activeOpacity={0.7}
      >
        <View style={styles.trackNumber}>
          {isCurrent && isPlaying ? (
            <Animated.View style={{ transform: [{ scale: pulseAnim }] }}>
              <Ionicons name="musical-notes" size={18} color={COLORS.gold} />
            </Animated.View>
          ) : (
            <Text style={styles.trackNumText}>{index + 1}</Text>
          )}
        </View>
        <View style={styles.trackInfo}>
          <Text style={[styles.trackTitle, isCurrent && { color: COLORS.gold }]} numberOfLines={1}>
            {item.title}
          </Text>
          <Text style={styles.trackArtist} numberOfLines={1}>{item.artist}</Text>
        </View>
        <View style={styles.trackMeta}>
          <Text style={styles.trackDuration}>{formatDuration(item.duration)}</Text>
          <View style={styles.trackStats}>
            <Ionicons name="play" size={10} color={COLORS.textMuted} />
            <Text style={styles.trackPlays}>{formatNumber(item.plays)}</Text>
          </View>
        </View>
        <TouchableOpacity style={styles.tipBtn} onPress={() => openTipModal(item)}>
          <Ionicons name="heart" size={16} color={COLORS.gold} />
          <Text style={styles.tipBtnText}>{item.tips_earned.toFixed(1)}</Text>
        </TouchableOpacity>
      </TouchableOpacity>
    );
  };

  const renderPlaylist = ({ item }: { item: Playlist }) => (
    <TouchableOpacity style={styles.playlistCard} activeOpacity={0.7}>
      <LinearGradient
        colors={['#2A1A4A', '#1A1A33']}
        style={styles.playlistGradient}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
      >
        <Ionicons name="musical-notes" size={32} color={COLORS.primaryLight} />
        <Text style={styles.playlistName} numberOfLines={1}>{item.name}</Text>
        <Text style={styles.playlistMeta}>
          {item.track_count} tracks &middot; {Math.floor(item.total_duration / 60)} min
        </Text>
      </LinearGradient>
    </TouchableOpacity>
  );

  const renderEarnings = () => (
    <ScrollView style={styles.earningsContainer}>
      <LinearGradient colors={['#2A1A0A', '#1A1A33']} style={styles.earningsCard}>
        <Text style={styles.earningsLabel}>Total Tips Earned</Text>
        <Text style={styles.earningsAmount}>{earnings.total_tips.toFixed(1)} THR</Text>
        <View style={styles.earningsGrid}>
          <View style={styles.earningStat}>
            <Ionicons name="play-circle" size={24} color={COLORS.info} />
            <Text style={styles.earningStatVal}>{formatNumber(earnings.total_plays)}</Text>
            <Text style={styles.earningStatLabel}>Total Plays</Text>
          </View>
          <View style={styles.earningStat}>
            <Ionicons name="disc" size={24} color={COLORS.primary} />
            <Text style={styles.earningStatVal}>{earnings.total_tracks}</Text>
            <Text style={styles.earningStatLabel}>Tracks</Text>
          </View>
          <View style={styles.earningStat}>
            <Ionicons name="trophy" size={24} color={COLORS.gold} />
            <Text style={styles.earningStatVal} numberOfLines={1}>{earnings.top_track}</Text>
            <Text style={styles.earningStatLabel}>Top Track</Text>
          </View>
        </View>
      </LinearGradient>

      <Text style={styles.sectionTitle}>Decent Music Network</Text>
      <View style={styles.decentCard}>
        <Ionicons name="globe-outline" size={24} color={COLORS.primary} />
        <View style={{ flex: 1, marginLeft: SPACING.md }}>
          <Text style={styles.decentTitle}>Direct Artist Payments</Text>
          <Text style={styles.decentDesc}>
            All tips go directly to artists via THR — no middlemen, no platform fees.
            Artists earn 100% of listener tips on Decent Music.
          </Text>
        </View>
      </View>
      <View style={styles.decentCard}>
        <Ionicons name="flash-outline" size={24} color={COLORS.gold} />
        <View style={{ flex: 1, marginLeft: SPACING.md }}>
          <Text style={styles.decentTitle}>ACIC-Powered Streaming</Text>
          <Text style={styles.decentDesc}>
            Music streams routed through Thronos ACIC nodes for ultra-low latency
            playback. Background playback with CarPlay/Android Auto support.
          </Text>
        </View>
      </View>
      <View style={styles.decentCard}>
        <Ionicons name="radio-outline" size={24} color={COLORS.success} />
        <View style={{ flex: 1, marginLeft: SPACING.md }}>
          <Text style={styles.decentTitle}>WhisperNote Integration</Text>
          <Text style={styles.decentDesc}>
            Audio-encoded transaction data via WhisperNote. Every play is an on-chain
            micro-transaction with full transparency.
          </Text>
        </View>
      </View>
    </ScrollView>
  );

  const tabs: { key: TabType; label: string; icon: keyof typeof Ionicons.glyphMap }[] = [
    { key: 'tracks', label: 'Tracks', icon: 'musical-notes' },
    { key: 'playlists', label: 'Playlists', icon: 'list' },
    { key: 'earnings', label: 'Earnings', icon: 'cash-outline' },
    { key: 'offline', label: 'Offline', icon: 'cloud-download-outline' },
  ];

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={styles.title}>Decent Music</Text>
        <TouchableOpacity>
          <Ionicons name="search" size={22} color={COLORS.textSecondary} />
        </TouchableOpacity>
      </View>

      {/* Tab Bar */}
      <View style={styles.tabBar}>
        {tabs.map((tab) => (
          <TouchableOpacity
            key={tab.key}
            style={[styles.tab, activeTab === tab.key && styles.tabActive]}
            onPress={() => setActiveTab(tab.key)}
          >
            <Ionicons
              name={tab.icon}
              size={16}
              color={activeTab === tab.key ? COLORS.gold : COLORS.textMuted}
            />
            <Text style={[styles.tabText, activeTab === tab.key && styles.tabTextActive]}>
              {tab.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Content */}
      {loading ? (
        <View style={styles.center}><ActivityIndicator color={COLORS.gold} size="large" /></View>
      ) : activeTab === 'tracks' ? (
        <FlatList
          data={tracks}
          keyExtractor={(t) => t.id}
          renderItem={renderTrack}
          contentContainerStyle={styles.list}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.gold} />}
        />
      ) : activeTab === 'playlists' ? (
        <FlatList
          data={playlists}
          keyExtractor={(p) => p.id}
          renderItem={renderPlaylist}
          numColumns={2}
          columnWrapperStyle={{ gap: SPACING.sm }}
          contentContainerStyle={styles.list}
        />
      ) : activeTab === 'earnings' ? (
        renderEarnings()
      ) : (
        <View style={styles.center}>
          <Ionicons name="cloud-download-outline" size={56} color={COLORS.textMuted} />
          <Text style={styles.emptyText}>No offline tracks</Text>
          <Text style={styles.emptySubText}>Tap the download icon on any track to save for offline playback</Text>
        </View>
      )}

      {/* Now Playing Bar */}
      {currentTrack && (
        <View style={styles.nowPlaying}>
          <Animated.View
            style={[styles.progressBar, {
              width: progressAnim.interpolate({ inputRange: [0, 1], outputRange: ['0%', '100%'] }),
            }]}
          />
          <View style={styles.nowPlayingContent}>
            <View style={styles.nowPlayingInfo}>
              <Text style={styles.nowPlayingTitle} numberOfLines={1}>{currentTrack.title}</Text>
              <Text style={styles.nowPlayingArtist} numberOfLines={1}>{currentTrack.artist}</Text>
            </View>
            <View style={styles.nowPlayingControls}>
              <TouchableOpacity onPress={() => { /* prev */ }}>
                <Ionicons name="play-skip-back" size={20} color={COLORS.text} />
              </TouchableOpacity>
              <TouchableOpacity onPress={togglePlayPause} style={styles.playPauseBtn}>
                <Ionicons name={isPlaying ? 'pause' : 'play'} size={22} color={COLORS.background} />
              </TouchableOpacity>
              <TouchableOpacity onPress={() => { /* next */ }}>
                <Ionicons name="play-skip-forward" size={20} color={COLORS.text} />
              </TouchableOpacity>
            </View>
          </View>
        </View>
      )}

      {/* Tip Modal */}
      <Modal visible={tipModalVisible} transparent animationType="fade">
        <View style={styles.modalOverlay}>
          <View style={styles.tipModal}>
            <Text style={styles.tipModalTitle}>Tip Artist</Text>
            <Text style={styles.tipModalArtist}>{tipTarget?.artist}</Text>
            <Text style={styles.tipModalTrack}>&quot;{tipTarget?.title}&quot;</Text>

            <View style={styles.tipAmounts}>
              {[1, 5, 10, 25].map((amt) => (
                <TouchableOpacity
                  key={amt}
                  style={[styles.tipAmountBtn, tipAmount === amt && styles.tipAmountBtnActive]}
                  onPress={() => setTipAmount(amt)}
                >
                  <Text style={[styles.tipAmountText, tipAmount === amt && styles.tipAmountTextActive]}>
                    {amt} THR
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            <View style={styles.tipModalActions}>
              <TouchableOpacity style={styles.tipCancelBtn} onPress={() => setTipModalVisible(false)}>
                <Text style={styles.tipCancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.tipSendBtn} onPress={sendTip}>
                <Ionicons name="heart" size={16} color="#FFF" />
                <Text style={styles.tipSendText}>Send {tipAmount} THR</Text>
              </TouchableOpacity>
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
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: SPACING.lg, paddingVertical: SPACING.md,
  },
  backBtn: { padding: SPACING.xs },
  title: { fontSize: FONT_SIZES.xxl, fontWeight: '700', color: COLORS.text },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', gap: SPACING.md, paddingHorizontal: SPACING.xl },
  emptyText: { fontSize: FONT_SIZES.lg, color: COLORS.textMuted, fontWeight: '600' },
  emptySubText: { fontSize: FONT_SIZES.sm, color: COLORS.textMuted, textAlign: 'center' },
  list: { paddingHorizontal: SPACING.lg, paddingBottom: 100 },

  // Tab Bar
  tabBar: { flexDirection: 'row', paddingHorizontal: SPACING.lg, marginBottom: SPACING.md, gap: SPACING.sm },
  tab: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    paddingVertical: SPACING.sm, borderRadius: BORDER_RADIUS.lg, gap: 4,
    backgroundColor: COLORS.surface,
  },
  tabActive: { backgroundColor: COLORS.gold + '20', borderWidth: 1, borderColor: COLORS.gold + '40' },
  tabText: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, fontWeight: '500' },
  tabTextActive: { color: COLORS.gold },

  // Track Row
  trackRow: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.lg,
    padding: SPACING.md, marginBottom: SPACING.sm,
    borderWidth: 1, borderColor: COLORS.border,
  },
  trackRowActive: { borderColor: COLORS.gold + '40', backgroundColor: COLORS.gold + '08' },
  trackNumber: { width: 28, alignItems: 'center' },
  trackNumText: { fontSize: FONT_SIZES.sm, color: COLORS.textMuted, fontWeight: '600' },
  trackInfo: { flex: 1, marginLeft: SPACING.sm },
  trackTitle: { fontSize: FONT_SIZES.md, fontWeight: '600', color: COLORS.text },
  trackArtist: { fontSize: FONT_SIZES.xs, color: COLORS.textSecondary, marginTop: 2 },
  trackMeta: { alignItems: 'flex-end', marginRight: SPACING.sm },
  trackDuration: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted, fontFamily: 'monospace' },
  trackStats: { flexDirection: 'row', alignItems: 'center', gap: 3, marginTop: 2 },
  trackPlays: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted },
  tipBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    backgroundColor: COLORS.gold + '15', paddingHorizontal: SPACING.sm, paddingVertical: 4,
    borderRadius: BORDER_RADIUS.full,
  },
  tipBtnText: { fontSize: FONT_SIZES.xs, color: COLORS.gold, fontWeight: '600' },

  // Playlist
  playlistCard: { flex: 1, marginBottom: SPACING.sm },
  playlistGradient: {
    padding: SPACING.lg, borderRadius: BORDER_RADIUS.lg, minHeight: 130,
    justifyContent: 'flex-end', gap: SPACING.xs,
  },
  playlistName: { fontSize: FONT_SIZES.lg, fontWeight: '700', color: COLORS.text },
  playlistMeta: { fontSize: FONT_SIZES.xs, color: COLORS.textSecondary },

  // Earnings
  earningsContainer: { flex: 1, paddingHorizontal: SPACING.lg },
  earningsCard: {
    borderRadius: BORDER_RADIUS.lg, padding: SPACING.lg, marginBottom: SPACING.lg,
    borderWidth: 1, borderColor: COLORS.gold + '30',
  },
  earningsLabel: { fontSize: FONT_SIZES.sm, color: COLORS.textSecondary },
  earningsAmount: { fontSize: FONT_SIZES.xxxl, fontWeight: '800', color: COLORS.gold, marginTop: SPACING.xs },
  earningsGrid: { flexDirection: 'row', justifyContent: 'space-around', marginTop: SPACING.lg },
  earningStat: { alignItems: 'center', gap: SPACING.xs },
  earningStatVal: { fontSize: FONT_SIZES.lg, fontWeight: '700', color: COLORS.text },
  earningStatLabel: { fontSize: FONT_SIZES.xs, color: COLORS.textMuted },

  sectionTitle: { fontSize: FONT_SIZES.xl, fontWeight: '700', color: COLORS.text, marginBottom: SPACING.md },
  decentCard: {
    flexDirection: 'row', backgroundColor: COLORS.surface, borderRadius: BORDER_RADIUS.lg,
    padding: SPACING.md, marginBottom: SPACING.sm, borderWidth: 1, borderColor: COLORS.border,
  },
  decentTitle: { fontSize: FONT_SIZES.md, fontWeight: '600', color: COLORS.text },
  decentDesc: { fontSize: FONT_SIZES.sm, color: COLORS.textSecondary, marginTop: 4, lineHeight: 18 },

  // Now Playing
  nowPlaying: {
    position: 'absolute', bottom: 0, left: 0, right: 0,
    backgroundColor: COLORS.backgroundCard, borderTopWidth: 1, borderTopColor: COLORS.border,
  },
  progressBar: {
    height: 2, backgroundColor: COLORS.gold,
  },
  nowPlayingContent: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: SPACING.lg, paddingVertical: SPACING.md,
  },
  nowPlayingInfo: { flex: 1 },
  nowPlayingTitle: { fontSize: FONT_SIZES.md, fontWeight: '600', color: COLORS.text },
  nowPlayingArtist: { fontSize: FONT_SIZES.xs, color: COLORS.textSecondary },
  nowPlayingControls: { flexDirection: 'row', alignItems: 'center', gap: SPACING.md },
  playPauseBtn: {
    width: 36, height: 36, borderRadius: BORDER_RADIUS.full,
    backgroundColor: COLORS.gold, justifyContent: 'center', alignItems: 'center',
  },

  // Tip Modal
  modalOverlay: {
    flex: 1, backgroundColor: COLORS.overlay, justifyContent: 'center', alignItems: 'center',
  },
  tipModal: {
    width: SCREEN_W - 48, backgroundColor: COLORS.backgroundCard,
    borderRadius: BORDER_RADIUS.xl, padding: SPACING.lg,
    borderWidth: 1, borderColor: COLORS.border,
  },
  tipModalTitle: { fontSize: FONT_SIZES.xl, fontWeight: '700', color: COLORS.text, textAlign: 'center' },
  tipModalArtist: { fontSize: FONT_SIZES.lg, color: COLORS.gold, textAlign: 'center', marginTop: SPACING.sm },
  tipModalTrack: { fontSize: FONT_SIZES.sm, color: COLORS.textSecondary, textAlign: 'center', marginTop: 4 },
  tipAmounts: {
    flexDirection: 'row', justifyContent: 'center', gap: SPACING.sm, marginTop: SPACING.lg,
  },
  tipAmountBtn: {
    paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm,
    borderRadius: BORDER_RADIUS.lg, backgroundColor: COLORS.surface,
    borderWidth: 1, borderColor: COLORS.border,
  },
  tipAmountBtnActive: { backgroundColor: COLORS.gold + '20', borderColor: COLORS.gold },
  tipAmountText: { fontSize: FONT_SIZES.md, fontWeight: '600', color: COLORS.textSecondary },
  tipAmountTextActive: { color: COLORS.gold },
  tipModalActions: { flexDirection: 'row', gap: SPACING.sm, marginTop: SPACING.lg },
  tipCancelBtn: {
    flex: 1, paddingVertical: SPACING.md, borderRadius: BORDER_RADIUS.lg,
    backgroundColor: COLORS.surface, alignItems: 'center',
  },
  tipCancelText: { fontSize: FONT_SIZES.md, color: COLORS.textSecondary, fontWeight: '600' },
  tipSendBtn: {
    flex: 2, flexDirection: 'row', gap: SPACING.xs,
    paddingVertical: SPACING.md, borderRadius: BORDER_RADIUS.lg,
    backgroundColor: COLORS.gold, alignItems: 'center', justifyContent: 'center',
  },
  tipSendText: { fontSize: FONT_SIZES.md, color: COLORS.background, fontWeight: '700' },
});
