"""
Marcus策略小助手 - AI驱动的量化策略分析平台 · 连续上涨策略优化
"""

__version__ = "2.7.0"
__author__ = "Marcus策略小助手"

from .core.types import StockData, ScanResult, MarketAnalysis
from .core.config import Config
from .core.engine import AInvestEngine

__all__ = [
    "StockData",
    "ScanResult", 
    "MarketAnalysis",
    "Config",
    "AInvestEngine",
]
