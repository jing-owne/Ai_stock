"""
Marcus策略小助手 - AI驱动的量化策略分析平台 · 公共模块重构
"""

__version__ = "2.6.5"
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
