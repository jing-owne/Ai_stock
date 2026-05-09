"""
AInvest - AI驱动的股票量化分析平台
"""

__version__ = "1.0.0"
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
