"""
Marcus 策略小助手 (AInvest) - AI驱动的量化策略选股平台
"""

__version__ = "2.1.0"
__author__ = "AInvest Team"

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
