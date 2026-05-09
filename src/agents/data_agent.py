"""
数据采集Agent
负责从各种数据源获取股票市场数据
"""
import logging
import random
from typing import List, Optional
from datetime import datetime, timedelta

from ..core.types import StockData
from ..core.config import Config


class DataAgent:
    """
    数据采集Agent
    
    支持多种数据源: Sina, Tushare, EastMoney
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger("AInvest.DataAgent")
        self._cache = {}
        self._cache_time = {}
        
    def fetch_market_data(
        self,
        date: Optional[str] = None,
        include_index: bool = False
    ) -> List[StockData]:
        """
        获取市场股票数据
        
        Args:
            date: 日期 (YYYY-MM-DD)，默认今天
            include_index: 是否包含指数
            
        Returns:
            StockData列表
        """
        date = date or datetime.now().strftime("%Y-%m-%d")
        
        # 检查缓存
        cache_key = f"market_data_{date}_{include_index}"
        if self.config.data_source.cache_enabled and cache_key in self._cache:
            if self._is_cache_valid(cache_key):
                self.logger.debug("使用缓存数据")
                return self._cache[cache_key]
        
        # 根据数据源获取数据
        provider = self.config.data_source.provider
        
        if provider == "sina":
            data = self._fetch_from_sina(date, include_index)
        elif provider == "tushare":
            data = self._fetch_from_tushare(date, include_index)
        elif provider == "eastmoney":
            data = self._fetch_from_eastmoney(date, include_index)
        else:
            # 模拟数据用于演示
            data = self._generate_mock_data(date)
        
        # 更新缓存
        if self.config.data_source.cache_enabled:
            self._cache[cache_key] = data
            self._cache_time[cache_key] = datetime.now()
        
        return data
    
    def fetch_stock_data(self, symbol: str, days: int = 30) -> List[StockData]:
        """
        获取单只股票历史数据
        
        Args:
            symbol: 股票代码
            days: 历史天数
            
        Returns:
            StockData列表
        """
        self.logger.info(f"获取股票{symbol}最近{days}天数据")
        
        # 模拟历史数据
        data = []
        base_date = datetime.now()
        
        for i in range(days):
            date = (base_date - timedelta(days=days-i-1)).strftime("%Y-%m-%d")
            base_price = random.uniform(10, 100)
            
            stock = StockData(
                symbol=symbol,
                name=f"股票{symbol}",
                date=date,
                open=base_price * random.uniform(0.98, 1.02),
                high=base_price * random.uniform(1.0, 1.05),
                low=base_price * random.uniform(0.95, 1.0),
                close=base_price,
                volume=random.uniform(1000000, 10000000),
                amount=random.uniform(100000000, 1000000000),
                change_pct=random.uniform(-5, 5),
                turn_rate=random.uniform(1, 10)
            )
            data.append(stock)
        
        return data
    
    def _fetch_from_sina(self, date: str, include_index: bool) -> List[StockData]:
        """从新浪获取数据"""
        self.logger.debug("从新浪获取数据...")
        # 实际实现需要使用requests库调用新浪API
        return self._generate_mock_data(date)
    
    def _fetch_from_tushare(self, date: str, include_index: bool) -> List[StockData]:
        """从Tushare获取数据"""
        self.logger.debug("从Tushare获取数据...")
        # 实际实现需要使用tushare库
        return self._generate_mock_data(date)
    
    def _fetch_from_eastmoney(self, date: str, include_index: bool) -> List[StockData]:
        """从东方财富获取数据"""
        self.logger.debug("从东方财富获取数据...")
        # 实际实现需要使用requests库调用东方财富API
        return self._generate_mock_data(date)
    
    def _generate_mock_data(self, date: str) -> List[StockData]:
        """生成模拟数据用于演示"""
        symbols = [
            ("600519", "贵州茅台"),
            ("000858", "五粮液"),
            ("601318", "中国平安"),
            ("000333", "美的集团"),
            ("002475", "立讯精密"),
            ("300750", "宁德时代"),
            ("600036", "招商银行"),
            ("000001", "平安银行"),
            ("601888", "中国中免"),
            ("300059", "东方财富"),
            ("002594", "比亚迪"),
            ("600900", "长江电力"),
            ("601012", "隆基绿能"),
            ("002352", "顺丰控股"),
            ("600276", "恒瑞医药"),
            ("000725", "京东方A"),
            ("601166", "兴业银行"),
            ("600887", "伊利股份"),
            ("002714", "牧原股份"),
            ("300015", "爱尔眼科"),
        ]
        
        data = []
        for symbol, name in symbols:
            base_price = random.uniform(10, 200)
            
            stock = StockData(
                symbol=symbol,
                name=name,
                date=date,
                open=round(base_price * random.uniform(0.98, 1.02), 2),
                high=round(base_price * random.uniform(1.0, 1.08), 2),
                low=round(base_price * random.uniform(0.92, 1.0), 2),
                close=round(base_price, 2),
                volume=random.uniform(5000000, 50000000),
                amount=random.uniform(100000000, 5000000000),
                change_pct=round(random.uniform(-3, 5), 2),
                turn_rate=round(random.uniform(1, 15), 2)
            )
            data.append(stock)
        
        return data
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """检查缓存是否有效"""
        if cache_key not in self._cache_time:
            return False
        
        elapsed = (datetime.now() - self._cache_time[cache_key]).total_seconds()
        return elapsed < self.config.data_source.cache_ttl
    
    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
        self._cache_time.clear()
        self.logger.info("缓存已清空")
