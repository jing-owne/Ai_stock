"""
数据采集Agent
负责从各种数据源获取股票市场数据
"""
import json
import logging
import urllib.request
from typing import List, Optional
from datetime import datetime

from ..core.types import StockData
from ..core.config import Config

# ─────────────────────────────────────────────
# 新浪财经沪深A股行情（按涨幅排序，取多页）
# ─────────────────────────────────────────────
_SINA_MARKET_URL = (
    "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php"
    "/Market_Center.getHQNodeData"
    "?page={page}&num=100&sort=amount&asc=0&node=hs_a&symbol=&_s_r_a=page"
)

# 东方财富行情中心（备用）
_EASTMONEY_FIELDS = "f2,f3,f4,f5,f6,f7,f10,f12,f14,f15,f16,f17,f18"
_EASTMONEY_MARKET_URL = (
    "https://push2.eastmoney.com/api/qt/clist/get"
    "?cb=&pn={page}&pz=200&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281"
    "&fltt=2&invt=2&fid=f3&fs=m:0+t:6,m:0+t:13,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
    f"&fields={_EASTMONEY_FIELDS}&_=1"
)


def _fetch_sina_market(max_pages: int = 3) -> List[StockData]:
    """
    从新浪财经批量拉取沪深A股实时行情（按成交额倒序）
    """
    today = datetime.now().strftime("%Y-%m-%d")
    result: List[StockData] = []
    logger = logging.getLogger("AInvest.DataAgent")

    for page in range(1, max_pages + 1):
        try:
            url = _SINA_MARKET_URL.format(page=page)
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Referer": "https://finance.sina.com.cn",
            })
            with urllib.request.urlopen(req, timeout=10) as r:
                raw = r.read().decode("gbk", errors="replace")
            items = json.loads(raw)
            if not items:
                break
            for item in items:
                try:
                    code = str(item.get("code", "")).zfill(6)
                    name = item.get("name", "")
                    close = item.get("trade")
                    change_pct = item.get("changepercent")
                    open_ = item.get("open")
                    high = item.get("high")
                    low = item.get("low")
                    volume = item.get("volume")   # 股
                    amount = item.get("amount")   # 元
                    turn_rate = item.get("turnoverratio")

                    if not code or not name:
                        continue
                    if close in (None, "-", "--", "", "0.000") or float(close) == 0:
                        continue

                    result.append(StockData(
                        symbol=code,
                        name=name,
                        date=today,
                        open=float(open_) if open_ not in (None, "-", "") else float(close),
                        high=float(high) if high not in (None, "-", "") else float(close),
                        low=float(low) if low not in (None, "-", "") else float(close),
                        close=float(close),
                        volume=float(volume) if volume not in (None, "-") else 0,
                        amount=float(amount) if amount not in (None, "-") else 0,
                        change_pct=float(change_pct) if change_pct not in (None, "-") else 0.0,
                        turn_rate=float(turn_rate) if turn_rate not in (None, "-") else 0.0,
                    ))
                except (TypeError, ValueError):
                    continue
        except Exception as e:
            logger.warning(f"新浪行情拉取第{page}页失败: {e}")
            break

    return result


def _fetch_eastmoney_market(max_pages: int = 3) -> List[StockData]:
    """
    从东方财富行情中心批量拉取沪深A股实时行情（备用）
    """
    today = datetime.now().strftime("%Y-%m-%d")
    result: List[StockData] = []
    logger = logging.getLogger("AInvest.DataAgent")

    for page in range(1, max_pages + 1):
        try:
            url = _EASTMONEY_MARKET_URL.format(page=page)
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
                "Referer": "https://quote.eastmoney.com/",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=10) as r:
                raw = r.read().decode("utf-8", errors="replace")
            raw = raw.strip()
            if raw.startswith("jQuery") or raw.startswith("cb"):
                raw = raw[raw.index("(") + 1: raw.rindex(")")]
            data = json.loads(raw)
            items = data.get("data", {}).get("diff", [])
            if not items:
                break
            for item in items:
                try:
                    code = str(item.get("f12", "")).zfill(6)
                    name = item.get("f14", "")
                    close = item.get("f2")
                    change_pct = item.get("f3")
                    open_ = item.get("f17")
                    high = item.get("f15")
                    low = item.get("f16")
                    volume = item.get("f5")
                    amount = item.get("f6")
                    turn_rate = item.get("f7")

                    if not code or not name:
                        continue
                    if close in (None, "-", "--") or close == 0:
                        continue

                    result.append(StockData(
                        symbol=code,
                        name=name,
                        date=today,
                        open=float(open_) if open_ not in (None, "-") else float(close),
                        high=float(high) if high not in (None, "-") else float(close),
                        low=float(low) if low not in (None, "-") else float(close),
                        close=float(close),
                        volume=float(volume) * 100 if volume not in (None, "-") else 0,
                        amount=float(amount) if amount not in (None, "-") else 0,
                        change_pct=float(change_pct) if change_pct not in (None, "-") else 0.0,
                        turn_rate=float(turn_rate) if turn_rate not in (None, "-") else 0.0,
                    ))
                except (TypeError, ValueError):
                    continue
        except Exception as e:
            logger.warning(f"东方财富行情拉取第{page}页失败: {e}")
            break

    return result


