"""
机构追踪策略
基于成交额/换手率/涨幅的代理指标推断机构行为

注: 真实机构持股数据需接入东财接口(后续迭代)
当前使用可观测数据替代 random 模拟
"""
from typing import List, Dict, Any, Optional
import logging

from ..base import BaseStrategy
from ...core.types import StockData, ScanResult, StrategyType
from ...core.indicators import calc_all_indicators
from ...data.kline_fetcher import KlineFetcher


class InstitutionStrategy(BaseStrategy):
    """
    机构追踪策略

    代理指标:
    - 大额成交 → 可能有大资金参与
    - 换手率适中(1%-5%) → 典型机构持仓特征
    - 温和上涨 → 可能是机构建仓推动
    - MACD金叉/均线多头 → 技术面确认
    """

    def __init__(self, kline_fetcher: Optional[KlineFetcher] = None):
        self._kline_fetcher = kline_fetcher or KlineFetcher(max_workers=10)
        self.logger = logging.getLogger("AInvest.InstitutionStrategy")

    @property
    def name(self) -> str:
        return "机构追踪策略"

    @property
    def strategy_type(self) -> StrategyType:
        return StrategyType.INSTITUTION

    def execute(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> List[ScanResult]:
        min_amount = params.get("min_amount", 200_000_000)

        # 批量获取K线
        candidates = [s for s in market_data if s.amount >= min_amount]
        symbols = [s.symbol for s in candidates]
        kline_data = self._kline_fetcher.fetch_batch(symbols, days=60)

        # 计算指标
        indicator_map = {}
        for symbol, kline_list in kline_data.items():
            arrays = self._kline_fetcher.get_numpy_arrays(kline_list)
            if arrays:
                indicator_map[symbol] = calc_all_indicators(
                    arrays["close"], arrays["volume"],
                    arrays["high"], arrays["low"]
                )

        max_amount = max((s.amount for s in market_data), default=1)
        results = []

        for stock in candidates:
            amount_rank_score = min(stock.amount / max_amount * 40, 40)

            turn_rate = stock.turn_rate
            if 1.0 <= turn_rate <= 5.0:
                turn_score = 25
            elif 0.5 <= turn_rate < 1.0:
                turn_score = 20
            elif 5.0 < turn_rate <= 8.0:
                turn_score = 15
            else:
                turn_score = 5

            if 0.5 <= stock.change_pct <= 4.0:
                price_score = 20
            elif 4.0 < stock.change_pct <= 7.0:
                price_score = 15
            elif stock.change_pct > 0:
                price_score = 10
            else:
                price_score = 0

            indicators = indicator_map.get(stock.symbol)
            tech_bonus = 0
            if indicators:
                if indicators.get("macd_golden_cross"):
                    tech_bonus += 10
                if indicators.get("ma_bullish_align"):
                    tech_bonus += 5

            score = round(amount_rank_score + turn_score + price_score + tech_bonus, 1)

            if score < 30:
                continue

            signals = self._generate_signals(
                amount_rank_score, turn_score, price_score, tech_bonus, stock
            )

            results.append(ScanResult(
                symbol=stock.symbol,
                name=stock.name,
                strategy=self.strategy_type,
                score=score,
                signals=signals,
                data=stock,
                metadata={
                    "amount_rank_score": round(amount_rank_score, 1),
                    "turn_score": turn_score,
                    "price_score": price_score,
                    "tech_bonus": tech_bonus,
                    "note": "代理指标，非真实机构数据",
                }
            ))

        results.sort(key=lambda x: x.score, reverse=True)
        return results

    def _generate_signals(
        self,
        amount_rank_score: float,
        turn_score: int,
        price_score: int,
        tech_bonus: int,
        stock: StockData
    ) -> List[str]:
        signals = []
        if amount_rank_score >= 30:
            signals.append("大额成交")
        if turn_score >= 20:
            signals.append("机构换手率特征")
        if price_score >= 15:
            signals.append("温和上涨建仓")
        if tech_bonus >= 10:
            signals.append("技术面确认")
        return signals
