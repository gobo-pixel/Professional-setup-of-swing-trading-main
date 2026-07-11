"""
Institutional Market Scanner - Production Version
Synchronized with WiredOrchestrator Contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import pandas as pd

from core.logger import get_logger

# Fixed Correct Class Imports
from data.market_data import MarketData
from features.feature_engineering import FeatureEngineeringEngine
from strategy.buy_strategy import BuyStrategyEngine
from strategy.sell_strategy import SellStrategyEngine
from strategy.buy_scoring import BuyScoringEngine
from strategy.sell_scoring import SellScoringEngine
from strategy.buy_probability import BuyProbabilityEngine
from strategy.sell_probability import SellProbabilityEngine
from decision.decision_engine import DecisionEngine
from decision.validation_engine import ValidationEngine
from risk.risk_manager import RiskManager
from risk.position_sizing import PositionSizingEngine
from risk.portfolio_rules import PortfolioRulesEngine
from fundamental.fundamental import FundamentalEngine
from news.sentiment_engine import SentimentEngine
from market.market_regime import MarketRegimeEngine

logger = get_logger(__name__)


@dataclass(slots=True)
class ScanResult:
    symbol: str
    action: str
    score: float
    probability: float
    confidence: float
    ranking: float
    position_size: int
    portfolio_allowed: bool
    diagnostics: dict[str, Any] = field(default_factory=dict)


class MarketScanner:
    """
    Master Scanner - Handles final order generation, ranking,
    and session-wide asset analytics for the Orchestrator.
    """

    def __init__(self):
        # Professional Standard: Use the actual Data Engine for pipeline management, not a single raw dataclass model
        try:
            from data.data_engine import DataEngine
            self.data_engine = DataEngine()
        except ImportError:
            self.data_engine = None
            logger.warning("DataEngine could not be imported. Scanner will rely on direct data injection parameters.")

        self.features = FeatureEngineeringEngine()
        self.buy_strat = BuyStrategyEngine()
        self.sell_strat = SellStrategyEngine()
        self.buy_score = BuyScoringEngine()
        self.sell_score = SellScoringEngine()
        self.buy_prob = BuyProbabilityEngine()
        self.sell_prob = SellProbabilityEngine()
        self.decision_engine = DecisionEngine()
        self.validation = ValidationEngine()
        self.risk = RiskManager()
        self.sizer = PositionSizingEngine()
        self.rules = PortfolioRulesEngine()
        self.fundamental = FundamentalEngine()
        self.sentiment = SentimentEngine()
        self.regime = MarketRegimeEngine()

        logger.info("Market Scanner Engine initialized under professional pipeline contracts.")

    def prepare_orders(
        self, decision: Any, signals: dict[str, Any], portfolio: dict[str, Any]
    ) -> list[ScanResult]:
        """
        Hard entrypoint matching the exact call inside orchestrator.py (Step 7).
        Processes decision signals, calculates sizing, applies portfolio rules,
        and ranks candidates.
        """
        logger.info(
            "Orchestrator contract callback: Preparing and ranking market orders."
        )

        # Fallback to general scanner loop if orchestration context needs raw symbols extraction
        symbols = (
            list(signals.get("buy", {}).keys())
            if isinstance(signals.get("buy"), dict)
            else []
        )
        if not symbols:
            return []

        # Dummy/Mock state matching for global evaluation criteria
        broker_status = {"status": "ONLINE"}
        market_state = {"max_trade_candidates": 20, "max_watchlist": 50}

        return self.scan_symbols(
            symbols=symbols,
            portfolio=portfolio,
            broker_status=broker_status,
            market_state=market_state,
        )

    def scan_symbol(
        self,
        symbol: str,
        portfolio: dict[str, Any],
        broker_status: dict[str, Any],
        market_state: dict[str, Any],
    ) -> ScanResult:
        logger.info("Scanning asset node: %s", symbol)
        diagnostics = {}

        try:
            # 1. DOWNLOAD DATA (market OHLCV + fundamentals + news, in one bundle)
            if self.data_engine is None:
                raise ValueError("DataEngine unavailable; cannot fetch market data.")

            bundle = self.data_engine.fetch(symbol=symbol)
            dataframe = bundle.market
            if dataframe is None or dataframe.empty:
                raise ValueError("No market data received.")

            diagnostics["candles"] = len(dataframe)
            diagnostics["symbol"] = symbol

            # 2. FEATURE ENGINEERING
            dataframe = self.features.generate(dataframe)
            latest = dataframe.iloc[-1]
            diagnostics["latest_close"] = round(float(latest["close"]), 2)

            # 2b. FUNDAMENTALS / NEWS SENTIMENT / MARKET REGIME
            # These feed the strategy + scoring engines (news_score / market_score /
            # sector_score are 0-100 normalized inputs).
            fundamentals = bundle.fundamentals or {}

            news_items = self.sentiment.evaluate(bundle.news or [])
            if news_items:
                avg_impact = sum(i.get("impact_score", 0.0) for i in news_items) / len(
                    news_items
                )
                news_score = max(0.0, min(100.0, 50.0 + avg_impact * 50.0))
            else:
                news_score = 50.0  # neutral when no news available
            diagnostics["news_score"] = round(news_score, 2)

            dataframe = self.regime.evaluate(dataframe)
            latest = dataframe.iloc[-1]
            latest_regime = latest["market_regime"]
            market_score = {"BULL": 75.0, "SIDEWAYS": 50.0, "BEAR": 25.0}.get(
                latest_regime, 50.0
            )
            diagnostics["market_regime"] = latest_regime
            diagnostics["market_score"] = market_score

            # NOTE: Sector rotation needs a cross-symbol sector-index dataframe
            # (see market/sector_rotation.py) which this per-symbol scan does not
            # have available. Using a neutral placeholder until sector index data
            # is wired into DataEngine.
            sector_score = 50.0

            # NOTE: "breadth" (market breadth) is also a market-wide metric
            # (see market/market_breadth.py) that needs advance/decline data
            # across the whole market, not a single symbol. Using a neutral
            # placeholder for the same reason as sector_score above.
            dataframe["breadth"] = 50.0

            # 3. STRATEGIES EVALUATION
            buy_decision = self.buy_strat.evaluate(
                dataframe=dataframe,
                fundamentals=fundamentals,
                news_score=news_score,
                market_score=market_score,
                sector_score=sector_score,
            )
            sell_decision = self.sell_strat.evaluate(
                dataframe=dataframe,
                fundamentals=fundamentals,
                news_score=news_score,
                market_score=market_score,
                sector_score=sector_score,
            )
            diagnostics["buy_signal"] = buy_decision.action
            diagnostics["sell_signal"] = sell_decision.action

            # 4. SCORING MATRIX
            buy_score = self.buy_score.score(
                dataframe=dataframe,
                fundamentals=fundamentals,
                news_score=news_score,
                market_score=market_score,
                sector_score=sector_score,
            )
            sell_score = self.sell_score.score(
                dataframe=dataframe,
                fundamentals=fundamentals,
                news_score=news_score,
                market_score=market_score,
                sector_score=sector_score,
            )
            diagnostics["buy_score"] = round(buy_score.overall, 2)
            diagnostics["sell_score"] = round(sell_score.overall, 2)

            # 5. PROBABILITY ENGINES
            buy_probability = self.buy_prob.evaluate(score=buy_score)
            sell_probability = self.sell_prob.evaluate(score=sell_score)
            diagnostics["buy_probability"] = round(buy_probability.win_probability, 2)
            diagnostics["sell_probability"] = round(
                sell_probability.success_probability, 2
            )

            # 6. DECISION ENGINE
            final_decision = self.decision_engine.evaluate(
                buy_decision=buy_decision,
                sell_decision=sell_decision,
                buy_score=buy_score,
                sell_score=sell_score,
                buy_probability=buy_probability,
                sell_probability=sell_probability,
            )
            diagnostics["decision"] = final_decision.action
            diagnostics["ranking"] = round(final_decision.ranking, 2)
            diagnostics["confidence"] = round(final_decision.confidence, 2)

            # 7. VALIDATION ENGINE
            validation = self.validation.validate(
                decision=final_decision,
                dataframe=dataframe,
                portfolio=portfolio,
                broker_status=broker_status,
                market_state=market_state,
            )
            diagnostics["validation_passed"] = validation.passed
            diagnostics["validation_action"] = validation.action
            diagnostics["validation_warnings"] = len(validation.warnings)

            if not validation.passed:
                logger.info("%s rejected by Validation Engine.", symbol)

            # 8. RISK MANAGER
            risk_result = self.risk.evaluate(
                validation=validation,
                decision=final_decision,
                dataframe=dataframe,
                portfolio=portfolio,
                market=market_state,
            )
            diagnostics["risk_safe"] = risk_result.safe
            diagnostics["risk_grade"] = risk_result.risk_grade
            diagnostics["total_risk"] = round(risk_result.total_risk, 2)

            # 9. POSITION SIZING
            position_result = self.sizer.calculate(
                decision=final_decision,
                validation=validation,
                risk=risk_result,
                dataframe=dataframe,
                portfolio=portfolio,
            )
            diagnostics["quantity"] = position_result.quantity
            diagnostics["position_value"] = round(position_result.position_value, 2)
            diagnostics["allocation"] = round(position_result.allocation_percent, 4)

            # 10. PORTFOLIO RULES
            portfolio_result = self.rules.evaluate(
                decision=final_decision,
                validation=validation,
                risk=risk_result,
                sizing=position_result,
                portfolio=portfolio,
            )
            diagnostics["portfolio_allowed"] = portfolio_result.allowed
            diagnostics["portfolio_score"] = round(portfolio_result.portfolio_score, 2)

            # RESOLVE FINAL SCORES
            if final_decision.action == "BUY":
                final_score = final_decision.buy_score
                probability = final_decision.buy_probability
            elif final_decision.action == "SELL":
                final_score = final_decision.sell_score
                probability = final_decision.sell_probability
            else:
                final_score = 0.0
                probability = 0.0

            return ScanResult(
                symbol=symbol,
                action=final_decision.action,
                score=round(final_score, 2),
                probability=round(probability, 2),
                confidence=round(final_decision.confidence, 2),
                ranking=round(final_decision.ranking, 2),
                position_size=position_result.quantity,
                portfolio_allowed=portfolio_result.allowed,
                diagnostics=diagnostics,
            )

        except Exception as exc:
            logger.exception("Scanner compilation error for %s", symbol)
            diagnostics["error"] = str(exc)
            return ScanResult(
                symbol=symbol,
                action="ERROR",
                score=0.0,
                probability=0.0,
                confidence=0.0,
                ranking=0.0,
                position_size=0,
                portfolio_allowed=False,
                diagnostics=diagnostics,
            )

    def scan_symbols(
        self,
        symbols: list[str],
        portfolio: dict[str, Any],
        broker_status: dict[str, Any],
        market_state: dict[str, Any],
    ) -> list[ScanResult]:
        logger.info("Starting scan pass of %d target nodes.", len(symbols))
        results: list[ScanResult] = []
        total = len(symbols)

        for index, symbol in enumerate(symbols, start=1):
            logger.info("[%d/%d] Sizing target context: %s", index, total, symbol)
            result = self.scan_symbol(
                symbol=symbol,
                portfolio=portfolio,
                broker_status=broker_status,
                market_state=market_state,
            )
            results.append(result)

        valid_results = [r for r in results if r.action != "ERROR"]
        executable_results = [
            r
            for r in valid_results
            if r.portfolio_allowed and r.action in ("BUY", "SELL")
        ]

        # Rank Results top-down
        executable_results.sort(
            key=lambda r: (r.ranking, r.confidence, r.score, r.probability),
            reverse=True,
        )

        for rank, result in enumerate(executable_results, start=1):
            result.diagnostics["rank"] = rank
            result.diagnostics["scanner_score"] = round(
                (
                    result.ranking * 0.40
                    + result.confidence * 0.30
                    + result.score * 0.20
                    + result.probability * 0.10
                ),
                2,
            )

        max_trade_candidates = int(market_state.get("max_trade_candidates", 20))
        return executable_results[:max_trade_candidates]

    @staticmethod
    def export_dataframe(results: list[ScanResult]) -> pd.DataFrame:
        rows = [
            {
                "Symbol": r.symbol,
                "Action": r.action,
                "Score": round(r.score, 2),
                "Probability": round(r.probability, 2),
                "Confidence": round(r.confidence, 2),
                "Ranking": round(r.ranking, 2),
                "Position": r.position_size,
                "Portfolio": r.portfolio_allowed,
            }
            for r in results
        ]
        return pd.DataFrame(rows)


# Alias assignment for orchestrator import fallback safety mapping
Scanner = MarketScanner
