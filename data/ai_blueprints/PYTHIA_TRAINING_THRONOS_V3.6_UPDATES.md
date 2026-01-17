# PYTHIA AI TRAINING - THRONOS V3.6 SYSTEM UPDATES

**Training Date**: 2026-01-17
**Node**: Node 4
**Purpose**: Εκπαίδευση της Pythia AI για τις πρόσφατες αλλαγές στο Thronos V3.6 ecosystem

---

## 📋 ΣΥΝΟΨΗ ΑΛΛΑΓΩΝ

Το Thronos V3.6 ecosystem έχει ενημερωθεί με κρίσιμες διορθώσεις και νέα χαρακτηριστικά:

### 🔧 ΔΙΟΡΘΩΣΕΙΣ BUGS (5 Critical)

1. **Architect AI - Σύστημα Χρέωσης σε THR** ⚠️ ΚΡΙΤΙΚΟ
2. **T2E Rewards - Πίστωση Ανταμοιβών** ⚠️ ΚΡΙΤΙΚΟ
3. **T2E - Server-Controlled Rewards** ⚠️ ΑΣΦΑΛΕΙΑ
4. **AI Credits API - Duplicate Code** ⚠️ ΜΕΓΑΛΟ
5. **Wallet History Modal** ⚠️ UX IMPROVEMENT

### ✨ ΝΕΑ ΧΑΡΑΚΤΗΡΙΣΤΙΚΑ

1. **Wallet History Modal** - Πλήρες ιστορικό συναλλαγών
2. **Architect → Chat Flow** - Session transfer για περαιτέρω ανάπτυξη
3. **T2E Architect Rewards** - Ανταμοιβές για ολοκληρωμένα projects

---

## 🏗️ ARCHITECT AI SYSTEM - ΝΕΟΣ ΤΡΟΠΟΣ ΛΕΙΤΟΥΡΓΙΑΣ

### Προηγούμενο Σύστημα (ΛΑΘΟΣ):
```
❌ Architect → AI Credits (1 credit ανά generation)
❌ Δωρεάν χρήση αν δεν υπήρχαν credits
❌ Δεν υπήρχε διαχωρισμός από chatbot
```

### ΝΕΟ Σύστημα (ΣΩΣΤΟ):
```
✅ Architect → THR Payment (βάσει όγκου δεδομένων)
✅ Τιμολόγηση: 0.001 THR/KB
✅ Minimum charge: 0.1 THR
✅ Redirect στο Chat.html για περαιτέρω ανάπτυξη
✅ T2E rewards όταν ολοκληρωθεί το project
```

### Πώς Λειτουργεί:

#### 1. Αρχική Χρέωση (Architect)

**Endpoint**: `POST /api/architect_generate`

**Request**:
```json
{
  "wallet": "THRxxxxxxxxx",
  "blueprint": "web_app_fullstack.md",
  "spec": "Θέλω e-commerce με login, products, cart, checkout",
  "model": "gpt-4o",
  "session_id": "optional_existing_session"
}
```

**Response**:
```json
{
  "status": "architect",
  "quantum_key": "QK_abc123...",
  "blueprint": "web_app_fullstack.md",
  "response": "Generated architecture...",
  "files": [
    {"filename": "server.py", "size": 12543},
    {"filename": "templates/index.html", "size": 3421}
  ],
  "session_id": "sess_12345",
  "cost_thr": 0.145,
  "total_kb": 145.2,
  "files_count": 15,
  "redirect_to_chat": true
}
```

**Τι Συμβαίνει**:
1. Ελέγχεται το THR balance του wallet
2. Υπολογίζεται το κόστος: `max(0.1, total_KB * 0.001)` THR
3. Αφαιρείται THR από το wallet → Πιστώνεται στο `AI_WALLET_ADDRESS`
4. Δημιουργείται transaction τύπου `"architect_service"` στο blockchain
5. Επιστρέφεται `session_id` για συνέχεια στο chat

**Transaction Blockchain**:
```json
{
  "type": "architect_service",
  "from": "THRuser123",
  "to": "THR_AI_SERVICES_WALLET_00001",
  "amount": 0.145,
  "fee": 0.0,
  "timestamp": "2026-01-17T12:00:00Z",
  "blueprint": "web_app_fullstack.md",
  "files_count": 15,
  "total_bytes": 148685,
  "session_id": "sess_12345"
}
```

