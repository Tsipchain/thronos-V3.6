# Complete Thronos Mining Guide
## Classic Mining + Heat Recovery + Auto Tier Upgrades

**Status:** Phase 6D Complete  
**Date:** May 18, 2026

---

## 🎯 Overview

The Thronos mining system now offers TWO parallel paths:

### Path A: Classic Mining (Always Works)
- **Requirement:** Proof-of-Work hash with valid difficulty
- **Reward:** 8 THR per block (base)
- **No setup needed:** Just mine, submit blocks, get paid
- **Equipment:** Optional

### Path B: Heat Recovery Bonuses (Earn Extra)
- **Requirement:** Install heat recovery equipment + submit valid proofs
- **Bonus:** 5-40% extra THR (TIER_1 to TIER_4)
- **Setup:** Register equipment → Submit heat proofs → Auto tier upgrade
- **Timeline:** Gradual rewards as efficiency improves

---

## 📊 Mining Paths Comparison

| Feature | Classic Mining | Heat Recovery Bonus |
|---------|----------------|---------------------|
| **Base Reward** | 8 THR/block | Same + 5-40% bonus |
| **Setup Required** | None | Equipment + proofs |
| **Equipment Cost** | $0 | $3K-$50K |
| **Payback Period** | N/A | 2-3 years |
| **Complexity** | Simple | Moderate |
| **Tier System** | N/A | Auto upgrades |
| **Fraud Penalties** | None | Escalating bans |

---

## 🔧 Path A: Classic Mining (Start Here)

### Step 1: Get Mining Job
```bash
GET /api/mining/work?address=THR7c...
```

**Response:**
```json
{
  "ok": true,
  "job_id": "job_12345...",
  "prev_hash": "0000abc...",
  "height": 200287,
  "target": 28948022...
}
```

### Step 2: Solve PoW
```
Nonce search until: SHA256(prev_hash + address + nonce) <= target
```

### Step 3: Submit Block
```bash
POST /api/mining/submit
{
  "thr_address": "THR7c...",
  "prev_hash": "0000abc...",
  "pow_hash": "0000xyz...",
  "nonce": 12345678,
  "height": 200287
}
```

**Success Response (200):**
```json
{
  "ok": true,
  "block_hash": "0000xyz...",
  "reward": 8.0,
  "height": 200287
}
```

**That's it!** You get 8 THR reward. No equipment needed.

---

## 🌡️ Path B: Heat Recovery (Advanced - Earn 5-40% Extra)

### Step 1: Register Equipment
Tell Thronos what heat recovery system you installed:

```bash
POST /api/miner/equipment/register
{
  "miner_address": "THR7c...",
  "equipment_type": "heat_exchanger",
  "location": "EU-GR-01",
  "capacity_kw": 50,
  "efficiency_percent": 90,
  "gps_latitude": 38.2466,
  "gps_longitude": 23.7372,
  "facility_photo_hash": "QmHash..."
}
```

**Response:**
```json
{
  "status": "registered",
  "message": "Equipment registration pending verification",
  "equipment_type": "heat_exchanger",
  "expected_tier": "TIER_4",
  "next_step": "Submit heat recovery proofs to verify equipment"
}
```

**Status:** PENDING_VERIFICATION (not earning bonus yet)

### Step 2: Submit Heat Proofs (Every 5 Minutes)
Collect sensor data from your miners:

```bash
POST /api/heat/submit-metrics
{
  "miner_address": "THR7c...",
  "device_type": "ASIC_S19",
  "device_count": 100,
  "power_consumption_watts": 135000,
  
  "ambient_temp_celsius": 15,
  "inlet_temp_celsius": 25,
  "outlet_temp_celsius": 55,
  "inlet_humidity_pct": 40,
  "outlet_humidity_pct": 35,
  "airflow_cfm": 10000,
  
  "pre_recovery_temp_celsius": 55,
  "post_recovery_temp_celsius": 35,
  "recirculation_flow_gpm": 100,
  "facility_temp_celsius": 28,
  "facility_humidity_pct": 45,
  "energy_generated_kwh": 12.5,
  
  "farm_location": "EU-GR-01",
  "use_case": "greenhouse",
  "gps_latitude": 38.2466,
  "gps_longitude": 23.7372,
  "gps_accuracy_meters": 10,
  "sensors_online": 12,
  "sensors_total": 12
}
```

