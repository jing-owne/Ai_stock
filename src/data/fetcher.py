"""
数据获取模块（向后兼容包装层）
实际实现已拆分为:
  fetchers/news.py    — 每日一言 + 财经新闻
  fetchers/calendar.py — IPO + 可转债日历
  fetchers/market.py  — 市场态势
"""
import logging
from typing import List, Dict, Optional, Any
from .fetchers.news import get_daily_quote, get_yicai_news, get_jin10_news, fetch_all_news
from .fetchers.calendar import get_ipo_calendar, get_bond_calendar
from .fetchers.market import get_market_overview

logger = logging.getLogger("AInvest.DataFetcher")


class DataFetcher:
    """数据获取器（委托实现）"""

    def __init__(self):
        self.logger = logger

    def get_daily_quote(self) -> str:
        return get_daily_quote()

    def get_yicai_news(self, page: int = 1, page_size: int = 20) -> List[Dict]:
        return get_yicai_news(page, page_size)

    def get_jin10_news(self, limit: int = 20) -> List[Dict]:
        return get_jin10_news(limit)

    def fetch_all_news(self) -> List[Dict]:
        return fetch_all_news()

    def get_ipo_calendar(self, max_days: int = 7) -> List[Dict]:
        return get_ipo_calendar(max_days)

    def get_bond_calendar(self, max_days: int = 7) -> List[Dict]:
        return get_bond_calendar(max_days)

    def get_market_overview(self) -> Dict[str, Any]:
        return get_market_overview()