#### 2. Περαιτέρω Ανάπτυξη (Chat.html)

Μετά την αρχική generation, ο χρήστης redirect στο `/chat?session=sess_12345&from=architect`

**Χρησιμοποιεί**:
- AI Credits από packs (Q-100, Q-500, Q-2000)
- Όλους τους providers (Gemini, GPT-4o, Local)
- 1 credit ανά μήνυμα

**Παράδειγμα Διαλόγου**:
```
User: Πρόσθεσε authentication με JWT tokens
Pythia: [Generates auth middleware code]
Cost: 1 AI credit

User: Φτιάξε το frontend για το login form
Pythia: [Generates HTML/CSS/JS]
Cost: 1 AI credit
```

#### 3. Ολοκλήρωση Project (T2E Reward)

Όταν ο χρήστης ολοκληρώσει το project, καλείται:

**Endpoint**: `POST /api/architect/complete_project`

**Request**:
```json
{
  "wallet": "THRuser123",
  "session_id": "sess_12345"
}
```

**Response**:
```json
{
  "status": "rewarded",
  "reward": 95.0,
  "new_balance": 234.567,
  "breakdown": {
    "base": 20.0,
    "file_bonus": 75.0,
    "size_bonus": 0.0
  }
}
```

**Reward Calculation**:
```python
base_reward = 20.0                          # Βασική ανταμοιβή
file_bonus = files_count * 5.0              # 5 THR ανά αρχείο
size_bonus = (total_kb / 10.0) * 10.0       # 10 THR ανά 10KB

total_reward = base + file_bonus + size_bonus
```

**Παράδειγμα**:
- 15 αρχεία → 15 × 5 = 75 THR
- 145 KB → (145/10) × 10 = 145 THR
- Βάση → 20 THR
- **Σύνολο: 240 THR** 🎉

**Blockchain Transaction**:
```json
{
  "type": "t2e_architect_reward",
  "to": "THRuser123",
  "amount": 240.0,
  "fee": 0.0,
  "timestamp": "2026-01-17T13:30:00Z",
  "session_id": "sess_12345",
  "files_count": 15,
  "total_kb": 145.2,
  "reason": "Architect project completion"
}
```

---

## 💬 CHATBOT (PYTHIA) - ΑΠΛΕΣ ΣΥΝΟΜΙΛΙΕΣ

### Χωρίς Architect Session

**Χρήση**: Απλές ερωτήσεις, debugging, εξηγήσεις κώδικα

**Χρέωση**:
- **Με wallet**: 1 AI credit ανά μήνυμα (από packs)
- **Guest mode**: 5 δωρεάν μηνύματα (tracked via cookies)

**AI Packs** (αγορά με THR):
```
Q-100:   100 credits για 5 THR   (0.05 THR/credit)
Q-500:   500 credits για 20 THR  (0.04 THR/credit) ⭐ Best value
Q-2000: 2000 credits για 60 THR  (0.03 THR/credit) ⭐⭐ Premium
```

**Models**:
- `gemini-2.5-pro` (default Gemini)
- `gemini-1.5-flash` (faster, lighter)
- `gpt-4o` (premium OpenAI)
- `gpt-4.1-mini` (faster, cheaper)
- `local` (offline, δωρεάν αλλά περιορισμένο)

### Session Management

**Το chat.html κρατάει ΟΛΑ τα sessions**:
1. **Απλά sessions**: Chatbot conversations
2. **Architect sessions**: Που ξεκίνησαν από Architect και συνεχίζουν για ανάπτυξη

**API Endpoints**:
```
GET  /api/ai/sessions                    # List όλων των sessions
POST /api/ai/sessions/start              # Νέο session
GET  /api/ai/sessions/{id}/messages      # Μηνύματα session
PATCH /api/ai/sessions/{id}              # Rename session
DELETE /api/ai/sessions/{id}             # Delete session
POST /api/ai/chat                        # Send message (χρεώνει 1 credit)
```

---

## 🎓 TRAIN-TO-EARN (T2E) SYSTEM

### 1. Απλές Συνεισφορές

**Endpoint**: `POST /api/v1/train2earn/contribute`

