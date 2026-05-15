"""
K线数据并发获取模块

设计目标:
- 并发获取多只股票的K线数据，用于技术指标计算
- 10线程并发: 200只约6秒, 500只约15秒
- 支持批量获取 + 结果缓存
"""

import logging
import time
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import requests
import urllib3

from ..core.types import StockData

# 抑制 HTTPS 不验证证书的警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger("AInvest.KlineFetcher")


class KlineFetcher:
    """K线数据获取器（双源 fallback：东财 → 新浪）"""

    EASTMONEY_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    SINA_KLINE_URL = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://quote.eastmoney.com/",
    }

    def __init__(self, max_workers: int = 1, timeout: int = 15, delay_per_request: float = 0.3):
        self.max_workers = max_workers
        self.timeout = timeout
        self.delay_per_request = delay_per_request
        self._cache: Dict[str, List[StockData]] = {}
        self._cache_time: Dict[str, float] = {}
        self._cache_ttl = 300
        self._eastmoney_available: Optional[bool] = None  # None=未测试, True=可用, False=不可用

    def fetch_one(self, symbol: str, days: int = 60) -> Optional[List[StockData]]:
        """
        获取单只股票K线数据

        Fallback: 东财 → 新浪 → None

        Args:
            symbol: 纯数字股票代码 (如 "600519")
            days: 获取最近多少天

        Returns:
            StockData 列表，从旧到新排列；失败返回 None
        """
        # 检查缓存
        cache_key = f"{symbol}_{days}"
        now = time.time()
        if cache_key in self._cache and (now - self._cache_time.get(cache_key, 0)) < self._cache_ttl:
            return self._cache[cache_key]

        # 首次调用时检测东财是否可用
        if self._eastmoney_available is None:
            self._eastmoney_available = self._test_eastmoney()

        # 东财可用时先尝试东财
        if self._eastmoney_available:
            result = self._fetch_from_eastmoney(symbol, days)
            if result:
                self._cache[cache_key] = result
                self._cache_time[cache_key] = now
                return result
            # 东财失败，标记不可用，后续直接走新浪
            self._eastmoney_available = False
            logger.info("东财K线不可用，切换新浪接口")

        # 新浪备用源
        result = self._fetch_from_sina(symbol, days)
        if result:
            self._cache[cache_key] = result
            self._cache_time[cache_key] = now
            return result

        return None

    def _test_eastmoney(self) -> bool:
        """测试东财K线接口是否可用（5秒超时）"""
        try:
            session = requests.Session()
            session.headers.update(self.HEADERS)
            resp = session.get(
                self.EASTMONEY_KLINE_URL,
                params={"secid": "1.600519", "fields1": "f1", "fields2": "f51",
                        "klt": "101", "fqt": "1", "beg": "0", "end": "20500101"},
                timeout=5, verify=False,
            )
            session.close()
            data = resp.json()
            available = data.get("rc") == 0 and data.get("data") is not None
            if available:
                logger.info("东财K线接口可用")
            else:
                logger.info("东财K线接口不可用(rc=%s)，将使用新浪备用源", data.get("rc"))
            return available
        except Exception:
            logger.info("东财K线接口不可用，将使用新浪备用源")
            return False

    def _fetch_from_eastmoney(self, symbol: str, days: int) -> Optional[List[StockData]]:
        """从东方财富获取K线"""
        try:
            secid = self._make_secid(symbol)
            from datetime import datetime, timedelta
            end_date = datetime.now().strftime("%Y%m%d")
            beg_date = (datetime.now() - timedelta(days=days + 30)).strftime("%Y%m%d")
            params = {
                "secid": secid,
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                "klt": "101",
                "fqt": "1",
                "beg": beg_date,
                "end": end_date,
            }

            for attempt in range(2):
                try:
                    session = requests.Session()
                    session.headers.update(self.HEADERS)
                    resp = session.get(self.EASTMONEY_KLINE_URL, params=params, timeout=self.timeout, verify=False)
                    data = resp.json()
                    session.close()
                    
                    if not data or data.get("rc") != 0:
                        if attempt < 1:
                            time.sleep(1.0)
                            continue
                        return None
                        
                    klines = data.get("data", {}).get("klines", [])
                    name = data.get("data", {}).get("name", "")
                    
                    if klines and len(klines) > days:
                        klines = klines[-days:]
                    if not klines:
                        return None

                    return self._parse_eastmoney_klines(symbol, name, klines)
                except Exception as e:
                    if attempt < 1:
                        time.sleep(1.0)
                        continue
                    logger.debug(f"东财 {symbol} K线失败: {e}")
                    return None
        except Exception:
            return None

    def _fetch_from_sina(self, symbol: str, days: int) -> Optional[List[StockData]]:
        """从新浪财经获取K线（东财的备用源，不限频）"""
        try:
            # 新浪接口: sh600519 或 sz000858
            sina_symbol = f"sh{symbol}" if symbol.startswith("6") else f"sz{symbol}"
            params = {
                "symbol": sina_symbol,
                "scale": "240",  # 日K线
                "ma": "no",
                "datalen": str(days),
            }
            session = requests.Session()
            session.headers.update({"User-Agent": self.HEADERS["User-Agent"]})
            resp = session.get(self.SINA_KLINE_URL, params=params, timeout=10)
            session.close()

            if resp.status_code != 200:
                return None

            import json
            data = json.loads(resp.text)
            if not data or not isinstance(data, list):
                return None

            stock_list = []
            for item in data:
                stock_list.append(StockData(
                    symbol=symbol,
                    name="",  # 新浪接口不返回名称
                    date=item.get("day", ""),
                    open=float(item.get("open", 0)),
                    close=float(item.get("close", 0)),
                    high=float(item.get("high", 0)),
                    low=float(item.get("low", 0)),
                    volume=float(item.get("volume", 0)),
                    amount=0.0,  # 新浪接口不含成交额
                    change_pct=0.0,  # 后面计算
                    turn_rate=0.0,
                ))

            # 计算涨跌幅
            for i in range(len(stock_list)):
                if i > 0 and stock_list[i-1].close > 0:
                    stock_list[i].change_pct = round(
                        (stock_list[i].close - stock_list[i-1].close) / stock_list[i-1].close * 100, 2
                    )

            if not stock_list:
                return None
            return stock_list
        except Exception as e:
            logger.debug(f"新浪 {symbol} K线失败: {e}")
            return None

    @staticmethod
    def _parse_eastmoney_klines(symbol: str, name: str, klines: list) -> List[StockData]:
        """解析东财K线数据"""
        stock_list = []
        for line in klines:
            parts = line.split(",")
            stock_list.append(StockData(
                symbol=symbol,
                name=name,
                date=parts[0],
                open=float(parts[1]),
                close=float(parts[2]),
                high=float(parts[3]),
                low=float(parts[4]),
                volume=float(parts[5]),
                amount=float(parts[6]),
                change_pct=float(parts[8]),
                turn_rate=float(parts[10]),
            ))
        return stock_list

    def fetch_batch(
        self,
        symbols: List[str],
        days: int = 60,
    ) -> Dict[str, List[StockData]]:
        """
        获取多只股票的K线数据

        默认串行 + 延迟，防东财限频。max_workers>1 时用线程池并发。

        Args:
            symbols: 股票代码列表
            days: 每只获取天数

        Returns:
            {symbol: [StockData]} 成功获取的股票
        """
        results: Dict[str, List[StockData]] = {}
        total = len(symbols)

        if total == 0:
            return results

        logger.info(f"开始获取 {total} 只股票K线数据 (并发={self.max_workers}, 延迟={self.delay_per_request}s)...")
        start_time = time.time()

        if self.max_workers <= 1:
            # 串行模式：最稳定，防限频
            for i, sym in enumerate(symbols):
                try:
                    kline = self.fetch_one(sym, days)
                    if kline:
                        results[sym] = kline
                except Exception as e:
                    logger.debug(f"{sym} 获取异常: {e}")

                if (i + 1) % 50 == 0:
                    logger.info(f"K线获取进度: {i+1}/{total}")

                # 请求间延迟
                if i < total - 1:
                    time.sleep(self.delay_per_request)
        else:
            # 并发模式：有限并发 + 延迟提交
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_map = {}
                for i, sym in enumerate(symbols):
                    future_map[executor.submit(self.fetch_one, sym, days)] = sym
                    if i < total - 1:
                        time.sleep(self.delay_per_request)

                done_count = 0
                for future in as_completed(future_map):
                    symbol = future_map[future]
                    done_count += 1
                    try:
                        kline = future.result()
                        if kline:
                            results[symbol] = kline
                    except Exception as e:
                        logger.debug(f"{symbol} 获取异常: {e}")

                    if done_count % 50 == 0:
                        logger.info(f"K线获取进度: {done_count}/{total}")

        elapsed = time.time() - start_time
        logger.info(
            f"K线获取完成: {len(results)}/{total} 只, 耗时 {elapsed:.1f}s"
        )
        return results

    def get_numpy_arrays(self, kline_data: List[StockData]) -> Optional[Dict[str, np.ndarray]]:
        """
        将K线数据转为numpy数组，方便指标计算

        Returns:
            {"close": ndarray, "volume": ndarray, "high": ndarray, "low": ndarray}
            或 None（数据不足）
        """
        if not kline_data or len(kline_data) < 10:
            return None

        close = np.array([d.close for d in kline_data], dtype=np.float64)
        volume = np.array([d.volume for d in kline_data], dtype=np.float64)
        high = np.array([d.high for d in kline_data], dtype=np.float64)
        low = np.array([d.low for d in kline_data], dtype=np.float64)

        return {"close": close, "volume": volume, "high": high, "low": low}

    @staticmethod
    def _make_secid(symbol: str) -> str:
        """股票代码 -> 东财 secid"""
        if symbol.startswith("6"):
            return f"1.{symbol}"
        else:
            return f"0.{symbol}"

    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
        self._cache_time.clear()
        logger.info("K线缓存已清空")
