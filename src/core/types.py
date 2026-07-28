"""
核心数据类型定义
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class StrategyType(Enum):
    """策略类型枚举 (v2.8 — 4聚合策略 + 向后兼容旧枚举)"""
    # 动量类（旧，_DEPRECATED — 仅供 aggregated 内部引用）
    VOLUME_BREAKOUT = "volume_breakout"       # → LaunchStrategy
    TURNOVER_RANK = "turnover_rank"           # → MoneyStrategy
    CONSECUTIVE_POSITIVE = "consecutive_positive"  # → BottomStrategy
    NET_INFLOW = "net_inflow"                 # → MoneyStrategy

    # 技术类（旧，_DEPRECATED — 仅供 aggregated 内部引用）
    MULTI_FACTOR = "multi_factor"             # → MoneyStrategy
    AI_TECHNICAL = "ai_technical"             # → TrendStrategy
    BOX_BREAKOUT = "box_breakout"             # → LaunchStrategy
    MA_TREND = "ma_trend"                     # → TrendStrategy
    BOTTOM_REBOUND = "bottom_rebound"         # → BottomStrategy
    TREND_CONFIRMATION = "trend_confirmation" # → TrendStrategy
    LAUNCH_FINGERPRINT = "launch_fingerprint" # → LaunchStrategy（内部0.35权重）

    # 4聚合策略（v2.8 主入口）
    BOTTOM = "bottom"       # 底部策略（底部反弹+连续小阳）
    LAUNCH = "launch"       # 启动策略（放量突破+箱体+指纹）
    TREND = "trend"         # 追涨策略（追涨确认+均线+AI技术面）
    MONEY = "money"         # 资金策略（资金净流入+成交额+多因子）

    # 综合
    COMPOSITE = "composite" # 综合策略（4聚合策略编排）

    # ── 向后兼容（标记为已合并）──
    VOLUME_SURGE = "volume_surge"             # → VOLUME_BREAKOUT
    INSTITUTION = "institution"               # → MULTI_FACTOR
    MA_DIVERGENCE = "ma_divergence"           # → MA_TREND
    RSI_OVERSOLD = "rsi_oversold"             # → BOTTOM_REBOUND
    NEW_HIGH_BREAK = "new_high_break"         # → VOLUME_BREAKOUT
    SUSTAINED_UPTREND = "sustained_uptrend"   # → MA_TREND


@dataclass
class StockData:
    """标的数据模型"""
    symbol: str                    # 代码
    name: str                      # 名称
    date: str                      # 日期 (YYYY-MM-DD)
    open: float                    # 开盘价
    high: float                    # 最高价
    low: float                     # 最低价
    close: float                   # 收盘价
    volume: float                  # 成交量
    amount: float                  # 成交额
    change_pct: float = 0.0        # 涨跌幅
    turn_rate: float = 0.0        # 换手率
    pe_ratio: Optional[float] = None  # 市盈率TTM ( 新增，供multi_factor使用)
    sector: Optional[str] = None      # 所属板块（供策略板块维度使用）
    
    def __post_init__(self):
        """数据验证"""
        if self.close <= 0:
            raise ValueError(f"收盘价必须大于0: {self.close}")
        if self.volume < 0:
            raise ValueError(f"成交量不能为负: {self.volume}")


@dataclass
class ScanResult:
    """扫描结果"""
    symbol: str                    # 代码
    name: str                      # 名称
    strategy: StrategyType         # 策略类型
    score: float                   # 综合评分 (0-100)
    signals: List[str]             # 交易信号列表
    data: Optional[StockData] = None  # 相关数据
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据
    
    @property
    def is_bullish(self) -> bool:
        """是否看多"""
        return (self.score >= 60 and len(self.signals) >= 2) or (
            self.score >= 80 and len(self.signals) >= 1
        )
    
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
