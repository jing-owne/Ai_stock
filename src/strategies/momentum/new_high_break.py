"""
突破前高策略 (v2.6.5新增)

核心逻辑：
- 检测股价突破20日/60日最高价
- 放量突破更可靠（量比>1.3）
- 区分真突破与假突破：回踩确认更优
- 适合趋势跟踪，顺势而为

参考指标：
- 收盘价 > 20日最高价（突破确认）
- 5日均量比 > 1.3（放量配合）
- 20日位置适中（30-80，不追高不接飞刀）
- MACD金叉或零轴上（趋势配合）
"""
from typing import List, Dict, Any
import logging

from ..base import BaseStrategy
from ...core.types import StockData, ScanResult, StrategyType


class NewHighBreakStrategy(BaseStrategy):
    """突破前高策略"""

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("AInvest.NewHighBreak")

    @property
    def name(self) -> str:
        return "突破前高"

    @property
    def strategy_type(self) -> StrategyType:
        return StrategyType.NEW_HIGH_BREAK

    def execute(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> List[ScanResult]:
        cfg = params.get("new_high_break", {}) if params else {}
        high_period = cfg.get("high_period", 20)
        min_breakout = cfg.get("min_breakout_pct", 0.5)
        min_change = cfg.get("min_price_change", 1.0)
        max_change = cfg.get("max_price_change", 7.0)
        min_amount = cfg.get("min_amount", 150_000_000)
        min_vol_ratio = cfg.get("min_volume_ratio", 1.3)
        min_score = cfg.get("min_score", 45)

        results = []
        for stock in market_data:
            # ── 基本筛选 ──
            if stock.change_pct < min_change or stock.change_pct > max_change:
                continue
            if stock.amount < min_amount:
                continue

            # ── 获取K线指标 ──
            indicators = getattr(self, '_indicators', {}).get(stock.symbol)
            if not indicators:
                continue

            # ── 突破前高检测 ──
            breakout_20d = indicators.get("breakout_20d_high")
            breakout_60d = indicators.get("breakout_60d_high")

            # 至少突破20日或60日新高
            if not breakout_20d and not breakout_60d:
                continue

            # ── 量比确认 ──
            vol_ratio = indicators.get("volume_ratio", 1.0)
            if vol_ratio < min_vol_ratio:
                # 缩量突破可能是假突破
                continue

            # ── 评分计算 ──
            score = 30  # 基础分

            # 突破力度加分
            if breakout_60d:
                score += 30  # 突破60日新高，力度更强
            elif breakout_20d:
                score += 20  # 突破20日新高

            # 量比加分
            vol_bonus = min((vol_ratio - 1.0) * 10, 20)
            score += vol_bonus

            # 涨幅加分
            change_bonus = min(stock.change_pct * 4, 15)
            score += change_bonus

            # 位置过滤：不追过高
            pos_20 = indicators.get("position_20d", 50)
            if pos_20 > 85:
                score -= 20  # 高位突破风险大
            elif pos_20 < 30:
                score += 10  # 低位突破更可靠

            # 技术面加分
            if indicators.get("macd_golden_cross"):
                score += 10
            if indicators.get("ma_bullish_align"):
                score += 8

            score = round(score, 1)

            if score < min_score:
                continue

            # ── 信号生成 ──
            signals = []
            sfx = "「前高」"
            if breakout_60d:
                signals.append("突破60日新高" + sfx)
            elif breakout_20d:
                signals.append("突破20日新高" + sfx)

            if vol_ratio >= 2.0:
                signals.append("巨量突破" + sfx)
            elif vol_ratio >= 1.5:
                signals.append("放量突破" + sfx)

            if pos_20 < 30:
                signals.append("低位启动" + sfx)

            if indicators.get("macd_golden_cross"):
                signals.append("MACD金叉" + sfx)
            if indicators.get("ma_bullish_align"):
                signals.append("多头排列" + sfx)

            results.append(ScanResult(
                symbol=stock.symbol,
                name=stock.name,
                strategy=StrategyType.NEW_HIGH_BREAK,
                score=score,
                signals=signals,
                data=stock,
                metadata={
                    "breakout_20d": breakout_20d,
                    "breakout_60d": breakout_60d,
                    "vol_ratio": round(vol_ratio, 2),
                    "position_20d": round(pos_20, 1),
                }
            ))

        results.sort(key=lambda x: x.score, reverse=True)
        self.logger.info(f"突破前高策略: {len(results)} 只标的")
        return results
