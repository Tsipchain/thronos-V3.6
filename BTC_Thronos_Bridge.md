
# Thronos BTC Bridge Module (wBTC → wTHR)

## Σκοπός

Το bridge επιτρέπει την μεταφορά μικροσυναλλαγών από το δίκτυο του Bitcoin (BTC) προς το Thronos Chain, με στόχο την αποφόρτιση του κύριου δικτύου και την απόδοση ανταμοιβών στους χρήστες που συμμετέχουν στη διαδικασία.

---

## Αρχιτεκτονική

- **Wrapped BTC (wBTC):** Οι BTC συναλλαγές κλειδώνονται σε multisig διευθύνσεις.
- **Mirror TX στο Thronos:** Η ίδια συναλλαγή αντικατοπτρίζεται στο δίκτυο Thronos ως wrapped THR.
- **Oracles ή Phantom Gateways:** Διασφαλίζουν την ακεραιότητα της αντιστοίχισης.

---

## Οφέλη

- ⚡ Γρηγορότερες συναλλαγές με χαμηλότερα fees
- 🔁 Επανεπένδυση μικροσυναλλαγών
- 🛡️ Προστασία του BTC mainnet
- 💰 Reward mining στους wrapped BTC validators (σε THR)

---

## Τεχνικά Στοιχεία

- SHA256 συμβατότητα (για εξόρυξη και στα δύο δίκτυα)
- Steganography tagging για μεταφορά wrapped TXs μέσω εικόνων ή ήχου
- Πλήρης καταγραφή και auditability

---

## Μέλλον

Το bridge θα υποστηρίξει και αντίστροφη ροή (THR → BTC), μόλις ολοκληρωθεί το multisig lock/unlock layer.
