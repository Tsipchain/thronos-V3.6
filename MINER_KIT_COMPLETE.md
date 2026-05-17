# 🔨 THRONOS Complete Miner Kit
## Hardware Support & Phase 6 Integration

---

## 📦 Hardware Support Matrix

### 1. ASIC Miners
**Best For:** Maximum hashrate, professional mining operations

**Specifications:**
```json
{
  "device_type": "ASIC_S19",
  "variants": [
    "ASIC_S19",
    "ASIC_S19_PRO",
    "ASIC_S19_XP",
    "ASIC_S21",
    "ASIC_T19",
    "ASIC_L7"
  ],
  "power_consumption_watts": {
    "S19": 1350,
    "S19_PRO": 1350,
    "S19_XP": 1321,
    "S21": 1500,
    "T19": 1280,
    "L7": 3060
  },
  "hashrate_thash": {
    "S19": 110,
    "S19_PRO": 110,
    "S19_XP": 140,
    "S21": 130,
    "T19": 84,
    "L7": 504
  },
  "heat_output_watts": {
    "S19": 1200,
    "S19_PRO": 1200,
    "S19_XP": 1180,
    "S21": 1350,
    "T19": 1150,
    "L7": 2750
  }
}
```

**Phase 6 Heat Recovery (ASIC):**
- Recovery potential: 15-25% of power consumption
- Typical recovery: 180-250 kWh/day per 100 units
- Tier: TIER_3 (Advanced Recovery - 25% bonus)
- Best use case: Greenhouse (+15% bonus), Aquaculture (+18% bonus)
- Example: 100 × S19 units = **+2.0 THR/block heat bonus**

---

### 2. GPU Miners
**Best For:** Flexible mining, switching algorithms, home mining

**Specifications:**
```json
{
  "device_type": "GPU",
  "variants": [
    "RTX_4090",
    "RTX_4080",
    "RTX_A100",
    "A40",
    "V100",
    "RX_7900_XTX"
  ],
  "power_consumption_watts": {
    "RTX_4090": 450,
    "RTX_4080": 320,
    "RTX_A100": 400,
    "A40": 300,
    "V100": 250,
    "RX_7900_XTX": 440
  },
  "hashrate_thash": {
    "RTX_4090": 45,
    "RTX_4080": 30,
    "RTX_A100": 35,
    "A40": 28,
    "V100": 22,
    "RX_7900_XTX": 42
  },
  "heat_output_watts": {
    "RTX_4090": 400,
    "RTX_4080": 280,
    "RTX_A100": 350,
    "A40": 260,
    "V100": 220,
    "RX_7900_XTX": 380
  }
}
```

**Phase 6 Heat Recovery (GPU):**
- Recovery potential: 12-20% of power consumption
- Typical recovery: 60-150 kWh/day per 100 units
- Tier: TIER_2 (Standard Recovery - 15% bonus)
- Best use case: Space Heating (+5% bonus), Livestock (+12% bonus)
- Example: 100 × RTX 4090 = **+1.2 THR/block heat bonus**

---

### 3. CPU Miners
**Best For:** Accessibility, distributed networks, low-power operations

**Specifications:**
```json
{
  "device_type": "CPU",
  "variants": [
    "RYZEN_7950X",
    "RYZEN_5950X",
    "INTEL_I9_13900K",
    "INTEL_XEON_W9_3595X",
    "ARM_SERVER"
  ],
  "power_consumption_watts": {
    "RYZEN_7950X": 170,
    "RYZEN_5950X": 105,
    "INTEL_I9_13900K": 125,
    "INTEL_XEON_W9_3595X": 250,
    "ARM_SERVER": 50
  },
  "hashrate_mhash": {
    "RYZEN_7950X": 850,
    "RYZEN_5950X": 650,
    "INTEL_I9_13900K": 700,
    "INTEL_XEON_W9_3595X": 1200,
    "ARM_SERVER": 150
  },
  "heat_output_watts": {
    "RYZEN_7950X": 150,
    "RYZEN_5950X": 90,
    "INTEL_I9_13900K": 110,
    "INTEL_XEON_W9_3595X": 220,
    "ARM_SERVER": 40
  }
}
```

**Phase 6 Heat Recovery (CPU):**
- Recovery potential: 10-18% of power consumption
- Typical recovery: 20-50 kWh/day per 100 units
- Tier: TIER_1 (Baseline Recovery - 5% bonus)
- Best use case: Space Heating (+5% bonus)
- Example: 100 × Ryzen 7950X = **+0.4 THR/block heat bonus**

---

### 4. USB ASIC Miners
**Best For:** Entry-level, testing, small operations, education

