# Τεχνική Περίληψη – Αλλαγές, Προβλήματα & Πλάνο Αποκατάστασης
**Tags:** #backend-restore #rpc #mining-whitelist #watchdog #node-roles #scheduler

## Πρόσφατες αλλαγές (τελευταίες 8 ημέρες)

- Συγχωνεύτηκαν PR που τροποποίησαν RPC endpoints (νέα/αλλαγμένα Flask routes), whitelist λογική, διαχείριση κόμβων (master/replica scheduler), UI multi-chain πορτοφολιού και μηχανισμό assets/pledge.
- Επεμβάσεις στο backend (Flask APIs) για multi-chain και whitelist οδήγησαν σε επικαλυπτόμενα routes και αλλαγές ρυθμίσεων κόμβων.
- Πιθανή αλλαγή ροής πιστοποίησης (whitelist), περιορισμός pledge σε BTC, και προσθήκες/μεταβολές για cross-chain bridges.

## Εντοπισμένα προβλήματα & αιτιάσεις

### RPC / Flask endpoints

- Διπλές δηλώσεις route (π.χ. `/api/blocks`) προκάλεσαν `AssertionError: View function mapping is overwriting an existing endpoint function`.
- Flask απαιτεί μοναδικά endpoint names ανά view, αλλιώς πέφτει ο server.
- Πριν το merge, τα RPC λειτουργούσαν. Τώρα οι κλήσεις αποτυγχάνουν λόγω AssertionError.

### Λειτουργία κόμβων / nodes

- Scheduler φαίνεται ρυθμισμένος (master ενεργός, replicas read-only), αλλά πρέπει να επανελεγχθεί υπό φόρτο.
- Η ρύθμιση `NODE_ROLE=replica`, `SCHEDULER_ENABLED=False` λειτουργεί, όμως απαιτείται επιβεβαίωση RPC routing προς master.

### Whitelisting διευθύνσεων

- Έλεγχος ορθότητας κανόνων whitelist: λάθος ρύθμιση μπορεί να μπλοκάρει νόμιμους χρήστες.
- Αν πριν λειτουργούσε σωστά, τώρα μπορεί να απορρίπτονται νέες διευθύνσεις.

### Multi-chain wallet modal

- Αλλαγές στο UI/modal πιθανόν έσπασαν τη ροή επιλογής δικτύων.
- Χρειάζεται επιβεβαίωση ότι το modal φορτώνει σωστά μετά το merge.

### Assets / pledge mechanics

- Το “BTC-only pledge” περιόρισε staking σε άλλες αλυσίδες (π.χ. ERC-20).
- Αν υπήρχε multi-asset pledge/bridges, αυτή η λειτουργία χάθηκε.

### AI & IoT subsystems

- **AI integration**: warnings για `google.generativeai` (deprecation 2026) + “model sync failed” με OpenAI.
- Χρειάζεται ενημέρωση/αντικατάσταση SDK (Google GenAI SDK) και έλεγχος OpenAI σύνδεσης.
- **IoT integration**: δεν εμφανίζονται σφάλματα, αλλά απαιτούνται tests στα endpoints/credentials.

### Subsystem “Music”

- Στα logs φαίνεται ομαλή λειτουργία, δεν απαιτείται επείγουσα διόρθωση.

## Πλάνο αποκατάστασης

### 1) Διόρθωση endpoints (RPC / Flask)

- Επαναφορά/μετονομασία routes ώστε κάθε Flask endpoint να έχει μοναδικό όνομα.
- Σε `add_url_rule`, να δοθούν διακριτά endpoint names ή να μετονομαστούν view functions.
  - [x] Προστέθηκαν τα `/api/mining/info` και `/api/last_hash` ως aliases των σταθερών endpoints.
  - [x] Προστέθηκε `/api/replica_health` για debugging replica node health.
  - [x] Προστέθηκε legacy alias `/api/mining_info` για CPU miners.

### 2) Επικαιροποίηση AI modules

- Αντικατάσταση `google.generativeai` με Google GenAI SDK πριν το 2026.
- Έλεγχος OpenAI API keys/endpoint.
- Αν χρειαστεί, ξεχωριστό AI microservice ή χρήση εναλλακτικού LLM framework.

### 3) Έλεγχος whitelist

- Επιβεβαίωση whitelist πριν από συναλλαγές.
- Ορθότητα προσθήκης/διαγραφής διευθύνσεων και συμμόρφωση AML.
  - [x] Mining whitelist απαιτεί `active` + `pledge_ok` όταν `MINING_WHITELIST_ONLY=1`.

### 4) Ανάκτηση nodes

