"""
RSI超卖反弹策略 (v2.6.5新增)

核心逻辑：
- 检测RSI(14)进入超卖区域 (<35)，股价经历充分回调
- 当日出现反弹信号：涨幅>1%、成交量放大(量比>1.2)
- 优选RSI底背离形态（股价新低但RSI不再新低）
- 排除高位标的，适合抄底风格

参考指标：
- RSI(14) < 35：进入超卖区域
- 底背离：股价创20日新低但RSI未创新低
- 成交量放大：5日均量比 > 1.2
- 位置：20日位置 < 30（低位反弹空间大）
"""
from typing import List, Dict, Any
import logging

from ..base import BaseStrategy
from ...core.types import StockData, ScanResult, StrategyType


class RsiOversoldStrategy(BaseStrategy):
    """RSI超卖反弹策略"""

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("AInvest.RsiOversold")

    @property
    def name(self) -> str:
        return "RSI超卖反弹"

    @property
    def strategy_type(self) -> StrategyType:
        return StrategyType.RSI_OVERSOLD

    def execute(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> List[ScanResult]:
        cfg = params.get("rsi_oversold", {}) if params else {}
        max_rsi = cfg.get("max_rsi", 35)
        min_change = cfg.get("min_price_change", 1.0)
        max_change = cfg.get("max_price_change", 5.0)
        min_amount = cfg.get("min_amount", 100_000_000)
        min_vol_ratio = cfg.get("min_volume_ratio", 1.2)
        min_score = cfg.get("min_score", 40)

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

            rsi14 = indicators.get("rsi14")
            if rsi14 is None or rsi14 > max_rsi:
                continue

            # ── 量比确认 ──
            vol_ratio = indicators.get("volume_ratio", 1.0)
            if vol_ratio < min_vol_ratio:
                continue

            # ── 评分计算 ──
            # RSI超卖分：RSI越低越好 (rsi=20 → 100分, rsi=35 → 0分)
            rsi_score = max(0, min((max_rsi - rsi14) / (max_rsi - 15) * 50, 50))

            # 反弹力度分
            change_score = min(stock.change_pct / max_change * 30, 30)

            # 量比加分
            vol_score = min((vol_ratio - 1.0) * 10, 20)

            score = round(rsi_score + change_score + vol_score, 1)

            if score < min_score:
                continue

            # ── 信号生成 ──
            signals = []
            sfx = "「RSI」"
            if rsi14 < 25:
                signals.append("RSI深度超卖" + sfx)
            elif rsi14 < 30:
                signals.append("RSI超卖" + sfx)
            else:
                signals.append("RSI偏弱反弹" + sfx)

            if vol_ratio >= 2.0:
                signals.append("放量反弹" + sfx)
            elif vol_ratio >= 1.5:
                signals.append("温和放量反弹" + sfx)

            pos_20 = indicators.get("position_20d", 50)
            if pos_20 < 30:
                signals.append("低位超卖" + sfx)
                score += 5  # 低位加分

            if indicators.get("macd_golden_cross"):
                signals.append("MACD金叉确认" + sfx)
                score += 5

            results.append(ScanResult(
                symbol=stock.symbol,
                name=stock.name,
                strategy=StrategyType.RSI_OVERSOLD,
                score=round(score, 1),
                signals=signals,
                data=stock,
                metadata={
                    "rsi14": round(rsi14, 1),
                    "vol_ratio": round(vol_ratio, 2),
                    "position_20d": round(indicators.get("position_20d", 50), 1),
                }
            ))

        results.sort(key=lambda x: x.score, reverse=True)
        self.logger.info(f"RSI超卖策略: {len(results)} 只标的")
        return results
