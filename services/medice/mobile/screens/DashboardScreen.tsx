import React, { useContext, useState } from "react";
import {
  View, Text, TouchableOpacity, StyleSheet, ActivityIndicator,
} from "react-native";
import { BLEContext } from "../context/BLEContext";
import { APIContext } from "../context/APIContext";

export default function DashboardScreen() {
  const { connected, temperature, connect, disconnect, scanning } = useContext(BLEContext);
  const { patient, postAntipyretic } = useContext(APIContext);
  const [marking, setMarking] = useState(false);

  const isFever = temperature !== null && temperature >= 38.0;
  const isHighFever = temperature !== null && temperature >= 39.0;

  const bgColor = isHighFever ? "#FF4444" : isFever ? "#FF8C00" : "#2ECC71";

  const handleAntipyretic = async () => {
    if (!patient?.active_fever_id) return;
    setMarking(true);
    try {
      await postAntipyretic(patient.active_fever_id);
    } finally {
      setMarking(false);
    }
  };

  return (
    <View style={[styles.container, { backgroundColor: bgColor }]}>
      <Text style={styles.name}>{patient?.name ?? "—"}</Text>
      <Text style={styles.temp}>
        {temperature !== null ? `${temperature.toFixed(1)}°C` : "---"}
      </Text>
      <Text style={styles.status}>
        {isHighFever ? "⚠️ ΥΨΗΛΟΣ ΠΥΡΕΤΟΣ" : isFever ? "🌡️ Πυρετός" : "✅ Κανονικό"}
      </Text>

      <TouchableOpacity
        style={styles.bleBtn}
        onPress={connected ? disconnect : connect}
        disabled={scanning}
      >
        {scanning ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.bleBtnText}>
            {connected ? "Αποσύνδεση BLE" : "Σύνδεση BLE"}
          </Text>
        )}
      </TouchableOpacity>

      {isFever && (
        <TouchableOpacity
          style={styles.antipyreticBtn}
          onPress={handleAntipyretic}
          disabled={marking}
        >
          <Text style={styles.antipyreticText}>
            {marking ? "..." : "💊 Éδωσα Αντιπυρετικό"}
          </Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: "center", justifyContent: "center", padding: 20 },
  name: { fontSize: 22, color: "#fff", fontWeight: "600", marginBottom: 8 },
  temp: { fontSize: 72, color: "#fff", fontWeight: "bold" },
  status: { fontSize: 18, color: "#fff", marginTop: 8, marginBottom: 32 },
  bleBtn: {
    backgroundColor: "rgba(0,0,0,0.25)",
    paddingHorizontal: 32, paddingVertical: 14,
    borderRadius: 24, marginBottom: 16,
  },
  bleBtnText: { color: "#fff", fontSize: 16, fontWeight: "600" },
  antipyreticBtn: {
    backgroundColor: "rgba(255,255,255,0.3)",
    paddingHorizontal: 28, paddingVertical: 12,
    borderRadius: 20,
  },
  antipyreticText: { color: "#fff", fontSize: 15, fontWeight: "600" },
});
