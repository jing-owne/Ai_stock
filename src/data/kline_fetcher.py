"""
K线数据并发获取模块

设计目标:
- 并发获取多只标的的K线数据，用于技术指标计算
- 10线程并发: 200只约6秒, 500只约15秒
- 支持批量获取 + 结果缓存

数据源说明:
- TDX通道: 依赖WorkBuddy通达信应用，不可单独作为数据源使用
- 东财通道: 生产环境默认数据源
- 新浪通道: 备用数据源

数据流区分:
- 选标的流程（生产）: 使用东财→新浪双源 fallback，不使用 KlineFetcher
- 分析流程（TDX）: 使用 source='tdx'，只走 TDX 通道
"""

import json
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
    """K线数据获取器（可配置数据源，带重试机制和数据验证）"""

    # 数据源常量
    # 注意: TDX 依赖 WorkBuddy 通达信应用，不能单独作为数据源使用
    SOURCE_TDX = "tdx"
    SOURCE_EASTMONEY = "eastmoney"
    SOURCE_SINA = "sina"

    EASTMONEY_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    SINA_KLINE_URL = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://quote.eastmoney.com/",
    }

    def __init__(self, max_workers: int = 1, timeout: int = 15, delay_per_request: float = 0.02,
                 source: str = None):
        """
        Args:
            source: 数据源选择
                - None（默认）: 自动模式，生产流程用东财→新浪
                - "tdx": 仅TDX通道（需WorkBuddy通达信应用支持）
                - "eastmoney": 仅东财通道
                - "sina": 仅新浪通道
        """
        self.max_workers = max_workers
        self.timeout = timeout
        self.delay_per_request = delay_per_request
        self.source = source
        self._cache: Dict[str, List[StockData]] = {}
        self._cache_time: Dict[str, float] = {}
        self._cache_ttl = 21600  # 6小时缓存（早上9:30设置，下午16:00仍有效）
        self._eastmoney_available: Optional[bool] = None
        self._tdx_available: Optional[bool] = None
        self._max_retries = 3  # 最大重试次数

    def fetch_one(self, symbol: str, days: int = 60) -> Optional[List[StockData]]:
        """
        获取单只标的K线数据

        Fallback 根据 source 配置:
        - source="tdx": 只用TDX（分析流程）
        - source="eastmoney": 东财
        - source=None: 自动模式（生产流程：优先东财→新浪）

        Args:
            symbol: 纯数字代码
            days: 获取最近多少天

        Returns:
            StockData 列表，从旧到新排列；失败返回 None
        """
        # 检查缓存
        cache_key = f"{symbol}_{days}"
        now = time.time()
        if cache_key in self._cache and (now - self._cache_time.get(cache_key, 0)) < self._cache_ttl:
            return self._cache[cache_key]

        # ═══════════════════════════════════════════════
        # 根据 source 选择数据源路由
        # ═══════════════════════════════════════════════
        if self.source == self.SOURCE_TDX:
            # 分析流程：仅 TDX 通道
            return self._fetch_with_tdx(symbol, days, cache_key, now)
        elif self.source == self.SOURCE_EASTMONEY:
            return self._fetch_with_eastmoney(symbol, days, cache_key, now)
        else:
            # 自动模式（生产流程）：TDX可用则优先TDX，否则东财→新浪
            result = self._fetch_with_tdx(symbol, days, cache_key, now)
            if result:
                return result
            return self._fetch_with_eastmoney(symbol, days, cache_key, now)

    def _fetch_with_tdx(self, symbol: str, days: int,
                        cache_key: str, now: float) -> Optional[List[StockData]]:
        """使用TDX通道获取K线（带重试机制）—— 需WorkBuddy通达信应用支持"""
        from .tdx_fetcher import get_tdx_fetcher

        last_error = None
        for attempt in range(self._max_retries):
            try:
                tdx = get_tdx_fetcher()
                if tdx is None:
                    last_error = "TDX客户端未初始化"
                    if attempt < self._max_retries - 1:
                        logger.debug(f"[{symbol}] TDX客户端未初始化，重试 {attempt+2}/{self._max_retries}")
                        time.sleep(0.5 * (attempt + 1))
                    continue

                kline_list = tdx.get_kline(symbol, frequency=4, offset=days)
                if not kline_list:
                    last_error = "返回空数据"
                    if attempt < self._max_retries - 1:
                        time.sleep(1.0 * (attempt + 1))
                    continue

                # 转换为StockData
                stock_list = []
                for k in kline_list:
                    try:
                        stock_list.append(StockData(
                            symbol=symbol,
                            name='',
                            date=k.get('date', ''),
                            open=float(k.get('open', 0)),
                            close=float(k.get('close', 0)),
                            high=float(k.get('high', 0)),
                            low=float(k.get('low', 0)),
                            volume=float(k.get('volume', 0)),
                            amount=float(k.get('amount', 0)),
                        ))
                    except (ValueError, TypeError) as e:
                        logger.debug(f"[{symbol}] K线数据转换失败: {e}, 数据: {k}")
                        continue

                # 数据验证
                if not self._validate_kline_data(symbol, stock_list, "TDX"):
                    last_error = "数据验证失败"
                    if attempt < self._max_retries - 1:
                        time.sleep(1.0 * (attempt + 1))
                    continue

                self._cache[cache_key] = stock_list
                self._cache_time[cache_key] = now
                logger.debug(f"[{symbol}] TDX K线获取成功: {len(stock_list)}条 (尝试{attempt+1}次)")
                return stock_list

            except Exception as e:
                last_error = str(e)
                if attempt < self._max_retries - 1:
                    logger.debug(f"[{symbol}] TDX K线失败，重试 {attempt+2}/{self._max_retries}: {e}")
                    time.sleep(1.0 * (attempt + 1))

        logger.warning(f"[{symbol}] TDX K线获取失败(重试{self._max_retries}次): {last_error}")
        return None

    def _fetch_with_eastmoney(self, symbol: str, days: int,
                              cache_key: str, now: float) -> Optional[List[StockData]]:
        """使用东财获取K线（生产流程默认数据源）"""
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
        """测试东财K线接口是否可用（多标的测试，3秒超时）"""
        test_symbols = ["600519", "000001", "300014"]
        for symbol in test_symbols:
            try:
                secid = self._make_secid(symbol)
                session = requests.Session()
                session.headers.update(self.HEADERS)
                resp = session.get(
                    self.EASTMONEY_KLINE_URL,
                    params={"secid": secid, "fields1": "f1", "fields2": "f51",
                            "klt": "101", "fqt": "1", "beg": "0", "end": "20500101"},
                    timeout=3, verify=False,
                )
                session.close()
                data = resp.json()
                available = data.get("rc") == 0 and data.get("data") is not None
                if available:
                    logger.info(f"东财K线接口可用(测试{symbol}通过)")
                    return True
                logger.debug(f"东财K线接口测试{symbol}: rc={data.get('rc')}")
            except Exception as e:
                logger.debug(f"东财K线接口测试{symbol}失败: {e}")

        logger.info("东财K线接口不可用(所有测试标的均失败)，将使用新浪备用源")
        return False

    def _fetch_from_eastmoney(self, symbol: str, days: int) -> Optional[List[StockData]]:
        """从东方财富获取K线（带重试机制）"""
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

            for attempt in range(self._max_retries):
                try:
                    session = requests.Session()
                    session.headers.update(self.HEADERS)
                    resp = session.get(self.EASTMONEY_KLINE_URL, params=params, timeout=self.timeout, verify=False)
                    data = resp.json()
                    session.close()

                    if not data or data.get("rc") != 0:
                        if attempt < self._max_retries - 1:
                            time.sleep(1.0 * (attempt + 1))
                            continue
                        return None

                    klines = data.get("data", {}).get("klines", [])
                    name = data.get("data", {}).get("name", "")

                    if klines and len(klines) > days:
                        klines = klines[-days:]
                    if not klines:
                        if attempt < self._max_retries - 1:
                            time.sleep(1.0 * (attempt + 1))
                            continue
                        return None

                    result = self._parse_eastmoney_klines(symbol, name, klines)
                    # 数据验证
                    if not self._validate_kline_data(symbol, result, "东财"):
                        if attempt < self._max_retries - 1:
                            time.sleep(1.0 * (attempt + 1))
                            continue
                        return None
                    return result

                except Exception as e:
                    if attempt < self._max_retries - 1:
                        logger.debug(f"[{symbol}] 东财K线失败，重试 {attempt+2}/{self._max_retries}: {e}")
                        time.sleep(1.0 * (attempt + 1))
                        continue
                    logger.warning(f"[{symbol}] 东财K线失败(重试{self._max_retries}次): {e}")
                    return None

        except Exception:
            return None

    def _fetch_from_sina(self, symbol: str, days: int) -> Optional[List[StockData]]:
        """从新浪财经获取K线（带重试机制）"""
        sina_symbol = f"sh{symbol}" if symbol.startswith("6") else f"sz{symbol}"
        params = {
            "symbol": sina_symbol,
            "scale": "240",
            "ma": "no",
            "datalen": str(days),
        }

        for attempt in range(self._max_retries):
            try:
                session = requests.Session()
                session.headers.update({"User-Agent": self.HEADERS["User-Agent"]})
                resp = session.get(self.SINA_KLINE_URL, params=params, timeout=10)
                session.close()

                if resp.status_code != 200:
                    if attempt < self._max_retries - 1:
                        time.sleep(1.0 * (attempt + 1))
                        continue
                    logger.warning(f"[{symbol}] 新浪返回HTTP {resp.status_code}")
                    return None

                data = json.loads(resp.text)
                if not data or not isinstance(data, list):
                    if attempt < self._max_retries - 1:
                        time.sleep(1.0 * (attempt + 1))
                        continue
                    logger.warning(f"[{symbol}] 新浪返回非列表数据")
                    return None

                stock_list = []
                for item in data:
                    stock_list.append(StockData(
                        symbol=symbol,
                        name="",
                        date=item.get("day", ""),
                        open=float(item.get("open", 0)),
                        close=float(item.get("close", 0)),
                        high=float(item.get("high", 0)),
                        low=float(item.get("low", 0)),
                        volume=float(item.get("volume", 0)),
                        amount=0.0,
                        change_pct=0.0,
                        turn_rate=0.0,
                    ))

                # 计算涨跌幅
                for i in range(len(stock_list)):
                    if i > 0 and stock_list[i-1].close > 0:
                        stock_list[i].change_pct = round(
                            (stock_list[i].close - stock_list[i-1].close) / stock_list[i-1].close * 100, 2
                        )

                if not stock_list:
                    if attempt < self._max_retries - 1:
                        time.sleep(1.0 * (attempt + 1))
                        continue
                    return None

                # 数据验证
                if not self._validate_kline_data(symbol, stock_list, "新浪"):
                    if attempt < self._max_retries - 1:
                        time.sleep(1.0 * (attempt + 1))
                        continue
                    return None

                return stock_list

            except Exception as e:
                if attempt < self._max_retries - 1:
                    logger.debug(f"[{symbol}] 新浪K线失败，重试 {attempt+2}/{self._max_retries}: {e}")
                    time.sleep(1.0 * (attempt + 1))
                    continue
                logger.warning(f"[{symbol}] 新浪K线失败(重试{self._max_retries}次): {e}")
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

    # ═══════════════════════════════════════════════
    # 数据验证
    # ═══════════════════════════════════════════════

    @staticmethod
    def _validate_kline_data(symbol: str, stock_list: List[StockData], source: str) -> bool:
        """
        验证K线数据合法性

        检查项:
        1. 收盘价 > 0
        2. 最高价 >= 最低价
        3. 数据量 >= 20（日线需要足够的历史数据）
        4. 日期格式正常

        Returns:
            True=数据合法, False=数据异常
        """
        if not stock_list:
            logger.warning(f"[{symbol}] {source}数据验证失败: 空数据")
            return False

        if len(stock_list) < 20:
            logger.warning(f"[{symbol}] {source}数据验证失败: 数据量不足({len(stock_list)}条)")
            return False

        invalid_count = 0
        date_errors = 0
        hl_errors = 0

        for k in stock_list:
            if k.close <= 0:
                invalid_count += 1
            if k.high < k.low:
                hl_errors += 1
            if not k.date or len(str(k.date)) < 8:
                date_errors += 1

        total = len(stock_list)
        error_rate = (invalid_count + hl_errors + date_errors) / (total * 3) if total > 0 else 1.0

        if error_rate > 0.2:
            logger.warning(
                f"[{symbol}] {source}数据验证失败: "
                f"异常率{error_rate:.1%} "
                f"(close<=0: {invalid_count}, high<low: {hl_errors}, date错误: {date_errors})"
            )
            return False

        if error_rate > 0:
            logger.debug(
                f"[{symbol}] {source}数据验证通过(少量异常): 异常率{error_rate:.1%}"
            )
        return True

    # ═══════════════════════════════════════════════
    # 交叉验证
    # ═══════════════════════════════════════════════

    def cross_validate(self, symbols: List[str], days: int = 5) -> Dict[str, dict]:
        """
        交叉验证: 用东财+新浪数据验证TDX数据准确性

        对配置中的每个标的:
        1. 获取 TDX 日线数据
        2. 获取 东财 日线数据（作为基准）
        3. 获取 新浪 日线数据（作为第二参考）
        4. 比较最近 N 天的收盘价

        Returns:
            {symbol: {"tdx_ok": bool, "eastmoney_ok": bool, "sina_ok": bool,
                      "tdx_vs_em_diff_pct": float, "valid": bool, "detail": str}}
        """
        results = {}

        for symbol in symbols:
            result = {
                "tdx_ok": False, "eastmoney_ok": False, "sina_ok": False,
                "tdx_vs_em_diff_pct": 0.0, "tdx_vs_sina_diff_pct": 0.0,
                "em_vs_sina_diff_pct": 0.0, "valid": False, "detail": ""
            }
            details = []

            # 1. TDX
            tdx_data = self._fetch_with_tdx_raw(symbol, days + 60)
            if tdx_data and len(tdx_data) >= max(days, 3):
                result["tdx_ok"] = True
                details.append(f"TDX:{len(tdx_data)}条")
            else:
                details.append("TDX:失败")

            # 2. 东财
            em_data = self._fetch_from_eastmoney(symbol, days + 60)
            if em_data and len(em_data) >= max(days, 3):
                result["eastmoney_ok"] = True
                details.append(f"东财:{len(em_data)}条")
            else:
                details.append("东财:失败")

            # 3. 新浪
            sina_data = self._fetch_from_sina(symbol, days + 60)
            if sina_data and len(sina_data) >= max(days, 3):
                result["sina_ok"] = True
                details.append(f"新浪:{len(sina_data)}条")
            else:
                details.append("新浪:失败")

            # 4. 交叉比对
            if result["tdx_ok"] and result["eastmoney_ok"]:
                result["tdx_vs_em_diff_pct"] = self._compare_closes(tdx_data, em_data, days, "TDX", "东财")
            else:
                result["tdx_vs_em_diff_pct"] = -1

            if result["tdx_ok"] and result["sina_ok"]:
                result["tdx_vs_sina_diff_pct"] = self._compare_closes(tdx_data, sina_data, days, "TDX", "新浪")
            else:
                result["tdx_vs_sina_diff_pct"] = -1

            if result["eastmoney_ok"] and result["sina_ok"]:
                result["em_vs_sina_diff_pct"] = self._compare_closes(em_data, sina_data, days, "东财", "新浪")
            else:
                result["em_vs_sina_diff_pct"] = -1

            # 5. 判定可靠性
            tdx_em = result["tdx_vs_em_diff_pct"]
            tdx_sina = result["tdx_vs_sina_diff_pct"]

            if result["tdx_ok"]:
                if tdx_em >= 0 and tdx_em < 2.0:
                    result["valid"] = True
                elif tdx_sina >= 0 and tdx_sina < 2.0:
                    result["valid"] = True
                elif tdx_em < 0 and tdx_sina < 0:
                    result["valid"] = True
                    details.append("(无他源交叉验证)")
                else:
                    result["valid"] = False
                    details.append(f"偏差大(TDXvs东财={tdx_em:.1f}%,TDXvs新浪={tdx_sina:.1f}%)")
            else:
                result["valid"] = False
                details.append("TDX不可用")

            result["detail"] = " | ".join(details)
            results[symbol] = result

        return results

    def _fetch_with_tdx_raw(self, symbol: str, days: int) -> Optional[List[StockData]]:
        """内部方法: 获取TDX原始数据（不使用缓存）用于交叉验证"""
        try:
            from .tdx_fetcher import get_tdx_fetcher
            tdx = get_tdx_fetcher()
            if tdx is None:
                return None
            kline_list = tdx.get_kline(symbol, frequency=4, offset=days)
            if not kline_list:
                return None
            stock_list = []
            for k in kline_list:
                try:
                    stock_list.append(StockData(
                        symbol=symbol, name='', date=k.get('date', ''),
                        open=float(k.get('open', 0)), close=float(k.get('close', 0)),
                        high=float(k.get('high', 0)), low=float(k.get('low', 0)),
                        volume=float(k.get('volume', 0)), amount=float(k.get('amount', 0)),
                    ))
                except (ValueError, TypeError):
                    continue
            return stock_list if stock_list else None
        except Exception:
            return None

    @staticmethod
    def _compare_closes(data_a: List[StockData], data_b: List[StockData],
                        days: int, label_a: str, label_b: str) -> float:
        """比较两组K线最近N天收盘价偏差，返回平均偏差百分比"""
        def make_date_map(data: List[StockData]) -> Dict[str, float]:
            result = {}
            for k in data:
                date_str = str(k.date)[:10]
                if k.close > 0:
                    result[date_str] = k.close
            return result

        map_a = make_date_map(data_a)
        map_b = make_date_map(data_b)

        common = sorted(set(map_a.keys()) & set(map_b.keys()))
        if not common:
            return -1

        compare = common[-min(days, len(common)):]
        if not compare:
            return -1

        total_diff = 0.0
        count = 0
        for d in compare:
            pa, pb = map_a[d], map_b[d]
            if pa > 0 and pb > 0:
                total_diff += abs(pa - pb) / max(pa, pb) * 100
                count += 1

        if count == 0:
            return -1

        avg = total_diff / count
        if avg > 1.0:
            logger.debug(f"交叉验证 {label_a} vs {label_b}: 平均偏差 {avg:.2f}%")

        return round(avg, 2)

    # ═══════════════════════════════════════════════
    # 批量获取
    # ═══════════════════════════════════════════════

    def fetch_batch(
        self,
        symbols: List[str],
        days: int = 60,
    ) -> Dict[str, List[StockData]]:
        """
        获取多只标的的K线数据

        默认串行 + 延迟，防东财限频。max_workers>1 时用线程池并发。
        已缓存的标的会直接复用，不会重新请求。

        Args:
            symbols: 代码列表
            days: 每只获取天数

        Returns:
            {symbol: [StockData]} 成功获取的标的
        """
        results: Dict[str, List[StockData]] = {}
        total = len(symbols)

        if total == 0:
            return results

        # 先检查缓存，分离已缓存和需要获取的
        now = time.time()
        need_fetch = []
        for sym in symbols:
            cache_key = f"{sym}_{days}"
            if cache_key in self._cache and (now - self._cache_time.get(cache_key, 0)) < self._cache_ttl:
                results[sym] = self._cache[cache_key]
            else:
                need_fetch.append(sym)

        if need_fetch:
            logger.info(
                f"开始获取 {len(need_fetch)}/{total} 只标的K线数据 "
                f"(缓存命中 {len(results)}, 并发={self.max_workers}, 延迟={self.delay_per_request}s)..."
            )
            start_time = time.time()

            if self.max_workers <= 1:
                # 串行模式：最稳定，防限频
                for i, sym in enumerate(need_fetch):
                    try:
                        kline = self.fetch_one(sym, days)
                        if kline:
                            results[sym] = kline
                    except Exception as e:
                        logger.debug(f"{sym} 获取异常: {e}")

                    if (i + 1) % 50 == 0:
                        logger.info(f"K线获取进度: {i+1}/{len(need_fetch)}")

                    # 请求间延迟
                    if i < len(need_fetch) - 1:
                        time.sleep(self.delay_per_request)
            else:
                # 并发模式：有限并发 + 延迟提交
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    future_map = {}
                    for i, sym in enumerate(need_fetch):
                        future_map[executor.submit(self.fetch_one, sym, days)] = sym
                        if i < len(need_fetch) - 1:
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
                            logger.info(f"K线获取进度: {done_count}/{len(need_fetch)}")

            elapsed = time.time() - start_time
            logger.info(
                f"K线获取完成: {len(results)}/{total} 只, 耗时 {elapsed:.1f}s"
            )
        else:
            logger.info(f"K线数据全部命中缓存: {len(results)}/{total} 只")

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
        """代码 -> 东财 secid"""
        if symbol.startswith("6"):
            return f"1.{symbol}"
        else:
            return f"0.{symbol}"

    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
        self._cache_time.clear()
        logger.info("K线缓存已清空")
