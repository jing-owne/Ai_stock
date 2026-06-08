"""
AI技术面策略

使用真实技术指标计算形态评分和趋势评分，
K线不可用时降级为行情估算。
"""
from typing import List, Dict, Any
import logging

from ..base import BaseStrategy
from ...core.types import StockData, ScanResult, StrategyType
from ...core.indicators import calc_pattern_score, calc_trend_score


class AITechnicalStrategy(BaseStrategy):
    """AI技术面策略"""

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("AInvest.AITechnical")
        self._indicators: Dict[str, Dict[str, float]] = {}
        self._kline_available: bool = True

    @property
    def name(self) -> str:
        return "AI技术面"

    @property
    def strategy_type(self) -> StrategyType:
        return StrategyType.AI_TECHNICAL

    def execute(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> List[ScanResult]:
        cfg = params.get("ai_technical", {}) if params else {}
        threshold = cfg.get("pattern_threshold", 0.75) * 100

        results = []
        for stock in market_data:
            indicators = self._indicators.get(stock.symbol)
            if not indicators:
                if not self._kline_available:
                    est_score = 50 + min(stock.change_pct * 3, 20) + min(stock.amount / 5e9 * 10, 15)
                    if est_score >= threshold:
                        results.append(ScanResult(
                            symbol=stock.symbol,
                            name=stock.name,
                            strategy=StrategyType.AI_TECHNICAL,
                            score=round(est_score, 1),
                            signals=["行情估算(无K线)"],
                            data=stock,
                            metadata={"note": "K线不可用，降级为行情估算"}
                        ))
                continue

            volume_ratio = indicators.get("volume_ratio", 1.0)
            pattern_score = calc_pattern_score(indicators, volume_ratio)
            trend_score = calc_trend_score(indicators)

            pattern_score = min(pattern_score, 100)
            trend_score = min(trend_score, 100)
            total_score = pattern_score * 0.5 + trend_score * 0.5

            if total_score < threshold:
                continue

            signals = []
            sfx = "「AI技术」"
            if pattern_score >= 85:
                signals.append("AI形态突破" + sfx)
            elif pattern_score >= 75:
                signals.append("AI形态良好" + sfx)
            if trend_score >= 80:
                signals.append("上升趋势确认" + sfx)
            if indicators.get("macd_golden_cross"):
                signals.append("MACD金叉" + sfx)

            results.append(ScanResult(
                symbol=stock.symbol,
                name=stock.name,
                strategy=StrategyType.AI_TECHNICAL,
                score=round(total_score, 1),
                signals=signals,
                data=stock,
                metadata={
                    "pattern_score": round(pattern_score, 1),
                    "trend_score": round(trend_score, 1),
                    "rsi14": round(indicators.get("rsi14", 0), 1),
                    "volume_ratio": round(volume_ratio, 2),
                }
            ))

        results.sort(key=lambda x: x.score, reverse=True)
        return results
