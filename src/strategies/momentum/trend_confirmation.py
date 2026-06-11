"""
追涨确认信号 (Trend Confirmation Signal) v2.6.8

参考 hikyuu ContinuousRiseSignal 回测指标：
- RSI(14) > 55（强势动能）
- MA5 > MA10 > MA20（均线多头排列）
- Volume > MA5(volume)（量价配合）
- 连续上涨 >= 3天（趋势一致性）

4条件全部满足 → 高置信度追涨信号
与 RSI超卖(抄底)方向相反，构成「低吸+追涨」双翼策略
"""
from typing import List, Dict, Any
import logging

from ..base import BaseStrategy
from ...core.types import StockData, ScanResult, StrategyType


class TrendConfirmationStrategy(BaseStrategy):
    """追涨确认信号 — 动量确认型策略"""

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("AInvest.TrendConfirmation")

    @property
    def name(self) -> str:
        return "追涨确认"

    @property
    def strategy_type(self) -> StrategyType:
        return StrategyType.TREND_CONFIRMATION

    def execute(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> List[ScanResult]:
        cfg = params.get("trend_confirmation", {}) if params else {}
        min_consecutive = cfg.get("min_consecutive_up", 3)
        min_rsi = cfg.get("min_rsi", 55)
        min_change = cfg.get("min_price_change", 0.5)
        max_change = cfg.get("max_price_change", 7.0)
        min_amount = cfg.get("min_amount", 100_000_000)
        min_score = cfg.get("min_score", 20)

        results = []
        for stock in market_data:
            if stock.change_pct < min_change or stock.change_pct > max_change:
                continue
            if stock.amount < min_amount:
                continue

            indicators = getattr(self, '_indicators', {}).get(stock.symbol)
            if not indicators:
                continue

            # ── 4条件确认 ──
            conditions_met = 0
            details = []

            # 条件1: RSI强势 (核心指标，来自hikyuu)
            rsi14 = indicators.get("rsi14", 50)
            if rsi14 > min_rsi:
                conditions_met += 1
                details.append(f"RSI={rsi14:.0f}")

            # 条件2: 均线多头排列 (来自hikyuu MA5>MA10>MA20)
            ma_bullish = indicators.get("ma_bullish_align", False)
            if ma_bullish:
                conditions_met += 1
                details.append("均线多头")

            # 条件3: 放量配合 (来自hikyuu Vol > MA5(Vol))
            vol_ratio = indicators.get("volume_ratio", 1.0)
            if vol_ratio > 1.0:
                conditions_met += 1
                details.append(f"放量{vol_ratio:.1f}x")

            # 条件4: 连续上涨 (来自hikyuu 连续N日上涨≥1%/天)
            consecutive_up = indicators.get("consecutive_up", 0)
            if consecutive_up >= min_consecutive:
                conditions_met += 1
                details.append(f"连涨{consecutive_up}日")

            if conditions_met < 2:
                continue

            # ── 评分 ──
            if conditions_met == 4:
                score = 60  # 满条件满分
            elif conditions_met == 3:
                score = 40
            else:  # 2
                score = 20

            # RSI在55-70区间加分（不过热）
            if 55 < rsi14 <= 70:
                score += 10

            # 量比适中加分
            if 1.2 <= vol_ratio <= 3.0:
                score += 5

            # 位置不过高加分
            pos_20d = indicators.get("position_20d", 50)
            if 30 <= pos_20d <= 70:
                score += 5

            score = min(round(score, 1), 80)

            if score < min_score:
                continue

            # ── 信号 ──
            signals = []
            sfx = "「追涨确认」"
            if conditions_met == 4:
                signals.append(f"4条件共振{sfx}")
            else:
                signals.append(f"{conditions_met}/4条件{sfx}")
            if rsi14 > 55:
                signals.append(f"RSI强势({rsi14:.0f})")
            if ma_bullish:
                signals.append("均线多头排列")
            if consecutive_up >= min_consecutive:
                signals.append(f"连涨{consecutive_up}日")

            results.append(ScanResult(
                symbol=stock.symbol,
                name=stock.name,
                strategy=StrategyType.TREND_CONFIRMATION,
                score=score,
                signals=signals,
                data=stock,
                metadata={
                    "conditions_met": conditions_met,
                    "rsi14": round(rsi14, 1),
                    "vol_ratio": round(vol_ratio, 2),
                    "consecutive_up": consecutive_up,
                    "ma_bullish": ma_bullish,
                    "position_20d": round(pos_20d, 1),
                }
            ))

        results.sort(key=lambda x: x.score, reverse=True)
        self.logger.info(f"追涨确认: {len(results)} 只标的")
        return results
