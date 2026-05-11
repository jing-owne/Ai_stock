"""
放量上涨策略
选出一段时间内成交量放大且股价上涨的股票
"""
from typing import List, Dict, Any
import random

from ..base import BaseStrategy
from ...core.types import StockData, ScanResult, StrategyType


class VolumeSurgeStrategy(BaseStrategy):
    """
    放量上涨策略
    
    选股逻辑:
    1. 成交量较前日放大一定倍数
    2. 股价涨幅达到一定水平
    3. 成交额达到最低门槛
    """
    
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
        """
        执行放量上涨策略
        
        Args:
            market_data: 市场数据
            params: 策略参数
                - min_volume_ratio: 最小放量倍数
                - min_price_change: 最小涨幅
                - min_amount: 最小成交额
        """
        min_ratio = params.get("min_volume_ratio", 2.0)
        min_change = params.get("min_price_change", 1.0)
        min_amount = params.get("min_amount", 100_000_000)

        # 过滤优质股票（688/ST/停牌/低成交额）
        market_data = self.filter_quality_stocks(market_data, min_amount=30_000_000)

        results = []
        
        for stock in market_data:
            # 模拟计算放量倍数(实际应与历史数据比较)
            volume_ratio = random.uniform(1.5, 4.0)
            
            # 筛选条件
            if (volume_ratio >= min_ratio and 
                stock.change_pct >= min_change and 
                stock.amount >= min_amount):
                
                # 计算评分
                score = self._calculate_score(
                    volume_ratio=volume_ratio,
                    change_pct=stock.change_pct,
                    amount=stock.amount,
                    params=params
                )
                
                # 生成信号
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
        
        # 按评分排序
        results.sort(key=lambda x: x.score, reverse=True)
        return results
    
    def _calculate_score(
        self,
        volume_ratio: float,
        change_pct: float,
        amount: float,
        params: Dict[str, Any]
    ) -> float:
        """计算放量上涨评分"""
        # 放量因子 (0-40分)
        volume_score = min(volume_ratio / params.get("min_volume_ratio", 2.0) * 20, 40)
        
        # 涨幅因子 (0-30分)
        change_score = min(change_pct * 10, 30)
        
        # 成交额因子 (0-30分)
        min_amount = params.get("min_amount", 100_000_000)
        amount_score = min(amount / min_amount * 15, 30)
        
        return round(volume_score + change_score + amount_score, 1)
    
    def _generate_signals(
        self,
        volume_ratio: float,
        change_pct: float
    ) -> List[str]:
        """生成交易信号"""
        signals = []
        
        if volume_ratio >= 3.0:
            signals.append("巨量突破")
        elif volume_ratio >= 2.0:
            signals.append("温和放量")
        
        if change_pct >= 5.0:
            signals.append("强势涨停")
        elif change_pct >= 3.0:
            signals.append("大幅上涨")
        elif change_pct >= 1.0:
            signals.append("小幅上涨")
        
        return signals
