import React, { createContext, useEffect, useRef, useState } from "react";
import { BleManager, Device } from "react-native-ble-plx";
import { useContext } from "react";
import { APIContext } from "./APIContext";

const TEMP_SERVICE_UUID  = "4fafc201-1fb5-459e-8fcc-c5c9c331914b";
const TEMP_CHAR_UUID     = "beb5483e-36e1-4688-b7f5-ea07361b26a8";
const VITAL_CHAR_UUID    = "beb5483e-36e1-4688-b7f5-ea07361b26aa";

export const BLEContext = createContext<any>({});

export function BLEProvider({ children }: { children: React.ReactNode }) {
  const manager    = useRef(new BleManager()).current;
  const deviceRef  = useRef<Device | null>(null);
  const [connected,   setConnected]   = useState(false);
  const [scanning,    setScanning]    = useState(false);
  const [temperature, setTemperature] = useState<number | null>(null);
  const [spo2,        setSpo2]        = useState<number | null>(null);
  const [bpm,         setBpm]         = useState<number | null>(null);
  const { postReading, patient }      = useContext(APIContext);

  useEffect(() => () => { manager.destroy(); }, []);

  const connect = async () => {
    setScanning(true);
    manager.startDeviceScan(null, { allowDuplicates: false }, async (err, device) => {
      if (err || !device) { setScanning(false); return; }
      if (device.name !== "ThronomedICE") return;

      manager.stopDeviceScan();
      try {
        const d = await device.connect();
        await d.discoverAllServicesAndCharacteristics();
        deviceRef.current = d;
        setConnected(true);
        setScanning(false);

        // Temperature + SpO2 + BPM combined reading
        d.monitorCharacteristicForService(TEMP_SERVICE_UUID, TEMP_CHAR_UUID, (e, char) => {
          if (e || !char?.value) return;
          const json = JSON.parse(Buffer.from(char.value, "base64").toString("utf8"));
          const temp: number = json.temperature;
          const s2: number   = json.spo2 ?? -1;
          const hr: number   = json.bpm  ?? -1;
          setTemperature(temp);
          if (s2  > 0) setSpo2(s2);
          if (hr > 0) setBpm(hr);
          if (patient?.id) {
            postReading({
              patient_id: patient.id,
              temperature: temp,
              spo2:       s2 > 0 ? s2 : undefined,
              bpm:        hr > 0 ? hr : undefined,
              spo2_valid: s2 > 0 && json.spo2_valid,
              bpm_valid:  hr > 0 && json.bpm_valid,
            });
          }
        });

        // Pulse-only frequent updates (every 1 min from device)
        d.monitorCharacteristicForService(TEMP_SERVICE_UUID, VITAL_CHAR_UUID, (e, char) => {
          if (e || !char?.value) return;
          const json = JSON.parse(Buffer.from(char.value, "base64").toString("utf8"));
          if (json.spo2 > 0) setSpo2(json.spo2);
          if (json.bpm  > 0) setBpm(json.bpm);
        });
      } catch { setScanning(false); }
    });
    setTimeout(() => { manager.stopDeviceScan(); setScanning(false); }, 15000);
  };

  const disconnect = async () => {
    await deviceRef.current?.cancelConnection();
    deviceRef.current = null;
    setConnected(false);
    setTemperature(null);
    setSpo2(null);
    setBpm(null);
  };

  return (
    <BLEContext.Provider value={{ connected, scanning, temperature, spo2, bpm, connect, disconnect }}>
      {children}
    </BLEContext.Provider>
  );
}
