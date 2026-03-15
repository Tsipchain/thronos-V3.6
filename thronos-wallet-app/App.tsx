import React, { useEffect, useState } from 'react';
import { StatusBar } from 'expo-status-bar';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { View, ActivityIndicator, StyleSheet } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as SplashScreen from 'expo-splash-screen';

// Screens
import WelcomeScreen from './src/screens/WelcomeScreen';
import CreateWalletScreen from './src/screens/CreateWalletScreen';
import ImportWalletScreen from './src/screens/ImportWalletScreen';
import HomeScreen from './src/screens/HomeScreen';
import HistoryScreen from './src/screens/HistoryScreen';
import SettingsScreen from './src/screens/SettingsScreen';
import SendScreen from './src/screens/SendScreen';
import ReceiveScreen from './src/screens/ReceiveScreen';
import SwapScreen from './src/screens/SwapScreen';
import StakeScreen from './src/screens/StakeScreen';
import ScanScreen from './src/screens/ScanScreen';
import T2EDashboardScreen from './src/screens/T2EDashboardScreen';
import BridgeScreen from './src/screens/BridgeScreen';
import MusicScreen from './src/screens/MusicScreen';
import PledgeScreen from './src/screens/PledgeScreen';

import { useStore } from './src/store/useStore';
import { COLORS } from './src/constants/theme';

// Navigation types
export type RootStackParamList = {
  Welcome: undefined;
  CreateWallet: undefined;
  ImportWallet: undefined;
  MainTabs: undefined;
  Send: undefined;
  Receive: undefined;
  Swap: undefined;
  Stake: undefined;
  Scan: undefined;
  T2E: undefined;
  Bridge: undefined;
  Music: undefined;
  Pledge: undefined;
};

export type TabParamList = {
  Home: undefined;
  T2E: undefined;
  Music: undefined;
  History: undefined;
  Settings: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();
const Tab = createBottomTabNavigator<TabParamList>();

SplashScreen.preventAutoHideAsync();

function MainTabs() {
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        tabBarIcon: ({ focused, color, size }) => {
          let iconName: keyof typeof Ionicons.glyphMap = 'home';
          switch (route.name) {
            case 'Home': iconName = focused ? 'wallet' : 'wallet-outline'; break;
            case 'T2E': iconName = focused ? 'sparkles' : 'sparkles-outline'; break;
            case 'Music': iconName = focused ? 'musical-notes' : 'musical-notes-outline'; break;
            case 'History': iconName = focused ? 'time' : 'time-outline'; break;
            case 'Settings': iconName = focused ? 'settings' : 'settings-outline'; break;
          }
          return <Ionicons name={iconName} size={size} color={color} />;
        },
        tabBarActiveTintColor: COLORS.gold,
        tabBarInactiveTintColor: COLORS.textMuted,
        tabBarStyle: {
          backgroundColor: COLORS.backgroundCard,
          borderTopColor: COLORS.border,
          borderTopWidth: 1,
          paddingBottom: 8,
          paddingTop: 8,
          height: 65,
        },
        tabBarLabelStyle: { fontSize: 11, fontWeight: '500' },
        headerStyle: { backgroundColor: COLORS.background },
        headerTintColor: COLORS.text,
        headerShown: false,
      })}
    >
      <Tab.Screen name="Home" component={HomeScreen} options={{ title: 'Wallet' }} />
      <Tab.Screen name="T2E" component={T2EDashboardScreen} options={{ title: 'Earn' }} />
      <Tab.Screen name="Music" component={MusicScreen} options={{ title: 'Music' }} />
      <Tab.Screen name="History" component={HistoryScreen} options={{ title: 'History' }} />
      <Tab.Screen name="Settings" component={SettingsScreen} options={{ title: 'Settings' }} />
    </Tab.Navigator>
  );
}

export default function App() {
  const [isReady, setIsReady] = useState(false);
  const { wallet } = useStore();

  useEffect(() => {
    async function prepare() {
      try {
        await new Promise((r) => setTimeout(r, 500));
      } finally {
        setIsReady(true);
        await SplashScreen.hideAsync();
      }
    }
    prepare();
  }, []);

  if (!isReady) {
    return (
      <View style={styles.loading}>
        <ActivityIndicator size="large" color={COLORS.gold} />
      </View>
    );
  }

  const isConnected = wallet.isConnected && wallet.address;

  return (
    <SafeAreaProvider>
      <NavigationContainer
        theme={{
          dark: true,
          colors: {
            primary: COLORS.gold,
            background: COLORS.background,
            card: COLORS.backgroundCard,
            text: COLORS.text,
            border: COLORS.border,
            notification: COLORS.error,
          },
        }}
      >
        <Stack.Navigator
          screenOptions={{
            headerShown: false,
            contentStyle: { backgroundColor: COLORS.background },
            animation: 'slide_from_right',
          }}
        >
          {!isConnected ? (
            <>
              <Stack.Screen name="Welcome" component={WelcomeScreen} />
              <Stack.Screen name="CreateWallet" component={CreateWalletScreen} />
              <Stack.Screen name="ImportWallet" component={ImportWalletScreen} />
            </>
          ) : (
            <>
              <Stack.Screen name="MainTabs" component={MainTabs} />
              <Stack.Screen name="Send" component={SendScreen} options={{ presentation: 'modal' }} />
              <Stack.Screen name="Receive" component={ReceiveScreen} options={{ presentation: 'modal' }} />
              <Stack.Screen name="Swap" component={SwapScreen} options={{ presentation: 'modal' }} />
              <Stack.Screen name="Stake" component={StakeScreen} options={{ presentation: 'modal' }} />
              <Stack.Screen name="Scan" component={ScanScreen} options={{ presentation: 'fullScreenModal' }} />
              <Stack.Screen name="Bridge" component={BridgeScreen} options={{ presentation: 'modal' }} />
              <Stack.Screen name="Music" component={MusicScreen} options={{ presentation: 'modal' }} />
              <Stack.Screen name="Pledge" component={PledgeScreen} options={{ presentation: 'modal' }} />
            </>
          )}
        </Stack.Navigator>
        <StatusBar style="light" />
      </NavigationContainer>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  loading: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: COLORS.background,
  },
});
