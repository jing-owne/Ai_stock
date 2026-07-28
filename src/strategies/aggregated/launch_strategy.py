"""
启动策略 LaunchStrategy (v2.8 Phase 1)

聚合：放量突破(0.35) + 箱体突破(0.30) + 启动指纹(0.35)

指纹策略不在 SUB_STRATEGIES 中单独注册，仅在 LaunchStrategy 内部聚合
（避免被执行两次；语义上指纹是启动信号的子模块）。
"""
from .base import AggregatedStrategy
from ..momentum.volume_breakout import VolumeBreakoutStrategy
from ..technical.box_breakout import BoxBreakoutStrategy
from ..technical.launch_fingerprint_strategy import LaunchFingerprintStrategy
from ...core.types import StrategyType


class LaunchStrategy(AggregatedStrategy):
    """聚合策略：放量突破 + 箱体突破 + 启动指纹"""

    @property
    def name(self) -> str:
        return "启动策略"

    @property
    def strategy_type(self) -> StrategyType:
        return StrategyType.LAUNCH

    def __init__(self):
        super().__init__()
        self._sub_strategies = [
            (VolumeBreakoutStrategy(), 0.35),
            (BoxBreakoutStrategy(), 0.30),
            (LaunchFingerprintStrategy(), 0.35),
        ]