**Success Response (200 - Valid Proof):**
```json
{
  "proof_id": "proof_THR7c_1716048000",
  "proof_level": "LEVEL_2",
  "proof_valid": true,
  "recovery_percentage": 18.5,
  "bonus_multiplier": 0.25,
  "calculated_heat_kwh": 50.0,
  
  "compliance": {
    "status": "verified",
    "current_tier": "TIER_3",
    "is_banned": false,
    "reputation_score": 100.0,
    "average_recovery_pct": 18.5
  },
  
  "equipment_status": {
    "type": "heat_exchanger",
    "verified": true,
    "operational": true,
    "capacity_kw": 50,
    "efficiency_percent": 90
  },
  
  "proof_statistics": {
    "total_submitted": 5,
    "valid": 5,
    "failed": 0,
    "success_rate": 100.0
  }
}
```

**What happened:**
- ✅ Equipment automatically verified (LEVEL_2 proof)
- ✅ Tier automatically upgraded to TIER_3 (18.5% recovery)
- ✅ You're now earning 25% bonus on mining rewards
- ✅ Next block you mine: 8 THR × 1.25 = **10 THR**

### Step 3: Auto Tier Upgrade
Every time you submit a proof:

```
Current Recovery %  →  New Tier  →  Bonus  →  Your Reward
5-10%  →  TIER_1  →  5%   →  8 × 1.05 = 8.4 THR
10-15% →  TIER_2  →  15%  →  8 × 1.15 = 9.2 THR
15-25% →  TIER_3  →  25%  →  8 × 1.25 = 10.0 THR ← You are here
25%+   →  TIER_4  →  40%  →  8 × 1.40 = 11.2 THR
```

**Tier upgrades automatically when:**
- Recovery improves in next proof
- Proof validates successfully (LEVEL_1+)
- Equipment is verified

---

## 🛡️ Safety: Classic Mining Always Works

Even if heat system fails:

1. ✅ Your blocks still get mined: 8 THR reward
2. ✅ No penalties or downtime
3. ✅ Equipment only adds bonus (never subtracts)
4. ✅ You can enable/disable heat system anytime

**Example:**
- Week 1: Mine with heat → Earn 10 THR + 1.2 bonus
- Week 2: Equipment breaks, can't submit proofs → Still earn 8 THR (no bonus)
- Week 3: Equipment fixed, submit new proof → Earn 10 THR again

---

## 📈 Example: 100 ASIC S19 Farm

### Classic Path Only
```
Hashrate: 11,000 TH/s
Difficulty: Assume 1 block per day
Daily reward: 8 THR × 1 = 8 THR
Monthly: 8 × 30 = 240 THR
Monthly USD: 240 × $50 = $12,000
```

### With Heat Recovery Equipment
```
Install: Heat exchanger ($3K) + ORC turbine ($30K)
Total setup cost: $33,000

Proof metrics:
- Recovery: 25% (TIER_4)
- Use case: Greenhouse (+15% bonus)
- Energy generated: 50 kWh/day = $4/day

Daily mining: 8 THR/day × 1.40 = 11.2 THR
Daily energy value: $4 × 50 kWh = $200
Daily greenhouse produce: $100
Total daily value: 11.2 THR + $304 = ~$860 (at $50/THR)

Monthly mining: 11.2 × 30 = 336 THR = $16,800
Monthly energy/produce: $304 × 30 = $9,120
Total monthly: $25,920

ROI: $33,000 ÷ $25,920 = 1.27 months payback
Annual profit: $25,920 × 12 = $311,000
```

---

## ⚠️ Fraud Detection & Penalties

### Automatic Fraud Checks
Every proof submission is validated for:
1. Physically possible temperatures (ΔT < 100°C)
2. Thermodynamically valid (5-50% recovery range)
3. Sensor consistency (humidity drops with cooling)
4. Facility validation (receives the heat)
5. Energy generation sanity checks
6. GPS accuracy verification
7. Sensor uptime (>90% required)

### Penalty System

| Violation | Action | Impact |
|-----------|--------|--------|
| **#1** | ⚠️ Warning + Monitoring | None (earn bonuses normally) |
| **#2** | 🚫 7-day suspension + tier downgrade | Temporarily banned, tier drops |
| **#3+** | 🔒 Permanent ban | Lose all heat bonuses forever |

**Example:**
```
Day 1: Submit fraudulent proof (impossible temps)
  → ⚠️ Warning issued, under monitoring

Day 15: Submit another bad proof
  → 🚫 7-day ban starts, tier: TIER_4 → TIER_3
  → Cannot earn heat bonus for 7 days
  → Still earn classic 8 THR/block

Day 22: 7-day ban ends, resubmit good proofs
  → ✅ Back to earning bonuses

Day 45: One more fraudulent proof
  → 🔒 Permanently banned from heat rewards
  → Can still mine for 8 THR (no bonus, ever)
```

---

## 📊 Check Your Status Anytime

```bash
GET /api/miner/status/THR7c...
```

