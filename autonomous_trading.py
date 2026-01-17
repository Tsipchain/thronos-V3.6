#!/usr/bin/env python3
"""
Thronos Autonomous Trading & Treasury Management
================================================
AI-powered autonomous trading and treasury management

Features:
- Automated liquidity management
- AMM pool optimization
- Treasury diversification
- Risk management
- Market making strategies
- Yield farming automation
- Portfolio rebalancing
- AI-driven trading decisions

Phase 6: AI Autonomy (Pythia)
Version: 5.0
"""

import os
import json
import time
import logging
import hashlib
import secrets
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Asset:
    """Treasury asset"""
    symbol: str
    balance: float
    value_usd: float
    allocation_percent: float
    target_allocation: float


@dataclass
class TradingStrategy:
    """Trading strategy configuration"""
    strategy_id: str
    name: str
    enabled: bool
    risk_level: str  # conservative, moderate, aggressive
    max_trade_size_usd: float
    stop_loss_percent: float
    take_profit_percent: float
    rebalance_threshold: float


@dataclass
class Trade:
    """Executed trade"""
    trade_id: str
    strategy_id: str
    timestamp: str
    trade_type: str  # buy, sell, swap, add_liquidity, remove_liquidity
    from_asset: str
    to_asset: str
    from_amount: float
    to_amount: float
    price: float
    fee: float
    reason: str
    profit_loss: float = 0.0
    status: str = "pending"  # pending, executed, failed


@dataclass
class TreasurySnapshot:
    """Treasury state snapshot"""
    timestamp: str
    total_value_usd: float
    assets: List[Asset]
    daily_pnl: float
    weekly_pnl: float
    monthly_pnl: float


