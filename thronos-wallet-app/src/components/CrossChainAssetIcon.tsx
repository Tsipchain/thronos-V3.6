import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import Svg, { Circle, Path, Text as SvgText } from 'react-native-svg';

type Props = {
  symbol: string;
  network: string;
  size?: number;
};

const TOKEN_COLORS: Record<string, string> = {
  USDC: '#2775CA',
  USDT: '#26A17B',
  BNB: '#F3BA2F',
  ETH: '#627EEA',
  BTC: '#F7931A',
  THR: '#D6B45B',
};

const NETWORK_BADGES: Record<string, { label: string; color: string }> = {
  bnb: { label: 'BNB', color: '#B88700' },
  arbitrum: { label: 'ARB', color: '#28A0F0' },
  base: { label: 'BASE', color: '#0052FF' },
  ethereum: { label: 'ETH', color: '#627EEA' },
  bitcoin: { label: 'BTC', color: '#F7931A' },
  thronos: { label: 'THR', color: '#B99A43' },
};

function TokenMark({ symbol, size }: { symbol: string; size: number }) {
  const token = symbol.toUpperCase();
  const color = TOKEN_COLORS[token] || '#64748B';
  const commonText = { fill: '#FFFFFF', fontSize: 18, fontWeight: '700' as const, textAnchor: 'middle' as const };
  return (
    <Svg width={size} height={size} viewBox="0 0 48 48">
      <Circle cx="24" cy="24" r="22" fill={color} />
      {token === 'USDC' ? (
        <>
          <Circle cx="24" cy="24" r="15" fill="none" stroke="#FFFFFF" strokeWidth="2.3" />
          <Path d="M16 17.5 C13.5 19.5 13.5 28.5 16 30.5 M32 17.5 C34.5 19.5 34.5 28.5 32 30.5" fill="none" stroke="#FFFFFF" strokeWidth="2.3" strokeLinecap="round" />
          <SvgText x="24" y="30" {...commonText} fontSize="17">$</SvgText>
        </>
      ) : token === 'USDT' ? (
        <>
          <Path d="M10 11 H38 M24 11 V36 M13 19 C16 23 32 23 35 19" fill="none" stroke="#FFFFFF" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
          <Path d="M17 28 C19 31 29 31 31 28" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" />
        </>
      ) : token === 'BNB' ? (
        <>
          <Path d="M24 5 L30 11 L24 17 L18 11 Z M13 16 L19 22 L13 28 L7 22 Z M35 16 L41 22 L35 28 L29 22 Z M24 25 L30 31 L24 37 L18 31 Z M24 17 L31 24 L24 31 L17 24 Z" fill="#FFFFFF" />
        </>
      ) : token === 'ETH' ? (
        <>
          <Path d="M24 5 L12.5 24 L24 30 L35.5 24 Z" fill="#FFFFFF" />
          <Path d="M24 32 L12.5 26 L24 43 L35.5 26 Z" fill="#D6DDFB" />
        </>
      ) : token === 'BTC' ? (
        <SvgText x="24" y="31" {...commonText} fontSize="22">₿</SvgText>
      ) : token === 'THR' ? (
        <>
          <Path d="M24 5 L39 14 L39 32 L24 41 L9 32 L9 14 Z" fill="none" stroke="#FFFFFF" strokeWidth="2.5" />
          <Path d="M17 17 H31 L24 31 Z" fill="#FFFFFF" />
        </>
      ) : (
        <SvgText x="24" y="30" {...commonText}>{token.slice(0, 1)}</SvgText>
      )}
    </Svg>
  );
}

export default function CrossChainAssetIcon({ symbol, network, size = 42 }: Props) {
  const badge = NETWORK_BADGES[network.toLowerCase()];
  const badgeWidth = badge?.label === 'BASE' ? 29 : 25;
  return (
    <View style={[styles.wrap, { width: size + 7, height: size + 5 }]}>
      <TokenMark symbol={symbol} size={size} />
      {badge ? (
        <View style={[styles.badge, { backgroundColor: badge.color, minWidth: badgeWidth }]}>
          <Text style={styles.badgeText}>{badge.label}</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    position: 'relative',
    alignItems: 'flex-start',
    justifyContent: 'flex-start',
    marginRight: 4,
  },
  badge: {
    position: 'absolute',
    right: -1,
    bottom: -1,
    height: 15,
    borderRadius: 5,
    borderWidth: 1.5,
    borderColor: '#101321',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 3,
  },
  badgeText: {
    color: '#FFFFFF',
    fontSize: 7,
    fontWeight: '800',
    letterSpacing: -0.2,
  },
});
