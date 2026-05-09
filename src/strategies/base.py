"""
策略基类
所有量化策略都应继承此基类
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any

from ..core.types import StockData, ScanResult, StrategyType


class BaseStrategy(ABC):
    """
    策略基类
    
    定义策略接口和通用功能
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """策略名称"""
        pass
    
    @property
    @abstractmethod
    def strategy_type(self) -> StrategyType:
        """策略类型"""
        pass
    
    @abstractmethod
    def execute(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> List[ScanResult]:
        """
        执行策略
        
        Args:
            market_data: 市场数据
            params: 策略参数
            
        Returns:
            符合条件的股票列表
        """
        pass
    
    def calculate_score(
        self,
        stock: StockData,
        factors: Dict[str, float]
    ) -> float:
        """
        计算股票评分
        
        Args:
            stock: 股票数据
            factors: 各因子评分
            
        Returns:
            综合评分 (0-100)
        """
        if not factors:
            return 50.0
        
        return sum(factors.values()) / len(factors)
    
    def filter_by_amount(
        self,
        stocks: List[StockData],
        min_amount: float
    ) -> List[StockData]:
        """按成交额筛选"""
        return [s for s in stocks if s.amount >= min_amount]
    
    def filter_by_change(
        self,
        stocks: List[StockData],
        min_change: float = 0
    ) -> List[StockData]:
        """按涨跌幅筛选"""
        return [s for s in stocks if s.change_pct >= min_change]
    
    def sort_by_amount(
        self,
        stocks: List[StockData],
        descending: bool = True
    ) -> List[StockData]:
        """按成交额排序"""
        return sorted(stocks, key=lambda x: x.amount, reverse=descending)
