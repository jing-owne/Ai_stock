"""
成交额排名策略
选取成交额最高的一批股票
"""
from typing import List, Dict, Any

from ..base import BaseStrategy
from ...core.types import StockData, ScanResult, StrategyType


class TurnoverRankStrategy(BaseStrategy):
    """
    成交额排名策略
    
    选股逻辑:
    1. 按成交额降序排列
    2. 取前N名
    3. 结合涨跌幅筛选
    """
    
    @property
    def name(self) -> str:
        return "成交额排名策略"
    
    @property
    def strategy_type(self) -> StrategyType:
        return StrategyType.TURNOVER_RANK
    
    def execute(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> List[ScanResult]:
        """
        执行成交额排名策略
        """
        top_n = params.get("top_n", 20)
        min_amount = params.get("min_amount", 500_000_000)
        sort_desc = params.get("sort_desc", True)
        
        # 按成交额排序
        sorted_stocks = sorted(
            market_data,
            key=lambda x: x.amount,
            reverse=sort_desc
        )
        
        # 取前N名
        top_stocks = sorted_stocks[:top_n]
        
        # 筛选最低成交额
        filtered_stocks = [s for s in top_stocks if s.amount >= min_amount]
        
        results = []
        max_amount = max(s.amount for s in filtered_stocks) if filtered_stocks else 1
        
        for rank, stock in enumerate(filtered_stocks, 1):
            score = self._calculate_score(
                rank=rank,
                amount=stock.amount,
                max_amount=max_amount,
                change_pct=stock.change_pct
            )
            
            signals = self._generate_signals(rank, stock)
            
            results.append(ScanResult(
                symbol=stock.symbol,
                name=stock.name,
                strategy=self.strategy_type,
                score=score,
                signals=signals,
                data=stock,
                metadata={
                    "rank": rank,
                    "amount": stock.amount,
                }
            ))
        
        return results
    
    def _calculate_score(
        self,
        rank: int,
        amount: float,
        max_amount: float,
        change_pct: float
    ) -> float:
        """计算成交额排名评分"""
        # 排名因子 (0-50分)
        rank_score = max(50 - (rank - 1) * 2.5, 10)
        
        # 成交额因子 (0-30分)
        amount_score = (amount / max_amount) * 30
        
        # 涨幅因子 (0-20分)
        change_score = min(max(change_pct, 0) * 5, 20)
        
        return round(rank_score + amount_score + change_score, 1)
    
    def _generate_signals(self, rank: int, stock: StockData) -> List[str]:
        """生成交易信号"""
        signals = []
        
        if rank <= 5:
            signals.append("成交额TOP5")
        elif rank <= 10:
            signals.append("成交活跃")
        
        if stock.change_pct > 0:
            signals.append("资金净流入")
        
        if stock.turn_rate > 5:
            signals.append("高换手率")
        
        return signals