- Διασφάλιση επικοινωνίας master/replica (RPC routing, heartbeat).
- Επαλήθευση ότι replicas κάνουν μόνο read και ο master κρατά έλεγχο.
  - [x] Replica heartbeat logs σιωπούν timeouts εκτός αν `HEARTBEAT_LOG_ERRORS=1`.
  - [x] Replica nodes επιβάλλουν `READ_ONLY=1` και απενεργοποιούν scheduler όταν δεν είναι master.

### 5) Restoration multi-chain wallet

- Επαναφορά UI/UX επιλογής δικτύων.
- Έλεγχος API κλήσεων ανά δίκτυο (BSC, Polygon κ.λπ.).
- Επιβεβαίωση derivation paths και σωστών addresses.

### 6) Assets & pledge

- Επαναφορά pledge πολλαπλών assets (ETH, BNB, BTC).
- Σύνδεση σε staking pools ή bridge contracts (lock/burn).
- Επανέλεγχος ERC-20 / BEP-20 pledge ροών.
  - [x] Το pledge UI τονίζει ότι το pledge είναι BTC-only → THR (άλλα chains μόνο bridge/balances).
  - [ ] Διασφάλιση ότι pledge/mining μένουν BTC-only → THR χωρίς να επηρεάζονται από άλλα chains (backend verification).

### 7) RPC routing & explorer

- Ενιαίος gateway που προωθεί RPC calls ανά `network`/`method`.
- Επιβεβαίωση ότι το explorer χρησιμοποιεί τα σωστά endpoints.
  - [x] Προστέθηκαν μικρά caches + timing logs για mining/last_hash endpoints (απομένει SLA verification).
  - [x] Προστέθηκε fast path και timing logs στο submit_block ώστε να μειωθούν mining timeouts.
  - [ ] Επιβεβαίωση ότι viewer filters (Bridge / Tokens / Swaps / L2E) βασίζονται στο canonical tagging χωρίς αλλαγές στα AMM endpoints.

### 8) IoT subsystem

- Επανεξέταση HTTP/MQTT endpoints και credentials.
- Βελτίωση reconnection/error logging.

## Επόμενα βήματα για native mobile wallet

### Cross-chain bridges

- Ενσωμάτωση lock-and-mint / burn-and-mint.
- UI/UX για chain επιλογή και παρακολούθηση swaps.

### Πολλαπλά assets ανά διεύθυνση

- Multi-asset wallet (τύπου Trust Wallet).
- Ένα recovery phrase, πολλαπλά keys ανά δίκτυο.

### Pledge ανά δίκτυο

- Διακριτό staking per chain (Ethereum/BTC nodes).
- Ενιαία προβολή αποτελεσμάτων στο UI.

### Υποσυστήματα Music/AI/IoT

- API integration στο mobile.
- Σταθεροποίηση backend (update deprecated libs, MQTT broker).

### RPC routing & whitelist

- Mobile endpoint που κάνει routing σε σωστό node.
- UI υποστήριξη whitelist και explorer compatibility.

## Προτάσεις τεχνικής ολοκλήρωσης

- Χρήση crypto-wallet βιβλιοθηκών (TrustWallet Core, Web3 SDKs) για multi-chain.
- Κοινοί API clients/microservices για AI/IoT.
- Modular αρχιτεκτονική (RPC node per chain, AI service, IoT service).
- Security: whitelist validation, logging/monitoring για όλα τα παραπάνω.

## Σημείωση αποκατάστασης

- Άμεση αντιμετώπιση με rollback όπου χρειάζεται.
- Επαναφορά προηγούμενων σταθερών commits.
- Κάλυψη κάθε αποκατάστασης με unit/integration tests.

## 3. Εκπαίδευση Πυθίας / Architect

- [x] Ο loader διαβάζει όλα τα `governance/*.md` (συμπεριλαμβανομένου του παρόντος).
- [x] Προσθήκη/επιβεβαίωση blueprint tags για εύκολη εύρεση:
  - `#backend-restore`, `#mining-whitelist`, `#watchdog`, `#rpc`
- [ ] Self-test:
  - Ρώτησε τον Architect στο `/chat` ή `/architect`:
    - «Ποια είναι η πολιτική mining whitelist και ποιος ο ρόλος του node 2;»
  - Επιβεβαίωσε ότι απαντά με βάση το παρόν plan.

## Notes

- Προστέθηκε `/api/replica_health` για γρήγορο replica debugging.
- Το pledge UI εμφανίζει πλέον ξεκάθαρα το BTC-only pledge μήνυμα.
- Προστέθηκε cache 10s για wallet balances ώστε να μειωθεί το “Loading balances…” latency.
- Προστέθηκαν timing logs & caches στα mining endpoints για αποφυγή timeouts (μένει SLA μέτρηση).
