"""
资金净流入策略 (v2.6.5新增)

核心逻辑：
- 获取20个交易日主力资金流向数据
- 统计连续主力净流入天数
- 分级评分：>10天+3分, >13天+5分, >15天+8分, >18天+10分
"""

from typing import List, Dict, Any, Optional
import logging

from ..base import BaseStrategy
from ...core.types import StockData, ScanResult, StrategyType
from ...core.indicators import calc_net_inflow_score
from ...data.money_flow_fetcher import MoneyFlowFetcher


class NetInflowStrategy(BaseStrategy):
    """资金净流入策略"""

    def __init__(self, flow_fetcher: Optional[MoneyFlowFetcher] = None):
        super().__init__()
        self.logger = logging.getLogger("AInvest.NetInflow")
        self._flow_fetcher = flow_fetcher or MoneyFlowFetcher(max_workers=4)

    @property
    def name(self) -> str:
        return "资金净流入"

    @property
    def strategy_type(self) -> StrategyType:
        return StrategyType.NET_INFLOW

    def execute(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> List[ScanResult]:
        cfg = params.get("net_inflow", {}) if params else {}
        min_change = cfg.get("min_price_change", 0.5)
        max_change = cfg.get("max_price_change", 7.0)
        min_amount = cfg.get("min_amount", 100_000_000)
        min_score = cfg.get("min_score", 1)  # 最低1分就能上榜

        # 筛选候选标的
        candidates = [
            s for s in market_data
            if min_change <= s.change_pct <= max_change and s.amount >= min_amount
        ]

        if not candidates:
            return []

        # 批量获取资金流向数据
        symbols = [s.symbol for s in candidates]
        flow_data = self._flow_fetcher.fetch_batch(symbols)

        results = []
        for stock in candidates:
            consecutive_days = flow_data.get(stock.symbol)
            if consecutive_days is None:
                continue

            # 评分
            score = calc_net_inflow_score(consecutive_days)
            if score < min_score:
                continue

            # 信号
            signals = []
            sfx = "「净流入」"
            if consecutive_days >= 18:
                signals.append(f"主力流量{consecutive_days}天" + sfx)
            elif consecutive_days >= 15:
                signals.append(f"持续流入{consecutive_days}天" + sfx)
            elif consecutive_days >= 13:
                signals.append(f"资金流入{consecutive_days}天" + sfx)
            elif consecutive_days >= 10:
                signals.append(f"资金关注{consecutive_days}天" + sfx)

            results.append(ScanResult(
                symbol=stock.symbol,
                name=stock.name,
                strategy=StrategyType.NET_INFLOW,
                score=score,
                signals=signals,
                data=stock,
                metadata={
                    "consecutive_inflow_days": consecutive_days,
                }
            ))

        results.sort(key=lambda x: x.score, reverse=True)
        self.logger.info(f"净流入策略: {len(results)} 只标的")
        return results
