"""
连续小阳吸筹策略 (v2.6.5新增)

核心逻辑：
- 检测连续3-7天小阳线（每日涨幅0.5%-3%）
- 累计涨幅2%-15%，显示主力缓慢吸筹
- 成交量温和放大配合
- 位置不过高（不是出货）

典型场景：主力悄悄建仓，每日控制涨幅不引起市场注意
"""
from typing import List, Dict, Any
import logging

from ..base import BaseStrategy
from ...core.types import StockData, ScanResult, StrategyType


class ConsecutivePositiveStrategy(BaseStrategy):
    """连续小阳吸筹策略"""

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("AInvest.ConsecutivePositive")

    @property
    def name(self) -> str:
        return "连续小阳吸筹"

    @property
    def strategy_type(self) -> StrategyType:
        return StrategyType.CONSECUTIVE_POSITIVE

    def execute(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> List[ScanResult]:
        cfg = params.get("consecutive_positive", {}) if params else {}
        min_days = cfg.get("min_consecutive_days", 3)
        max_days = cfg.get("max_consecutive_days", 7)
        max_daily = cfg.get("max_daily_change", 3.0)
        min_cumulative = cfg.get("min_cumulative_change", 2.0)
        max_cumulative = cfg.get("max_cumulative_change", 15.0)
        min_amount = cfg.get("min_amount", 100_000_000)
        min_score = cfg.get("min_score", 40)

        results = []
        for stock in market_data:
            # ── 基本筛选 ──
            if stock.amount < min_amount:
                continue
            if stock.change_pct <= 0:
                continue

            # ── 获取K线指标 ──
            indicators = getattr(self, '_indicators', {}).get(stock.symbol)
            if not indicators:
                continue

            # ── 连续阳线检测 ──
            consecutive_up = indicators.get("consecutive_up", 0)
            if consecutive_up < min_days or consecutive_up > max_days:
                continue

            # ── 累计涨幅检测 ──
            cumulative_change = indicators.get("cumulative_change_5d")
            if cumulative_change is None:
                continue
            if cumulative_change < min_cumulative or cumulative_change > max_cumulative:
                continue

            # ── 阳线质量检测 ──
            # 平均每日涨幅（不应该太大）
            avg_daily = cumulative_change / consecutive_up if consecutive_up > 0 else 0
            if avg_daily > max_daily:
                continue

            # ── 评分计算 ──
            score = 25  # 基础分

            # 连续天数分
            days_score = min((consecutive_up - min_days + 1) * 8, 24)
            score += days_score

            # 累计涨幅分：温和上涨最优
            if 3 <= cumulative_change <= 8:
                score += 25  # 最佳区间
            elif cumulative_change < 3:
                score += 15
            else:
                score += 10

            # 量比加分
            vol_ratio = indicators.get("volume_ratio", 1.0)
            if 1.2 <= vol_ratio <= 2.5:
                score += 15  # 温和放量最优
            elif vol_ratio > 2.5:
                score += 8   # 放量过多可能是出货

            # 位置加分
            pos_20 = indicators.get("position_20d", 50)
            if 20 <= pos_20 <= 60:
                score += 15  # 中低位最佳
            elif pos_20 < 20:
                score += 10  # 低位也不错
            elif pos_20 > 80:
                score -= 15  # 高位减分

            # 技术面加分
            if indicators.get("ma_bullish_align"):
                score += 8
            if indicators.get("macd_golden_cross"):
                score += 5

            score = round(score, 1)

            if score < min_score:
                continue

            # ── 信号生成 ──
            signals = []
            sfx = "「吸筹」"
            if consecutive_up >= 5:
                signals.append(f"连阳{consecutive_up}日建仓" + sfx)
            else:
                signals.append(f"连阳{consecutive_up}日温和建仓" + sfx)

            if 3 <= cumulative_change <= 8:
                signals.append("温和吸筹" + sfx)
            elif cumulative_change > 8:
                signals.append("加速吸筹" + sfx)

            if 20 <= pos_20 <= 60:
                signals.append("中位蓄势" + sfx)
            elif pos_20 < 20:
                signals.append("底部吸筹" + sfx)

            results.append(ScanResult(
                symbol=stock.symbol,
                name=stock.name,
                strategy=StrategyType.CONSECUTIVE_POSITIVE,
                score=score,
                signals=signals,
                data=stock,
                metadata={
                    "consecutive_up": consecutive_up,
                    "cumulative_change": round(cumulative_change, 2),
                    "vol_ratio": round(vol_ratio, 2),
                    "position_20d": round(pos_20, 1),
                }
            ))

        results.sort(key=lambda x: x.score, reverse=True)
        self.logger.info(f"连续小阳策略: {len(results)} 只标的")
        return results
