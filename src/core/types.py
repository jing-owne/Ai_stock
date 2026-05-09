"""
核心数据类型定义
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class StrategyType(Enum):
    """策略类型枚举"""
    VOLUME_SURGE = "volume_surge"           # 放量上涨策略
    TURNOVER_RANK = "turnover_rank"         # 成交额排名策略
    MULTI_FACTOR = "multi_factor"           # 多因子策略
    AI_TECHNICAL = "ai_technical"           # AI技术面策略
    INSTITUTION = "institution"             # 机构追踪策略


@dataclass
class StockData:
    """股票数据模型"""
    symbol: str                    # 股票代码
    name: str                      # 股票名称
    date: str                      # 日期 (YYYY-MM-DD)
    open: float                    # 开盘价
    high: float                    # 最高价
    low: float                     # 最低价
    close: float                   # 收盘价
    volume: float                  # 成交量
    amount: float                  # 成交额
    change_pct: float = 0.0        # 涨跌幅
    turn_rate: float = 0.0        # 换手率
    
    def __post_init__(self):
        """数据验证"""
        if self.close <= 0:
            raise ValueError(f"收盘价必须大于0: {self.close}")
        if self.volume < 0:
            raise ValueError(f"成交量不能为负: {self.volume}")


@dataclass
class ScanResult:
    """扫描结果"""
    symbol: str                    # 股票代码
    name: str                      # 股票名称
    strategy: StrategyType         # 策略类型
    score: float                   # 综合评分 (0-100)
    signals: List[str]             # 交易信号列表
    data: Optional[StockData] = None  # 相关数据
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据
    
    @property
    def is_bullish(self) -> bool:
        """是否看多"""
        return self.score >= 60 and len(self.signals) >= 2
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "symbol": self.symbol,
            "name": self.name,
            "strategy": self.strategy.value,
            "score": self.score,
            "signals": self.signals,
            "is_bullish": self.is_bullish,
            "metadata": self.metadata
        }


@dataclass
class MarketAnalysis:
    """市场分析报告"""
    date: str                      # 分析日期
    market_sentiment: str          # 市场情绪 (乐观/中性/悲观)
    sector_heat: Dict[str, float]  # 板块热度
    risk_level: str                # 风险等级 (高/中/低)
    recommendations: List[str]      # 建议
    summary: str                    # 总结
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "date": self.date,
            "market_sentiment": self.market_sentiment,
            "sector_heat": self.sector_heat,
            "risk_level": self.risk_level,
            "recommendations": self.recommendations,
            "summary": self.summary,
            "timestamp": self.timestamp.isoformat()
        }
