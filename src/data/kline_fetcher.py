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

from ..core.types import StockData

logger = logging.getLogger("AInvest.KlineFetcher")


class KlineFetcher:
    """并发K线数据获取器"""

    EASTMONEY_KLINE_URL = "http://push2his.eastmoney.com/api/qt/stock/kline/get"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    def __init__(self, max_workers: int = 10, timeout: int = 15):
        self.max_workers = max_workers
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(self.HEADERS)
        self._cache: Dict[str, List[StockData]] = {}
        self._cache_time: Dict[str, float] = {}
        self._cache_ttl = 300  # 5分钟缓存

    def fetch_one(self, symbol: str, days: int = 60) -> Optional[List[StockData]]:
        """
        获取单只股票K线数据

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

        try:
            secid = self._make_secid(symbol)
            params = {
                "secid": secid,
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                "klt": "101",
                "fqt": "1",
                "lmt": str(days),
            }

            resp = self._session.get(self.EASTMONEY_KLINE_URL, params=params, timeout=self.timeout)
            data = resp.json()
            klines = data.get("data", {}).get("klines", [])
            name = data.get("data", {}).get("name", "")

            if not klines:
                return None

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

            # 缓存
            self._cache[cache_key] = stock_list
            self._cache_time[cache_key] = now
            return stock_list

        except Exception as e:
            logger.debug(f"获取 {symbol} K线失败: {e}")
            return None

    def fetch_batch(
        self,
        symbols: List[str],
        days: int = 60,
    ) -> Dict[str, List[StockData]]:
        """
        并发获取多只股票的K线数据

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

        logger.info(f"开始并发获取 {total} 只股票K线数据 (线程={self.max_workers})...")
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_map = {
                executor.submit(self.fetch_one, sym, days): sym
                for sym in symbols
            }

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
