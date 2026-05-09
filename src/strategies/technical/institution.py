"""
机构追踪策略
追踪机构持仓和动向
"""
from typing import List, Dict, Any
import random

from ..base import BaseStrategy
from ...core.types import StockData, ScanResult, StrategyType


class InstitutionStrategy(BaseStrategy):
    """
    机构追踪策略
    
    关注:
    - 机构持仓变化
    - 机构调研动向
    - 机构评级调整
    """
    
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
        """
        执行机构追踪策略
        """
        min_inst_count = params.get("min_inst_count", 3)
        min_inst_ratio = params.get("min_inst_ratio", 0.05)
        
        results = []
        
        for stock in market_data:
            # 模拟机构数据
            inst_count = random.randint(1, 10)
            inst_ratio = random.uniform(0.02, 0.15)
            inst_change = random.uniform(-5, 10)
            
            # 筛选条件
            if inst_count >= min_inst_count and inst_ratio >= min_inst_ratio:
                score = self._calculate_score(
                    inst_count=inst_count,
                    inst_ratio=inst_ratio,
                    inst_change=inst_change,
                    change_pct=stock.change_pct
                )
                
                signals = self._generate_signals(
                    inst_count,
                    inst_ratio,
                    inst_change
                )
                
                results.append(ScanResult(
                    symbol=stock.symbol,
                    name=stock.name,
                    strategy=self.strategy_type,
                    score=score,
                    signals=signals,
                    data=stock,
                    metadata={
                        "inst_count": inst_count,
                        "inst_ratio": round(inst_ratio * 100, 2),
                        "inst_change": round(inst_change, 2),
                    }
                ))
        
        results.sort(key=lambda x: x.score, reverse=True)
        return results
    
    def _calculate_score(
        self,
        inst_count: int,
        inst_ratio: float,
        inst_change: float,
        change_pct: float
    ) -> float:
        """计算机构评分"""
        # 机构数量因子 (0-30分)
        count_score = min(inst_count * 3, 30)
        
        # 机构持仓因子 (0-30分)
        ratio_score = min(inst_ratio * 200, 30)
        
        # 机构增减持因子 (0-20分)
        change_score = max(10 + inst_change * 2, 0) if inst_change > 0 else max(10 + inst_change * 1, 0)
        
        # 价格表现因子 (0-20分)
        price_score = min(max(change_pct * 4, 0), 20)
        
        return round(count_score + ratio_score + change_score + price_score, 1)
    
    def _generate_signals(
        self,
        inst_count: int,
        inst_ratio: float,
        inst_change: float
    ) -> List[str]:
        """生成机构信号"""
        signals = []
        
        if inst_count >= 7:
            signals.append("多家机构重仓")
        elif inst_count >= 4:
            signals.append("机构关注")
        
        if inst_ratio >= 0.10:
            signals.append("机构高比例持仓")
        
        if inst_change >= 5:
            signals.append("机构大幅增持")
        elif inst_change >= 2:
            signals.append("机构温和增持")
        elif inst_change <= -2:
            signals.append("机构小幅减持")
        
        return signals
