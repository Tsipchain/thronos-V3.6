# Phase 6: IoT Heat Metrics Framework
## Waste Heat Recovery & Energy Economics (Software-Only)

---

## Overview

**Phase 6** enables miners to monetize waste heat from ASIC operations through a decentralized energy recovery system. Miners report heat recovery metrics, earn THR bonuses, and receive real-time price signals for recovered energy.

**Timeline:** Years 2-3 (parallel with Phase C5 mining)
**Scope:** Software framework only - no hardware dependencies
**Integration:** Plugs into Phase C5 mining rewards

---

## Core Architecture

### 1. Heat Metrics Collection

```python
@dataclass
class MinerHeatMetrics:
    """Real-time heat data from mining operation"""
    miner_address: str
    timestamp: str                      # ISO 8601
    
    # Hardware metrics
    device_type: str                    # "ASIC_S19", "CPU", "GPU", etc.
    device_count: int
    power_consumption_watts: float      # Total power draw
    
    # Heat recovery metrics
    ambient_temp_celsius: float         # Outside temperature
    inlet_temp_celsius: float           # Air entering mining rig
    outlet_temp_celsius: float          # Air exiting mining rig
    
    # Heat recovery calculation
    airflow_cfm: float                  # Cubic feet per minute
    heat_recovered_joules: float        # Total joules captured
    heat_recovered_kwh: float           # Converted to kWh
    
    # Efficiency metrics
    pue_ratio: float                    # Power Usage Effectiveness (1.0 = perfect)
    recovery_percentage: float          # % of waste heat captured (0-100)
    
    # Location & use case
    farm_location: str                  # Geo-location code
    use_case: str                       # "space_heating", "greenhouse", "livestock", etc.
    
    # Verification
    verified: bool = False
    verification_signature: str = ""
    block_height: int = 0
```

### 2. Heat Reward Tier System

```python
class HeatRewardTier(Enum):
    """Heat recovery efficiency tiers"""
    TIER_1 = {
        "name": "Baseline Recovery",
        "recovery_min": 5,
        "recovery_max": 10,
        "bonus_percentage": 0.05,       # 5% bonus on block reward
        "description": "Basic waste heat capture"
    }
    
    TIER_2 = {
        "name": "Standard Recovery",
        "recovery_min": 10,
        "recovery_max": 15,
        "bonus_percentage": 0.15,       # 15% bonus
        "description": "Moderate heat recovery system"
    }
    
    TIER_3 = {
        "name": "Advanced Recovery",
        "recovery_min": 15,
        "recovery_max": 25,
        "bonus_percentage": 0.25,       # 25% bonus
        "description": "High-efficiency heat capture"
    }
    
    TIER_4 = {
        "name": "Elite Recovery",
        "recovery_min": 25,
        "recovery_max": 100,
        "bonus_percentage": 0.40,       # 40% bonus
        "description": "Industrial-grade heat recovery"
    }
```

### 3. Heat Reward Pool

```python
@dataclass
class HeatRewardPool:
    """Accumulated heat recovery rewards"""
    miner_address: str
    current_block_reward: float         # From Phase C5
    heat_recovery_kwh_day: float        # Average daily recovery
    heat_bonus_percentage: float        # Tier-based bonus
    heat_bonus_amount: float            # THR bonus earned
    
    # Energy economics
    energy_value_usd_per_kwh: float     # Market price
    heat_value_usd: float               # Converted energy value
    thr_price_usd: float                # Current THR/USD
    heat_equivalent_thr: float          # Energy value in THR
    
    # Total incentive
    base_mining_reward: float           # 8 THR (Phase C5)
    heat_bonus_reward: float            # + heat bonus
    total_reward: float                 # Combined
    
    timestamp: str = ""
    
    def calculate_total_reward(self) -> float:
        """Calculate total miner reward: base + heat bonus"""
        return round(self.base_mining_reward + self.heat_bonus_reward, 6)
```

### 4. Energy Conversion Economics

