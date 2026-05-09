"""
多因子量化策略
综合考虑多个因子进行选股
"""
from typing import List, Dict, Any
import random

from ..base import BaseStrategy
from ...core.types import StockData, ScanResult, StrategyType


class MultiFactorStrategy(BaseStrategy):
    """
    多因子量化策略
    
    综合评分因子:
    - 成交量因子
    - 价格因子
    - 换手率因子
    - 技术面因子
    """
    
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
        """
        执行多因子策略
        """
        volume_weight = params.get("volume_weight", 0.2)
        price_weight = params.get("price_weight", 0.3)
        turnover_weight = params.get("turnover_weight", 0.25)
        tech_weight = params.get("tech_weight", 0.25)
        min_score = params.get("min_score", 60)
        
        results = []
        
        # 计算各因子的基准值
        max_amount = max(s.amount for s in market_data) if market_data else 1
        max_change = max(s.change_pct for s in market_data) if market_data else 1
        
        for stock in market_data:
            # 计算各因子得分
            factors = {}
            
            # 成交量因子
            factors["volume"] = (stock.amount / max_amount) * 100
            
            # 价格因子 (涨幅归一化)
            factors["price"] = max(0, min(stock.change_pct / max_change * 100 if max_change > 0 else 50, 100))
            
            # 换手率因子
            factors["turnover"] = min(stock.turn_rate * 10, 100)
            
            # 技术面因子 (模拟)
            factors["technical"] = random.uniform(60, 90)
            
            # 综合评分
            total_score = (
                factors["volume"] * volume_weight +
                factors["price"] * price_weight +
                factors["turnover"] * turnover_weight +
                factors["technical"] * tech_weight
            )
            
            # 筛选最低分
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
        """生成交易信号"""
        signals = []
        
        if factors["volume"] >= 80:
            signals.append("量能充沛")
        elif factors["volume"] >= 60:
            signals.append("量能较好")
        
        if factors["price"] >= 80:
            signals.append("涨幅领先")
        
        if factors["turnover"] >= 80:
            signals.append("换手活跃")
        
        if factors["technical"] >= 80:
            signals.append("技术形态好")
        
        return signals
