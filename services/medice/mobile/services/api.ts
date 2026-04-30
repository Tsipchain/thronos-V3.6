import AsyncStorage from "@react-native-async-storage/async-storage";
import axios from "axios";

export async function registerFCMToken(token: string): Promise<void> {
  const apiUrl = (await AsyncStorage.getItem("medice_api_url")) ?? "https://medice.thronos.io";
  const patientRaw = await AsyncStorage.getItem("medice_patient");
  if (!patientRaw) return;
  const patient = JSON.parse(patientRaw);
  await axios.post(`${apiUrl}/patients/${patient.id}/fcm-token`, { token });
}