**Response:**
```json
{
  "miner_address": "THR7c...",
  "compliance": {
    "status": "compliant",
    "current_tier": "TIER_3",
    "is_banned": false,
    "reputation_score": 98.0,
    "average_recovery_pct": 18.5
  },
  "equipment": {
    "type": "heat_exchanger",
    "verified": true,
    "operational": true,
    "capacity_kw": 50,
    "efficiency_percent": 90
  },
  "proof_statistics": {
    "total_submitted": 156,
    "valid": 154,
    "failed": 2,
    "fraud_violations": 0,
    "success_rate": 98.7
  },
  "rewards": {
    "total_heat_bonus_thr": 1248.5,
    "last_calculation": "2026-05-18T10:30:00Z"
  }
}
```

---

## 🚀 Quick Start Checklists

### ✅ Classic Mining (5 minutes)
- [ ] Get mining job: `GET /api/mining/work?address=YOUR_ADDRESS`
- [ ] Solve PoW hash
- [ ] Submit block: `POST /api/mining/submit`
- [ ] Receive 8 THR reward
- [ ] Done!

### ✅ Heat Recovery Bonus (1-2 weeks)
- [ ] Install heat recovery equipment
- [ ] Register equipment: `POST /api/miner/equipment/register`
- [ ] Set up sensor data collection (every 5 minutes)
- [ ] Submit first heat proof: `POST /api/heat/submit-metrics`
- [ ] Check status: `GET /api/miner/status/YOUR_ADDRESS`
- [ ] Monitor proofs (should see tier upgrades)
- [ ] Start earning bonuses immediately

---

## 🔗 API Endpoint Summary

### Mining
- `GET /api/mining/work` - Get mining job
- `POST /api/mining/submit` - Submit completed block
- `GET /api/mining/info` - Mining info & halving schedule

### Heat Recovery (Optional)
- `POST /api/miner/equipment/register` - Register equipment
- `POST /api/heat/submit-metrics` - Submit heat proof
- `GET /api/miner/status/<address>` - Get compliance status
- `GET /api/heat/monitor/farms` - Network farm stats
- `GET /api/heat/monitor/farm/<address>` - Individual farm monitoring
- `GET /api/heat/compliance/report` - Network compliance report

---

## ⚡ Key Points

1. **Classic mining NEVER requires heat data**
   - Mine indefinitely without any equipment
   - Get 8 THR per block guaranteed
   - No setup, no maintenance, no risk

2. **Heat bonuses are purely optional**
   - Install equipment if you want extra rewards
   - Takes 1-3 months to pay for itself
   - Can earn 11.2 THR/block with perfect 25%+ recovery

3. **Tiers upgrade automatically**
   - Submit better proofs → tier improves
   - Recovery % drives tier classification
   - Bonuses apply to NEXT mining block

4. **Fraud protection is automatic**
   - Impossible physics rejected immediately
   - Escalating penalties (warning → suspension → ban)
   - 3-strike system keeps network honest

5. **Both systems work independently**
   - Mining works without heat data
   - Heat bonuses don't affect mining
   - No dependencies or blocking

---

## 🎓 Example Workflows

### Miner #1: Just Wants Easy 8 THR
```
1. Start mining
2. Get job, solve PoW, submit block
3. Receive 8 THR
4. Repeat
```

### Miner #2: Wants To Max Out With Heat
```
1. Buy heat exchanger ($3K)
2. Install + register equipment
3. Set up sensor network
4. Submit proof every 5 minutes
5. Tier upgrades: TIER_1 → TIER_2 → TIER_3 → TIER_4
6. Earn 11.2 THR/block + energy value
7. Payback in ~1 month, profit from then on
```

### Miner #3: Tests Equipment First
```
1. Start mining (8 THR/block)
2. Install simple heat exchanger
3. Collect 1 week of data
4. Register equipment (still earning 8 THR)
5. Submit first proof (now earning 8.4 THR with TIER_1)
6. Improve system over 2 weeks (reaches TIER_3)
7. Final: 10 THR/block + energy bonuses
```

---

## 📞 Support

**For mining issues:**
- Check `/api/mining/info` endpoint
- Verify blocks aren't stale (tip height changing)
- Confirm difficulty is reasonable

**For heat recovery issues:**
- Check `/api/miner/status/<address>` for compliance
- Review proof anomalies in response
- Verify sensor data matches physical equipment
- Contact third-party verifier if equipment won't verify

**For penalties:**
- Check violation details in `/api/miner/status`
- Submit clean proofs to clear monitoring status
- Wait 7 days if suspended
- Permanent bans cannot be appealed

---

**Last Updated:** May 18, 2026  
**Next Phase:** Real-world deployment, sensor integration, IoT mesh networks