class AutonomousTrading:
    """
    Autonomous Trading & Treasury Management System
    """

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)

        # Storage
        self.treasury_path = self.data_dir / "treasury.json"
        self.strategies_path = self.data_dir / "trading_strategies.json"
        self.trades_path = self.data_dir / "trades.jsonl"
        self.snapshots_path = self.data_dir / "treasury_snapshots.jsonl"

        # Configuration
        self.auto_trade_enabled = os.getenv("AUTO_TRADE_ENABLED", "false").lower() == "true"
        self.max_daily_trades = int(os.getenv("MAX_DAILY_TRADES", "10"))
        self.emergency_stop_loss = float(os.getenv("EMERGENCY_STOP_LOSS", "0.05"))  # 5%

        # State
        self.treasury: Dict[str, float] = {}
        self.strategies: Dict[str, TradingStrategy] = {}
        self.trades_today = 0
        self.last_trade_date = ""
        self.total_treasury_value_usd = 0.0

        # Load state
        self._load_treasury()
        self._load_strategies()
        self._initialize_default_strategies()

        # Try to load AI engine
        try:
            from ai_agent_service import ThronosAI
            self.ai_engine = ThronosAI()
            self.ai_available = True
            logger.info("🤖 AI trading engine loaded")
        except:
            self.ai_engine = None
            self.ai_available = False
            logger.warning("AI engine not available - using rule-based trading")

        logger.info("💰 Autonomous Trading System initialized")
        logger.info(f"   Auto-trade: {self.auto_trade_enabled}")
        logger.info(f"   Max trades/day: {self.max_daily_trades}")
        logger.info(f"   Treasury value: ${self.total_treasury_value_usd:,.2f}")

    def _load_treasury(self):
        """Load treasury state"""
        if not self.treasury_path.exists():
            # Initialize with default assets
            self.treasury = {
                'THR': 100000.0,
                'WBTC': 0.5,
                'L2E': 50000.0,
                'USD': 10000.0
            }
            self._save_treasury()
            return

        try:
            with open(self.treasury_path, 'r') as f:
                data = json.load(f)
                self.treasury = data.get('assets', {})
                self.total_treasury_value_usd = data.get('total_value_usd', 0.0)
        except Exception as e:
            logger.error(f"Error loading treasury: {e}")

    def _save_treasury(self):
        """Save treasury state"""
        try:
            data = {
                'assets': self.treasury,
                'total_value_usd': self.total_treasury_value_usd,
                'last_updated': datetime.utcnow().isoformat()
            }
            with open(self.treasury_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving treasury: {e}")

    def _load_strategies(self):
        """Load trading strategies"""
        if not self.strategies_path.exists():
            return

        try:
            with open(self.strategies_path, 'r') as f:
                data = json.load(f)
                self.strategies = {
                    sid: TradingStrategy(**sdata)
                    for sid, sdata in data.items()
                }
        except Exception as e:
            logger.error(f"Error loading strategies: {e}")

    def _save_strategies(self):
        """Save trading strategies"""
        try:
            data = {
                sid: asdict(strategy)
                for sid, strategy in self.strategies.items()
            }
            with open(self.strategies_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving strategies: {e}")

    def _log_trade(self, trade: Trade):
        """Log trade to file"""
        try:
            with open(self.trades_path, 'a') as f:
                f.write(json.dumps(asdict(trade)) + '\n')
        except Exception as e:
            logger.error(f"Error logging trade: {e}")

    def _log_snapshot(self, snapshot: TreasurySnapshot):
        """Log treasury snapshot"""
        try:
            with open(self.snapshots_path, 'a') as f:
                f.write(json.dumps(asdict(snapshot)) + '\n')
        except Exception as e:
            logger.error(f"Error logging snapshot: {e}")

    def _initialize_default_strategies(self):
        """Initialize default trading strategies"""
        if len(self.strategies) > 0:
            return

        default_strategies = [
            TradingStrategy(
                strategy_id="rebalance_conservative",
                name="Conservative Portfolio Rebalancing",
                enabled=True,
                risk_level="conservative",
                max_trade_size_usd=5000.0,
                stop_loss_percent=0.03,
                take_profit_percent=0.05,
                rebalance_threshold=0.10
            ),
            TradingStrategy(
                strategy_id="amm_optimization",
                name="AMM Pool Optimization",
                enabled=True,
                risk_level="moderate",
                max_trade_size_usd=10000.0,
                stop_loss_percent=0.05,
                take_profit_percent=0.10,
                rebalance_threshold=0.15
            ),
            TradingStrategy(
                strategy_id="yield_farming",
                name="Automated Yield Farming",
                enabled=False,
                risk_level="aggressive",
                max_trade_size_usd=20000.0,
                stop_loss_percent=0.10,
                take_profit_percent=0.20,
                rebalance_threshold=0.20
            )
        ]

        for strategy in default_strategies:
            self.strategies[strategy.strategy_id] = strategy

        self._save_strategies()
        logger.info(f"Initialized {len(default_strategies)} default strategies")

    # ========================================================================
    # PRICE ORACLE (Simulated)
    # ========================================================================

    def get_price(self, asset: str, quote: str = "USD") -> float:
        """Get current price of asset in quote currency"""
        # Simulated prices - in production, fetch from oracle
        prices = {
            'THR': 0.000030,  # THR/USD
            'WBTC': 45000.0,  # WBTC/USD
            'L2E': 0.00002,   # L2E/USD
            'USD': 1.0,       # USD/USD
        }

        asset_price = prices.get(asset, 0.0)
        quote_price = prices.get(quote, 1.0)

        if quote_price == 0:
            return 0.0

        return asset_price / quote_price

    def get_treasury_value(self) -> float:
        """Calculate total treasury value in USD"""
        total_usd = 0.0

        for asset, balance in self.treasury.items():
            price = self.get_price(asset, "USD")
            value = balance * price
            total_usd += value

        self.total_treasury_value_usd = total_usd
        return total_usd

    # ========================================================================
    # PORTFOLIO ANALYSIS
    # ========================================================================

    def get_asset_allocation(self) -> List[Asset]:
        """Get current asset allocation"""
        total_value = self.get_treasury_value()
        assets = []

        target_allocations = {
            'THR': 0.50,   # 50%
            'WBTC': 0.30,  # 30%
            'L2E': 0.15,   # 15%
            'USD': 0.05,   # 5%
        }

        for symbol, balance in self.treasury.items():
            price = self.get_price(symbol, "USD")
            value_usd = balance * price
            allocation = (value_usd / total_value * 100) if total_value > 0 else 0

            assets.append(Asset(
                symbol=symbol,
                balance=balance,
                value_usd=value_usd,
                allocation_percent=allocation,
                target_allocation=target_allocations.get(symbol, 0.0) * 100
            ))

        return assets

    def analyze_rebalancing_needs(self) -> List[Dict[str, Any]]:
        """Analyze if portfolio needs rebalancing"""
        logger.info("📊 Analyzing portfolio...")

        recommendations = []
        assets = self.get_asset_allocation()

        for asset in assets:
            diff = asset.allocation_percent - asset.target_allocation
            abs_diff = abs(diff)

            if abs_diff > 10:  # More than 10% deviation
                action = "SELL" if diff > 0 else "BUY"
                urgency = "HIGH" if abs_diff > 20 else "MEDIUM"

                recommendations.append({
                    'asset': asset.symbol,
                    'action': action,
                    'current_allocation': f"{asset.allocation_percent:.1f}%",
                    'target_allocation': f"{asset.target_allocation:.1f}%",
                    'deviation': f"{abs_diff:.1f}%",
                    'urgency': urgency,
                    'estimated_amount_usd': abs_diff / 100 * self.total_treasury_value_usd
                })

        logger.info(f"Found {len(recommendations)} rebalancing opportunities")
        return recommendations

    # ========================================================================
    # TRADING EXECUTION
    # ========================================================================

    def execute_swap(
        self,
        from_asset: str,
        to_asset: str,
        amount: float,
        reason: str = "Manual trade",
        strategy_id: str = "manual"
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Execute a token swap

        Returns: (success, message, trade_id)
        """
        logger.info(f"💱 Executing swap: {amount} {from_asset} → {to_asset}")

        # Check if we have enough balance
        if self.treasury.get(from_asset, 0) < amount:
            return False, f"Insufficient {from_asset} balance", None

        # Check daily trade limit
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if self.last_trade_date != today:
            self.trades_today = 0
            self.last_trade_date = today

        if self.trades_today >= self.max_daily_trades:
            return False, "Daily trade limit reached", None

        # Get prices
        from_price = self.get_price(from_asset, "USD")
        to_price = self.get_price(to_asset, "USD")

        if from_price == 0 or to_price == 0:
            return False, "Price data unavailable", None

        # Calculate amounts
        from_value_usd = amount * from_price
        fee_percent = 0.003  # 0.3% fee
        fee_usd = from_value_usd * fee_percent
        to_amount = (from_value_usd - fee_usd) / to_price

        # Create trade
        trade_id = f"trade_{int(time.time())}_{secrets.token_hex(4)}"

        trade = Trade(
            trade_id=trade_id,
            strategy_id=strategy_id,
            timestamp=datetime.utcnow().isoformat(),
            trade_type="swap",
            from_asset=from_asset,
            to_asset=to_asset,
            from_amount=amount,
            to_amount=to_amount,
            price=to_price / from_price,
            fee=fee_usd,
            reason=reason,
            status="executed"
        )

        # Update treasury
        self.treasury[from_asset] = self.treasury.get(from_asset, 0) - amount
        self.treasury[to_asset] = self.treasury.get(to_asset, 0) + to_amount

        self._save_treasury()
        self._log_trade(trade)

        self.trades_today += 1

        logger.info(f"✅ Swap executed: {trade_id}")
        logger.info(f"   Received: {to_amount:.6f} {to_asset}")
        logger.info(f"   Fee: ${fee_usd:.2f}")

        return True, f"Swap executed successfully. Trade ID: {trade_id}", trade_id

    def auto_rebalance(self, dry_run: bool = True) -> List[Trade]:
        """Automatically rebalance portfolio"""
        logger.info(f"🔄 Auto-rebalancing portfolio (dry_run={dry_run})...")

        if not self.auto_trade_enabled and not dry_run:
            logger.warning("Auto-trade is disabled")
            return []

        recommendations = self.analyze_rebalancing_needs()
        executed_trades = []

        for rec in recommendations:
            if rec['urgency'] != 'HIGH':
                continue  # Only execute high-urgency rebalancing

            strategy = self.strategies.get('rebalance_conservative')
            if not strategy or not strategy.enabled:
                continue

            # Determine trade
            if rec['action'] == 'SELL':
                from_asset = rec['asset']
                to_asset = 'USD'  # Sell to stablecoin
            else:  # BUY
                from_asset = 'USD'
                to_asset = rec['asset']

            # Calculate amount (limited by strategy max trade size)
            amount_usd = min(rec['estimated_amount_usd'], strategy.max_trade_size_usd)
            from_price = self.get_price(from_asset, "USD")

            if from_price == 0:
                continue

            amount = amount_usd / from_price

            if not dry_run:
                success, msg, trade_id = self.execute_swap(
                    from_asset=from_asset,
                    to_asset=to_asset,
                    amount=amount,
                    reason=f"Auto-rebalance: {rec['action']} {rec['asset']}",
                    strategy_id=strategy.strategy_id
                )

                if success:
                    logger.info(f"✅ Rebalancing trade executed: {trade_id}")
            else:
                logger.info(f"[DRY RUN] Would execute: {amount:.6f} {from_asset} → {to_asset}")

        return executed_trades

    # ========================================================================
    # AMM OPTIMIZATION
    # ========================================================================

    def optimize_amm_pools(self) -> List[Dict[str, Any]]:
        """Optimize AMM pool positions"""
        logger.info("⚡ Optimizing AMM pools...")

        optimizations = []

        # Example optimization: add liquidity to underfunded pools
        # In production, this would analyze actual AMM pools

        pools = [
            {'name': 'THR/WBTC', 'liquidity_usd': 50000, 'optimal_liquidity_usd': 100000},
            {'name': 'THR/L2E', 'liquidity_usd': 30000, 'optimal_liquidity_usd': 50000},
        ]

        for pool in pools:
            deficit = pool['optimal_liquidity_usd'] - pool['liquidity_usd']

            if deficit > 1000:  # More than $1000 deficit
                optimizations.append({
                    'pool': pool['name'],
                    'action': 'ADD_LIQUIDITY',
                    'amount_usd': deficit,
                    'reason': 'Insufficient liquidity',
                    'priority': 'HIGH' if deficit > 10000 else 'MEDIUM'
                })

        logger.info(f"Found {len(optimizations)} AMM optimization opportunities")
        return optimizations

    # ========================================================================
    # AI TRADING DECISIONS
    # ========================================================================

    def get_ai_trading_recommendation(self) -> Optional[Dict[str, Any]]:
        """Get AI-powered trading recommendation"""
        if not self.ai_available:
            return None

        try:
            # Prepare market context
            assets = self.get_asset_allocation()
            context = {
                'treasury_value_usd': self.total_treasury_value_usd,
                'assets': [asdict(a) for a in assets],
                'strategies': [asdict(s) for s in self.strategies.values()],
            }

            prompt = f"""Analyze this crypto treasury and provide trading recommendation:

{json.dumps(context, indent=2)}

Consider:
1. Portfolio balance
2. Market conditions
3. Risk management
4. Opportunity cost

Provide ONE specific, actionable recommendation."""

            response = self.ai_engine.generate_response(prompt)

            # Parse AI recommendation
            # In production, use structured output

            return {
                'recommendation': response.get('response', ''),
                'confidence': 0.75,
                'provider': response.get('provider', 'unknown')
            }

        except Exception as e:
            logger.error(f"AI recommendation error: {e}")
            return None

    # ========================================================================
    # STATISTICS & REPORTING
    # ========================================================================

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get trading performance statistics"""
        # Calculate from trade history
        # This is simplified - in production, calculate actual PnL

        return {
            'treasury_value_usd': self.total_treasury_value_usd,
            'daily_pnl': 250.0,  # Simulated
            'weekly_pnl': 1200.0,
            'monthly_pnl': 5000.0,
            'total_trades': self.trades_today,
            'auto_trade_enabled': self.auto_trade_enabled,
            'active_strategies': len([s for s in self.strategies.values() if s.enabled]),
        }

    def create_snapshot(self):
        """Create treasury snapshot"""
        assets = self.get_asset_allocation()
        stats = self.get_performance_stats()

        snapshot = TreasurySnapshot(
            timestamp=datetime.utcnow().isoformat(),
            total_value_usd=self.total_treasury_value_usd,
            assets=assets,
            daily_pnl=stats['daily_pnl'],
            weekly_pnl=stats['weekly_pnl'],
            monthly_pnl=stats['monthly_pnl']
        )

        self._log_snapshot(snapshot)
        return snapshot


def main():
    """Test the autonomous trading system"""
    print("💰 Thronos Autonomous Trading System\n")

    trading = AutonomousTrading()

    # Show treasury
    print("📊 Treasury Status:")
    assets = trading.get_asset_allocation()
    for asset in assets:
        print(f"  {asset.symbol}: {asset.balance:.4f} (${asset.value_usd:,.2f}) - {asset.allocation_percent:.1f}%")
    print(f"\n  Total Value: ${trading.total_treasury_value_usd:,.2f}\n")

    # Analyze rebalancing
    print("🔍 Rebalancing Analysis:")
    recommendations = trading.analyze_rebalancing_needs()
    for rec in recommendations:
        print(f"  [{rec['urgency']}] {rec['action']} {rec['asset']}")
        print(f"    Current: {rec['current_allocation']} → Target: {rec['target_allocation']}")
        print(f"    Amount: ${rec['estimated_amount_usd']:,.2f}\n")

    # Test swap (dry run)
    print("💱 Test Swap:")
    success, msg, trade_id = trading.execute_swap(
        from_asset="THR",
        to_asset="WBTC",
        amount=1000.0,
        reason="Test swap"
    )
    print(f"  {msg}\n")

    # Get AI recommendation
    print("🤖 AI Trading Recommendation:")
    ai_rec = trading.get_ai_trading_recommendation()
    if ai_rec:
        print(f"  {ai_rec['recommendation']}")
        print(f"  Confidence: {ai_rec['confidence']*100:.0f}%\n")

    # Performance stats
    print("📈 Performance Statistics:")
    stats = trading.get_performance_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
