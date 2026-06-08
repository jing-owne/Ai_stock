"""
均线趋势策略 (v2.6.5 合并版)

= ma_divergence + sustained_uptrend 合并

合并逻辑 — 两级均线检测:
1. 短期均线 (MA5/MA10/MA20 粘合发散):
   - 过去20天MA频繁粘合(距离<5%) >= 3天
   - 当日MA5 > MA10 > MA20 多头排列
   - 评分: 0-70 (粘合度+排列+放量)

2. 长期均线 (MA20/MA60/MA120 多头排列):
   - close > MA20 > MA60 > MA120
   - 评分: 0-30 (趋势确认强加分)

总分 = 短期检测分 + 长期确认分 → 最高100
"""
from typing import List, Dict, Any
import logging

from ..base import BaseStrategy
from ...core.types import StockData, ScanResult, StrategyType


class MATrendStrategy(BaseStrategy):
    """均线趋势策略 = 均线发散 + 持续上涨 合并"""

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("AInvest.MATrend")
        self._indicators: Dict[str, Dict[str, float]] = {}

    @property
    def name(self) -> str:
        return "均线趋势"

    @property
    def strategy_type(self) -> StrategyType:
        return StrategyType.MA_TREND

    def execute(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> List[ScanResult]:
        cfg = params.get("ma_trend", {}) if params else {}
        max_convergence = cfg.get("max_convergence", 5.0)
        min_convergence_days = cfg.get("min_convergence_days", 3)
        min_change = cfg.get("min_price_change", 1.0)
        max_change = cfg.get("max_price_change", 7.0)
        min_amount = cfg.get("min_amount", 100_000_000)
        min_score = cfg.get("min_score", 35)

        results = []
        for stock in market_data:
            if stock.change_pct < min_change or stock.change_pct > max_change:
                continue
            if stock.amount < min_amount:
                continue

            indicators = self._indicators.get(stock.symbol)
            if not indicators:
                continue

            # ── 短期均线粘合发散检测 ──
            convergence = indicators.get("ma_convergence_20d")
            conv_days = indicators.get("ma_convergence_days", 0)
            short_term_ok = (
                convergence is not None
                and convergence <= max_convergence
                and conv_days >= min_convergence_days
            )

            # ── 长期均线多头检测 ──
            long_term_ok = indicators.get("sustained_uptrend", False)

            # ── 至少满足其中一个 ──
            if not short_term_ok and not long_term_ok:
                continue

            # ── 评分 ──
            score = 0
            origin = []

            if short_term_ok:
                # 粘合度分: 越粘合分越高 (5%→30分, 0%→70分)
                conv_score = max(0, 70 - (convergence / max_convergence * 70))
                # 多头排列加分
                if indicators.get("ma_bullish_align"):
                    conv_score = min(conv_score + 20, 70)
                # 放量配合
                vol_ratio = indicators.get("volume_ratio", 1.0)
                if vol_ratio >= 1.5:
                    conv_score = min(conv_score + 10, 70)
                score += conv_score
                origin.append("均线粘合发散")

            if long_term_ok:
                # 长期多头确认（比short_term分略低，但稳定）
                score += 30
                origin.append("长周期多头")

            score = round(min(score, 100), 1)
            if score < min_score:
                continue

            # ── 信号 ──
            signals = []
            sfx = "「均线」"
            if short_term_ok:
                if convergence < 2.0:
                    signals.append("均线高度粘合" + sfx)
                else:
                    signals.append("均线粘合" + sfx)
                if indicators.get("ma_bullish_align"):
                    signals.append("多头排列发散" + sfx)
            if long_term_ok:
                signals.append("长周期多头趋势" + sfx)
            if indicators.get("macd_golden_cross"):
                signals.append("MACD金叉" + sfx)
            pos_20 = indicators.get("position_20d", 50)
            if pos_20 < 50:
                signals.append("低位启动" + sfx)
            elif pos_20 < 70:
                signals.append("中位启动" + sfx)
            vol_ratio = indicators.get("volume_ratio", 1.0)
            if vol_ratio >= 1.5:
                signals.append("放量配合" + sfx)

            results.append(ScanResult(
                symbol=stock.symbol,
                name=stock.name,
                strategy=StrategyType.MA_TREND,
                score=score,
                signals=signals,
                data=stock,
                metadata={
                    "convergence": round(convergence, 2) if convergence else None,
                    "convergence_days": conv_days,
                    "short_term": short_term_ok,
                    "long_term": long_term_ok,
                    "origin": origin,
                }
            ))

        results.sort(key=lambda x: x.score, reverse=True)
        self.logger.debug(f"均线趋势: {len(results)} 只")
        return results
