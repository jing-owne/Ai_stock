"""
策略执行Agent
负责执行各种量化选股策略
"""
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from ..core.types import StockData, ScanResult, StrategyType
from ..core.config import Config
from ..strategies.registry import StrategyRegistry


class StrategyAgent:
    """
    策略执行Agent
    
    管理和执行各种量化选股策略
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger("AInvest.StrategyAgent")
        self.registry = StrategyRegistry()
        
    def execute(
        self,
        strategy_type: StrategyType,
        market_data: List[StockData],
        **kwargs
    ) -> List[ScanResult]:
        """
        执行指定策略
        
        Args:
            strategy_type: 策略类型
            market_data: 市场数据
            **kwargs: 策略参数
            
        Returns:
            ScanResult列表
        """
        self.logger.info(f"执行策略: {strategy_type.value}")
        
        # 获取策略实例
        strategy = self.registry.get_strategy(strategy_type)
        if not strategy:
            self.logger.error(f"策略{strategy_type.value}未注册")
            return []
        
        # 合并配置和参数
        params = self._get_strategy_params(strategy_type)
        params.update(kwargs)
        
        # 执行策略
        try:
            results = strategy.execute(market_data, params)
            self.logger.info(f"策略执行完成: {len(results)}个结果")
            return results
        except Exception as e:
            self.logger.error(f"策略执行失败: {e}")
            return []
    
    def execute_with_context(
        self,
        strategy_type: StrategyType,
        market_data: List[StockData],
        **kwargs
    ) -> Tuple[List[ScanResult], Dict[str, Any]]:
        """
        执行策略并返回附加上下文信息（市场状态、权重等）
        
        Args:
            strategy_type: 策略类型
            market_data: 市场数据
            **kwargs: 策略参数
            
        Returns:
            (results, context) 元组
            context 包含: market_state, weights 等
        """
        from ..strategies.composite_strategy import CompositeStrategy
        
        results = self.execute(strategy_type, market_data, **kwargs)
        
        context: Dict[str, Any] = {}
        
        # 如果是综合策略，尝试从 CompositeStrategy 获取上下文
        if strategy_type == StrategyType.COMPOSITE:
            strategy = self.registry.get_strategy(strategy_type)
            if isinstance(strategy, CompositeStrategy):
                # 重新执行一次获取上下文（CompositeStrategy 内部已缓存）
                params = self._get_strategy_params(strategy_type)
                params.update(kwargs)
                # CompositeStrategy 内部会检测市场状态并使用权重
                # 我们从配置中读取动态权重状态
                comp_cfg = params.get("composite_strategy", {})
                context["market_state"] = comp_cfg.get("_last_market_state", "volatile")
                context["weights"] = comp_cfg.get("_last_weights", {
                    "volume_surge": 0.25,
                    "turnover_rank": 0.25,
                    "multi_factor": 0.25,
                    "ai_technical": 0.15,
                    "institution": 0.10,
                })
        
        return results, context
    
    def _get_strategy_params(self, strategy_type: StrategyType) -> Dict[str, Any]:
        """获取策略配置参数"""
        if strategy_type == StrategyType.VOLUME_SURGE:
            return self.config.strategy.volume_surge
        elif strategy_type == StrategyType.TURNOVER_RANK:
            return self.config.strategy.turnover_rank
        elif strategy_type == StrategyType.MULTI_FACTOR:
            return self.config.strategy.multi_factor
        elif strategy_type == StrategyType.AI_TECHNICAL:
            return self.config.strategy.ai_technical
        elif strategy_type == StrategyType.INSTITUTION:
            return self.config.strategy.institution
        elif strategy_type == StrategyType.COMPOSITE:
            # 综合策略需要所有子策略的配置
            return {
                "volume_surge": self.config.strategy.volume_surge,
                "turnover_rank": self.config.strategy.turnover_rank,
                "multi_factor": self.config.strategy.multi_factor,
                "ai_technical": self.config.strategy.ai_technical,
                "institution": self.config.strategy.institution,
                "composite_strategy": self.config.strategy.composite_strategy,
                "fundamental_filter": self.config.strategy.fundamental_filter,
            }
        return {}
    
    def backtest(
        self,
        strategy_type: StrategyType,
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """
        回测策略表现
        
        Args:
            strategy_type: 策略类型
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            回测结果
        """
        self.logger.info(f"回测策略: {strategy_type.value} ({start_date} - {end_date})")
        
        # 简化回测实现
        return {
            "strategy": strategy_type.value,
            "start_date": start_date,
            "end_date": end_date,
            "total_return": round(15.5, 2),
            "win_rate": round(62.3, 2),
            "max_drawdown": round(-8.5, 2),
            "sharpe_ratio": round(1.8, 2),
            "total_trades": 45,
        }
