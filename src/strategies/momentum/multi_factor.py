"""
多因子增强策略 (v2.6.5 合并版)

= multi_factor + institution 合并

整合逻辑:
1. 基础多因子: 成交量25% + 价格25% + 换手率15% + 技术面35%
2. 机构特征增强: 大额成交加分 + 机构型换手率加分 + 温和涨幅加分
3. 技术面增强: MACD金叉/均线多头=机构建仓确认
"""
from typing import List, Dict, Any
import logging

from ..base import BaseStrategy
from ...core.types import StockData, ScanResult, StrategyType
from ...core.indicators import calc_technical_score


class MultiFactorStrategy(BaseStrategy):
    """多因子增强策略 = 多因子 + 机构特征"""

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("AInvest.MultiFactor")
        self._indicators: Dict[str, Dict[str, float]] = {}
        self._kline_available: bool = True

    @property
    def name(self) -> str:
        return "多因子增强"

    @property
    def strategy_type(self) -> StrategyType:
        return StrategyType.MULTI_FACTOR

    def execute(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> List[ScanResult]:
        cfg = params.get("multi_factor", {}) if params else {}
        v_weight = cfg.get("volume_weight", 0.25)
        p_weight = cfg.get("price_weight", 0.25)
        t_weight = cfg.get("turnover_weight", 0.15)
        tech_weight = cfg.get("tech_weight", 0.35)
        min_score = cfg.get("min_score", 40)
        min_amount = cfg.get("min_amount", 200_000_000)

        max_amount = max((s.amount for s in market_data), default=1)
        max_change = max((abs(s.change_pct) for s in market_data), default=1) or 1

        results = []
        for stock in market_data:
            if stock.amount < min_amount:
                continue

            indicators = self._indicators.get(stock.symbol)
            # ── v2.6.10: PE从StockData获取（aggregator不含基本面数据）──
            pe_ratio = stock.pe_ratio
            if pe_ratio is not None and pe_ratio < 0:
                # PE为负(亏损) → 技术面基础分降至1%
                if indicators:
                    technical = calc_technical_score(indicators) * 0.01
                else:
                    technical = 40.0 * 0.01
                has_neg_pe = True
            else:
                if indicators:
                    technical = calc_technical_score(indicators)
                else:
                    technical = 40.0
                has_neg_pe = False

            # ── 基础多因子 ──
            factors = {
                "volume": (stock.amount / max_amount) * 100,
                "price": max(0, min(stock.change_pct / max_change * 100, 100)),
                "turnover": min(stock.turn_rate * 10, 100),
                "technical": technical,
            }
            base_score = (
                factors["volume"] * v_weight +
                factors["price"] * p_weight +
                factors["turnover"] * t_weight +
                factors["technical"] * tech_weight
            )

            # ── 机构特征增强 (原 institution 逻辑) ──
            institution_bonus = 0
            # 大额成交 = 大资金可能参与
            institution_bonus += min(stock.amount / max_amount * 15, 15)
            # 机构型换手率 1%-5%
            if 1.0 <= stock.turn_rate <= 5.0:
                institution_bonus += 10
            elif 0.5 <= stock.turn_rate < 1.0:
                institution_bonus += 8
            elif 5.0 < stock.turn_rate <= 8.0:
                institution_bonus += 5
            # 温和涨幅 = 机构建仓特征
            if -5.0 <= stock.change_pct <= 7.0:
                institution_bonus += 8
            elif 4.0 < stock.change_pct <= 7.0:
                institution_bonus += 5
            # 技术面确认
            if indicators:
                if indicators.get("macd_golden_cross"):
                    institution_bonus += 5
                if indicators.get("ma_bullish_align"):
                    institution_bonus += 3

            total = round(base_score + institution_bonus, 1)
            if total < min_score:
                continue

            # ── v2.6.9: PE为负 → 信号加风险标注 ─────────────────────
            signals = []
            sfx = "「多因子」"
            if has_neg_pe:
                signals.append("⚠️亏损标的(PE为负)")
            if factors["volume"] >= 80:
                signals.append("量能充沛" + sfx)
            if factors["price"] >= 80:
                signals.append("涨幅领先" + sfx)
            if technical >= 70:
                signals.append("技术面强势" + sfx)
            if institution_bonus >= 15:
                signals.append("机构特征明显" + sfx)

            results.append(ScanResult(
                symbol=stock.symbol,
                name=stock.name,
                strategy=StrategyType.MULTI_FACTOR,
                score=total,
                signals=signals,
                data=stock,
                metadata={
                    "factors": {k: round(v, 1) for k, v in factors.items()},
                    "institution_bonus": round(institution_bonus, 1),
                }
            ))

        results.sort(key=lambda x: x.score, reverse=True)
        return results