**Specifications:**
```json
{
  "device_type": "USB_ASIC",
  "variants": [
    "ANTMINER_U1",
    "COMPAC_F4",
    "DUALMINER_USB",
    "TERMINATOR_ASIC",
    "BLOCKSTREAM_JADE"
  ],
  "power_consumption_watts": {
    "ANTMINER_U1": 4,
    "COMPAC_F4": 15,
    "DUALMINER_USB": 8,
    "TERMINATOR_ASIC": 25,
    "BLOCKSTREAM_JADE": 3
  },
  "hashrate_ghash": {
    "ANTMINER_U1": 1.6,
    "COMPAC_F4": 55,
    "DUALMINER_USB": 20,
    "TERMINATOR_ASIC": 180,
    "BLOCKSTREAM_JADE": 0.5
  },
  "heat_output_watts": {
    "ANTMINER_U1": 3,
    "COMPAC_F4": 12,
    "DUALMINER_USB": 6,
    "TERMINATOR_ASIC": 20,
    "BLOCKSTREAM_JADE": 2
  }
}
```

**Phase 6 Heat Recovery (USB ASIC):**
- Recovery potential: 8-15% of power consumption
- Typical recovery: 2-5 kWh/day per 100 units
- Tier: TIER_1 (Baseline Recovery - 5% bonus)
- Best use case: Educational (no heat bonus needed)
- Example: 1000 × Compac F4 = **+0.3 THR/block heat bonus**

---

### 5. IoT Mining Nodes
**Best For:** Distributed sensing, low-power, always-on devices

**Specifications:**
```json
{
  "device_type": "IOT_NODE",
  "variants": [
    "RASPBERRY_PI_4",
    "RASPBERRY_PI_5",
    "JETSON_NANO",
    "JETSON_ORIN",
    "ORANGE_PI",
    "ROCKCHIP_RK3588"
  ],
  "power_consumption_watts": {
    "RASPBERRY_PI_4": 5,
    "RASPBERRY_PI_5": 8,
    "JETSON_NANO": 15,
    "JETSON_ORIN": 40,
    "ORANGE_PI": 4,
    "ROCKCHIP_RK3588": 10
  },
  "hashrate_mhash": {
    "RASPBERRY_PI_4": 10,
    "RASPBERRY_PI_5": 15,
    "JETSON_NANO": 25,
    "JETSON_ORIN": 80,
    "ORANGE_PI": 8,
    "ROCKCHIP_RK3588": 20
  },
  "heat_output_watts": {
    "RASPBERRY_PI_4": 4,
    "RASPBERRY_PI_5": 6,
    "JETSON_NANO": 12,
    "JETSON_ORIN": 30,
    "ORANGE_PI": 3,
    "ROCKCHIP_RK3588": 8
  },
  "thermal_sensors": true,
  "data_collection": ["temp", "humidity", "pressure", "air_quality"],
  "reporting_interval_seconds": 300
}
```

**Phase 6 Heat Recovery (IoT):**
- Recovery potential: 5-12% of power consumption
- Typical recovery: 0.2-1 kWh/day per 100 units
- Tier: TIER_1 (Baseline Recovery - 5% bonus)
- Special feature: **Dual functionality** - mine + data collection
- Data types: Temperature, humidity, environmental sensors
- Example: 10,000 × Raspberry Pi 4 = **+0.2 THR/block heat bonus**

---

### 6. Hybrid Mining Rigs
**Best For:** Flexible operations, multi-algorithm support

**Specifications:**
```json
{
  "device_type": "HYBRID_RIG",
  "composition": {
    "gpu_count": 6,
    "gpu_type": "RTX_4080",
    "cpu_type": "RYZEN_7950X",
    "system_memory_gb": 128,
    "storage_ssd_tb": 2
  },
  "power_consumption_watts": {
    "total": 2500,
    "cpu": 170,
    "gpu_per_unit": 320,
    "motherboard_psu": 200
  },
  "hashrate_combined": {
    "sha256d": 25,
    "ethash": 180,
    "randomx": 850
  },
  "heat_output_watts": 2200
}
```

**Phase 6 Heat Recovery (Hybrid):**
- Recovery potential: 18-22% of power consumption
- Typical recovery: 150-250 kWh/day per unit
- Tier: TIER_3 (Advanced Recovery - 25% bonus)
- Best use case: Greenhouse (+15% bonus), Aquaculture (+18% bonus)
- Example: 50 × Hybrid Rigs = **+2.5 THR/block heat bonus**

---

## 🌡️ Phase 6 Heat Recovery Integration

### Device Metrics Template

