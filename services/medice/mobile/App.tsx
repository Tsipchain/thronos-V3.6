import React, { useEffect } from "react";
import { NavigationContainer } from "@react-navigation/native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import messaging from "@react-native-firebase/messaging";
import { BLEProvider } from "./context/BLEContext";
import { APIProvider } from "./context/APIContext";
import DashboardScreen from "./screens/DashboardScreen";
import FeverHistoryScreen from "./screens/FeverHistoryScreen";
import SettingsScreen from "./screens/SettingsScreen";
import { registerFCMToken } from "./services/api";

const Tab = createBottomTabNavigator();

export default function App() {
  useEffect(() => {
    const setupFCM = async () => {
      const authStatus = await messaging().requestPermission();
      const enabled =
        authStatus === messaging.AuthorizationStatus.AUTHORIZED ||
        authStatus === messaging.AuthorizationStatus.PROVISIONAL;
      if (enabled) {
        const token = await messaging().getToken();
        await registerFCMToken(token);
      }
    };
    setupFCM();

    messaging().onMessage(async (remoteMessage) => {
      console.log("FCM foreground message:", remoteMessage);
    });
  }, []);

  return (
    <APIProvider>
      <BLEProvider>
        <NavigationContainer>
          <Tab.Navigator>
            <Tab.Screen name="Dashboard" component={DashboardScreen} />
            <Tab.Screen name="Ιστορικό" component={FeverHistoryScreen} />
            <Tab.Screen name="Ρυθμίσεις" component={SettingsScreen} />
          </Tab.Navigator>
        </NavigationContainer>
      </BLEProvider>
    </APIProvider>
  );
}
