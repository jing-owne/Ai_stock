"""
测试策略模块 (v2.6.5)
"""
import pytest
from src.core.types import StockData, StrategyType
from src.strategies.momentum.volume_breakout import VolumeBreakoutStrategy
from src.strategies.momentum.turnover_rank import TurnoverRankStrategy
from src.strategies.momentum.multi_factor import MultiFactorStrategy


def create_test_stock(symbol: str, name: str, **kwargs) -> StockData:
    """创建测试用标的数据"""
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


class TestVolumeBreakoutStrategy:
    """测试放量突破策略"""

    def test_strategy_properties(self):
        strategy = VolumeBreakoutStrategy()
        assert "放量突破" in strategy.name
        assert strategy.strategy_type == StrategyType.VOLUME_BREAKOUT

    def test_execute_with_filter(self):
        strategy = VolumeBreakoutStrategy()
        stocks = [
            create_test_stock("600519", "贵州茅台", change_pct=5.0, amount=5000000000),
            create_test_stock("000858", "五粮液", change_pct=1.0, amount=100000000),
            create_test_stock("600036", "招商银行", change_pct=0.5, amount=200000000),
        ]
        params = {"min_volume_ratio": 2.0, "min_price_change": 1.0, "min_amount": 100000000}
        results = strategy.execute(stocks, params)
        assert isinstance(results, list)

    def test_calculate_score(self):
        strategy = VolumeBreakoutStrategy()
        stock = create_test_stock("600519", "贵州茅台")
        factors = {"volume_ratio": 3.0, "change_pct": 5.0}
        params = {"min_volume_ratio": 2.0, "min_price_change": 1.0, "min_amount": 100000000}
        score = strategy._calculate_score(**factors, params=params)
        assert 0 <= score <= 100


class TestTurnoverRankStrategy:

    def test_strategy_properties(self):
        strategy = TurnoverRankStrategy()
        assert "成交额" in strategy.name
        assert strategy.strategy_type == StrategyType.TURNOVER_RANK

    def test_execute_with_ranking(self):
        strategy = TurnoverRankStrategy()
        stocks = [
            create_test_stock("600519", "贵州茅台", amount=5000000000),
            create_test_stock("000858", "五粮液", amount=3000000000),
            create_test_stock("601318", "中国平安", amount=2000000000),
        ]
        params = {"top_n": 3, "min_amount": 100000000, "sort_desc": True}
        results = strategy.execute(stocks, params)
        if len(results) >= 2:
            assert results[0].score >= results[1].score


class TestMultiFactorStrategy:

    def test_strategy_properties(self):
        strategy = MultiFactorStrategy()
        assert "多因子" in strategy.name
        assert strategy.strategy_type == StrategyType.MULTI_FACTOR

    def test_execute_with_factors(self):
        strategy = MultiFactorStrategy()
        stocks = [
            create_test_stock("600519", "贵州茅台", change_pct=3.0, turn_rate=5.0),
            create_test_stock("000858", "五粮液", change_pct=1.5, turn_rate=2.0),
        ]
        params = {"volume_weight": 0.2, "price_weight": 0.3, "turnover_weight": 0.25,
                  "tech_weight": 0.25, "min_score": 50}
        results = strategy.execute(stocks, params)
        assert isinstance(results, list)
