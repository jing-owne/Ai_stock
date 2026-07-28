"""
放量突破策略 (v2.6.5 合并版)

= volume_surge + new_high_break 合并

合并后逻辑:
1. 放量检测: 5日均量比 >= 1.3，使用真实K线计算
2. 突破检测: 突破20日/60日新高 或 低位放量上涨
3. 防套过滤: 高位放量、连续上涨过多、振幅过大 → 过滤
4. 评分: 量比30% + 突破40% + 涨幅20% + 成交额10%
"""
from typing import List, Dict, Any, Optional
import logging
import numpy as np

from ..base import BaseStrategy
from ...core.types import StockData, ScanResult, StrategyType


class VolumeBreakoutStrategy(BaseStrategy):
    """放量突破策略 = 放量上涨 + 突破前高 合并"""

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("AInvest.VolumeBreakout")
        # 共享缓存（由composite注入）
        self._indicators: Dict[str, Dict[str, float]] = {}
        self._kline_available: bool = True

    @property
    def name(self) -> str:
        return "放量突破"

    @property
    def strategy_type(self) -> StrategyType:
        return StrategyType.VOLUME_BREAKOUT

    def _calculate_score(self, volume_ratio: float, change_pct: float, params: Dict[str, Any]) -> float:
        """Backward-compatible score helper used by existing unit tests."""
        min_volume_ratio = params.get("min_volume_ratio", 1.3)
        min_change = params.get("min_price_change", -5.0)
        if volume_ratio < min_volume_ratio or change_pct < min_change:
            return 0.0
        volume_score = min(volume_ratio / max(min_volume_ratio, 0.1) * 35, 45)
        change_score = min(max(change_pct, 0) * 5, 35)
        base_score = 20
        return round(min(base_score + volume_score + change_score, 100), 1)

    def execute(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> List[ScanResult]:
        cfg = params.get("volume_breakout", {}) or params or {}
        min_volume_ratio = cfg.get("min_volume_ratio", 1.3)
        min_change = cfg.get("min_price_change", -5.0)
        max_change = cfg.get("max_price_change", 7.0)
        min_amount = cfg.get("min_amount", 100_000_000)
        max_consecutive_up = cfg.get("max_consecutive_up", 10)
        max_position_20d = cfg.get("max_position_20d", 99)
        max_amplitude = cfg.get("max_amplitude", 15.0)

        results = []
        max_amount = max((s.amount for s in market_data), default=1)
        filtered_count = {"high_change": 0, "consecutive": 0, "position": 0, "amplitude": 0}

        for stock in market_data:
            if stock.change_pct < min_change or stock.amount < min_amount:
                continue

            indicators = self._indicators.get(stock.symbol)
            if not indicators:
                continue

            volume_ratio = indicators.get("volume_ratio", 1.0)
            if volume_ratio < min_volume_ratio:
                continue

            # ── 位置感知的涨幅过滤 ──
            pos_20d = indicators.get("position_20d", 50)
            effective_max_change = max_change + 2.0 if pos_20d < 50 else max_change
            if stock.change_pct > effective_max_change:
                filtered_count["high_change"] += 1
                continue

            # ── 防套过滤 ──
            consecutive_up = indicators.get("consecutive_up", 0)
            if consecutive_up > max_consecutive_up and pos_20d > 60:
                filtered_count["consecutive"] += 1
                continue

            if pos_20d > max_position_20d:
                filtered_count["position"] += 1
                continue

            avg_amp = indicators.get("avg_amplitude_5d", 3)
            if avg_amp > max_amplitude and pos_20d > 50:
                filtered_count["amplitude"] += 1
                continue

            # ── 突破检测 (原 new_high_break 逻辑) ──
            breakout_20d = indicators.get("breakout_20d_high", False) or indicators.get("breakout_20d", False)
            breakout_60d = indicators.get("breakout_60d_high", False) or indicators.get("breakout_60d", False)
            is_breakout = breakout_20d or breakout_60d

            # ── 评分 ──
            volume_score = min(volume_ratio / 2.0 * 30, 30)
            breakthrough_score = 40 if is_breakout else (20 if pos_20d < 30 else 10)
            change_score = min(stock.change_pct * 5, 20)
            amount_score = min(stock.amount / max_amount * 10, 10)
            score = round(volume_score + breakthrough_score + change_score + amount_score, 1)

            # ── 信号 ──
            signals = []
            sfx = "「放量突破」"
            if is_breakout and breakout_60d:
                signals.append("突破60日新高" + sfx)
            elif is_breakout and breakout_20d:
                signals.append("突破20日新高" + sfx)
            if volume_ratio >= 3.0:
                signals.append("巨量突破" + sfx)
            elif volume_ratio >= 2.0:
                signals.append("温和放量" + sfx)
            if pos_20d < 30:
                signals.append("低位启动" + sfx)
            if stock.change_pct > max_change and pos_20d < 50:
                signals.append("低位涨停突破" + sfx)
            if stock.change_pct >= 7.0:
                signals.append("强势上涨" + sfx)

            results.append(ScanResult(
                symbol=stock.symbol,
                name=stock.name,
                strategy=StrategyType.VOLUME_BREAKOUT,
                score=score,
                signals=signals,
                data=stock,
                metadata={
                    "volume_ratio": round(volume_ratio, 2),
                    "is_breakout": is_breakout,
                    "position_20d": round(pos_20d, 1),
                }
            ))

        if any(v > 0 for v in filtered_count.values()):
            self.logger.debug(
                f"放量突破防套: 高涨幅={filtered_count['high_change']} "
                f"连涨={filtered_count['consecutive']} "
                f"高位={filtered_count['position']} 巨震={filtered_count['amplitude']}"
            )

        results.sort(key=lambda x: x.score, reverse=True)
        return results
