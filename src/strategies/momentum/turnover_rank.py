"""
成交额排名策略

纯行情数据策略，不依赖K线。
选出成交额排名前列的活跃标的。
"""
from typing import List, Dict, Any
import logging

from ..base import BaseStrategy
from ...core.types import StockData, ScanResult, StrategyType


class TurnoverRankStrategy(BaseStrategy):
    """成交额排名策略"""

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("AInvest.TurnoverRank")

    @property
    def name(self) -> str:
        return "成交额排名"

    @property
    def strategy_type(self) -> StrategyType:
        return StrategyType.TURNOVER_RANK

    def execute(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> List[ScanResult]:
        cfg = params.get("turnover_rank", {}) if params else {}
        top_n = cfg.get("top_n", 20)
        min_amount = cfg.get("min_amount", 500_000_000)

        sorted_stocks = sorted(market_data, key=lambda x: x.amount, reverse=True)
        top_stocks = [s for s in sorted_stocks[:top_n] if s.amount >= min_amount]

        results = []
        max_amount = max((s.amount for s in top_stocks), default=1)

        for rank, stock in enumerate(top_stocks, 1):
            rank_score = max(50 - (rank - 1) * 2.5, 10)
            amount_score = (stock.amount / max_amount) * 30
            change_score = min(max(stock.change_pct, 0) * 5, 20)
            score = round(rank_score + amount_score + change_score, 1)

            signals = []
            sfx = "「成交额」"
            if rank <= 5:
                signals.append("成交额TOP5" + sfx)
            elif rank <= 10:
                signals.append("成交活跃" + sfx)
            if stock.change_pct > 0:
                signals.append("资金活跃" + sfx)

            results.append(ScanResult(
                symbol=stock.symbol,
                name=stock.name,
                strategy=StrategyType.TURNOVER_RANK,
                score=score,
                signals=signals,
                data=stock,
                metadata={"rank": rank, "amount": stock.amount}
            ))

        return results
