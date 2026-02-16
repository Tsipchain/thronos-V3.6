# Thronos — Deutsche Produktkommunikation

**Version**: 2026.2
**Zielmarkt**: DACH (Österreich, Deutschland, Schweiz)
**Sprache**: Deutsch (Hochdeutsch, Du-Form für B2C, Sie-Form für B2B)
**Stand**: 15. Februar 2026

---

## Inhaltsverzeichnis

1. [Unternehmensvorstellung](#1-unternehmensvorstellung)
2. [Produktbundles](#2-produktbundles)
3. [VerifyID — Geräteidentität](#3-verifyid--geräteidentität)
4. [Driver Telemetry — Fahrzeugtelemetrie](#4-driver-telemetry--fahrzeugtelemetrie)
5. [IoT Telemetry + AI L2](#5-iot-telemetry--ai-l2)
6. [Preisübersicht](#6-preisübersicht)
7. [Pilot-KPIs & Erfolgskriterien](#7-pilot-kpis--erfolgskriterien)
8. [Compliance & Regulierung](#8-compliance--regulierung)
9. [Glossar](#9-glossar)

---

## 1. Unternehmensvorstellung

### Über Thronos

Thronos ist ein österreichisches Blockchain-Betriebssystem der nächsten Generation. Wir verbinden SHA256-Sicherheit mit KI-gestützter Automatisierung, dezentraler Identität und Off-Grid-Fähigkeit — alles auf einer einzigen Plattform.

**Rechtsform**: FlexCo e.U. (Österreich)
**Gründung**: 2024
**Sitz**: Österreich
**Token**: THR (Utility-Token, MiCA-konform)
**Blockchain**: SHA256-basiert, Bitcoin-kompatibel

### Unsere Mission

> *"Pledge to the unburnable — Stärke in jedem Block."*

Wir schaffen eine digitale Infrastruktur, die auch dann funktioniert, wenn das Internet ausfällt. Unsere Technologie schützt Identitäten, sichert Daten und belohnt Beiträge zum Netzwerk — transparent, dezentral und datenschutzkonform.

### Warum Österreich?

- Registrierter Firmensitz in Österreich
- Erste Pilotprojekte im DACH-Raum
- Wertschöpfung und IP verbleiben in Österreich
- Ausgerichtet auf FFG-Förderprogramme und AWS-Startup-Credits

---

## 2. Produktbundles

Thronos bietet drei kommerzielle Bundles, die unabhängig oder kombiniert eingesetzt werden können:

| Bundle | Zielgruppe | Kernnutzen |
|:-------|:-----------|:-----------|
| **VerifyID Enterprise** | Logistik, Flottenmanagement, Compliance | Geräteidentität & Hardware-Attestierung |
| **Driver Telemetry** | Flottenbetreiber, Versicherungen, F&E | Datenschutzkonforme Fahrzeugtelemetrie |
| **IoT + AI L2** | Smart City, Industrie 4.0, Umweltmonitoring | KI-gestützte IoT-Datenverarbeitung |

---

## 3. VerifyID — Geräteidentität

### Was ist VerifyID?

VerifyID ist ein dezentrales Geräteidentitäts-System. Es ermöglicht Unternehmen, Hardware (IoT-Sensoren, Mining-Geräte, Fahrzeug-Telematik) kryptographisch zu registrieren und zu verifizieren — ohne zentrale Datenbank.

### Funktionsweise

1. **Registrierung**: Gerät sendet Hardware-Fingerprint an die Thronos-Blockchain.
2. **Challenge/Response**: Kryptographische Herausforderung mit 5-Minuten-Gültigkeit.
3. **SHA256-Attestierung**: Hardware-Proof über ASIC-Mining-Chips.
4. **On-Chain-Protokollierung**: Jede Verifizierung wird unveränderlich gespeichert.

### Vorteile

- **Fälschungssicher**: Hardware-basierte Identität, nicht kopierbar
- **Audit-fähig**: Vollständiger Prüfpfad auf der Blockchain
- **API-first**: RESTful-Integration in bestehende Systeme
- **Mehrsprachig**: DE, EN, EL, ES, FR, JA, ZH

### Anwendungsfälle

- Flottenmanagement: Jedes Fahrzeug hat eine verifizierte On-Chain-Identität
- Supply Chain: Sensoren in der Lieferkette kryptographisch gesichert
- Compliance: Nachweis der Geräteintegrität für Audits

---

## 4. Driver Telemetry — Fahrzeugtelemetrie

### Was ist Driver Telemetry?

Ein datenschutzkonformes System zur Erfassung von Fahrzeug- und Fahrertelemetrie. Rohe GPS-Daten werden **auf dem Gerät gehasht** — es werden keine Koordinaten gespeichert, sondern nur kryptographische Routennachweise.

### Train-to-Earn (T2E)

Fahrer verdienen THR-Token, indem sie qualitativ hochwertige Telemetriedaten beisteuern, die zum Training von KI-Modellen für autonomes Fahren verwendet werden.

**Belohnungsaufteilung**:
- 80% an den Datenlieferanten (Fahrer/Flottenbetreiber)
- 10% an das Netzwerk (Validatoren)
- 10% an den KI-/T2E-Pool

### Datenschutz-Garantie (Privacy-by-Design)

- Keine rohen GPS-Koordinaten auf der Blockchain
- Hashing erfolgt auf dem Endgerät (Client-side)
- Nur Proof-of-Route wird übertragen
- DSGVO-konform: Recht auf Löschung für Off-Chain-Daten
- Keine Weitergabe an Dritte ohne explizite Zustimmung

### Vorteile für Flottenbetreiber

- Reduktion der Versicherungskosten durch nachgewiesenes Fahrverhalten
- Beitrag zur KI-Forschung mit Vergütung in THR
- Echtzeit-Dashboard für Flottenüberwachung
- Integration mit bestehenden Telematiksystemen via API

---

## 5. IoT Telemetry + AI L2

### Was ist IoT Telemetry + AI L2?

Eine Plattform für die sichere Erfassung, Verarbeitung und KI-gestützte Analyse von IoT-Sensordaten — von Smart Parking bis Umweltmonitoring.

### KI Layer 2 (AI L2) — Was es kann und was nicht

**Was AI L2 kann**:
- Anomalie-Erkennung in Echtzeit-Sensordaten
- Muster-Analyse über Zeitreihen
- Automatische Klassifizierung von Gerätezuständen
- Dezentrale Inferenz über mehrere Knoten
- Oracle-Dienste für verifizierte Datenpunkte

**Was AI L2 NICHT ist**:
- Kein Ersatz für zertifizierte Sicherheitssysteme
- Keine autonome Entscheidungsfindung ohne menschliche Aufsicht
- Kein generatives KI-Modell (kein ChatGPT-Ersatz)
- Keine Verarbeitung personenbezogener Daten ohne Einwilligung

### Smart Parking (Pilotprojekt)

- Echtzeit-Belegungserkennung über IoT-Sensoren
- Bezahlung mit THR-Token
- Dashboard für Stadtplanung
- Sub-Sekunden-Reaktionszeit

### Off-Grid-Fähigkeit

- LoRa-Konnektivität (bis 15 km Reichweite)
- Solarbetrieb (Victron/RS485-Integration)
- Drei Betriebsmodi: Voll / Öko / Überlebensmodus
- Keine Internetabhängigkeit im Überlebensmodus

---

## 6. Preisübersicht

### VerifyID Enterprise

| Tarif | Preis/Monat | Geräte | Verifizierungen/Monat |
|:------|:------------|:-------|:----------------------|
| Starter | €99 | bis 100 | 10.000 |
| Business | €499 | bis 1.000 | 100.000 |
| Enterprise | Auf Anfrage | Unbegrenzt | Unbegrenzt + SLA |

### Driver Telemetry

| Tarif | Preis/Monat | Fahrzeuge | Extras |
|:------|:------------|:----------|:-------|
| Pilot | €199 | bis 50 | Standard-Dashboard |
| Fleet | €799 | bis 500 | Prioritäts-Datenpipeline |
| Enterprise | Auf Anfrage | Unbegrenzt | White-Label, On-Prem |

### IoT + AI L2

| Tarif | Preis/Monat | IoT-Knoten | KI-Funktionen |
|:------|:------------|:-----------|:--------------|
| City Pilot | €299 | bis 200 | Basis-KI |
| City Pro | €999 | bis 2.000 | Volle AI L2 |
| National | Auf Anfrage | Unbegrenzt | Regierungs-SLA |

*Alle Preise zzgl. USt. Jahresabonnement: 2 Monate gratis.*

---

## 7. Pilot-KPIs & Erfolgskriterien

### VerifyID (6-Monats-Pilot)
- ≥ 3 zahlende Kunden im DACH-Raum
- < 200 ms durchschnittliche Verifizierungszeit
- ≥ 99,5% Verfügbarkeit
- ≥ 95% Kundenzufriedenheit (NPS > 40)

### Driver Telemetry (6-Monats-Pilot)
- ≥ 1 Flottenbetreiber mit 20+ Fahrzeugen
- ≥ 10.000 km erfasste Telemetriedaten
- Messbare Verbesserung des KI-Modells
- Positive Kosten-Nutzen-Analyse für den Betreiber

### IoT + AI L2 (6-Monats-Pilot)
- ≥ 1 Smart-Parking-Pilot (50+ Sensoren) in Wien oder Graz
- Sub-Sekunden-Belegungserkennung
- Positiver ROI innerhalb von 12 Monaten
- Erfolgreicher Off-Grid-Test (72 Stunden ohne Internet)

---

## 8. Compliance & Regulierung

### Token-Klassifizierung
- THR ist ein **Utility-Token** gemäß MiCA-Verordnung (Markets in Crypto-Assets)
- **Kein E-Geld**, kein Wertpapier, kein Zahlungsmittel
- Verwendung ausschließlich innerhalb des Thronos-Ökosystems

### AML/KYC-Grenzen
- Thronos ist **keine Bank** und kein Zahlungsinstitut
- Fiat-Einzahlungen (Stripe) unterliegen der AML/KYC-Prüfung von Stripe
- VerifyID ist **kein KYC-Anbieter** — es verifiziert Geräte, nicht Personen
- BTC-Bridge: Non-custodial, Nutzer verwalten ihre eigenen Schlüssel

### Datenschutz (DSGVO)
- Keine personenbezogenen Daten auf der Blockchain
- GPS-Daten werden auf dem Endgerät gehasht (Client-side)
- Recht auf Löschung gilt für Off-Chain-Datenbanken
- Datenschutz-Folgenabschätzung (DSFA) wird für Enterprise-Kunden bereitgestellt

### Österreichisches Recht
- FlexCo e.U. nach österreichischem Recht
- Gerichtsstand: Österreich
- Anwendbares Recht: Österreichisches Recht + EU-Verordnungen

---

## 9. Glossar

| Begriff | Erklärung |
|:--------|:----------|
| **THR** | Thronos-Token, der native Utility-Token des Netzwerks |
| **T2E (Train-to-Earn)** | Belohnungsmechanismus für Daten, die KI-Modelle trainieren |
| **L2E (Learn-to-Earn)** | Belohnungsmechanismus für absolvierte Lernkurse |
| **VerifyID** | Dezentrales Geräteidentitäts- und Attestierungssystem |
| **Pytheia** | Autonomer KI-Agent für Netzwerküberwachung und Governance |
| **AI L2** | KI-Schicht 2 — dezentrale Inferenz auf der Thronos-Blockchain |
| **SHA256** | Kryptographischer Hash-Algorithmus (Bitcoin-kompatibel) |
| **BFT/Quorum** | Byzantinische Fehlertoleranz — Konsensverfahren mit Validatoren |
| **LoRa** | Long Range — Funktechnologie für IoT mit bis zu 15 km Reichweite |
| **Audio-Fi** | Thronos-Protokoll zur Datenübertragung via Audiosignal |
| **FlexCo** | Flexible Company — österreichische Rechtsform für Startups |
| **MiCA** | Markets in Crypto-Assets — EU-Verordnung für Kryptoassets |
| **DSGVO** | Datenschutz-Grundverordnung (= GDPR) |
| **FFG** | Österreichische Forschungsförderungsgesellschaft |

---

*"Pledge to the unburnable — Stärke in jedem Block."*

*© 2026 Thronos FlexCo e.U. (Österreich) — Alle Rechte vorbehalten.*
