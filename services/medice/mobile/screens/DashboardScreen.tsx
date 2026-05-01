import React, { useContext, useState } from "react";
import {
  View, Text, TouchableOpacity, StyleSheet,
  ActivityIndicator, ScrollView,
} from "react-native";
import { BLEContext } from "../context/BLEContext";
import { APIContext } from "../context/APIContext";

export default function DashboardScreen() {
  const { connected, temperature, spo2, bpm, connect, disconnect, scanning } = useContext(BLEContext);
  const { patient, postAntipyretic } = useContext(APIContext);
  const [marking, setMarking] = useState(false);

  const isFever     = temperature !== null && temperature >= 38.0;
  const isHighFever = temperature !== null && temperature >= 39.0;
  const isSpo2Low   = spo2 !== null && spo2 < 94;
  const isSpo2Crit  = spo2 !== null && spo2 < 90;
  const isHRAbnorm  = bpm  !== null && (bpm < 60 || bpm > 130);

  const bgColor = isSpo2Crit || isHighFever ? "#FF2222"
                : isSpo2Low  || isFever      ? "#FF8C00"
                : "#2ECC71";

  const handleAntipyretic = async () => {
    if (!patient?.active_fever_id) return;
    setMarking(true);
    try { await postAntipyretic(patient.active_fever_id); }
    finally { setMarking(false); }
  };

  return (
    <ScrollView contentContainerStyle={[styles.container, { backgroundColor: bgColor }]}>
      <Text style={styles.name}>{patient?.name ?? "—"}</Text>

      {/* Temperature */}
      <View style={styles.bigCard}>
        <Text style={styles.bigLabel}>🌡️ Θερμοκρασία</Text>
        <Text style={styles.bigValue}>
          {temperature !== null ? `${temperature.toFixed(1)}°C` : "---"}
        </Text>
        <Text style={styles.subLabel}>
          {isHighFever ? "⚠️ ΥΨΗΛΟΣ ΠΥΡΕΤΟΣ"
           : isFever   ? "🌡️ Πυρετός"
                       : "✅ Κανονική"}
        </Text>
      </View>

      {/* SpO2 + BPM row */}
      <View style={styles.vitalRow}>
        <View style={[styles.vitalCard, isSpo2Crit && styles.danger, isSpo2Low && !isSpo2Crit && styles.warn]}>
          <Text style={styles.vitalLabel}>🧠 SpO₂</Text>
          <Text style={styles.vitalValue}>
            {spo2 !== null ? `${spo2.toFixed(0)}%` : "---"}
          </Text>
          <Text style={styles.vitalSub}>
            {isSpo2Crit ? "🚨 KRITIKO" : isSpo2Low ? "⚠️ Chamiló" : "✅ OK"}
          </Text>
        </View>

        <View style={[styles.vitalCard, isHRAbnorm && styles.warn]}>
          <Text style={styles.vitalLabel}>❤️‍🩹 BPM</Text>
          <Text style={styles.vitalValue}>
            {bpm !== null ? `${bpm}` : "---"}
          </Text>
          <Text style={styles.vitalSub}>
            {bpm !== null && bpm < 60  ? "⚠️ Brady"
           : bpm !== null && bpm > 130 ? "⚠️ Tachy"
                                       : bpm !== null ? "✅ OK" : ""}
          </Text>
        </View>
      </View>

      {/* BLE button */}
      <TouchableOpacity
        style={styles.bleBtn}
        onPress={connected ? disconnect : connect}
        disabled={scanning}
      >
        {scanning
          ? <ActivityIndicator color="#fff" />
          : <Text style={styles.bleBtnText}>
              {connected ? "Αποσύνδεση BLE" : "Σύνδεση BLE"}
            </Text>
        }
      </TouchableOpacity>

      {/* Antipyretic */}
      {isFever && (
        <TouchableOpacity style={styles.antipyreticBtn} onPress={handleAntipyretic} disabled={marking}>
          <Text style={styles.antipyreticText}>
            {marking ? "..." : "💊 Éδωσα Αντιπυρετικό"}
          </Text>
        </TouchableOpacity>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container:   { flexGrow: 1, alignItems: "center", justifyContent: "center", padding: 20 },
  name:        { fontSize: 22, color: "#fff", fontWeight: "600", marginBottom: 16 },
  bigCard: {
    backgroundColor: "rgba(0,0,0,0.2)", borderRadius: 16,
    padding: 20, alignItems: "center", marginBottom: 16, width: "100%",
  },
  bigLabel:    { fontSize: 14, color: "rgba(255,255,255,0.8)", marginBottom: 4 },
  bigValue:    { fontSize: 64, color: "#fff", fontWeight: "bold" },
  subLabel:    { fontSize: 16, color: "#fff", marginTop: 4 },
  vitalRow:    { flexDirection: "row", gap: 12, marginBottom: 20, width: "100%" },
  vitalCard: {
    flex: 1, backgroundColor: "rgba(0,0,0,0.2)", borderRadius: 14,
    padding: 16, alignItems: "center",
  },
  danger: { backgroundColor: "rgba(180,0,0,0.5)" },
  warn:   { backgroundColor: "rgba(180,80,0,0.4)" },
  vitalLabel:  { fontSize: 12, color: "rgba(255,255,255,0.8)", marginBottom: 4 },
  vitalValue:  { fontSize: 32, color: "#fff", fontWeight: "700" },
  vitalSub:    { fontSize: 11, color: "#fff", marginTop: 2 },
  bleBtn: {
    backgroundColor: "rgba(0,0,0,0.25)", paddingHorizontal: 32,
    paddingVertical: 14, borderRadius: 24, marginBottom: 16,
  },
  bleBtnText:      { color: "#fff", fontSize: 16, fontWeight: "600" },
  antipyreticBtn:  { backgroundColor: "rgba(255,255,255,0.3)", paddingHorizontal: 28, paddingVertical: 12, borderRadius: 20 },
  antipyreticText: { color: "#fff", fontSize: 15, fontWeight: "600" },
});
