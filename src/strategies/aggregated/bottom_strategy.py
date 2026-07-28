"""
底部策略 BottomStrategy (v2.8 Phase 1)

聚合：底部反弹(0.6) + 连续小阳吸筹(0.4)
"""
from .base import AggregatedStrategy
from ..technical.bottom_rebound import BottomReboundStrategy
from ..momentum.consecutive_positive import ConsecutivePositiveStrategy
from ...core.types import StrategyType


class BottomStrategy(AggregatedStrategy):
    """聚合策略：底部反弹 + 连续小阳吸筹"""

    @property
    def name(self) -> str:
        return "底部策略"

    @property
    def strategy_type(self) -> StrategyType:
        return StrategyType.BOTTOM

    def __init__(self):
        super().__init__()
        self._sub_strategies = [
            (BottomReboundStrategy(), 0.6),
            (ConsecutivePositiveStrategy(), 0.4),
        ]
