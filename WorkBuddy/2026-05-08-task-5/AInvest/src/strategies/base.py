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

    def filter_quality_stocks(
        self,
        stocks: List[StockData],
        min_amount: float = 30000000  # 默认成交额3000W
    ) -> List[StockData]:
        """
        过滤优质股票（过滤688/ST/停牌/低成交额）

        Args:
            stocks: 股票列表
            min_amount: 最低成交额（默认3000万=30000000元）

        Returns:
            过滤后的股票列表
        """
        filtered = []
        for s in stocks:
            # 过滤科创板（688开头）
            if s.symbol.startswith("688"):
                continue
            # 过滤ST/*ST/SST/S*ST
            name_upper = s.name.upper()
            if any(kw in name_upper for kw in ["ST", "*ST", "SST", "S*ST", "S "]):
                continue
            # 过滤停牌（成交量为0）
            if s.volume <= 0:
                continue
            # 过滤成交额过低
            if s.amount < min_amount:
                continue
            filtered.append(s)
        return filtered