```python
{
    "miner_address": "THR7c_your_address",
    "timestamp": "2026-05-17T12:00:00Z",
    
    # Device Info
    "device_type": "ASIC_S19",          # Required
    "device_count": 100,                 # Required
    "power_consumption_watts": 135000,   # Total power
    
    # Temperature Data
    "ambient_temp_celsius": 15,
    "inlet_temp_celsius": 25,
    "outlet_temp_celsius": 55,
    
    # Heat Recovery
    "airflow_cfm": 50000,                # Cubic feet per minute
    "heat_recovered_joules": 180000000,  # Total joules captured
    "heat_recovered_kwh": 50,            # Converted to kWh
    
    # Efficiency
    "pue_ratio": 1.15,                   # Power Usage Effectiveness
    "recovery_percentage": 18.5,         # % of waste heat captured
    
    # Location & Use Case
    "farm_location": "EU-GR-01",
    "use_case": "greenhouse"
}
```

---

## 💰 Reward Examples by Device Type

### Scenario 1: 100 ASIC S19 Miners (Greenhouse)
```
Base Mining Reward (Phase C5):
├─ 100 devices × 8 THR/block × 720 blocks/day
├─ = 576,000 THR/day baseline
└─ = 17.28M THR/month

Heat Recovery (18% recovery → TIER_3 + Greenhouse bonus):
├─ Recovery: 18% × 25% bonus × (1 + 0.15 use case) = 5.18%
├─ = 576,000 × 0.0518 = 29,836 THR/day bonus
└─ = 895,080 THR/month bonus

TOTAL MONTHLY: 17.28M + 0.895M = 18.175M THR (+5.2% increase)
Energy Value: 50 kWh/day × $0.08 = $120/month recovered energy
```

### Scenario 2: 500 GPU Miners (Space Heating)
```
Base Mining Reward (Phase C5):
├─ 500 devices × 8 THR/block × 720 blocks/day
├─ = 2,880,000 THR/day baseline
└─ = 86.4M THR/month

Heat Recovery (15% recovery → TIER_2 + Space Heating bonus):
├─ Recovery: 15% × 15% bonus × (1 + 0.05 use case) = 2.36%
├─ = 2,880,000 × 0.0236 = 67,968 THR/day bonus
└─ = 2,039,040 THR/month bonus

TOTAL MONTHLY: 86.4M + 2.04M = 88.44M THR (+2.4% increase)
Energy Value: 150 kWh/day × $0.08 = $360/month recovered energy
```

### Scenario 3: 10,000 IoT Nodes (Mixed)
```
Base Mining Reward (Phase C5):
├─ 10,000 devices × 8 THR/block × 720 blocks/day
├─ = 57,600,000 THR/day baseline
└─ = 1.728B THR/month

Heat Recovery (8% recovery → TIER_1 + dual data collection):
├─ Recovery: 8% × 5% bonus = 0.4%
├─ = 57,600,000 × 0.004 = 230,400 THR/day bonus
└─ = 6,912,000 THR/month bonus

SPECIAL FEATURES:
├─ Environmental data collection (temp, humidity, pressure)
├─ Real-time weather stations across network
└─ Scientific contribution bonus: +10% (ecosystem fund allocation)

TOTAL MONTHLY: 1.728B + 0.006B = 1.734B THR (+0.4% base + 10% science bonus)
Data Value: Invaluable for climate research + agriculture optimization
```

---

## 🔧 Getting Started: Miner Setup

### Step 1: Determine Your Hardware
```
1. ASIC (maximum reward): S19, S21, L7, T19
2. GPU (flexible): RTX 4090, 4080, A100
3. CPU (accessible): Ryzen 7950X, Intel Xeon
4. USB (entry-level): Compac F4, Terminator
5. IoT (distributed): Raspberry Pi, Jetson
6. Hybrid (professional): Multi-GPU + CPU + specialized
```

### Step 2: Configure Your Miner
```bash
# Copy template configuration
cp /app/config/miner-config-template.json /app/config/miner.json

# Edit with your settings
nano /app/config/miner.json
```

### Step 3: Submit Heat Metrics (Phase 6)
```bash
# Submit initial metrics
curl -X POST http://localhost:8000/api/heat/submit-metrics \
  -H "Content-Type: application/json" \
  -d '{
    "miner_address": "THR7c_your_address",
    "device_type": "ASIC_S19",
    "device_count": 50,
    "power_consumption_watts": 67500,
    "ambient_temp_celsius": 20,
    "inlet_temp_celsius": 30,
    "outlet_temp_celsius": 60,
    "airflow_cfm": 25000,
    "heat_recovered_joules": 90000000,
    "heat_recovered_kwh": 25,
    "pue_ratio": 1.15,
    "recovery_percentage": 18.5,
    "farm_location": "EU-GR-01",
    "use_case": "greenhouse"
  }'
```

