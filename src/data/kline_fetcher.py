"""
K线数据并发获取模块

设计目标:
- 并发获取多只标的的K线数据，用于技术指标计算
- 10线程并发: 200只约6秒, 500只约15秒
- 支持批量获取 + 结果缓存（内存 + 当日磁盘）

数据源说明:
- 新浪通道: 自动模式首选（稳定、不限频）
- 腾讯通道: 自动模式次选
- 东财通道: 自动模式末选（push2 子域名易 RemoteDisconnected）
- TDX通道: 仅分析流程使用，依赖WorkBuddy通达信应用

数据流区分:
- 选标的流程（生产）: 自动模式 新浪→腾讯→东财 三源 fallback + 超时熔断
- 分析流程（TDX）: 使用 source='tdx'，只走 TDX 通道

熔断策略:
- 单次请求超时 3s
- 单源连续 3 次失败 → 标记不可用，本轮跳过该源
"""

import json
import logging
import os
import time
from dataclasses import asdict
from datetime import datetime, timedelta
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
    SOURCE_TDX = "tdx"
    SOURCE_EASTMONEY = "eastmoney"
    SOURCE_SINA = "sina"
    SOURCE_TENCENT = "tencent"

    # 自动模式优先级（开关关闭时）：新浪 → 腾讯 → 东财
    AUTO_SOURCE_ORDER = [SOURCE_SINA, SOURCE_TENCENT, SOURCE_EASTMONEY]
    # TDX开关打开时优先级：TDX → 新浪 → 腾讯 → 东财
    AUTO_SOURCE_ORDER_WITH_TDX = [SOURCE_TDX, SOURCE_SINA, SOURCE_TENCENT, SOURCE_EASTMONEY]

    # TDX开关（从strategy_config.json读取）
    _tdx_enabled: Optional[bool] = None

    EASTMONEY_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    SINA_KLINE_URL = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
    TENCENT_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    TENCENT_QUOTE_URL = "http://qt.gtimg.cn/q="  # 实时行情（仅用于刷新磁盘缓存中冻结的"今日"bar）
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://quote.eastmoney.com/",
    }

    def __init__(self, max_workers: int = 8, timeout: int = 15, delay_per_request: float = 0.015,
                 source: str = None, no_cache: bool = False):
        """
        Args:
            source: 数据源选择
                - None（默认）: 自动模式，根据TDX开关决定优先级
                - "tdx": 仅TDX通道（需WorkBuddy通达信应用支持，分析流程）
                - "eastmoney": 仅东财通道
                - "sina": 仅新浪通道
        """
        self.max_workers = max_workers
        self.timeout = timeout
        self.delay_per_request = delay_per_request
        self.source = source
        self.no_cache = no_cache
        self._cache: Dict[str, List[StockData]] = {}
        self._cache_time: Dict[str, float] = {}
        self._cache_ttl = 21600  # 6小时缓存（早上9:30设置，下午16:00仍有效）
        self._eastmoney_available: Optional[bool] = None
        self._tdx_available: Optional[bool] = None
        self._max_retries = 1  # 单源最大重试次数（熔断由上层统一处理）

        # ── 超时熔断状态 ──
        self._request_timeout = 3  # 单次请求超时 3s
        self._circuit_threshold = 3  # 连续 3 次失败 → 熔断
        # 初始化所有可能的数据源（含TDX）
        all_sources = self.AUTO_SOURCE_ORDER_WITH_TDX
        self._source_fail_count: Dict[str, int] = {s: 0 for s in all_sources}
        self._source_available: Dict[str, bool] = {s: True for s in all_sources}

        # ── 当日磁盘缓存 ──
        self._disk_cache_root = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "cache", "kline"
        )
        # action2: 实例化时即清理过期K线缓存（保留最近2天），保证任何调用路径都触发清理，
        # 不再只依赖 fetch_batch。
        self._cleanup_old_kline_cache(keep_days=2)

    @classmethod
    def _is_tdx_enabled(cls) -> bool:
        """从strategy_config.json读取TDX开关状态"""
        if cls._tdx_enabled is not None:
            return cls._tdx_enabled
        try:
            from ..core.config import load_runtime_config
            cfg = load_runtime_config()
            cls._tdx_enabled = cfg.get("tdx_data_source", cfg.get("tdx_enabled", False))
            logger.info(f"TDX数据源开关: {'开启' if cls._tdx_enabled else '关闭'}")
        except Exception as e:
            logger.debug(f"读取TDX开关失败，默认关闭: {e}")
            cls._tdx_enabled = False
        return cls._tdx_enabled

    @staticmethod
    def _filter_as_of(kline_list: Optional[List[StockData]], as_of: Optional[str], days: int) -> Optional[List[StockData]]:
        if not kline_list:
            return kline_list
        if not as_of:
            return kline_list[-days:] if len(kline_list) > days else kline_list
        cutoff = str(as_of)[:10]
        filtered = [k for k in kline_list if str(k.date)[:10] <= cutoff]
        if len(filtered) > days:
            filtered = filtered[-days:]
        return filtered or None

    def fetch_one(self, symbol: str, days: int = 60, as_of: Optional[str] = None) -> Optional[List[StockData]]:
        """
        获取单只标的K线数据

        Fallback 根据 source 配置:
        - source="tdx": 只用TDX（分析流程）
        - source="eastmoney": 东财
        - source="sina": 新浪
        - source=None: 自动模式（生产流程：新浪→腾讯→东财 三源 fallback + 熔断）

        Args:
            symbol: 纯数字代码
            days: 获取最近多少天

        Returns:
            StockData 列表，从旧到新排列；失败返回 None
        """
        cache_key = f"{symbol}_{days}_{as_of or 'latest'}"
        now = time.time()

        if not self.no_cache:
            # 检查内存缓存
            if cache_key in self._cache and (now - self._cache_time.get(cache_key, 0)) < self._cache_ttl:
                return self._filter_as_of(self._cache[cache_key], as_of, days)

            # 检查当日磁盘缓存（跨进程复用"历史"K线，避免重复拉取）
            disk_hit = self._load_disk_cache(symbol, days)
            if disk_hit:
                # action1: 历史 bar 复用磁盘缓存；但"今日"那根 bar 必须实时刷新，
                # 否则盘中会沿用开盘快照，导致技术信号全天不变。
                if as_of is None:
                    disk_hit = self._refresh_last_bar_realtime(symbol, disk_hit, days)
                disk_hit = self._filter_as_of(disk_hit, as_of, days)
                if not disk_hit:
                    return None
                self._cache[cache_key] = disk_hit
                self._cache_time[cache_key] = now
                logger.debug(f"[{symbol}] K线磁盘缓存命中(末根已实时刷新): {len(disk_hit)}条")
                return disk_hit

        # ═══════════════════════════════════════════════
        # 根据 source 选择数据源路由
        # ═══════════════════════════════════════════════
        if self.source == self.SOURCE_TDX:
            # 分析流程：TDX优先 + fallback
            result = self._fetch_with_tdx(symbol, days, cache_key, now)
            return self._filter_as_of(result, as_of, days)
        elif self.source == self.SOURCE_EASTMONEY:
            result = self._fetch_from_eastmoney(symbol, days)
            result = self._filter_as_of(result, as_of, days)
            if result:
                self._cache[cache_key] = result
                self._cache_time[cache_key] = now
                if as_of is None:
                    self._save_disk_cache(symbol, result)
            return result
        elif self.source == self.SOURCE_SINA:
            result = self._fetch_from_sina(symbol, days)
            result = self._filter_as_of(result, as_of, days)
            if result:
                self._cache[cache_key] = result
                self._cache_time[cache_key] = now
                if as_of is None:
                    self._save_disk_cache(symbol, result)
            return result
        else:
            # 自动模式：根据TDX开关决定优先级
            # 开关ON:  TDX → 新浪 → 腾讯 → 东财
            # 开关OFF: 新浪 → 腾讯 → 东财
            result = self._fetch_auto(symbol, days, cache_key, now)
            return self._filter_as_of(result, as_of, days)

    # ═══════════════════════════════════════════════
    # action1: 末根实时刷新（盘中日K线的"今日"bar 必须实时）
    # ═══════════════════════════════════════════════

    def _fetch_today_bar(self, symbol: str) -> Optional[List[StockData]]:
        """实时拉取标的"今日"那根日K线 bar（腾讯实时行情）。

        仅用于替换磁盘缓存中冻结的"今日 bar"，历史 bar 仍走磁盘缓存。
        返回 [StockData(date=今天)] 或 None（拉取失败/非交易日尚无今日bar）。
        """
        tc_symbol = f"sh{symbol}" if symbol.startswith("6") else f"sz{symbol}"
        url = f"{self.TENCENT_QUOTE_URL}{tc_symbol}"
        try:
            session = requests.Session()
            session.headers.update({
                "User-Agent": self.HEADERS["User-Agent"],
                "Referer": "https://finance.qq.com/",
            })
            resp = session.get(url, timeout=self._request_timeout)
            session.close()
            if resp.status_code != 200:
                return None
            line = resp.text.strip()
            if "v_" not in line or "~" not in line:
                return None
            parts = line.split('~')
            if len(parts) < 43:
                return None
            close = float(parts[3]) if parts[3] else 0
            if close <= 0:
                return None
            prev_close = float(parts[5]) if parts[5] else 0
            pct = round((close - prev_close) / prev_close * 100, 2) if prev_close else 0.0
            today = datetime.now().strftime("%Y-%m-%d")
            return [StockData(
                symbol=symbol,
                name="",
                date=today,
                open=round(float(parts[4]) if parts[4] else close, 2),
                high=round(float(parts[41]) if parts[41] else close, 2),
                low=round(float(parts[42]) if parts[42] else close, 2),
                close=round(close, 2),
                volume=float(parts[6]) * 100 if parts[6] else 0.0,       # 手→股
                amount=float(parts[37]) * 10000 if parts[37] else 0.0,   # 万元→元
                change_pct=pct,
                turn_rate=round(float(parts[38]) if parts[38] else 0, 2),
            )]
        except Exception as e:
            logger.debug(f"[{symbol}] 实时今日bar拉取失败(不影响历史缓存): {e}")
            return None

    def _refresh_last_bar_realtime(self, symbol: str, kline_list: List[StockData], days: int) -> List[StockData]:
        """若磁盘缓存末根日期为"今天"，则用实时今日bar替换末根；否则原样返回。

        历史 N-1 根 bar 复用磁盘缓存（省带宽），仅"今日"那根实时刷新，
        既满足"保留历史K线、但日K线实时拉取"的缓存定位，又避免盘中沿用开盘快照。
        实时拉取失败时降级沿用缓存末根，不中断。
        """
        if not kline_list:
            return kline_list
        last = kline_list[-1]
        last_date = str(last.date)[:10]
        today = datetime.now().strftime("%Y-%m-%d")
        if last_date != today:
            # 末根不是今天（如周末/休市后首根仍是上一交易日），无需刷新
            return kline_list
        today_bars = self._fetch_today_bar(symbol)
        if not today_bars:
            logger.debug(f"[{symbol}] 实时今日bar获取失败，沿用缓存末根")
            return kline_list
        return kline_list[:-1] + today_bars

    # ═══════════════════════════════════════════════
    # 自动模式：三源优先级 + 超时熔断
    # ═══════════════════════════════════════════════

    def _fetch_auto(self, symbol: str, days: int, cache_key: str, now: float) -> Optional[List[StockData]]:
        """自动模式：根据TDX开关选择优先级，按序遍历数据源，首个成功即返回；失败累计熔断"""
        # 根据开关决定数据源优先级
        source_order = self.AUTO_SOURCE_ORDER_WITH_TDX if self._is_tdx_enabled() else self.AUTO_SOURCE_ORDER
        
        for source in source_order:
            if not self._source_available.get(source, True):
                continue  # 已熔断，跳过
            result = self._dispatch_source(source, symbol, days)
            if result:
                self._source_fail_count[source] = 0  # 成功，重置计数
                self._cache[cache_key] = result
                self._cache_time[cache_key] = now
                self._save_disk_cache(symbol, result)
                return result
            # 失败：累计熔断计数
            self._source_fail_count[source] += 1
            if self._source_fail_count[source] >= self._circuit_threshold:
                self._source_available[source] = False
                logger.warning(
                    f"数据源 {source} 连续失败 {self._circuit_threshold} 次，已熔断切换 "
                    f"(剩余可用: {[s for s in source_order if self._source_available.get(s, True)]})"
                )
        logger.warning(f"[{symbol}] 所有数据源均失败 (优先级: {source_order})")
        return None

    def _dispatch_source(self, source: str, symbol: str, days: int) -> Optional[List[StockData]]:
        """路由到指定数据源的获取方法"""
        if source == self.SOURCE_SINA:
            return self._fetch_from_sina(symbol, days)
        elif source == self.SOURCE_TENCENT:
            return self._fetch_from_tencent(symbol, days)
        elif source == self.SOURCE_EASTMONEY:
            # 懒加载：首次使用东财时测试可用性（用自选标的），失败则跳过
            if self._eastmoney_available is None:
                self._eastmoney_available = self._test_eastmoney()
            if not self._eastmoney_available:
                return None
            return self._fetch_from_eastmoney(symbol, days)
        elif source == self.SOURCE_TDX:
            # TDX通道（开关打开时使用）
            return self._fetch_from_tdx_auto(symbol, days)
        return None

    def _fetch_from_tdx_auto(self, symbol: str, days: int) -> Optional[List[StockData]]:
        """自动模式下的TDX获取（带fallback，不使用独立缓存）"""
        from .tdx_fetcher import get_tdx_fetcher
        
        try:
            tdx = get_tdx_fetcher()
            if tdx is None:
                logger.debug(f"[{symbol}] TDX客户端未连接")
                return None

            kline_list = tdx.get_kline(symbol, frequency=4, offset=days)
            if not kline_list:
                return None

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
                    logger.debug(f"[{symbol}] TDX数据转换失败: {e}")
                    continue

            if not self._validate_kline_data(symbol, stock_list, "TDX"):
                return None
            return stock_list

        except Exception as e:
            logger.debug(f"[{symbol}] TDX自动获取失败: {e}")
            return None

    def _fetch_with_tdx(self, symbol: str, days: int,
                        cache_key: str, now: float) -> Optional[List[StockData]]:
        """使用TDX通道获取K线（带重试机制）—— 需WorkBuddy通达信应用支持
        
        分析流程数据源优先级: TDX → 新浪 → 腾讯 → 东财
        如果TDX失败，自动fallback到其他数据源
        """
        from .tdx_fetcher import get_tdx_fetcher

        last_error = None
        
        # 步骤1: 尝试TDX
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

        logger.warning(f"[{symbol}] TDX K线获取失败(重试{self._max_retries}次): {last_error}，尝试fallback...")
        
        # 步骤2: TDX失败，fallback到新浪
        result = self._fetch_from_sina(symbol, days)
        if result:
            self._cache[cache_key] = result
            self._cache_time[cache_key] = now
            self._save_disk_cache(symbol, result)
            logger.info(f"[{symbol}] Tallback到新浪成功: {len(result)}条")
            return result
        
        # 步骤3: 新浪失败，fallback到腾讯
        result = self._fetch_from_tencent(symbol, days)
        if result:
            self._cache[cache_key] = result
            self._cache_time[cache_key] = now
            self._save_disk_cache(symbol, result)
            logger.info(f"[{symbol}] Tallback到腾讯成功: {len(result)}条")
            return result
        
        # 步骤4: 腾讯失败，fallback到东财
        if self._eastmoney_available is None:
            self._eastmoney_available = self._test_eastmoney()
        if self._eastmoney_available:
            result = self._fetch_from_eastmoney(symbol, days)
            if result:
                self._cache[cache_key] = result
                self._cache_time[cache_key] = now
                self._save_disk_cache(symbol, result)
                logger.info(f"[{symbol}] Tallback到东财成功: {len(result)}条")
                return result
        
        logger.warning(f"[{symbol}] 所有数据源均失败（TDX→新浪→腾讯→东财）")
        return None

    def _load_test_symbols(self) -> List[str]:
        """从 watchlist.json + strategy_config.json 加载自选标的代码（holdings + watchlist）"""
        try:
            symbols = []
            # 持仓
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "strategy_config.json"
            )
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            symbols += [h.get("symbol") for h in cfg.get("holdings", []) if h.get("symbol")]
        except Exception as e:
            logger.debug(f"加载持仓json失败: {e}")
        try:
            # 自选
            wl_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "watchlist.json"
            )
            with open(wl_path, "r", encoding="utf-8") as f:
                wl = json.load(f)
            symbols += [w.get("symbol") for w in wl if w.get("symbol")]
        except Exception as e:
            logger.debug(f"加载自选json失败: {e}")
        if symbols:
            return symbols
        # 回退：原硬编码列表
        return ["600519", "000001", "300014"]

    def _test_eastmoney(self) -> bool:
        """测试东财K线接口是否可用（用自选标的测试，3秒超时）"""
        test_symbols = self._load_test_symbols()[:3]
        for symbol in test_symbols:
            try:
                secid = self._make_secid(symbol)
                session = requests.Session()
                session.headers.update(self.HEADERS)
                resp = session.get(
                    self.EASTMONEY_KLINE_URL,
                    params={"secid": secid, "fields1": "f1", "fields2": "f51",
                            "klt": "101", "fqt": "1", "beg": "0", "end": "20500101"},
                    timeout=self._request_timeout, verify=False,
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

        logger.info("东财K线接口不可用(自选标的测试均失败)，自动模式将优先新浪/腾讯")
        return False

    def _fetch_from_eastmoney(self, symbol: str, days: int) -> Optional[List[StockData]]:
        """从东方财富获取K线（带重试机制）"""
        try:
            secid = self._make_secid(symbol)
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
                    resp = session.get(self.EASTMONEY_KLINE_URL, params=params, timeout=self._request_timeout, verify=False)
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
                resp = session.get(self.SINA_KLINE_URL, params=params, timeout=self._request_timeout)
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

    def _fetch_from_tencent(self, symbol: str, days: int) -> Optional[List[StockData]]:
        """从腾讯获取日K线（前复权，自动模式次选源）"""
        tc_symbol = f"sh{symbol}" if symbol.startswith("6") else f"sz{symbol}"
        # param=代码,周期(day),起始,,结束,条数,前复权(qfq)
        param = f"{tc_symbol},day,,,{days},qfq"
        try:
            session = requests.Session()
            session.headers.update({"User-Agent": self.HEADERS["User-Agent"]})
            resp = session.get(
                self.TENCENT_KLINE_URL,
                params={"param": param},
                timeout=self._request_timeout,
            )
            session.close()

            if resp.status_code != 200:
                logger.debug(f"[{symbol}] 腾讯返回HTTP {resp.status_code}")
                return None

            data = resp.json()
            if not data or data.get("code") != 0:
                logger.debug(f"[{symbol}] 腾讯返回异常: code={data.get('code') if data else 'None'}")
                return None

            # 响应结构: data.{symbol}.qfqday 或 data.{symbol}.day
            symbol_data = data.get("data", {}).get(tc_symbol, {})
            klines = symbol_data.get("qfqday") or symbol_data.get("day") or []
            if not klines:
                logger.debug(f"[{symbol}] 腾讯无K线数据")
                return None

            # 每行: [date, open, close, high, low, volume, ...]
            stock_list = []
            for row in klines:
                if not row or len(row) < 6:
                    continue
                try:
                    stock_list.append(StockData(
                        symbol=symbol,
                        name="",
                        date=str(row[0]),
                        open=float(row[1]),
                        close=float(row[2]),
                        high=float(row[3]),
                        low=float(row[4]),
                        volume=float(row[5]),
                        amount=0.0,
                        change_pct=0.0,
                        turn_rate=0.0,
                    ))
                except (ValueError, TypeError):
                    continue

            # 计算涨跌幅
            for i in range(len(stock_list)):
                if i > 0 and stock_list[i-1].close > 0:
                    stock_list[i].change_pct = round(
                        (stock_list[i].close - stock_list[i-1].close) / stock_list[i-1].close * 100, 2
                    )

            if not self._validate_kline_data(symbol, stock_list, "腾讯"):
                return None
            return stock_list

        except Exception as e:
            logger.debug(f"[{symbol}] 腾讯K线失败: {e}")
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
        as_of: Optional[str] = None,
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
            cache_key = f"{sym}_{days}_{as_of or 'latest'}"
            if cache_key in self._cache and (now - self._cache_time.get(cache_key, 0)) < self._cache_ttl:
                cached = self._filter_as_of(self._cache[cache_key], as_of, days)
                if cached:
                    results[sym] = cached
                else:
                    need_fetch.append(sym)
            else:
                need_fetch.append(sym)

        if need_fetch:
            logger.info(
                f"开始获取 {len(need_fetch)}/{total} 只标的K线数据 "
                f"(缓存命中 {len(results)}, 并发={self.max_workers}, 延迟={self.delay_per_request}s)..."
            )
            start_time = time.time()
            # 顺手清理旧日期磁盘缓存（保留最近2天）
            self._cleanup_old_kline_cache(keep_days=2)

            if self.max_workers <= 1:
                # 串行模式：最稳定，防限频
                for i, sym in enumerate(need_fetch):
                    try:
                        kline = self.fetch_one(sym, days, as_of=as_of)
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
                        future_map[executor.submit(self.fetch_one, sym, days, as_of)] = sym
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

    # ═══════════════════════════════════════════════
    # 当日磁盘缓存（跨进程复用）
    # ═══════════════════════════════════════════════

    def _disk_cache_path(self, symbol: str) -> str:
        """当日K线磁盘缓存路径: cache/kline/{YYYY-MM-DD}/{symbol}.json"""
        date_str = datetime.now().strftime("%Y-%m-%d")
        return os.path.join(self._disk_cache_root, date_str, f"{symbol}.json")

    def _load_disk_cache(self, symbol: str, days: int) -> Optional[List[StockData]]:
        """加载当日磁盘缓存；命中且条数足够时返回最近 days 条（切片满足不同 days 参数）"""
        path = self._disk_cache_path(symbol)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if not isinstance(raw, list) or len(raw) < days:
                return None
            stock_list = []
            for d in raw[-days:]:
                # 兼容 pe_ratio 可选字段
                stock_list.append(StockData(
                    symbol=d.get("symbol", symbol),
                    name=d.get("name", ""),
                    date=d.get("date", ""),
                    open=float(d.get("open", 0)),
                    high=float(d.get("high", 0)),
                    low=float(d.get("low", 0)),
                    close=float(d.get("close", 0)),
                    volume=float(d.get("volume", 0)),
                    amount=float(d.get("amount", 0)),
                    change_pct=float(d.get("change_pct", 0)),
                    turn_rate=float(d.get("turn_rate", 0)),
                ))
            return stock_list
        except Exception as e:
            logger.debug(f"[{symbol}] 磁盘缓存读取失败: {e}")
            return None

    def _save_disk_cache(self, symbol: str, kline_list: List[StockData]) -> None:
        """写入当日磁盘缓存"""
        if self.no_cache:
            # no_cache 模式（TDX 分析分支）：不落盘，避免污染生产流程的磁盘缓存
            return
        if not kline_list:
            return
        path = self._disk_cache_path(symbol)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump([asdict(k) for k in kline_list], f, ensure_ascii=False)
        except Exception as e:
            logger.debug(f"[{symbol}] 磁盘缓存写入失败: {e}")

    def _cleanup_old_kline_cache(self, keep_days: int = 2) -> None:
        """清理旧日期的K线缓存目录（保留最近 keep_days 天）"""
        try:
            if not os.path.isdir(self._disk_cache_root):
                return
            today = datetime.now()
            for dirname in os.listdir(self._disk_cache_root):
                dirpath = os.path.join(self._disk_cache_root, dirname)
                if not os.path.isdir(dirpath):
                    continue
                try:
                    file_date = datetime.strptime(dirname, "%Y-%m-%d")
                except ValueError:
                    continue
                if (today - file_date).days > keep_days:
                    import shutil
                    shutil.rmtree(dirpath, ignore_errors=True)
                    logger.info(f"清理旧K线缓存目录: {dirname}")
        except Exception as e:
            logger.debug(f"清理K线缓存异常(非关键): {e}")

    def clear_cache(self):
        """清空内存缓存（磁盘缓存保留，跨运行复用）"""
        self._cache.clear()
        self._cache_time.clear()
        logger.info("K线内存缓存已清空")

    def cleanup_disk_cache(self, keep_days: int = 2):
        """手动触发磁盘缓存清理"""
        self._cleanup_old_kline_cache(keep_days)
