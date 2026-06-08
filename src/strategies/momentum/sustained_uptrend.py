"""
持续上涨策略 (v2.6.5新增)

核心逻辑：
- 当日交易价格 > MA20 > MA60 > MA120
- 中长期均线多头排列，趋势健康
- 评分：满足条件 +10分
"""

from typing import List, Dict, Any
import logging

from ..base import BaseStrategy
from ...core.types import StockData, ScanResult, StrategyType
from ...core.indicators import calc_sustained_uptrend_score


class SustainedUptrendStrategy(BaseStrategy):
    """持续上涨策略"""

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("AInvest.SustainedUptrend")

    @property
    def name(self) -> str:
        return "持续上涨"

    @property
    def strategy_type(self) -> StrategyType:
        return StrategyType.SUSTAINED_UPTREND

    def execute(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> List[ScanResult]:
        cfg = params.get("sustained_uptrend", {}) if params else {}
        min_change = cfg.get("min_price_change", 0.3)
        max_change = cfg.get("max_price_change", 7.0)
        min_amount = cfg.get("min_amount", 100_000_000)

        results = []
        for stock in market_data:
            if stock.change_pct < min_change or stock.change_pct > max_change:
                continue
            if stock.amount < min_amount:
                continue

            # 从共享指标缓存获取
            indicators = getattr(self, '_indicators', {}).get(stock.symbol)
            if not indicators:
                continue

            score = calc_sustained_uptrend_score(indicators)
            if score <= 0:
                continue

            # 详细信号
            signals = []
            sfx = "「持续上涨」"
            signals.append("多头排列" + sfx)

            close_last = indicators.get("close_last") or 0
            sma20 = indicators.get("sma20", 0)
            sma60 = indicators.get("sma60", 0)
            sma120 = indicators.get("sma120", 0)

            if sma120 > 0:
                dist = round((close_last - sma120) / sma120 * 100, 1)
                signals.append(f"距MA120 +{dist}%" + sfx)

            results.append(ScanResult(
                symbol=stock.symbol,
                name=stock.name,
                strategy=StrategyType.SUSTAINED_UPTREND,
                score=score,
                signals=signals,
                data=stock,
                metadata={
                    "sma20": round(sma20, 2),
                    "sma60": round(sma60, 2),
                    "sma120": round(sma120, 2),
                }
            ))

        results.sort(key=lambda x: x.score, reverse=True)
        self.logger.info(f"持续上涨策略: {len(results)} 只标的")
        return results
