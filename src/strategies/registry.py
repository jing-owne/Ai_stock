"""
策略注册表
管理和获取所有可用策略
"""
from typing import Dict, Optional, List
from .base import BaseStrategy
from .momentum.volume_surge import VolumeSurgeStrategy
from .momentum.turnover_rank import TurnoverRankStrategy
from .momentum.multi_factor import MultiFactorStrategy
from .technical.ai_technical import AITechnicalStrategy
from .technical.institution import InstitutionStrategy
from ..core.types import StrategyType


class StrategyRegistry:
    """
    策略注册表
    
    单例模式，管理所有策略实例
    """
    
    _instance = None
    _strategies: Dict[StrategyType, BaseStrategy] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._register_strategies()
        return cls._instance
    
    def _register_strategies(self):
        """注册所有策略"""
        self._strategies = {
            StrategyType.VOLUME_SURGE: VolumeSurgeStrategy(),
            StrategyType.TURNOVER_RANK: TurnoverRankStrategy(),
            StrategyType.MULTI_FACTOR: MultiFactorStrategy(),
            StrategyType.AI_TECHNICAL: AITechnicalStrategy(),
            StrategyType.INSTITUTION: InstitutionStrategy(),
        }
    
    def get_strategy(self, strategy_type: StrategyType) -> Optional[BaseStrategy]:
        """获取指定策略"""
        return self._strategies.get(strategy_type)
    
    def list_strategies(self) -> List[str]:
        """列出所有可用策略"""
        return [s.name for s in self._strategies.values()]
    
    def get_strategy_types(self) -> List[StrategyType]:
        """获取所有策略类型"""
        return list(self._strategies.keys())
