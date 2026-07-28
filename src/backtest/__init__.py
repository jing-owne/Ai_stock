"""
回测 / 跟踪 包 (v2.8)

对外导出核心类，方便 CLI 与邮件钩子调用。
"""
from .models import RecommendationRecord, StrategyMode, HoldStyle, RunType, TradingSession
from .tracker import RecommendationTracker, classify_trading_session, is_regular_trading_time
from .returns import ReturnCalculator
from .allocator import PositionAllocator, PortfolioPlan
from .report import PerformanceReporter
from .limiter import can_buy, can_sell, is_limit_up, is_limit_down, limit_pct, limit_status

__all__ = [
    "RecommendationRecord", "StrategyMode", "HoldStyle", "RunType", "TradingSession",
    "RecommendationTracker", "ReturnCalculator", "PositionAllocator",
    "PortfolioPlan", "PerformanceReporter",
    "classify_trading_session", "is_regular_trading_time",
    "can_buy", "can_sell", "is_limit_up", "is_limit_down", "limit_pct", "limit_status",
]
