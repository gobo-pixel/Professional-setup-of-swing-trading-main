"""
WIRED ORCHESTRATOR (PRODUCTION FLOW)
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import time

from core.logger import get_logger
from data.data_engine import DataEngine
from data.watchlist import WatchlistManager
from features.feature_engineering import FeatureEngineeringEngine
from market.market_regime import MarketRegimeEngine
from strategy.buy_strategy import BuyStrategyEngine
from strategy.sell_strategy import SellStrategyEngine
from decision.decision_engine import DecisionEngine
from risk.risk_manager import RiskManager
from execution.scanner import MarketScanner
from execution.broker import BrokerEngine, OrderRequest
from execution.tracker import PositionTracker
from portfolio.portfolio import PortfolioEngine, PortfolioState
from analytics.analytics import AnalyticsEngine
from output.report_generator import ReportGenerator

logger = get_logger(__name__)


@dataclass
class OrchestratorContext:
    mode: str
    cycle_id: int = 0
    timestamp: float = 0.0
    last_data: Any = None
    last_features: Any = None
    last_signals: Any = None
    last_decision: Any = None
    last_risk: Any = None
    last_execution: Any = None
    last_portfolio: Dict[str, Any] = None
    last_analytics: Any = None


class WiredOrchestrator:
    def __init__(self, mode: str = "BACKTEST"):
        self.mode = mode
        self.data_engine = DataEngine()
        self.feature_engine = FeatureEngineeringEngine()
        self.market = MarketRegimeEngine()
        self.buy_strategy = BuyStrategyEngine()
        self.sell_strategy = SellStrategyEngine()
        self.decision_engine = DecisionEngine()
        self.risk_engine = RiskManager()
        self.scanner = MarketScanner()
        self.broker = BrokerEngine()
        self.portfolio = PortfolioEngine(
            state=PortfolioState(total_capital=100000.0, available_capital=100000.0)
        )
        self.analytics = AnalyticsEngine()
        self.tracker = PositionTracker()
        self.context = OrchestratorContext(mode=mode)
        logger.info(f"WIRED ORCHESTRATOR initialized in {mode} mode")

    def run_cycle(self, symbols: list[str], portfolio_state: Any) -> OrchestratorContext:
        self.context.cycle_id += 1
        
        # Scan
        scan_candidates = self.scanner.scan_symbols(
            symbols=symbols,
            portfolio=self.portfolio.snapshot(),
            broker_status={"status": "ONLINE"},
            market_state={"max_trade_candidates": 20}
        )
        self.context.last_signals = scan_candidates

        # Report Generation
        if scan_candidates:
            ReportGenerator.append_to_master_report(scan_candidates)
            logger.info("Report appended.")
            
        return self.context

    def shutdown(self) -> None:
        logger.info("Shutdown initiated")

def main():
    orchestrator = WiredOrchestrator(mode="BACKTEST")
    watchlist = WatchlistManager("storage/watchlist.json")
    symbols = watchlist.load()
    if symbols:
        orchestrator.run_cycle(symbols=symbols, portfolio_state={})

if __name__ == "__main__":
    main()
