"""
资金策略 MoneyStrategy (v2.8 Phase 1)

聚合：资金净流入(0.35) + 成交额排名(0.30) + 多因子增强(0.35)

⚠️ 横截面策略例外 — 必须重写 execute：
TurnoverRank/MultiFactor/NetInflow 依赖全市场排名/归一化。
基类逐股调用 [stock] 会导致排名退化（每只都是第1名 → 分值恒满分）。
此处改为：每个子策略跑【全市场】一次，按 symbol 加权聚合。
"""
from typing import List, Dict, Any, Optional

from .base import AggregatedStrategy
from ..momentum.net_inflow import NetInflowStrategy
from ..momentum.turnover_rank import TurnoverRankStrategy
from ..momentum.multi_factor import MultiFactorStrategy
from ...core.types import StockData, ScanResult, StrategyType


class MoneyStrategy(AggregatedStrategy):
    """聚合策略：资金净流入 + 成交额排名 + 多因子增强（横截面模式）"""

    @property
    def name(self) -> str:
        return "资金策略"

    @property
    def strategy_type(self) -> StrategyType:
        return StrategyType.MONEY

    def __init__(self):
        super().__init__()
        self._sub_strategies = [
            (NetInflowStrategy(), 0.35),
            (TurnoverRankStrategy(), 0.30),
            (MultiFactorStrategy(), 0.35),
        ]

    # ── 重写 execute：横截面模式（每个子策略跑全市场一次）──
    def execute(
        self,
        market_data: List[StockData],
        params: Optional[Dict[str, Any]] = None
    ) -> List[ScanResult]:
        # ① 独立运行兜底（同基类）
        if not self._indicators:
            self._self_prefetch(market_data, as_of=(params or {}).get("as_of"))

        # ② 缓存传播（同基类）
        for sub, _w in self._sub_strategies:
            if hasattr(sub, '_indicators'):
                sub._indicators = self._indicators
            if hasattr(sub, '_kline_cache'):
                sub._kline_cache = self._kline_cache
            if hasattr(sub, '_kline_available'):
                sub._kline_available = self._kline_available

        # ③ 横截面聚合：每个子策略跑全市场一次 → 按 symbol 加权
        sym_scores: Dict[str, float] = {}
        sym_weights: Dict[str, float] = {}
        sym_hits: Dict[str, List[str]] = {}
        stock_map = {s.symbol: s for s in market_data}

        for strategy, weight in self._sub_strategies:
            sub_results = strategy.execute(market_data, params)  # 传全市场
            for r in sub_results:
                if r.score > 0:
                    sym_scores[r.symbol] = sym_scores.get(r.symbol, 0.0) + r.score * weight
                    sym_weights[r.symbol] = sym_weights.get(r.symbol, 0.0) + weight
                    sym_hits.setdefault(r.symbol, []).append(strategy.name)
                    if r.data:
                        stock_map[r.symbol] = r.data

        # ④ 共识分：最高子策略分 × 共识乘数
        results: List[ScanResult] = []
        for sym in set(list(sym_scores.keys()) + list(sym_weights.keys())):
            raw_scores = sym_scores.get(sym, 0.0)
            total_w = sym_weights.get(sym, 0.0)
            if total_w <= 0:
                continue

            # 用加权平均估算各子策略对该标的的贡献强度
            base_estimate = raw_scores / total_w

            total_strategy_weight = sum(w for _strategy, w in self._sub_strategies) or 1.0
            consensus = 0.7 + 0.3 * (total_w / total_strategy_weight)

            final_score = base_estimate * consensus
            stock = stock_map.get(sym)
            results.append(ScanResult(
                symbol=sym,
                name=stock.name if stock else sym,
                score=round(min(final_score, 100), 1),
                signals=[f"{self.name}:资金聚合"],
                strategy=StrategyType.MONEY,
                data=stock,
                metadata={
                    "consensus_score": round(final_score, 1),
                    "base_estimate": round(base_estimate, 1),
                    "hit_weight": round(total_w, 3),
                    "hit_sub_strategies": sym_hits.get(sym, []),
                },
            ))

        return results
