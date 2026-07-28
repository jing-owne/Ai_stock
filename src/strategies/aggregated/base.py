"""
聚合策略统一基类 AggregatedStrategy (v2.8 Phase 1)

职责：
- 编排循环：逐股遍历 → 注入共享缓存 → 加权聚合子策略分
- 独立运行兜底：单策略模式下自拉预取（_self_prefetch）
- 子策略缓存传播：将 _indicators/_kline_cache 下发给每个子策略

⚠️ 横截面例外：MoneyStrategy 三个子策略需要全市场排名/归一化，
不能逐股调用基类，必须重写 execute（见 money_strategy.py）。
"""
from typing import List, Dict, Any, Optional, Tuple
import logging

from ..base import BaseStrategy
from ...core.types import StockData, ScanResult, StrategyType


class AggregatedStrategy(BaseStrategy):
    """聚合策略基类：复用编排循环，子类只声明 _sub_strategies 与 strategy_type"""

    def __init__(self):
        super().__init__()
        self._sub_strategies: List[Tuple[BaseStrategy, float]] = []  # [(实例, 权重), ...]
        self._indicators: Dict[str, Dict[str, float]] = {}           # Composite 注入或自预取
        self._kline_cache: Dict[str, List[StockData]] = {}           # 供指纹子策略复用原始K线
        self._kline_available: bool = False

    # ── 子类必须覆写 ──
    @property
    def strategy_type(self) -> StrategyType:
        raise NotImplementedError

    @property
    def name(self) -> str:
        raise NotImplementedError

    # ── 主入口 ──
    def execute(
        self,
        market_data: List[StockData],
        params: Optional[Dict[str, Any]] = None
    ) -> List[ScanResult]:
        # ① 独立运行兜底：非 Composite 注入时自拉预取
        if not self._indicators:
            self._self_prefetch(market_data, as_of=(params or {}).get("as_of"))

        # ② 向子策略传播共享缓存（避免子策略各自重拉K线）
        for sub, _w in self._sub_strategies:
            if hasattr(sub, '_indicators'):
                sub._indicators = self._indicators
            if hasattr(sub, '_kline_cache'):
                sub._kline_cache = self._kline_cache
            if hasattr(sub, '_kline_available'):
                sub._kline_available = self._kline_available

        results: List[ScanResult] = []
        for stock in market_data:
            indicators = self._indicators.get(stock.symbol, {})
            if not indicators:
                continue

            weighted_score = 0.0
            hit_weight = 0.0
            sub_details: List[str] = []

            for strategy, weight in self._sub_strategies:
                sub_result = strategy.execute([stock], params)
                if sub_result and sub_result[0].score > 0:
                    weighted_score += sub_result[0].score * weight
                    hit_weight += weight
                    sub_details.append(f"{strategy.name}({sub_result[0].score:.0f})")

            if hit_weight > 0:
                base = weighted_score / hit_weight
                total_weight = sum(w for _strategy, w in self._sub_strategies) or 1.0
                consensus = 0.7 + 0.3 * (hit_weight / total_weight)
                final_score = base * consensus

                results.append(ScanResult(
                    symbol=stock.symbol,
                    name=stock.name,
                    score=round(min(final_score, 100), 1),
                    signals=[f"{self.name}:{'|'.join(sub_details)}"],
                    strategy=self.strategy_type,
                    data=stock,
                    metadata={
                        "sub_strategies": sub_details,
                        "consensus_score": round(final_score, 1),
                        "base_score": round(base, 1),
                        "hit_weight": round(hit_weight, 3),
                    },
                ))

        return results

    # ── 独立运行自预取 ──
    def _self_prefetch(self, market_data: List[StockData], as_of: Optional[str] = None) -> None:
        """单策略模式下自拉预取（复用 prefetch_kline_indicators）"""
        from ...data.prefetch import prefetch_kline_indicators

        symbols = list({s.symbol for s in market_data if s.amount >= 200_000_000})
        if not symbols:
            self._indicators = {}
            return

        ind, kln, cnt = prefetch_kline_indicators(
            symbols=symbols,
            keep_kline=True,
            log_prefix=self.name,
            as_of=as_of,
        )
        self._indicators = ind
        self._kline_cache = kln
        self._kline_available = cnt > 0
        if not self._kline_available:
            logging.getLogger("AInvest.AggregatedStrategy").warning(
                f"[{self.name}] K线获取失败({len(symbols)}只)，策略将降级"
            )
