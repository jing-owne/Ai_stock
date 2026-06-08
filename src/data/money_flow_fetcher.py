"""
资金流向数据获取模块 (v2.6.5新增)

使用东财主力资金流向API获取连续净流入天数
"""

import logging
import time
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger("AInvest.MoneyFlowFetcher")

# 东财资金流向API
MONEYFLOW_URL = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/",
}


class MoneyFlowFetcher:
    """资金流向数据获取器（20日主力净流入）"""

    def __init__(self, max_workers: int = 4, delay_per_request: float = 0.05):
        self.max_workers = max_workers
        self.delay_per_request = delay_per_request
        self._cache: Dict[str, int] = {}  # symbol → consecutive_inflow_days

    @staticmethod
    def make_secid(symbol: str) -> str:
        """代码 → 东财 secid"""
        if symbol.startswith("6"):
            return f"1.{symbol}"
        return f"0.{symbol}"

    def fetch_one(self, symbol: str) -> Optional[int]:
        """
        获取单只标的20日主力资金净流入情况

        Returns:
            连续净流入天数，失败返回 None
        """
        if symbol in self._cache:
            return self._cache[symbol]

        try:
            secid = self.make_secid(symbol)
            params = {
                "lmt": "20",
                "klt": "101",
                "secid": secid,
                "fields1": "f1,f2,f3,f7",
                "fields2": "f51,f52",  # f51=日期, f52=主力净流入
            }

            session = requests.Session()
            session.headers.update(HEADERS)
            resp = session.get(MONEYFLOW_URL, params=params, timeout=8, verify=False)
            session.close()

            data = resp.json()
            if not data or data.get("rc") != 0:
                return None

            klines = data.get("data", {}).get("klines", [])
            if not klines:
                return None

            # 解析主力净流入，从最近往回统计连续净流入天数
            consecutive = 0
            for line in reversed(klines):
                parts = line.split(",")
                if len(parts) >= 2:
                    main_inflow = float(parts[1])
                    if main_inflow > 0:
                        consecutive += 1
                    else:
                        break  # 遇到流出即停止

            self._cache[symbol] = consecutive
            return consecutive

        except Exception as e:
            logger.debug(f"资金流向 {symbol} 获取失败: {e}")
            return None

    def fetch_batch(self, symbols: List[str]) -> Dict[str, int]:
        """
        批量获取多只标的资金流向数据

        Returns:
            {symbol: consecutive_inflow_days}
        """
        results: Dict[str, int] = {}
        total = len(symbols)

        if total == 0:
            return results

        # 分离缓存
        need_fetch = []
        for sym in symbols:
            if sym in self._cache:
                results[sym] = self._cache[sym]
            else:
                need_fetch.append(sym)

        if not need_fetch:
            return results

        logger.info(f"获取 {len(need_fetch)}/{total} 只标的资金流向数据...")
        start_time = time.time()

        if self.max_workers <= 1:
            for i, sym in enumerate(need_fetch):
                try:
                    days = self.fetch_one(sym)
                    if days is not None:
                        results[sym] = days
                except Exception:
                    pass
                if i < len(need_fetch) - 1:
                    time.sleep(self.delay_per_request)
        else:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_map = {}
                for i, sym in enumerate(need_fetch):
                    future_map[executor.submit(self.fetch_one, sym)] = sym
                    if i < len(need_fetch) - 1:
                        time.sleep(self.delay_per_request)

                for future in as_completed(future_map):
                    symbol = future_map[future]
                    try:
                        days = future.result()
                        if days is not None:
                            results[symbol] = days
                    except Exception:
                        pass

        elapsed = time.time() - start_time
        logger.info(f"资金流向获取完成: {len(results)}/{total} 只, 耗时 {elapsed:.1f}s")
        return results

    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()

    @staticmethod
    def count_consecutive_inflow(kline_list: list) -> int:
        """从原始K线列表统计连续净流入天数（供离线使用）"""
        consecutive = 0
        for line in reversed(kline_list):
            parts = line.split(",")
            if len(parts) >= 2:
                if float(parts[1]) > 0:
                    consecutive += 1
                else:
                    break
        return consecutive
