"""
策略注册表

所有策略均在此注册，支持独立增删。
9大策略（v2.6.5）+ 1个综合策略。
"""
from typing import Dict, Type
from ..core.types import StrategyType

from .base import BaseStrategy
from .composite_strategy import CompositeStrategy

# 动量类
from .momentum.volume_breakout import VolumeBreakoutStrategy
from .momentum.turnover_rank import TurnoverRankStrategy
from .momentum.multi_factor import MultiFactorStrategy
from .momentum.consecutive_positive import ConsecutivePositiveStrategy
from .momentum.net_inflow import NetInflowStrategy

# 技术类
from .technical.ai_technical import AITechnicalStrategy
from .technical.box_breakout import BoxBreakoutStrategy
from .technical.ma_trend import MATrendStrategy
from .technical.bottom_rebound import BottomReboundStrategy


class StrategyRegistry:
    """策略注册表 — 所有策略在此注册，支持增删"""

    _strategies: Dict[StrategyType, BaseStrategy] = {}

    @classmethod
    def initialize(cls):
        """初始化所有策略（单例）"""
        if cls._strategies:
            return

        # ── 9大独立策略 ──
        cls._strategies[StrategyType.VOLUME_BREAKOUT] = VolumeBreakoutStrategy()
        cls._strategies[StrategyType.TURNOVER_RANK] = TurnoverRankStrategy()
        cls._strategies[StrategyType.MULTI_FACTOR] = MultiFactorStrategy()
        cls._strategies[StrategyType.AI_TECHNICAL] = AITechnicalStrategy()
        cls._strategies[StrategyType.BOX_BREAKOUT] = BoxBreakoutStrategy()
        cls._strategies[StrategyType.MA_TREND] = MATrendStrategy()
        cls._strategies[StrategyType.BOTTOM_REBOUND] = BottomReboundStrategy()
        cls._strategies[StrategyType.CONSECUTIVE_POSITIVE] = ConsecutivePositiveStrategy()
        cls._strategies[StrategyType.NET_INFLOW] = NetInflowStrategy()
        # 综合策略
        cls._strategies[StrategyType.COMPOSITE] = CompositeStrategy()

        # ── 向后兼容映射 ──
        cls._strategies[StrategyType.VOLUME_SURGE] = cls._strategies[StrategyType.VOLUME_BREAKOUT]
        cls._strategies[StrategyType.INSTITUTION] = cls._strategies[StrategyType.MULTI_FACTOR]
        cls._strategies[StrategyType.MA_DIVERGENCE] = cls._strategies[StrategyType.MA_TREND]
        cls._strategies[StrategyType.RSI_OVERSOLD] = cls._strategies[StrategyType.BOTTOM_REBOUND]
        cls._strategies[StrategyType.NEW_HIGH_BREAK] = cls._strategies[StrategyType.VOLUME_BREAKOUT]
        cls._strategies[StrategyType.SUSTAINED_UPTREND] = cls._strategies[StrategyType.MA_TREND]

    @classmethod
    def get_strategy(cls, strategy_type: StrategyType) -> BaseStrategy:
        """获取策略实例"""
        cls.initialize()
        return cls._strategies.get(strategy_type)

    @classmethod
    def register(cls, strategy_type: StrategyType, strategy: BaseStrategy):
        """注册/替换策略"""
        cls._strategies[strategy_type] = strategy

    @classmethod
    def unregister(cls, strategy_type: StrategyType):
        """卸载策略"""
        cls._strategies.pop(strategy_type, None)

    @classmethod
    def list_all(cls) -> Dict[StrategyType, BaseStrategy]:
        """列出所有已注册策略"""
        cls.initialize()
        return dict(cls._strategies)

    @classmethod
    def list_active(cls) -> Dict[StrategyType, BaseStrategy]:
        """列出活跃策略（排除向后兼容的重复映射）"""
        cls.initialize()
        active_types = {
            StrategyType.VOLUME_BREAKOUT, StrategyType.TURNOVER_RANK,
            StrategyType.MULTI_FACTOR, StrategyType.AI_TECHNICAL,
            StrategyType.BOX_BREAKOUT, StrategyType.MA_TREND,
            StrategyType.BOTTOM_REBOUND, StrategyType.CONSECUTIVE_POSITIVE,
            StrategyType.NET_INFLOW, StrategyType.COMPOSITE,
        }
        return {k: v for k, v in cls._strategies.items() if k in active_types}