```python
class EnergyConverter:
    """Convert recovered heat to economic value"""
    
    # Reference: Global energy markets (2024)
    ENERGY_PRICE_USD_PER_KWH = {
        "industrial": 0.08,              # Industrial average
        "commercial": 0.12,              # Commercial rate
        "residential": 0.15,             # Residential rate
        "peak": 0.25,                    # Peak pricing
    }
    
    # Conversion factors
    JOULES_PER_KWH = 3_600_000
    BTU_PER_JOULE = 0.000947817
    
    @staticmethod
    def joules_to_kwh(joules: float) -> float:
        """Convert joules to kilowatt-hours"""
        return joules / EnergyConverter.JOULES_PER_KWH
    
    @staticmethod
    def joules_to_btu(joules: float) -> float:
        """Convert joules to BTU"""
        return joules * EnergyConverter.BTU_PER_JOULE
    
    @staticmethod
    def estimate_energy_value(
        kwh_recovered: float,
        market_segment: str = "industrial"
    ) -> float:
        """Estimate USD value of recovered energy"""
        price = EnergyConverter.ENERGY_PRICE_USD_PER_KWH.get(
            market_segment,
            EnergyConverter.ENERGY_PRICE_USD_PER_KWH["industrial"]
        )
        return round(kwh_recovered * price, 4)
    
    @staticmethod
    def energy_value_to_thr(
        energy_value_usd: float,
        thr_price_usd: float = 0.0001  # Default: 1 THR = 0.0001 BTC equivalent
    ) -> float:
        """Convert USD energy value to THR equivalent"""
        if thr_price_usd <= 0:
            return 0.0
        return round(energy_value_usd / thr_price_usd, 6)
```

### 5. Use Case Rewards

```python
class UseCase(Enum):
    """Heat recovery application types"""
    
    SPACE_HEATING = {
        "name": "Space Heating",
        "efficiency_bonus": 0.10,        # 10% bonus (reliable, stable)
        "seasonal_factor": 0.5,          # Varies by season
        "reliability": 0.95,              # 95% uptime expected
        "examples": ["warehouse", "greenhouse", "facility"]
    }
    
    GREENHOUSE = {
        "name": "Greenhouse Farming",
        "efficiency_bonus": 0.15,        # 15% bonus (high value)
        "seasonal_factor": 1.0,           # Year-round demand
        "reliability": 0.98,              # 98% uptime required
        "examples": ["tomato", "lettuce", "herbs", "flowers"]
    }
    
    LIVESTOCK = {
        "name": "Livestock Operations",
        "efficiency_bonus": 0.12,        # 12% bonus
        "seasonal_factor": 0.7,           # Varies by season
        "reliability": 0.90,              # 90% uptime
        "examples": ["dairy", "poultry", "swine"]
    }
    
    AQUACULTURE = {
        "name": "Fish Farming",
        "efficiency_bonus": 0.18,        # 18% bonus (specialized)
        "seasonal_factor": 1.0,           # Year-round
        "reliability": 0.99,              # 99% uptime (critical)
        "examples": ["tilapia", "salmon", "shrimp"]
    }
    
    DESALINATION = {
        "name": "Water Treatment",
        "efficiency_bonus": 0.20,        # 20% bonus (infrastructure)
        "seasonal_factor": 1.0,           # Year-round
        "reliability": 0.99,              # 99% uptime
        "examples": ["desalination", "purification"]
    }
```

---

## Phase 6 Features

### 1. Real-Time Metrics Reporting

```python
class IoTMetricsReporter:
    """IoT gateway for farm-to-blockchain heat reporting"""
    
    def __init__(self, farm_address: str):
        self.farm_address = farm_address
        self.metrics_buffer = []
        self.last_report_block = 0
    
    def report_heat_metrics(self, metrics: MinerHeatMetrics) -> str:
        """Submit heat metrics to blockchain"""
        # Verify metrics authenticity
        # Store on-chain or in mempool
        # Return transaction ID
        pass
    
    def calculate_tier(self, recovery_percentage: float) -> HeatRewardTier:
        """Determine reward tier based on recovery %"""
        for tier in HeatRewardTier:
            if (tier.recovery_min <= recovery_percentage <= tier.recovery_max):
                return tier
        return HeatRewardTier.TIER_1
    
    def get_reward_multiplier(
        self,
        recovery_pct: float,
        use_case: UseCase
    ) -> float:
        """Calculate total reward multiplier"""
        tier = self.calculate_tier(recovery_pct)
        use_case_bonus = use_case.efficiency_bonus
        return 1.0 + tier.bonus_percentage + use_case_bonus
```

