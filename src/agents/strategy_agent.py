"""
策略执行Agent
负责执行各种量化策略
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
    
    管理和执行各种量化策略
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
        
        # 单策略模式：预取K线并注入指标（CompositeStrategy会自己处理）
        if strategy_type != StrategyType.COMPOSITE:
            self._prefetch_and_inject_indicators(strategy, market_data, as_of=kwargs.get("as_of"))
        
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
    
    def _prefetch_and_inject_indicators(self, strategy, market_data: List[StockData], as_of: Optional[str] = None):
        """预取K线并注入指标（单策略模式）"""
        from ..data.prefetch import prefetch_kline_indicators

        symbols = list({s.symbol for s in market_data if s.amount >= 200_000_000})
        ind, kln, cnt = prefetch_kline_indicators(
            symbols=symbols,
            keep_kline=True,
            log_prefix="单策略",
            as_of=as_of,
        )
        
        if hasattr(strategy, '_indicators'):
            strategy._indicators = ind
        if hasattr(strategy, '_kline_cache'):
            strategy._kline_cache = kln
        if hasattr(strategy, '_kline_available'):
            strategy._kline_available = cnt > 0
    
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
                # 从策略实例直接读取（StrategyContext 访问器）
                context["market_state"] = strategy.last_market_state
                context["weights"] = strategy.last_weights
        
        return results, context
    
    # 策略类型 → config.strategy 属性名 映射表（config key ≠ StrategyType 名）
    # v2.8: 旧 config key 保留不动，避免破坏 settings.yaml 兼容性
    _PARAM_MAP = {
        StrategyType.VOLUME_SURGE: "volume_surge",
        StrategyType.VOLUME_BREAKOUT: "volume_surge",     # → config.strategy.volume_surge
        StrategyType.TURNOVER_RANK: "turnover_rank",
        StrategyType.MULTI_FACTOR: "multi_factor",
        StrategyType.AI_TECHNICAL: "ai_technical",
        StrategyType.INSTITUTION: "institution",
        StrategyType.BOX_BREAKOUT: "box_breakout",
        StrategyType.MA_DIVERGENCE: "ma_divergence",
        StrategyType.MA_TREND: "ma_divergence",           # → config.strategy.ma_divergence
        StrategyType.BOTTOM_REBOUND: "bottom_rebound",
        StrategyType.CONSECUTIVE_POSITIVE: "consecutive_positive",
        StrategyType.NET_INFLOW: "net_inflow",
        StrategyType.TREND_CONFIRMATION: "trend_confirmation",
        StrategyType.RSI_OVERSOLD: "rsi_oversold",
        StrategyType.NEW_HIGH_BREAK: "new_high_break",
        StrategyType.SUSTAINED_UPTREND: "sustained_uptrend",
        StrategyType.LAUNCH_FINGERPRINT: "launch_fingerprint",
        # 4聚合策略 (v2.8)
        StrategyType.BOTTOM: "bottom",
        StrategyType.LAUNCH: "launch",
        StrategyType.TREND: "trend",
        StrategyType.MONEY: "money",
    }

    def _get_strategy_params(self, strategy_type: StrategyType) -> Dict[str, Any]:
        """获取策略配置参数（映射表驱动，易于扩展新策略）"""
        # 综合策略：聚合所有子策略配置
        if strategy_type == StrategyType.COMPOSITE:
            cfg = self.config.strategy
            volume_cfg = getattr(cfg, "volume_breakout", getattr(cfg, "volume_surge", {}))
            ma_cfg = getattr(cfg, "ma_trend", getattr(cfg, "ma_divergence", {}))
            return {
                "volume_surge": getattr(cfg, "volume_surge", {}),
                "volume_breakout": volume_cfg,
                "turnover_rank": getattr(cfg, "turnover_rank", {}),
                "multi_factor": getattr(cfg, "multi_factor", {}),
                "ai_technical": getattr(cfg, "ai_technical", {}),
                "institution": getattr(cfg, "institution", {}),
                "box_breakout": getattr(cfg, "box_breakout", {}),
                "ma_divergence": getattr(cfg, "ma_divergence", {}),
                "ma_trend": ma_cfg,
                "rsi_oversold": getattr(cfg, "rsi_oversold", {}),
                "new_high_break": getattr(cfg, "new_high_break", {}),
                "consecutive_positive": getattr(cfg, "consecutive_positive", {}),
                "bottom_rebound": getattr(cfg, "bottom_rebound", {}),
                "net_inflow": getattr(cfg, "net_inflow", {}),
                "trend_confirmation": getattr(cfg, "trend_confirmation", {}),
                "composite_strategy": getattr(cfg, "composite_strategy", {}),
                "fundamental_filter": getattr(cfg, "fundamental_filter", {}),
                "launch_fingerprint": getattr(cfg, "launch_fingerprint", {}),
                "bottom": getattr(cfg, "bottom", {}),
                "launch": getattr(cfg, "launch", {}),
                "trend": getattr(cfg, "trend", {}),
                "money": getattr(cfg, "money", {}),
            }

        # 单策略：从映射表取属性名，配置缺失时返回空字典（向后兼容）
        attr = self._PARAM_MAP.get(strategy_type)
        if attr is None:
            return {}
        cfg = getattr(self.config.strategy, attr, {})
        params = dict(cfg)
        params[attr] = cfg
        alias = {
            "volume_surge": "volume_breakout",
            "ma_divergence": "ma_trend",
            "rsi_oversold": "bottom_rebound",
            "new_high_break": "volume_breakout",
            "sustained_uptrend": "trend_confirmation",
            "institution": "multi_factor",
        }.get(attr)
        if alias:
            params[alias] = cfg
        return params
    
    def backtest(
        self,
        strategy_type: StrategyType,
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """
        回测策略表现

        当前版本: 基于策略历史表现统计的框架回测
        TODO: 接入真实K线数据逐日模拟回测

        Args:
            strategy_type: 策略类型
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            回测结果
        """
        self.logger.info(f"回测策略: {strategy_type.value} ({start_date} - {end_date})")

        # 计算回测天数
        from datetime import datetime
        try:
            d1 = datetime.strptime(start_date, "%Y-%m-%d")
            d2 = datetime.strptime(end_date, "%Y-%m-%d")
            trading_days = max(1, int((d2 - d1).days * 5 / 7))  # 粗略估算交易日
        except ValueError:
            trading_days = 30

        return {
            "strategy": strategy_type.value,
            "start_date": start_date,
            "end_date": end_date,
            "trading_days": trading_days,
            "total_return": None,       # TODO: 基于真实回测
            "win_rate": None,           # TODO: 基于真实回测
            "max_drawdown": None,       # TODO: 基于真实回测
            "sharpe_ratio": None,       # TODO: 基于真实回测
            "total_trades": None,       # TODO: 基于真实回测
            "note": "回测框架已搭建，待接入真实K线逐日模拟",
        }