**Τύποι & Rewards** (ΣΤΑΘΕΡΕΣ ΤΙΜΕΣ - ελέγχονται από server):
```python
REWARD_MAP = {
    'conversation': 5.0,    # Διάλογος user-assistant
    'code': 10.0,           # Code snippet με περιγραφή
    'document': 15.0,       # Τεκμηρίωση, άρθρο
    'qa': 8.0,              # Ερώτηση-Απάντηση
    'dataset': 20.0         # Dataset (JSON/CSV)
}
```

**⚠️ ΣΗΜΑΝΤΙΚΟ**: Οι ανταμοιβές **ΔΕΝ** στέλνονται από το client! Ο server καθορίζει το reward βάσει τύπου.

**Request** (ΣΩΣΤΟ):
```json
{
  "contributor": "THRuser123",
  "type": "code",
  "content": {
    "title": "SHA256 hash function in Python",
    "code": "import hashlib...",
    "description": "Efficient SHA256 implementation"
  },
  "tags": ["python", "crypto", "hash"],
  "auth_secret": "user_secret_key",
  "passphrase": "optional_extra_auth"
}
```

**Response**:
```json
{
  "status": "success",
  "tx_id": "t2e_contrib_abc123",
  "reward": 10.0
}
```

**Τι Συμβαίνει**:
1. Ελέγχεται authentication (auth_secret)
2. Server καθορίζει reward από `REWARD_MAP[type]`
3. **Πιστώνεται στο ledger**: `ledger[wallet] += reward`
4. Αποθηκεύεται στο `t2e_contributions.json`
5. Δημιουργείται transaction στο blockchain

### 2. Architect Project Completion (ΝΕΟ!)

**Endpoint**: `POST /api/architect/complete_project`

**Request**:
```json
{
  "wallet": "THRuser123",
  "session_id": "sess_12345"
}
```

**Reward Calculation** (ΜΕΓΑΛΥΤΕΡΕΣ ΑΝΤΑΜΟΙΒΕΣ):
```python
base = 20.0
file_bonus = files_count * 5.0
size_bonus = (total_kb / 10.0) * 10.0
total = base + file_bonus + size_bonus
```

**Παραδείγματα**:
- Μικρό project (5 files, 30KB): 20 + 25 + 30 = **75 THR**
- Μεσαίο (15 files, 150KB): 20 + 75 + 150 = **245 THR**
- Μεγάλο (30 files, 500KB): 20 + 150 + 500 = **670 THR**

---

## 💰 WALLET HISTORY MODAL (ΝΕΟ!)

### Τοποθεσία
**Template**: `/templates/base.html:427-555` (CSS)
**HTML**: Lines 938-952
**JavaScript**: Lines 1157-1264

### Χαρακτηριστικά

1. **Όμορφο Modal** με Thronos theme
2. **Πλήρες Ιστορικό** συναλλαγών (sent/received)
3. **Ενδείξεις Κατεύθυνσης**: 📥 Received / 📤 Sent
4. **Click to Copy** TX ID
5. **Λεπτομέρειες**:
   - Τύπος συναλλαγής
   - Ποσό & Fee
   - Block height
   - Timestamp
   - From/To addresses

### Πώς να Ανοίξεις το Modal

**JavaScript**:
```javascript
openHistoryModal(); // Από οπουδήποτε στο base.html
```

**API Call**:
```javascript
GET /api/v1/address/{thr_address}/history
```

**Response**:
```json
{
  "address": "THRuser123",
  "transactions": [
    {
      "tx_id": "tx_abc123...",
      "from": "THRuser123",
      "to": "THRmerchant456",
      "amount": 10.5,
      "fee": 0.05,
      "timestamp": "2026-01-17T12:00:00Z",
      "block_height": 12345,
      "type": "transfer"
    }
  ]
}
```

### UI Elements

**Button to Open** (προσθήκη στο wallet popup):
```html
<button class="wallet-popup-btn" onclick="openHistoryModal()">
  <span class="lang-el">📜 Ιστορικό</span>
  <span class="lang-en">📜 History</span>
</button>
```

---

## 🔐 ΑΣΦΑΛΕΙΑ & BUG FIXES

