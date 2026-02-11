
# Λευκή Βίβλος Thronos Chain & THR

## Έκδοση 2026.1 | Thronos Network V3.6: Το Σχέδιο Επιβίωσης

## Εισαγωγή

Το Thronos Chain είναι ένα καινοτόμο blockchain σχεδιασμένο για πλήρη ανθεκτικότητα, αποκέντρωση και επιβίωση. Συνδυάζει χαρακτηριστικά του Bitcoin (ασφάλεια SHA256), την ταχύτητα και χαμηλά τέλη του XRP, με μοναδικές δυνατότητες όπως offline nodes, μεταφορά μέσω ραδιοκυμάτων και steganography.

Η V3.6 αντιπροσωπεύει μια αλλαγή παραδείγματος: ένα blockchain που λειτουργεί όχι μόνο στο internet, αλλά μέσω ήχου, ραδιοκυμάτων, εικόνων και φωτός. Ένα δίκτυο σχεδιασμένο να επιβιώνει κατάρρευση δικτύου, λογοκρισία και αποτυχία υποδομής.

## 1. Αρχιτεκτονική Hardware (Το Οπλοστάσιο)

### Α. Οι "Εγκέφαλοι" (Local Compute Cluster)

**G1 Mini Gaming PC (Ryzen 9 8945HS, 32GB DDR5)**
- Ρόλος: Main Node, Blockchain Indexer, API Host (Railway Bridge)
- Λειτουργία: Διαχειρίζεται το VerifyID (KYC) και το κεντρικό ledger
- Υπηρεσίες: Master chain writer, public API, scheduler jobs

**Mini PC (Ryzen 7 8745HS, 32GB DDR4)**
- Ρόλος: AI/LLM Node & Autodriver Controller
- Λειτουργία: Τρέχει τοπικό LLM για λήψη αποφάσεων και επεξεργασία τηλεμετρίας GPS
- Υπηρεσίες: AI inference, model routing, telemetry aggregation

### Β. Δίκτυο & Υποδομή (Backbone)

**Cisco 1121 Router**: Το «κάστρο» του δικτύου. Διαχωρίζει τους IoT miners με hardware firewall και VLAN isolation.

**Κεραία LoRa (High Gain)**: Ακτίνα 15km, σύνδεση με IoT nodes χωρίς internet.

**Peiko Translator X9**: Ασύρματο Bluetooth Audio Interface για φωνητικές εντολές και ηχητικές συναλλαγές (WAV).

### Γ. Mining & Validation (Legacy Revitalization)

**USB Block Erupters**: Παλιά ASICs ως "Identity Validators" - Proof of Work shares για VerifyID.

**Powered USB Hub (7+ θύρες)**: Σταθερή τροφοδοσία 0.5A ανά stick.

## 2. Survival Mode: Επικοινωνία Χωρίς Internet (Audio-Fi)

Μετάδοση δεδομένων μέσω Ήχου:

1. **Encoding**: Η συναλλαγή (JSON) μετατρέπεται σε QR Code
2. **Modulation**: Το QR μετατρέπεται σε WAV (FSK modulation)
3. **Transmission**: Εκπομπή μέσω ασυρμάτου, Peiko X9 ή LoRa
4. **Decoding**: Το Ryzen 7 AI node "ακούει" τον ήχο, τον καθαρίζει μέσω AI και εκτελεί offline

### WhisperNote Protocol
- Κωδικοποίηση συναλλαγών σε ηχητικούς τόνους (1kHz, 2kHz, 4kHz)
- Web Audio API για browser-based μετάδοση
- WAV download για offline μεταφορά

### RadioNode
- RF μετάδοση blocks χωρίς internet ή ρεύμα
- Συμβατό με SDR (Software Defined Radio)
- LoRa modulation για μεγάλες αποστάσεις

## 3. Off-Grid Λειτουργία (Ηλιακή Ενέργεια)

Πλήρης αυτονομία με φωτοβολταϊκά. Solar Controller (Victron/RS485) στέλνει δεδομένα μπαταρίας στο G1.

| Λειτουργία | Μπαταρία | Ενεργές Υπηρεσίες |
|:-----------|:---------|:-------------------|
| **Full Mode** | >80% | CPU Mining, ASIC Validation, Full API, AI |
| **Eco Mode** | 30-80% | Μόνο VerifyID & AI Inference |
| **Survival Mode** | <30% | Μόνο LoRa & Audio-Link |

## 4. Ασφάλεια & Εργαλεία (Kali Linux Integration)