### Step 4: Monitor Heat Rewards
```bash
# Check your heat rewards
curl http://localhost:8000/api/heat/rewards/THR7c_your_address

# View network heat statistics
curl http://localhost:8000/api/heat/stats
```

### Step 5: Start Mining
```bash
# Start mining
/app/bin/miner --config /app/config/miner.json --pool http://localhost:8000/api/miner/submit
```

---

## 📊 Heat Recovery Optimization Tips

### For ASIC Miners
- Install liquid cooling systems (recovery: 15-25%)
- Use ductwork to direct exhaust heat
- Monitor PUE ratio (aim for 1.10-1.15)
- Best use case: Greenhouse (15% bonus)

### For GPU Miners
- Install large heatsinks and high-RPM fans
- Use case: Space heating (5% bonus) or Livestock (12% bonus)
- Recovery potential: 12-20%
- Cooling efficiency critical for 24/7 operation

### For CPU Miners
- Use high-efficiency cooling
- Recovery: 10-18%
- Best for space heating in cold climates
- Lower heat output = better electricity efficiency

### For IoT Nodes
- Passive cooling (natural airflow)
- Low power = low heat = limited recovery
- Value is in distributed sensing + dual functionality
- Data collection enables predictive agriculture/weather

### For Hybrid Rigs
- Optimize both GPU and CPU workloads
- Dedicated cooling loops for maximum recovery
- Recovery: 18-22% (best in class)
- Aquaculture use case (18% bonus) + heat bonus

---

## 🌍 Use Cases by Region

### Cold Climates (Europe North, Canada, Russia)
- **Primary:** Space Heating (+5% bonus)
- **Secondary:** Livestock (+12% bonus)
- **Optimal recovery:** 15-25%
- **Recommendation:** ASIC or Hybrid rigs

### Temperate Climates (Mediterranean, Central Europe)
- **Primary:** Greenhouse (+15% bonus)
- **Secondary:** Space Heating (+5% bonus)
- **Optimal recovery:** 12-18%
- **Recommendation:** ASIC or GPU miners

### Tropical Climates (Southeast Asia, Middle East)
- **Primary:** Aquaculture (+18% bonus)
- **Secondary:** Desalination (+20% bonus)
- **Optimal recovery:** 10-20%
- **Recommendation:** GPU or efficient ASIC

### Distributed Networks (Worldwide)
- **Primary:** IoT Nodes (+5% bonus + science)
- **Secondary:** Environmental data collection
- **Optimal recovery:** 5-12%
- **Recommendation:** Raspberry Pi, Jetson Nano

---

## 🎯 Summary: Complete Miner Kit

| Type | Power | Hashrate | Heat | Tier | Use Case | Monthly Bonus |
|------|-------|----------|------|------|----------|---|
| **ASIC S19** | 135kW (100×) | 11 TH/s | 600° | TIER_3 | Greenhouse | +29.8k THR |
| **GPU RTX4090** | 45kW (100×) | 4.5 TH/s | 180° | TIER_2 | Space Heat | +67.9k THR |
| **CPU Ryzen7950X** | 17kW (100×) | 850 MH/s | 60° | TIER_1 | Space Heat | +13.7k THR |
| **USB Compac F4** | 1.5kW (100×) | 5.5 GH/s | 6° | TIER_1 | Education | +2.7k THR |
| **IoT RPi4** | 500W (100×) | 1 GH/s | 0.2° | TIER_1 | Science | +4.6k THR |
| **Hybrid Rig** | 2.5kW (1×) | 25 TH/s | 2.2° | TIER_3 | Aquaculture | +1.8k THR |

---

## ✅ Phase 6 Complete

- ✅ ASIC miners (S19, S21, L7, T19)
- ✅ GPU miners (RTX, Jetson, AMD)
- ✅ CPU miners (Ryzen, Intel, ARM)
- ✅ USB ASIC miners (compact, low-power)
- ✅ IoT mining nodes (distributed sensing)
- ✅ Hybrid mining rigs (professional multi-device)
- ✅ Heat recovery integration (4-tier system)
- ✅ Use case bonuses (5 types)
- ✅ Regional optimization (climate-based)
- ✅ API endpoints (metrics, rewards, stats)
- ✅ Interactive dashboard (multi-language)
- ✅ Mining reward integration (automatic bonus)

---

**Thronos Mining System: Complete & Production Ready** 🚀

All miners can now earn heat recovery bonuses automatically when reporting metrics.
Join the decentralized heat recovery network and turn your waste heat into THR!