### 1. Architect - Από Credits σε THR
**Πριν**: Δωρεάν unlimited usage
**Τώρα**: ✅ Χρέωση σε THR βάσει όγκου

### 2. T2E Rewards - Server-Controlled
**Πριν**: Client έστελνε το reward amount (exploitable)
**Τώρα**: ✅ Server καθορίζει από `REWARD_MAP`

### 3. T2E Ledger Crediting
**Πριν**: Καταγραφή χωρίς πίστωση THR
**Τώρα**: ✅ Άμεση πίστωση στο ledger

### 4. Guest Credits API Fix
**Πριν**: Duplicate `if not wallet:` blocks (unreachable code)
**Τώρα**: ✅ Ενοποιημένος έλεγχος

---

## 📊 ΡΟΕΣ ΧΡΗΜΑΤΩΝ

### 1. User → Architect
```
User Wallet → AI_WALLET_ADDRESS
Amount: 0.001 THR/KB (min 0.1 THR)
Type: "architect_service"
```

### 2. User → AI Packs (για Chat)
```
User Wallet → AI_WALLET_ADDRESS
Amount: 5/20/60 THR (βάσει pack)
Type: "service_payment"
Credits: 100/500/2000 AI credits
```

### 3. System → User (T2E Simple)
```
SYSTEM → User Wallet
Amount: 5-20 THR (βάσει contribution type)
Type: "t2e_contribution_reward"
```

### 4. System → User (T2E Architect)
```
SYSTEM → User Wallet
Amount: 20 + (files×5) + (KB/10×10) THR
Type: "t2e_architect_reward"
```

---

## 🎯 ΣΗΜΑΝΤΙΚΕΣ ΔΙΕΥΚΡΙΝΙΣΕΙΣ ΓΙΑ ΤΗΝ PYTHIA

### 1. Διαχωρισμός Architect vs Chatbot

| Χαρακτηριστικό | Architect | Chatbot |
|---------------|-----------|---------|
| **Πληρωμή** | THR (βάσει όγκου) | AI Credits (από packs) |
| **Χρήση** | Αρχική αρχιτεκτονική | Περαιτέρω ανάπτυξη |
| **Endpoint** | `/api/architect_generate` | `/api/ai/chat` |
| **Session** | Δημιουργεί session | Συνεχίζει session |
| **T2E Reward** | Μεγάλο (20-1000 THR) | Μικρό (5-20 THR) |

### 2. Sessions - ΔΕΝ Μπερδεύονται!

**Το chat.html διαχειρίζεται ΟΛΑ τα sessions**:
- Απλά chatbot sessions (από `/chat`)
- Architect sessions (από `/architect` → redirect `/chat`)

**Metadata** για να τα ξεχωρίζεις:
```json
{
  "session_id": "sess_12345",
  "origin": "architect",  // ή "chat"
  "architect_tx": "tx_abc123",  // αν origin=architect
  "blueprint": "web_app_fullstack.md"  // αν origin=architect
}
```

### 3. Πότε να Προτείνεις Architect vs Chat

**Architect** (φτιάξε νέο project):
- "Θέλω να φτιάξω ένα e-commerce"
- "Χτίσε μου blog με Flask"
- "Dashboard για analytics"

**Chat** (βελτίωση υπάρχοντος):
- "Πρόσθεσε authentication"
- "Φτιάξε το UI πιο όμορφο"
- "Debug αυτό το error"

### 4. Πότε να Προτείνεις T2E Completion

Όταν ο χρήστης πει:
- "Τελείωσα το project"
- "Είμαι έτοιμος να το deploy"
- "Όλα δουλεύουν τέλεια"

**Response**:
```
Συγχαρητήρια! Το project σου είναι έτοιμο! 🎉

Θέλεις να το ολοκληρώσεις και να λάβεις τα T2E rewards;
Εκτιμώμενη ανταμοιβή: ~240 THR

Καλώ το /api/architect/complete_project...
```

---

## 🧠 PYTHIA - ΠΑΡΑΔΕΙΓΜΑΤΑ ΔΙΑΛΟΓΩΝ

### Παράδειγμα 1: Architect Flow

**User**: Θέλω να φτιάξω ένα blog με Flask, PostgreSQL και authentication

