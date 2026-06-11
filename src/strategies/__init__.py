"""
策略模块 — 10大独立策略（v2.6.8）
动量类: volume_breakout, turnover_rank, multi_factor, consecutive_positive, net_inflow, trend_confirmation
技术类: ai_technical, box_breakout, ma_trend, bottom_rebound
"""
from .base import BaseStrategy
from .momentum.volume_breakout import VolumeBreakoutStrategy
from .momentum.turnover_rank import TurnoverRankStrategy
from .momentum.multi_factor import MultiFactorStrategy
from .momentum.consecutive_positive import ConsecutivePositiveStrategy
from .momentum.net_inflow import NetInflowStrategy
from .momentum.trend_confirmation import TrendConfirmationStrategy
from .technical.ai_technical import AITechnicalStrategy
from .technical.box_breakout import BoxBreakoutStrategy
from .technical.ma_trend import MATrendStrategy
from .technical.bottom_rebound import BottomReboundStrategy
from .registry import StrategyRegistry

__all__ = [
    "BaseStrategy",
    "VolumeBreakoutStrategy",
    "TurnoverRankStrategy",
    "MultiFactorStrategy",
    "ConsecutivePositiveStrategy",
    "NetInflowStrategy",
    "TrendConfirmationStrategy",
    "AITechnicalStrategy",
    "BoxBreakoutStrategy",
    "MATrendStrategy",
    "BottomReboundStrategy",
    "StrategyRegistry",
]
