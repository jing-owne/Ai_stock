"""
放量上涨策略
选出一段时间内成交量放大且股价上涨的股票
使用真实K线数据计算5日均量比
"""
from typing import List, Dict, Any, Optional
import logging

from ..base import BaseStrategy
from ...core.types import StockData, ScanResult, StrategyType
from ...core.indicators import calc_all_indicators
from ...data.kline_fetcher import KlineFetcher


class VolumeSurgeStrategy(BaseStrategy):
    """
    放量上涨策略

    选股逻辑:
    1. 成交量较5日均量放大一定倍数（真实数据）
    2. 股价涨幅达到一定水平
    3. 成交额达到最低门槛
    """

    def __init__(self, kline_fetcher: Optional[KlineFetcher] = None):
        self._kline_fetcher = kline_fetcher or KlineFetcher(max_workers=10)
        self.logger = logging.getLogger("AInvest.VolumeSurgeStrategy")

    @property
    def name(self) -> str:
        return "放量上涨策略"

    @property
    def strategy_type(self) -> StrategyType:
        return StrategyType.VOLUME_SURGE

    def execute(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> List[ScanResult]:
        min_ratio = params.get("min_volume_ratio", 2.0)
        min_change = params.get("min_price_change", 1.0)
        min_amount = params.get("min_amount", 100_000_000)

        # 筛选候选股票
        candidates = [s for s in market_data
                      if s.change_pct >= min_change and s.amount >= min_amount]

        # 批量获取K线计算真实放量倍数
        symbols = [s.symbol for s in candidates]
        kline_data = self._kline_fetcher.fetch_batch(symbols, days=10)

        results = []
        for stock in candidates:
            # 从K线数据获取真实放量倍数
            kline = kline_data.get(stock.symbol)
            if not kline or len(kline) < 6:
                continue

            arrays = self._kline_fetcher.get_numpy_arrays(kline)
            if not arrays:
                continue

            indicators = calc_all_indicators(
                arrays["close"], arrays["volume"],
                arrays["high"], arrays["low"]
            )
            volume_ratio = indicators.get("volume_ratio")
            if volume_ratio is None or volume_ratio < min_ratio:
                continue

            score = self._calculate_score(
                volume_ratio=volume_ratio,
                change_pct=stock.change_pct,
                amount=stock.amount,
                params=params
            )

            signals = self._generate_signals(
                volume_ratio=volume_ratio,
                change_pct=stock.change_pct
            )

            results.append(ScanResult(
                symbol=stock.symbol,
                name=stock.name,
                strategy=self.strategy_type,
                score=score,
                signals=signals,
                data=stock,
                metadata={
                    "volume_ratio": round(volume_ratio, 2),
                    "change_pct": stock.change_pct,
                }
            ))

        results.sort(key=lambda x: x.score, reverse=True)
        return results

    def _calculate_score(
        self,
        volume_ratio: float,
        change_pct: float,
        amount: float,
        params: Dict[str, Any]
    ) -> float:
        volume_score = min(volume_ratio / params.get("min_volume_ratio", 2.0) * 20, 40)
        change_score = min(change_pct * 10, 30)
        min_amount = params.get("min_amount", 100_000_000)
        amount_score = min(amount / min_amount * 15, 30)
        return round(volume_score + change_score + amount_score, 1)

    def _generate_signals(
        self,
        volume_ratio: float,
        change_pct: float
    ) -> List[str]:
        signals = []
        if volume_ratio >= 3.0:
            signals.append("巨量突破")
        elif volume_ratio >= 2.0:
            signals.append("温和放量")
        if change_pct >= 5.0:
            signals.append("强势上涨")
        elif change_pct >= 3.0:
            signals.append("大幅上涨")
        elif change_pct >= 1.0:
            signals.append("小幅上涨")
        return signals