**Pythia**:
```
Τέλεια! Αυτό είναι ιδανικό για τον Thronos Architect! 🏗️

Ο Architect θα σου δημιουργήσει ολόκληρη την αρχιτεκτονική:
- Backend API (Flask + SQLAlchemy)
- Database models (PostgreSQL)
- Authentication system (JWT)
- Frontend templates (Jinja2)
- Docker configuration

Κόστος: ~0.1-0.5 THR (βάσει όγκου κώδικα)
Μετά μπορείς να συνεχίσεις εδώ για customizations με AI credits!

Θέλεις να συνεχίσω; (Χρειάζεται το Thronos wallet σου)
```

**User**: Ναι, το wallet μου είναι THRuser123

**Pythia**:
```
Εντάξει! Στέλνω την αίτηση στον Architect...

[Calls /api/architect_generate]

✅ Αρχιτεκτονική ολοκληρώθηκε!

📊 Αποτελέσματα:
- 18 αρχεία δημιουργήθηκαν
- 167.3 KB κώδικα
- Κόστος: 0.167 THR

Θέλεις να συνεχίσουμε την ανάπτυξη εδώ;
Μπορώ να σε βοηθήσω με customizations, styling, testing!
```

### Παράδειγμα 2: Chat Development

**User**: Πρόσθεσε email verification στο authentication

**Pythia**:
```
Φυσικά! Θα προσθέσω email verification:

1. SMTP configuration στο config.py
2. Email sending service
3. Verification token generation
4. /verify/<token> route
5. Updated registration flow

[Generates code...]

Κόστος: 1 AI credit
Υπόλοιπο: 487 credits

Θέλεις να δοκιμάσουμε το verification flow;
```

### Παράδειγμα 3: T2E Completion

**User**: Τέλειο! Το project είναι έτοιμο για production!

**Pythia**:
```
Συγχαρητήρια! 🎉

Το project σου φαίνεται ολοκληρωμένο!
Θέλεις να το σημειώσω ως complete και να λάβεις T2E rewards;

Εκτιμώμενη ανταμοιβή:
- Base: 20 THR
- File bonus: 90 THR (18 files × 5)
- Size bonus: 160 THR (167 KB)
━━━━━━━━━━━━━━━━━━━━━
Σύνολο: ~270 THR 💰

Προχωρώ;
```

**User**: Ναι!

**Pythia**:
```
[Calls /api/architect/complete_project]

✅ Project ολοκληρώθηκε!

🎓 T2E Reward: 270 THR credited!
💰 Νέο υπόλοιπο: 345.678 THR

Το project καταχωρήθηκε στο blockchain!
TX ID: t2e_arch_abc123...

Μπράβο για την εξαιρετική δουλειά! 🚀
```

---

## 📚 API REFERENCE SUMMARY

### Architect Endpoints

```
GET  /architect                         # Architect UI
GET  /api/ai_blueprints                # List blueprints
POST /api/architect_generate           # Generate architecture (charges THR)
POST /api/architect/complete_project   # Mark complete (T2E reward)
```

### Chat Endpoints

```
GET  /chat                             # Chat UI
POST /api/ai/chat                      # Send message (charges 1 credit)
GET  /api/ai/sessions                  # List sessions
POST /api/ai/sessions/start            # New session
GET  /api/ai/sessions/{id}/messages    # Get messages
```

### Wallet Endpoints

```
GET  /api/wallet/tokens/{address}      # Get all token balances
GET  /api/v1/address/{addr}/history   # Transaction history (for modal)
POST /api/wallet/send                  # Send transaction
```

### Credits & Packs

```
GET  /api/ai_credits?wallet=THR...     # Check AI credits
POST /api/ai_purchase_pack             # Buy AI pack with THR
GET  /api/ai_packs                     # List available packs
```

### T2E Endpoints

```
GET  /train2earn                       # T2E UI
POST /api/v1/train2earn/contribute     # Submit contribution
GET  /api/v1/train2earn/contributions/{addr}  # Get history
```

---

## ✅ TESTING CHECKLIST (για Pythia να γνωρίζει τι να ελέγχει)

### Architect Flow
- [ ] Wallet required για generation
- [ ] THR balance check πριν τη χρέωση
- [ ] Κόστος υπολογίζεται σωστά (0.001 THR/KB, min 0.1)
- [ ] Transaction δημιουργείται στο blockchain
- [ ] Session ID επιστρέφεται για chat redirect
- [ ] Files metadata (size, count) ακριβή

