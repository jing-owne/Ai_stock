"""
底部反弹策略 (v2.6.5 合并版)

= rsi_oversold + bottom_rebound 合并

合并逻辑 — 三层底部确认:
1. RSI超卖检测: RSI(14) < 35 + 今日放量反弹 → +30分
2. 日线拐头: MA5拐头向上(近3日SMA5斜率转正) → +30分
3. 多周期确认: 周线多头排列 + 月线MACD强势 → +40分

总分 = 三层独立评分 → 最高100
"""
from typing import List, Dict, Any
import logging
import numpy as np

from ..base import BaseStrategy
from ...core.types import StockData, ScanResult, StrategyType
from ...core.indicators import calc_macd, resample_to_weekly, resample_to_monthly


class BottomReboundStrategy(BaseStrategy):
    """底部反弹策略 = RSI超卖 + 触底反弹 合并"""

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("AInvest.BottomRebound")
        self._indicators: Dict[str, Dict[str, float]] = {}
        self._kline_cache: Dict[str, list] = {}

    @property
    def name(self) -> str:
        return "底部反弹"

    @property
    def strategy_type(self) -> StrategyType:
        return StrategyType.BOTTOM_REBOUND

    def execute(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> List[ScanResult]:
        cfg = params.get("bottom_rebound", {}) if params else {}
        min_change = cfg.get("min_price_change", -5.0)
        min_amount = cfg.get("min_amount", 100_000_000)
        min_score = cfg.get("min_score", 30)

        results = []
        for stock in market_data:
            if stock.change_pct < min_change or stock.amount < min_amount:
                continue

            indicators = self._indicators.get(stock.symbol)
            if not indicators:
                continue

            total = 0
            origin = []

            # ── 层1: RSI超卖反弹 (原 rsi_oversold) ──
            rsi14 = indicators.get("rsi14", 50)
            volume_ratio = indicators.get("volume_ratio", 1.0)
            pos_20d = indicators.get("position_20d", 50)

            if rsi14 < 35 and volume_ratio >= 1.3 and pos_20d < 30:
                # RSI越低分越高: RSI=20→30分, RSI=35→15分
                rsi_score = max(0, (35 - rsi14) / 15 * 30)
                total += rsi_score
                origin.append(f"RSI超卖({rsi14:.0f})")

            # ── 层2: 日线MA5拐头向上 ──
            if indicators.get("ma5_turning_up"):
                total += 30
                origin.append("日线拐头")

            # ── 层3: 多周期确认 ──
            kline_list = self._kline_cache.get(stock.symbol)
            if kline_list and len(kline_list) >= 132:
                close_arr = np.array([k.close for k in kline_list])

                # 周线多头排列
                weekly_close = resample_to_weekly(close_arr)
                if len(weekly_close) >= 20:
                    sma5_w = float(np.mean(weekly_close[-5:]))
                    sma10_w = float(np.mean(weekly_close[-10:]))
                    sma20_w = float(np.mean(weekly_close[-20:]))
                    weekly_bull = sma5_w > sma10_w > sma20_w

                    # 月线MACD
                    monthly_close = resample_to_monthly(close_arr)
                    if len(monthly_close) >= 35:
                        macd_data = calc_macd(monthly_close)
                        macd_hist = macd_data["macd"][-1]
                        macd_strong = not np.isnan(macd_hist) and macd_hist > 0.618

                        if weekly_bull and macd_strong:
                            total += 40
                            origin.append("周线多头+月线MACD强")
                        elif weekly_bull:
                            total += 20
                            origin.append("周线多头")
                        elif macd_strong:
                            total += 20
                            origin.append("月线MACD强")

            total = round(min(total, 100), 1)
            if total < min_score:
                continue

            signals = []
            sfx = "「底部」"
            if rsi14 < 35:
                signals.append(f"RSI超卖({rsi14:.0f})" + sfx)
            if indicators.get("ma5_turning_up"):
                signals.append("日线拐头向上" + sfx)
            if "周线多头" in str(origin):
                signals.append("周线多头排列" + sfx)
            if "月线MACD强" in str(origin):
                signals.append("月线MACD强势" + sfx)
            if pos_20d < 30:
                signals.append("极端低位" + sfx)

            results.append(ScanResult(
                symbol=stock.symbol,
                name=stock.name,
                strategy=StrategyType.BOTTOM_REBOUND,
                score=total,
                signals=signals,
                data=stock,
                metadata={
                    "rsi14": round(rsi14, 1),
                    "volume_ratio": round(volume_ratio, 2),
                    "position_20d": round(pos_20d, 1),
                    "origin": origin,
                }
            ))

        results.sort(key=lambda x: x.score, reverse=True)
        return results
