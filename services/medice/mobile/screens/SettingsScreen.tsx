import React, { useContext, useState } from "react";
import { View, Text, TextInput, TouchableOpacity, StyleSheet, Alert } from "react-native";
import { APIContext } from "../context/APIContext";

export default function SettingsScreen() {
  const { apiUrl, setApiUrl, guardian, patient } = useContext(APIContext);
  const [inputUrl, setInputUrl] = useState(apiUrl);

  const save = () => {
    setApiUrl(inputUrl.trim());
    Alert.alert("Αποθηκεύτηκε", "Το API URL ενημερώθηκε.");
  };

  return (
    <View style={styles.container}>
      <Text style={styles.label}>API URL</Text>
      <TextInput
        style={styles.input}
        value={inputUrl}
        onChangeText={setInputUrl}
        autoCapitalize="none"
        keyboardType="url"
        placeholder="https://medice.thronos.io"
      />
      <TouchableOpacity style={styles.btn} onPress={save}>
        <Text style={styles.btnText}>Αποθήκευση</Text>
      </TouchableOpacity>

      {guardian && (
        <View style={styles.infoBox}>
          <Text style={styles.infoLabel}>Κηδεμόνας</Text>
          <Text>{guardian.name}</Text>
          <Text style={styles.sub}>{guardian.email}</Text>
        </View>
      )}

      {patient && (
        <View style={styles.infoBox}>
          <Text style={styles.infoLabel}>Παιδί</Text>
          <Text>{patient.name}</Text>
          <Text style={styles.sub}>Patient ID: {patient.id}</Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 20, backgroundColor: "#fff" },
  label: { fontSize: 13, color: "#888", marginBottom: 4 },
  input: {
    borderWidth: 1, borderColor: "#DDD", borderRadius: 8,
    padding: 10, fontSize: 15, marginBottom: 12,
  },
  btn: {
    backgroundColor: "#2C3E50", borderRadius: 8,
    padding: 12, alignItems: "center", marginBottom: 24,
  },
  btnText: { color: "#fff", fontSize: 15, fontWeight: "600" },
  infoBox: { backgroundColor: "#F8F9FA", borderRadius: 10, padding: 14, marginBottom: 12 },
  infoLabel: { fontSize: 12, color: "#888", marginBottom: 4, fontWeight: "600" },
  sub: { fontSize: 12, color: "#555" },
});