### 2. Heat Reward Integration

```python
def calculate_mining_reward_with_heat(
    base_reward: float,                 # 8.0 THR from Phase C5
    heat_metrics: MinerHeatMetrics,
    energy_price_usd_per_kwh: float = 0.08,
    thr_price_usd: float = 0.0001
) -> HeatRewardPool:
    """Calculate total mining reward including heat bonus"""
    
    # 1. Determine tier
    tier = HeatRewardTier[
        f"TIER_{max(1, min(4, int(heat_metrics.recovery_percentage / 10)))}"
    ]
    
    # 2. Calculate heat bonus
    heat_bonus_pct = tier.bonus_percentage
    heat_bonus_thr = base_reward * heat_bonus_pct
    
    # 3. Calculate energy value
    energy_value_usd = EnergyConverter.estimate_energy_value(
        heat_metrics.heat_recovered_kwh,
        "industrial"
    )
    energy_value_thr = EnergyConverter.energy_value_to_thr(
        energy_value_usd,
        thr_price_usd
    )
    
    # 4. Apply use case bonus
    use_case_bonus = 0.10  # Example
    total_bonus_thr = heat_bonus_thr * (1 + use_case_bonus)
    
    return HeatRewardPool(
        miner_address=heat_metrics.miner_address,
        current_block_reward=base_reward,
        heat_recovery_kwh_day=heat_metrics.heat_recovered_kwh,
        heat_bonus_percentage=heat_bonus_pct,
        heat_bonus_amount=total_bonus_thr,
        energy_value_usd_per_kwh=energy_price_usd_per_kwh,
        heat_value_usd=energy_value_usd,
        thr_price_usd=thr_price_usd,
        heat_equivalent_thr=energy_value_thr,
        base_mining_reward=base_reward,
        heat_bonus_reward=total_bonus_thr,
        total_reward=base_reward + total_bonus_thr
    )
```

### 3. Farm Integration APIs

**Endpoint: POST /api/mining/heat-metrics**
```json
{
  "miner_address": "THR7c...",
  "device_type": "ASIC_S19",
  "device_count": 100,
  "power_consumption_watts": 50000,
  "ambient_temp_celsius": 15,
  "inlet_temp_celsius": 25,
  "outlet_temp_celsius": 55,
  "airflow_cfm": 10000,
  "heat_recovered_joules": 180000000,
  "heat_recovered_kwh": 50,
  "pue_ratio": 1.15,
  "recovery_percentage": 18.5,
  "farm_location": "EU-GR-01",
  "use_case": "greenhouse"
}
```

**Response:**
```json
{
  "status": "accepted",
  "transaction_id": "heat_reward_tx_...",
  "metrics_id": "metric_...",
  "tier": "TIER_2",
  "reward_multiplier": 1.35,
  "heat_bonus_thr": 1.08,
  "estimated_daily_reward": 5.92,
  "energy_value_usd": 4.00,
  "next_report_in_blocks": 60
}
```

**Endpoint: GET /api/mining/heat-rewards/:address**
```json
{
  "miner_address": "THR7c...",
  "total_heat_recovered_kwh_day": 150,
  "current_tier": "TIER_3",
  "use_case": "greenhouse",
  "base_reward_per_block": 8.0,
  "heat_bonus_percentage": 0.25,
  "heat_bonus_per_block": 2.0,
  "total_reward_per_block": 10.0,
  "daily_estimated_thr": 14400,
  "monthly_estimated_thr": 432000,
  "energy_stats": {
    "kwh_daily": 150,
    "kwh_monthly": 4500,
    "usd_value_daily": 36.00,
    "usd_value_monthly": 1080.00
  }
}
```

---

## Economic Model

### Heat Bonus Scaling

