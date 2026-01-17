# Release Verification (OPS)

## Build stamp διαθέσιμο
1. Άνοιξε `/api/health` και επιβεβαίωσε ότι επιστρέφει `build_id` και `git_commit`.

## Footer: build_id αντιστοίχιση + συμπεριφορά
1. Άνοιξε `/` (ή οποιοδήποτε page).
2. Κάνε scroll: το footer δεν πρέπει να κρύβει περιεχόμενο στη μέση της σελίδας.
3. Πήγαινε στο τέλος της σελίδας: το footer εμφανίζεται.
4. Επιβεβαίωσε ότι:
   - Κάτω δεξιά εμφανίζεται `build: <id>` που ταιριάζει με `/api/health`.
   - Υπάρχει το κείμενο “Thronos Network ® CopyRights 2023–2026”.

## Wallet History: UI κατηγορίες
1. Άνοιξε Wallet → “Ιστορικό Συναλλαγών”.
2. Επιβεβαίωσε ότι οι καρτέλες/κατηγορίες φορτώνουν χωρίς σφάλματα.

## Wallet widget gate
1. Wallet widget loads.
2. Transaction categories visible.

## Wallet History: reset φίλτρων
1. Πάτα Tokens, THR, L2E, Swaps.
2. Κλείσε το modal και άνοιξέ το ξανά.
3. Αναμενόμενο: ξεκινά σε ασφαλές default (“All”) και δεν κρατά “μόλυνση”.

## Token filter leakage test
1. Πήγαινε Tokens view και ενεργοποίησε token chips.
2. Γύρνα σε THR/L2E/Swaps.
3. Αναμενόμενο: οι άλλες κατηγορίες δεν επηρεάζονται από token-only κατάσταση.

## TX feed persistence
1. Κάνε restart/redeploy.
2. Άνοιξε `/api/tx_feed` και επιβεβαίωσε ότι προηγούμενες κινήσεις υπάρχουν.

## Viewer/Wallet: ιστορικό μετά από restart
1. Μετά από restart, Viewer → Transfers και Wallet History/Wallet Tokens δείχνουν παλιές μεταφορές.

## Decimals sanity στον Viewer → Tokens
1. Έλεγξε tokens: HPNNIS/JAM/MAR/L2E/WBTC.
2. Αναμενόμενο: decimals σωστά ανά token, “default” μόνο όταν λείπει πραγματικά metadata.

## Decimals sanity σε Transfer rows
1. Κάνε 1 token transfer.
2. Αναμενόμενο: Viewer → Transfers και Wallet → Tokens δείχνουν ίδιο ποσό/precision.

## Swaps δεν εξαφανίζονται
1. Αν υπάρχουν swaps/liquidity actions, εμφανίζονται στο Swaps tab.

## AI provider status χωρίς διαρροές
1. Κάλεσε `/api/ai/provider_status`.
2. Αναμενόμενο: δείχνει κατάσταση (configured/library_loaded) και τελευταίο error per provider, χωρίς secrets.

## Συνέπεια providers vs model list
1. Σύγκρινε `/api/ai/provider_status` με `/api/ai_models` σε mode hybrid/all.
2. Αναμενόμενο: δεν δηλώνει enabled μοντέλα από provider που είναι ουσιαστικά κλειστός.

## AI request charging discipline
1. Κάνε AI request με ενεργό μοντέλο.
2. Αναμενόμενο: credits αφαιρούνται μόνο σε επιτυχημένη κλήση.

## AI callability με explicit model
1. Ζήτησε μοντέλο τύπου `gpt-4.1-mini`.
2. Αναμενόμενο: είτε επιτυχία είτε structured response που δηλώνει ότι δεν έγινε attempt/χρέωση.

## Claude enablement gating
1. Αν δεν υπάρχουν Anthropic keys, τα Claude models εμφανίζονται disabled στο `/api/ai_models`.
2. Αν υπάρχουν keys, εμφανίζονται enabled.

## Claude selection behavior
1. Διάλεξε Claude model από UI.
2. Αναμενόμενο: ή απαντά Claude, ή επιστρέφεται καθαρό provider_error (χωρίς σιωπηλό fallback/charges).

## Chat session: reset δεν “σβήνει” session
1. Κάνε clear/reset messages και refresh.
2. Αναμενόμενο: το session παραμένει διαθέσιμο.

## Chat session: delete χωρίς 403
1. Δοκίμασε delete session.
2. Αναμενόμενο: 200 OK και UI περνά σε άλλο session χωρίς loop.

## Rename/Delete persist
1. Rename session, refresh.
2. Αναμενόμενο: το νέο όνομα/κατάσταση κρατιέται.

## Offline/Thrai: no repetition
1. `/api/thrai/ask` σε διαδοχικά διαφορετικά prompts.
2. Αναμενόμενο: διαφορετικές απαντήσεις (όχι επανάληψη προηγούμενου).

## Offline/Thrai: prompt validation
1. Στείλε κενό prompt.
2. Αναμενόμενο: καθαρό validation error χωρίς να πειράζει το session/history.

## Wallet counts debug sanity
1. Άνοιξε `/api/tx_feed?wallet=...&debug_counts=1`.
2. Σύγκρινε με wallet history category counts.
3. Αναμενόμενο: οι αριθμοί συμφωνούν χωρίς λάθος ταξινόμηση τύπων.
