"""
多因子量化策略
综合考虑多个因子进行选股，技术因子使用真实技术指标
"""
from typing import List, Dict, Any, Optional
import logging

from ..base import BaseStrategy
from ...core.types import StockData, ScanResult, StrategyType
from ...core.indicators import calc_all_indicators, calc_technical_score
from ...data.kline_fetcher import KlineFetcher


class MultiFactorStrategy(BaseStrategy):
    """
    多因子量化策略

    综合评分因子:
    - 成交量因子（真实）
    - 价格因子（真实）
    - 换手率因子（真实）
    - 技术面因子（真实技术指标）
    """

    def __init__(self, kline_fetcher: Optional[KlineFetcher] = None):
        self._kline_fetcher = kline_fetcher or KlineFetcher(max_workers=10)
        self.logger = logging.getLogger("AInvest.MultiFactorStrategy")

    @property
    def name(self) -> str:
        return "多因子量化策略"

    @property
    def strategy_type(self) -> StrategyType:
        return StrategyType.MULTI_FACTOR

    def execute(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> List[ScanResult]:
        volume_weight = params.get("volume_weight", 0.20)
        price_weight = params.get("price_weight", 0.25)
        turnover_weight = params.get("turnover_weight", 0.20)
        tech_weight = params.get("tech_weight", 0.35)
        min_score = params.get("min_score", 60)

        # 批量获取K线数据
        symbols = [s.symbol for s in market_data if s.amount >= 50_000_000]
        kline_data = self._kline_fetcher.fetch_batch(symbols, days=60)

        # 计算技术指标
        indicator_map = {}
        for symbol, kline_list in kline_data.items():
            arrays = self._kline_fetcher.get_numpy_arrays(kline_list)
            if arrays:
                indicator_map[symbol] = calc_all_indicators(
                    arrays["close"], arrays["volume"],
                    arrays["high"], arrays["low"]
                )

        max_amount = max((s.amount for s in market_data), default=1)
        max_change = max((s.change_pct for s in market_data), default=1) or 1

        results = []
        for stock in market_data:
            factors = {}

            factors["volume"] = (stock.amount / max_amount) * 100
            factors["price"] = max(0, min(stock.change_pct / max_change * 100 if max_change > 0 else 50, 100))
            factors["turnover"] = min(stock.turn_rate * 10, 100)

            # 真实技术面因子
            indicators = indicator_map.get(stock.symbol)
            if indicators:
                factors["technical"] = calc_technical_score(indicators)
            else:
                factors["technical"] = 40.0  # 无数据给保守分

            total_score = (
                factors["volume"] * volume_weight +
                factors["price"] * price_weight +
                factors["turnover"] * turnover_weight +
                factors["technical"] * tech_weight
            )

            if total_score >= min_score:
                signals = self._generate_signals(factors)
                results.append(ScanResult(
                    symbol=stock.symbol,
                    name=stock.name,
                    strategy=self.strategy_type,
                    score=round(total_score, 1),
                    signals=signals,
                    data=stock,
                    metadata={"factors": {k: round(v, 1) for k, v in factors.items()}}
                ))

        results.sort(key=lambda x: x.score, reverse=True)
        return results

    def _generate_signals(self, factors: Dict[str, float]) -> List[str]:
        signals = []
        if factors["volume"] >= 80:
            signals.append("量能充沛")
        elif factors["volume"] >= 60:
            signals.append("量能较好")
        if factors["price"] >= 80:
            signals.append("涨幅领先")
        if factors["turnover"] >= 80:
            signals.append("换手活跃")
        if factors["technical"] >= 70:
            signals.append("技术面强势")
        return signals