```
Recovery %  | Tier    | Bonus | Example Daily
0-5%        | TIER_1  | 5%    | 0.40 THR extra
5-10%       | TIER_1  | 5%    | 0.40 THR extra
10-15%      | TIER_2  | 15%   | 1.20 THR extra
15-25%      | TIER_3  | 25%   | 2.00 THR extra
25%+        | TIER_4  | 40%   | 3.20 THR extra
```

### Example Economics

```
SCENARIO: 100 ASIC S19 miners, 18% heat recovery, greenhouse

Base Reward (Phase C5):
├─ 100 devices × 8 THR/block × 360 blocks/day
├─ = 288,000 THR/day
└─ = 8.64M THR/month

Heat Recovery Bonus (TIER_2 + Greenhouse):
├─ 18% recovery × 15% bonus + 15% use case bonus
├─ = 288,000 × 0.30 = 86,400 THR/day bonus
└─ = 2.59M THR/month bonus

Energy Value (50 kWh/day captured):
├─ 50 kWh × $0.08/kWh × 30 days
├─ = $120/month recovered energy value
└─ = 12,000 THR equivalent (at 0.0001 BTC price)

TOTAL MONTHLY:
├─ Mining rewards: 8.64M THR
├─ Heat bonuses: 2.59M THR
└─ TOTAL: 11.23M THR (26% increase from heat)
```

---

## Implementation Roadmap

### Phase 6A: Software Framework (Months 1-2)
- [ ] Heat metrics data structures
- [ ] Reward calculation engine
- [ ] Energy converter utilities
- [ ] Farm integration APIs
- [ ] Real-time dashboard

### Phase 6B: Farm Onboarding (Months 2-3)
- [ ] IoT gateway templates
- [ ] Hardware integration examples (no actual hardware)
- [ ] Metrics validation & verification
- [ ] Tier qualification testing

### Phase 6C: Incentive Launch (Months 3-6)
- [ ] Enable heat metrics in live network
- [ ] Begin distributing heat bonuses
- [ ] Monitor efficiency improvements
- [ ] Iterate on tier thresholds

### Phase 6D: Advanced Features (Months 6+)
- [ ] Predictive energy pricing
- [ ] AI-optimized heat scheduling
- [ ] Carbon offset certificates
- [ ] Farm reputation scoring

---

## Integration with Phase C5

```
MINING REWARD CALCULATION:

Base Reward (Phase C5)
        ↓
    8 THR/block
        ↓
   Halving Schedule (1,312,500 blocks)
        ↓
Distribution Split
├─ 80% to Miner (6.4 THR)
├─ 10% to AI Pool (0.8 THR)
├─ 5% to Full Nodes (0.4 THR)
└─ 5% to Ecosystem (0.4 THR)
        ↓
    Miner receives 6.4 THR
        ↓
    + Heat Metrics Bonus (Phase 6)
        ↓
    Heat Tier determines bonus %
    (5% - 40% additional)
        ↓
    FINAL MINER REWARD: 6.4 - 8.96 THR per block
```

---

## Success Metrics (Phase 6)

By end of Year 2:

| Metric | Target |
|--------|--------|
| Participating farms | 100+ |
| Total heat recovery | 500+ kWh/day |
| Average tier | TIER_2+ |
| Miner reward increase | 20-30% |
| Energy value realized | $50K+/month |
| Network hashpower | 2x+ from heat incentive |

---

## Technical Notes

- **Software-Only:** No actual temperature sensors or hardware required for MVP
- **Simulated Metrics:** Farms can submit test metrics for validation
- **Flexible Integration:** Works with any mining device type (ASIC, GPU, CPU)
- **Extensible:** Easy to add new use cases and tier thresholds
- **Privacy:** Farm location optional, uses geo-codes, not GPS
- **Verification:** Metrics signed by farm operator, immutable audit trail

---

## Files to Create

```
├── iot_heat_metrics.py           # Core data structures
├── energy_converter.py           # Economics calculations
├── heat_reward_engine.py         # Reward logic
├── farm_integration.py           # API endpoints
├── templates/heat_dashboard.html # Real-time UI
└── tests/test_heat_rewards.py   # Unit tests
```

---

**Phase 6 Status:** Design Complete ✅
**Next Step:** Implementation
