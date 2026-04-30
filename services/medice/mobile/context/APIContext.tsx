import React, { createContext, useState, useEffect } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import axios from "axios";

export const APIContext = createContext<any>({});

export function APIProvider({ children }: { children: React.ReactNode }) {
  const [apiUrl, setApiUrlState] = useState("https://medice.thronos.io");
  const [guardian, setGuardian] = useState<any>(null);
  const [patient, setPatient] = useState<any>(null);
  const [feverHistory, setFeverHistory] = useState<any[]>([]);

  useEffect(() => {
    const load = async () => {
      const stored = await AsyncStorage.getItem("medice_api_url");
      if (stored) setApiUrlState(stored);
      const g = await AsyncStorage.getItem("medice_guardian");
      if (g) setGuardian(JSON.parse(g));
      const p = await AsyncStorage.getItem("medice_patient");
      if (p) setPatient(JSON.parse(p));
    };
    load();
  }, []);

  useEffect(() => {
    if (patient?.id) fetchFeverHistory(patient.id);
  }, [patient]);

  const setApiUrl = async (url: string) => {
    setApiUrlState(url);
    await AsyncStorage.setItem("medice_api_url", url);
  };

  const postReading = async (data: { patient_id: string; temperature: number }) => {
    try {
      const res = await axios.post(`${apiUrl}/readings`, {
        ...data,
        device_id: data.patient_id,
        timestamp: new Date().toISOString(),
      });
      if (res.data?.active_fever_id !== undefined) {
        setPatient((prev: any) => ({ ...prev, active_fever_id: res.data.active_fever_id }));
      }
    } catch (e) {
      console.warn("postReading error:", e);
    }
  };

  const postAntipyretic = async (feverEventId: string) => {
    await axios.put(`${apiUrl}/fever-events/${feverEventId}/antipyretic`);
    if (patient?.id) fetchFeverHistory(patient.id);
  };

  const fetchFeverHistory = async (patientId: string) => {
    try {
      const res = await axios.get(`${apiUrl}/patients/${patientId}/fever-history`);
      setFeverHistory(res.data);
    } catch (e) {
      console.warn("fetchFeverHistory error:", e);
    }
  };

  return (
    <APIContext.Provider value={{
      apiUrl, setApiUrl, guardian, patient, feverHistory, postReading, postAntipyretic,
    }}>
      {children}
    </APIContext.Provider>
  );
}
