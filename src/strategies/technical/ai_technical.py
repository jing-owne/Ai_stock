"""
AI技术面分析策略
基于真实技术指标进行形态识别和趋势评分
"""
from typing import List, Dict, Any, Optional
import logging

from ..base import BaseStrategy
from ...core.types import StockData, ScanResult, StrategyType
from ...core.indicators import calc_all_indicators, calc_pattern_score, calc_trend_score
from ...data.kline_fetcher import KlineFetcher


class AITechnicalStrategy(BaseStrategy):
    """
    AI技术面策略

    基于真实技术指标:
    - K线形态评分（SMA/布林带/MACD组合）
    - 趋势评分（均线排列/RSI/MACD）
    - 放量突破信号
    """

    def __init__(self, kline_fetcher: Optional[KlineFetcher] = None):
        self._kline_fetcher = kline_fetcher or KlineFetcher(max_workers=10)
        self.logger = logging.getLogger("AInvest.AITechnicalStrategy")

    @property
    def name(self) -> str:
        return "AI技术面策略"

    @property
    def strategy_type(self) -> StrategyType:
        return StrategyType.AI_TECHNICAL

    def execute(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> List[ScanResult]:
        pattern_threshold = params.get("pattern_threshold", 0.75)

        # 批量获取K线
        symbols = [s.symbol for s in market_data if s.change_pct > -2]
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

        results = []
        for stock in market_data:
            indicators = indicator_map.get(stock.symbol)
            if not indicators:
                continue

            volume_ratio = indicators.get("volume_ratio", 1.0)
            pattern_score = calc_pattern_score(indicators, volume_ratio)
            trend_score = calc_trend_score(indicators)

            pattern_score = min(pattern_score, 100)
            trend_score = min(trend_score, 100)
            total_score = pattern_score * 0.5 + trend_score * 0.5

            if total_score >= pattern_threshold * 100:
                signals = self._generate_signals(
                    pattern_score, trend_score, indicators, stock
                )
                results.append(ScanResult(
                    symbol=stock.symbol,
                    name=stock.name,
                    strategy=self.strategy_type,
                    score=round(total_score, 1),
                    signals=signals,
                    data=stock,
                    metadata={
                        "pattern_score": round(pattern_score, 1),
                        "trend_score": round(trend_score, 1),
                        "rsi14": round(indicators.get("rsi14", 0), 1),
                        "volume_ratio": round(volume_ratio, 2),
                    }
                ))

        results.sort(key=lambda x: x.score, reverse=True)
        return results

    def _generate_signals(
        self,
        pattern_score: float,
        trend_score: float,
        indicators: Dict[str, float],
        stock: StockData
    ) -> List[str]:
        signals = []
        if pattern_score >= 85:
            signals.append("AI形态突破")
        elif pattern_score >= 75:
            signals.append("AI形态良好")
        if trend_score >= 80:
            signals.append("上升趋势确认")
        elif trend_score >= 70:
            signals.append("趋势向好")
        if indicators.get("macd_golden_cross"):
            signals.append("MACD金叉")
        if indicators.get("ma_bullish_align"):
            signals.append("均线多头排列")
        if stock.change_pct > 3:
            signals.append("强势信号")
        return signals
