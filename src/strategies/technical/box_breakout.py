"""
箱体突破策略

检测长期横盘缩量后放量突破箱体上沿。
典型特征：30日股价在±15%区间震荡 + 放量突破上沿。
"""
from typing import List, Dict, Any
import logging

from ..base import BaseStrategy
from ...core.types import StockData, ScanResult, StrategyType
from ...core.indicators import calc_box_breakout_score


class BoxBreakoutStrategy(BaseStrategy):
    """箱体突破策略"""

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("AInvest.BoxBreakout")
        self._indicators: Dict[str, Dict[str, float]] = {}

    @property
    def name(self) -> str:
        return "箱体突破"

    @property
    def strategy_type(self) -> StrategyType:
        return StrategyType.BOX_BREAKOUT

    def execute(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> List[ScanResult]:
        cfg = params.get("box_breakout", {}) if params else {}
        max_box_range = cfg.get("max_box_range", 18.0)
        min_box_range = cfg.get("min_box_range", 3.0)
        min_breakout_pct = cfg.get("min_breakout_pct", -1.0)
        min_change = cfg.get("min_price_change", 2.0)
        max_change = cfg.get("max_price_change", 7.0)
        min_amount = cfg.get("min_amount", 100_000_000)
        min_score = cfg.get("min_score", 40)

        results = []
        for stock in market_data:
            if stock.change_pct < min_change or stock.change_pct > max_change:
                continue
            if stock.amount < min_amount:
                continue

            indicators = self._indicators.get(stock.symbol)
            if not indicators:
                continue

            box_range = indicators.get("box_range_30d")
            if box_range is None or box_range > max_box_range or box_range < min_box_range:
                continue

            breakout = indicators.get("breakout_pct", -5)
            if breakout < min_breakout_pct:
                continue

            score = calc_box_breakout_score(indicators)
            if score < min_score:
                continue

            signals = []
            sfx = "「箱体」"
            if breakout >= 0:
                signals.append("突破箱体上沿" + sfx)
            else:
                signals.append("接近箱体上沿" + sfx)
            if indicators.get("box_vol_ratio", 1.0) >= 1.5:
                signals.append("放量突破" + sfx)
            pos_20 = indicators.get("position_20d", 50)
            if pos_20 < 50:
                signals.append("低位启动" + sfx)
            if indicators.get("macd_golden_cross"):
                signals.append("MACD金叉" + sfx)

            results.append(ScanResult(
                symbol=stock.symbol,
                name=stock.name,
                strategy=StrategyType.BOX_BREAKOUT,
                score=round(score, 1),
                signals=signals,
                data=stock,
                metadata={
                    "box_range": round(box_range, 1),
                    "breakout_pct": round(breakout, 2),
                    "box_vol_ratio": round(indicators.get("box_vol_ratio", 1.0), 2),
                }
            ))

        results.sort(key=lambda x: x.score, reverse=True)
        self.logger.debug(f"箱体突破: {len(results)} 只")
        return results