class DataAgent:
    """
    数据采集Agent
    优先从新浪财经拉取真实行情；失败时尝试东方财富；均失败则降级到演示数据。
    """

    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger("AInvest.DataAgent")
        self._cache = {}
        self._cache_time = {}

    def fetch_market_data(
        self,
        date: Optional[str] = None,
        include_index: bool = False
    ) -> List[StockData]:
        """
        获取市场股票数据
        优先新浪 → 东方财富 → 演示数据
        """
        date = date or datetime.now().strftime("%Y-%m-%d")

        cache_key = f"market_data_{date}_{include_index}"
        if self.config.data_source.cache_enabled and cache_key in self._cache:
            if self._is_cache_valid(cache_key):
                self.logger.debug("使用缓存数据")
                return self._cache[cache_key]

        # 主：新浪财经
        data = self._fetch_from_sina(date, include_index)

        # 备：东方财富
        if not data:
            self.logger.warning("新浪行情为空，尝试东方财富...")
            data = self._fetch_from_eastmoney(date, include_index)

        # 降级：演示数据
        if not data:
            self.logger.warning("真实行情均不可用，降级到演示数据")
            data = self._generate_mock_data(date)

        if self.config.data_source.cache_enabled:
            self._cache[cache_key] = data
            self._cache_time[cache_key] = datetime.now()

        return data

    def fetch_stock_data(self, symbol: str, days: int = 30) -> List[StockData]:
        """获取单只股票数据（取当日实时快照）"""
        self.logger.info(f"获取股票{symbol}数据")
        today_data = self.fetch_market_data()
        stock_map = {s.symbol: s for s in today_data}
        target = stock_map.get(symbol)
        return [target] if target else []

    def _fetch_from_sina(self, date: str, include_index: bool) -> List[StockData]:
        self.logger.debug("从新浪财经拉取行情...")
        try:
            stocks = _fetch_sina_market(max_pages=3)
            self.logger.info(f"新浪行情拉取完成，共 {len(stocks)} 只股票")
            return stocks
        except Exception as e:
            self.logger.warning(f"新浪行情拉取失败: {e}")
            return []

    def _fetch_from_eastmoney(self, date: str, include_index: bool) -> List[StockData]:
        self.logger.debug("从东方财富行情中心拉取数据...")
        try:
            stocks = _fetch_eastmoney_market(max_pages=3)
            self.logger.info(f"东方财富行情拉取完成，共 {len(stocks)} 只股票")
            return stocks
        except Exception as e:
            self.logger.warning(f"东方财富行情拉取失败: {e}")
            return []

    def _generate_mock_data(self, date: str) -> List[StockData]:
        """生成演示数据（仅在真实数据不可用时使用）"""
        import random
        symbols = [
            ("600519", "贵州茅台", 1450.0),
            ("000858", "五粮液", 88.0),
            ("601318", "中国平安", 41.0),
            ("000333", "美的集团", 55.0),
            ("002475", "立讯精密", 22.0),
            ("300750", "宁德时代", 210.0),
            ("600036", "招商银行", 33.0),
            ("000001", "平安银行", 11.0),
            ("601888", "中国中免", 55.0),
            ("300059", "东方财富", 14.0),
            ("002594", "比亚迪", 280.0),
            ("600900", "长江电力", 25.0),
            ("601012", "隆基绿能", 12.0),
            ("002352", "顺丰控股", 38.0),
            ("600276", "恒瑞医药", 32.0),
            ("000725", "京东方A", 4.5),
            ("601166", "兴业银行", 17.0),
            ("600887", "伊利股份", 22.0),
            ("002714", "牧原股份", 35.0),
            ("300015", "爱尔眼科", 12.0),
        ]
        data = []
        for symbol, name, base_price in symbols:
            change_pct = round(random.uniform(-3, 5), 2)
            close = round(base_price * (1 + change_pct / 100), 2)
            data.append(StockData(
                symbol=symbol,
                name=name,
                date=date,
                open=round(base_price * random.uniform(0.99, 1.01), 2),
                high=round(close * random.uniform(1.0, 1.03), 2),
                low=round(close * random.uniform(0.97, 1.0), 2),
                close=close,
                volume=random.uniform(5000000, 50000000),
                amount=round(close * random.uniform(5000000, 50000000) * 0.1),
                change_pct=change_pct,
                turn_rate=round(random.uniform(1, 15), 2)
            ))
        return data

    def _is_cache_valid(self, cache_key: str) -> bool:
        if cache_key not in self._cache_time:
            return False
        elapsed = (datetime.now() - self._cache_time[cache_key]).total_seconds()
        return elapsed < self.config.data_source.cache_ttl

    def clear_cache(self):
        self._cache.clear()
        self._cache_time.clear()
        self.logger.info("缓存已清空")
