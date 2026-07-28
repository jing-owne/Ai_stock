"""
追涨策略 TrendStrategy (v2.8 Phase 1)

聚合：追涨确认(0.35) + 均线趋势(0.35) + AI技术面(0.30)
"""
from .base import AggregatedStrategy
from ..momentum.trend_confirmation import TrendConfirmationStrategy
from ..technical.ma_trend import MATrendStrategy
from ..technical.ai_technical import AITechnicalStrategy
from ...core.types import StrategyType


class TrendStrategy(AggregatedStrategy):
    """聚合策略：追涨确认 + 均线趋势 + AI技术面"""

    @property
    def name(self) -> str:
        return "追涨策略"

    @property
    def strategy_type(self) -> StrategyType:
        return StrategyType.TREND

    def __init__(self):
        super().__init__()
        self._sub_strategies = [
            (TrendConfirmationStrategy(), 0.35),
            (MATrendStrategy(), 0.35),
            (AITechnicalStrategy(), 0.30),
        ]