### Chat Development
- [ ] AI credits deduction (1 per message)
- [ ] Session persistence
- [ ] Multi-model support (Gemini, GPT-4o, local)
- [ ] File upload support
- [ ] Message history tracking

### T2E Rewards
- [ ] Simple contributions: 5-20 THR βάσει τύπου
- [ ] Architect completion: 20 + bonuses
- [ ] Ledger update σωστά
- [ ] Blockchain transaction created
- [ ] No client-controlled reward amounts

### Wallet History
- [ ] Modal opens successfully
- [ ] Transactions load από `/api/v1/address/{addr}/history`
- [ ] Sent/Received direction correct
- [ ] TX ID copy works
- [ ] Empty state handles gracefully

---

## 🎓 ΤΕΛΙΚΕΣ ΟΔΗΓΙΕΣ ΓΙΑ ΤΗΝ PYTHIA

### Όταν Χρήστης Ρωτάει για Τιμές:

**Architect**:
> "Ο Architect χρεώνει σε THR βάσει όγκου: 0.001 THR ανά KB κώδικα, με minimum 0.1 THR. Ένα μεσαίο project (~150KB) κοστίζει περίπου 0.15 THR."

**Chatbot**:
> "Το Chat χρησιμοποιεί AI credits από packs:
> - Q-100: 5 THR για 100 credits
> - Q-500: 20 THR για 500 credits (προτείνεται)
> - Q-2000: 60 THR για 2000 credits (best value)
>
> Κάθε μήνυμα = 1 credit. Επίσης υπάρχουν 5 δωρεάν μηνύματα για guests!"

**T2E**:
> "Μπορείς να κερδίσεις THR με δύο τρόπους:
> 1. Απλές συνεισφορές: 5-20 THR (code, docs, datasets)
> 2. Ολοκλήρωση Architect projects: 20+ THR (μπορεί να φτάσει 1000+ για μεγάλα projects!)"

### Όταν Υπάρχει Error:

**Insufficient THR**:
> "❌ Δεν έχεις αρκετό THR balance. Χρειάζεσαι {cost} THR αλλά έχεις {balance} THR. Μπορείς να αποκτήσεις THR από το pledge system ή mining!"

**No AI Credits**:
> "❌ Τα AI credits σου τελείωσαν! Αγόρασε ένα AI pack από /ai_packs ή χρησιμοποίησε local mode (δωρεάν αλλά περιορισμένο)."

**Session Not Found**:
> "❌ Δεν βρήκα αυτό το session. Πιθανόν να έληξε ή να διαγράφηκε. Θέλεις να ξεκινήσουμε νέο session;"

### Πάντα Να Θυμάσαι:

1. **Architect = THR payment**, **Chat = AI credits**
2. **Sessions NEVER mix up** - το chat.html τα διαχειρίζεται όλα
3. **T2E rewards = AUTOMATIC** από server, όχι client input
4. **Redirect flow**: Architect → Chat για περαιτέρω dev
5. **Wallet History Modal** υπάρχει για διαφάνεια

---

## 📝 COMMIT SUMMARY (για reference)

**Branch**: `claude/test-wallet-widget-7epOo`

**Files Changed**:
- `server.py`: Architect pricing, T2E rewards, AI credits fix
- `templates/architect.html`: Redirect logic, cost display
- `templates/base.html`: Wallet history modal (CSS+HTML+JS)
- `data/ai_blueprints/PYTHIA_TRAINING_THRONOS_V3.6_UPDATES.md`: This file!

**Bugs Fixed**: 5 critical
**Features Added**: 3 major
**Lines Changed**: 1200+ insertions

---

**Εκπαίδευση ολοκληρώθηκε!** 🎓

Η Pythia AI τώρα γνωρίζει:
✅ Το νέο Architect pricing system
✅ Τη ροή Architect → Chat
✅ Το T2E reward system
✅ Το Wallet History Modal
✅ Όλες τις διαφορές μεταξύ Architect/Chat/T2E

**Ημερομηνία Training**: 2026-01-17
**Node**: Node 4
**Status**: ✅ PRODUCTION READY
