"""
测试数据类型
"""
import pytest
from datetime import datetime

from src.core.types import StockData, ScanResult, MarketAnalysis, StrategyType


class TestStockData:
    """测试StockData类"""
    
    def test_create_valid_stock_data(self):
        """测试创建有效的股票数据"""
        stock = StockData(
            symbol="600519",
            name="贵州茅台",
            date="2024-01-15",
            open=1800.0,
            high=1850.0,
            low=1790.0,
            close=1840.0,
            volume=1000000,
            amount=1800000000,
            change_pct=2.5,
            turn_rate=0.5
        )
        
        assert stock.symbol == "600519"
        assert stock.name == "贵州茅台"
        assert stock.close == 1840.0
        assert stock.change_pct == 2.5
    
    def test_invalid_close_price(self):
        """测试无效的收盘价"""
        with pytest.raises(ValueError):
            StockData(
                symbol="600519",
                name="贵州茅台",
                date="2024-01-15",
                open=1800.0,
                high=1850.0,
                low=1790.0,
                close=0,  # 无效价格
                volume=1000000,
                amount=1800000000
            )
    
    def test_negative_volume(self):
        """测试负数成交量"""
        with pytest.raises(ValueError):
            StockData(
                symbol="600519",
                name="贵州茅台",
                date="2024-01-15",
                open=1800.0,
                high=1850.0,
                low=1790.0,
                close=1840.0,
                volume=-1000,  # 负数
                amount=1800000000
            )


class TestScanResult:
    """测试ScanResult类"""
    
    def test_create_scan_result(self):
        """测试创建扫描结果"""
        result = ScanResult(
            symbol="600519",
            name="贵州茅台",
            strategy=StrategyType.VOLUME_SURGE,
            score=85.5,
            signals=["巨量突破", "强势涨停"]
        )
        
        assert result.symbol == "600519"
        assert result.score == 85.5
        assert len(result.signals) == 2
        assert result.is_bullish is True
    
    def test_is_bullish_threshold(self):
        """测试看多判断阈值"""
        # 高分但信号少 - 不看多
        result_low_signals = ScanResult(
            symbol="600519",
            name="贵州茅台",
            strategy=StrategyType.VOLUME_SURGE,
            score=75.0,
            signals=["信号1"]  # 只有1个信号
        )
        assert result_low_signals.is_bullish is False
        
        # 低分但信号多 - 不看多
        result_low_score = ScanResult(
            symbol="600519",
            name="贵州茅台",
            strategy=StrategyType.VOLUME_SURGE,
            score=55.0,
            signals=["信号1", "信号2", "信号3"]  # 3个信号
        )
        assert result_low_score.is_bullish is False
    
    def test_to_dict(self):
        """测试转换为字典"""
        result = ScanResult(
            symbol="600519",
            name="贵州茅台",
            strategy=StrategyType.VOLUME_SURGE,
            score=85.5,
            signals=["巨量突破"]
        )
        
        d = result.to_dict()
        assert d["symbol"] == "600519"
        assert d["strategy"] == "volume_surge"
        assert d["is_bullish"] is True


class TestMarketAnalysis:
    """测试MarketAnalysis类"""
    
    def test_create_market_analysis(self):
        """测试创建市场分析"""
        analysis = MarketAnalysis(
            date="2024-01-15",
            market_sentiment="乐观",
            sector_heat={"新能源": 0.85, "消费": 0.72},
            risk_level="中",
            recommendations=["关注热点板块", "控制仓位"],
            summary="市场情绪较好"
        )
        
        assert analysis.market_sentiment == "乐观"
        assert analysis.risk_level == "中"
        assert len(analysis.sector_heat) == 2