- **SDR**: Παρακολούθηση φάσματος για Jamming
- **Bettercap**: Προστασία IoT miners από MitM επιθέσεις
- **Wireshark**: Ανάλυση κίνησης Cisco 1121
- **Hardware Firewall**: Enterprise-grade packet filtering

## 5. Αρχιτεκτονική Πολλαπλών Κόμβων

| Node | Ρόλος | Hardware | Λειτουργία |
|:-----|:------|:---------|:-----------|
| **Node 1 (Master)** | Chain Writer | G1 Mini (Ryzen 9) | Public API, εγγραφές ledger, scheduler |
| **Node 2 (Replica)** | Read-Only | Railway Cloud | Background workers, API reads |
| **Node 3 (Vercel)** | Static Frontend | Vercel CDN | Static assets, native wallet hosting |
| **Node 4 (AI Core)** | AI/LLM | Mini PC (Ryzen 7) | Model inference, Pytheia governance |

## 6. Τεχνικά Χαρακτηριστικά

- **Αλγόριθμος**: SHA256 (Bitcoin-compatible)
- **Συμβατότητα**: Antminers, Block Erupters, CPU miners
- **Ταχύτητα**: Άμεση επιβεβαίωση μέσω ασύγχρονου node syncing
- **Χαμηλά fees**: Κατάλληλο για μικροπληρωμές
- **Max Supply**: 21,000,001 THR
- **Halving**: Κάθε 4 χρόνια
- **Ισοτιμία**: 1 THR = 0.0001 BTC

## 7. Tokenomics

- **Token**: Thronos (THR)
- **Max Supply**: 21,000,001
- **Κατανομή**: 80% Mining / 10% AI Treasury / 10% Burn
- **Mining**: SHA256 (ASIC & CPU)

## 8. Οικοσύστημα

### BTC Bridge
Κατάθεση BTC -> auto-mint THR | Καύση THR -> αποδέσμευση BTC
Watcher Service με Blockstream API + RPC fallback. Multi-sig ασφάλεια.

### DeFi
AMM pools, token swap, liquidity pools, fiat gateway (Stripe).

### AI (Pythia & PYTHEIA)
- Multi-provider: OpenAI, Gemini, Claude, Local LLMs
- PYTHEIA: Αυτόματη παρακολούθηση υγείας συστήματος
- Autonomous trading, oracle services
- On-chain AI interaction ledger

### Μουσική Πλατφόρμα
80/10/10 ανταμοιβές: 80% Καλλιτέχνης, 10% Δίκτυο, 10% AI/T2E

### L2E & T2E
Learn-to-Earn μαθήματα με THR ανταμοιβές. Train-to-Earn GPS τηλεμετρία για αυτόνομη οδήγηση.

### VerifyID (On-Chain KYC)
BTC pledge, PDF contracts με steganography, ASIC PoW shares, recovery protocol.

### Crypto Hunters (Play-to-Earn)
Παιχνίδι γεωεντοπισμού με ανταμοιβές THR.

## 9. PhantomFace Steganography

Η τεχνολογία PhantomFace επιτρέπει την απόκρυψη signed συναλλαγών μέσα σε εικόνες με LSB τεχνικές. Κάθε εικόνα γίνεται node. Recovery protocol εξάγει send_secret μέσω AES decryption.

## 10. Blockchain Explorer

9 tabs: Blocks, Transfers, Mempool, Live Stats, Tokens, Pools, L2E, Music, VerifyID/T2E

## 11. Mobile & Native Wallet

- React Native SDK (Android/iOS)
- HD wallet (BTC, ETH, SOL, THR)
- Native HTML Wallet Widget με 14 κατηγορίες ιστορικού
- Chrome Extension
- Bridge deposit modal, Music/Telemetry modal
- 5 γλώσσες (EL, EN, JA, RU, ES)

## Όραμα

Το Thronos Chain φιλοδοξεί να είναι το πιο ανθεκτικό, αποκεντρωμένο και καθολικά διαθέσιμο blockchain. Ακόμη και σε συνθήκες καταστροφής, θα παραμείνει ενεργό μέσω ραδιοσυχνοτήτων, offline nodes και αναλογικών καναλιών.

**"In Crypto we Trust, in Survival we Mine."**

---

## Λίστα Αγορών / Ελέγχου

- [ ] Powered USB Hub (7+ θύρες)
- [ ] RTL-SDR v4 Dongle
- [ ] Καλώδιο LMR-400 για κεραία LoRa
- [ ] RS485 to USB Adapter (φωτοβολταϊκά)
- [ ] Peiko X9 (Pairing με Ryzen 7)
- [ ] Solar Controller (Victron/RS485)

---

*Thronos Chain: Resistance is not futile. It is profitable.*
