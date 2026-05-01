import React, { createContext, useState, useEffect } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import axios from "axios";

export const APIContext = createContext<any>({});

export function APIProvider({ children }: { children: React.ReactNode }) {
  const [apiUrl,       setApiUrlState] = useState("https://medice.thronos.io");
  const [guardian,     setGuardian]    = useState<any>(null);
  const [patient,      setPatient]     = useState<any>(null);
  const [feverHistory, setFeverHistory] = useState<any[]>([]);

  useEffect(() => {
    (async () => {
      const url = await AsyncStorage.getItem("medice_api_url");
      if (url) setApiUrlState(url);
      const g = await AsyncStorage.getItem("medice_guardian");
      if (g) setGuardian(JSON.parse(g));
      const p = await AsyncStorage.getItem("medice_patient");
      if (p) setPatient(JSON.parse(p));
    })();
  }, []);

  useEffect(() => { if (patient?.id) fetchFeverHistory(patient.id); }, [patient]);

  const setApiUrl = async (url: string) => {
    setApiUrlState(url);
    await AsyncStorage.setItem("medice_api_url", url);
  };

  const postReading = async (data: {
    patient_id: string;
    temperature: number;
    spo2?: number;
    bpm?: number;
    spo2_valid?: boolean;
    bpm_valid?: boolean;
  }) => {
    try {
      const res = await axios.post(`${apiUrl}/readings`, {
        ...data,
        device_id: data.patient_id,
        timestamp: new Date().toISOString(),
      });
      if (res.data?.active_fever_id !== undefined)
        setPatient((p: any) => ({ ...p, active_fever_id: res.data.active_fever_id }));
    } catch (e) { console.warn("postReading:", e); }
  };

  const postAntipyretic = async (id: string) => {
    await axios.put(`${apiUrl}/fever-events/${id}/antipyretic`);
    if (patient?.id) fetchFeverHistory(patient.id);
  };

  const fetchFeverHistory = async (pid: string) => {
    try {
      const res = await axios.get(`${apiUrl}/patients/${pid}/fever-history`);
      setFeverHistory(res.data);
    } catch (e) { console.warn("feverHistory:", e); }
  };

  return (
    <APIContext.Provider value={{
      apiUrl, setApiUrl, guardian, patient, feverHistory, postReading, postAntipyretic,
    }}>
      {children}
    </APIContext.Provider>
  );
}
