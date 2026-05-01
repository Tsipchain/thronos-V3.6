import React, { useContext } from "react";
import { View, Text, FlatList, StyleSheet } from "react-native";
import { APIContext } from "../context/APIContext";

export default function FeverHistoryScreen() {
  const { feverHistory } = useContext(APIContext);

  const renderItem = ({ item }: { item: any }) => {
    const start = new Date(item.start_time).toLocaleString("el-GR");
    const peak = item.peak_temp?.toFixed(1) ?? "—";
    const durationH = item.end_time
      ? ((new Date(item.end_time).getTime() - new Date(item.start_time).getTime()) / 3600000).toFixed(1)
      : null;

    return (
      <View style={styles.card}>
        <Text style={styles.date}>{start}</Text>
        <Text style={styles.peak}>Μέγιστο: {peak}°C</Text>
        {durationH && <Text style={styles.duration}>Διάρκεια: {durationH}h</Text>}
        {item.antipyretic_given && <Text style={styles.tag}>💊 Αντιπυρετικό</Text>}
        {item.blockchain_tx && <Text style={styles.blockchain}>⛓ Blockchain: {item.blockchain_tx.slice(0, 12)}…</Text>}
      </View>
    );
  };

  return (
    <View style={styles.container}>
      <FlatList
        data={feverHistory}
        keyExtractor={(item) => item.id?.toString() ?? Math.random().toString()}
        renderItem={renderItem}
        ListEmptyComponent={<Text style={styles.empty}>Δεν υπάρχουν καταγεγραμμένοι πυρετοί.</Text>}
        contentContainerStyle={{ padding: 16 }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#F5F5F5" },
  card: {
    backgroundColor: "#fff", borderRadius: 12, padding: 16,
    marginBottom: 12, elevation: 2,
  },
  date: { fontSize: 13, color: "#888", marginBottom: 4 },
  peak: { fontSize: 20, fontWeight: "700", color: "#E74C3C" },
  duration: { fontSize: 14, color: "#555" },
  tag: { fontSize: 13, color: "#27AE60", marginTop: 4 },
  blockchain: { fontSize: 11, color: "#7F8C8D", marginTop: 4 },
  empty: { textAlign: "center", color: "#aaa", marginTop: 48, fontSize: 15 },
});
