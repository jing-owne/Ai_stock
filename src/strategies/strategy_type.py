"""
策略类型定义
"""
from enum import Enum


class StrategyType(Enum):
    """策略类型枚举"""
    VOLUME_SURGE = "volume_surge"           # 放量上涨策略
    TURNOVER_RANK = "turnover_rank"        # 成交额排名策略
    MULTI_FACTOR = "multi_factor"           # 多因子策略
    AI_TECHNICAL = "ai_technical"          # AI技术面策略
    INSTITUTION = "institution"             # 机构追踪策略
    STRATEGY_COUNT = "strategy_count"       # 策略数量评分
    MYHHUB = "myhhub"                       # 基本面因子
    HIKYUU = "hikyuu"                     # 趋势策略
    NORTHSTAR = "northstar"                 # 北向资金策略
    
    @classmethod
    def from_string(cls, value: str) -> "StrategyType":
        """从字符串创建策略类型"""
        for strategy in cls:
            if strategy.value == value.lower():
                return strategy
        raise ValueError(f"未知的策略类型: {value}")
    
    @classmethod
    def list_all(cls) -> list:
        """列出所有策略类型"""
        return [s.value for s in cls]
