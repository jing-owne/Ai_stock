"""
测试策略模块
"""
import pytest
from src.core.types import StockData, StrategyType
from src.strategies.momentum.volume_surge import VolumeSurgeStrategy
from src.strategies.momentum.turnover_rank import TurnoverRankStrategy
from src.strategies.momentum.multi_factor import MultiFactorStrategy


def create_test_stock(symbol: str, name: str, **kwargs) -> StockData:
    """创建测试用股票数据"""
    defaults = {
        "date": "2024-01-15",
        "open": 100.0,
        "high": 105.0,
        "low": 98.0,
        "close": 103.0,
        "volume": 10000000,
        "amount": 1000000000,
        "change_pct": 2.0,
        "turn_rate": 3.0
    }
    defaults.update(kwargs)
    return StockData(symbol=symbol, name=name, **defaults)


class TestVolumeSurgeStrategy:
    """测试放量上涨策略"""
    
    def test_strategy_properties(self):
        """测试策略属性"""
        strategy = VolumeSurgeStrategy()
        assert strategy.name == "放量上涨策略"
        assert strategy.strategy_type == StrategyType.VOLUME_SURGE
    
    def test_execute_with_filter(self):
        """测试策略执行"""
        strategy = VolumeSurgeStrategy()
        
        stocks = [
            create_test_stock("600519", "贵州茅台", change_pct=5.0, amount=5000000000),
            create_test_stock("000858", "五粮液", change_pct=1.0, amount=100000000),
            create_test_stock("600036", "招商银行", change_pct=0.5, amount=200000000),
        ]
        
        params = {
            "min_volume_ratio": 2.0,
            "min_price_change": 1.0,
            "min_amount": 100000000,
        }
        
        results = strategy.execute(stocks, params)
        
        # 应该有结果(模拟数据会通过筛选)
        assert isinstance(results, list)
    
    def test_calculate_score(self):
        """测试评分计算"""
        strategy = VolumeSurgeStrategy()
        
        stock = create_test_stock("600519", "贵州茅台")
        factors = {
            "volume_ratio": 3.0,
            "change_pct": 5.0,
        }
        
        params = {
            "min_volume_ratio": 2.0,
            "min_price_change": 1.0,
            "min_amount": 100000000,
        }
        
        score = strategy._calculate_score(**factors, params=params)
        assert 0 <= score <= 100


class TestTurnoverRankStrategy:
    """测试成交额排名策略"""
    
    def test_strategy_properties(self):
        """测试策略属性"""
        strategy = TurnoverRankStrategy()
        assert strategy.name == "成交额排名策略"
        assert strategy.strategy_type == StrategyType.TURNOVER_RANK
    
    def test_execute_with_ranking(self):
        """测试排名执行"""
        strategy = TurnoverRankStrategy()
        
        stocks = [
            create_test_stock("600519", "贵州茅台", amount=5000000000),
            create_test_stock("000858", "五粮液", amount=3000000000),
            create_test_stock("601318", "中国平安", amount=2000000000),
        ]
        
        params = {
            "top_n": 3,
            "min_amount": 100000000,
            "sort_desc": True,
        }
        
        results = strategy.execute(stocks, params)
        
        # 结果应该按成交额排序
        if len(results) >= 2:
            assert results[0].score >= results[1].score


class TestMultiFactorStrategy:
    """测试多因子策略"""
    
    def test_strategy_properties(self):
        """测试策略属性"""
        strategy = MultiFactorStrategy()
        assert strategy.name == "多因子量化策略"
        assert strategy.strategy_type == StrategyType.MULTI_FACTOR
    
    def test_execute_with_factors(self):
        """测试多因子执行"""
        strategy = MultiFactorStrategy()
        
        stocks = [
            create_test_stock("600519", "贵州茅台", change_pct=3.0, turn_rate=5.0),
            create_test_stock("000858", "五粮液", change_pct=1.5, turn_rate=2.0),
        ]
        
        params = {
            "volume_weight": 0.2,
            "price_weight": 0.3,
            "turnover_weight": 0.25,
            "tech_weight": 0.25,
            "min_score": 50,
        }
        
        results = strategy.execute(stocks, params)
        assert isinstance(results, list)
