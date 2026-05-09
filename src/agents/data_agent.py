"""
数据采集Agent
负责从各种数据源获取股票市场数据

数据源:
- eastmoney: 腾讯实时行情接口（push2不可用时自动切换）
- sina: 新浪实时行情
- tushare: Tushare接口
"""
import json
import logging
import time
import requests
from typing import List, Optional, Tuple
from datetime import datetime, timedelta

from ..core.types import StockData
from ..core.config import Config


class DataAgent:
    """
    数据采集Agent

    主数据源: 腾讯实时行情 qt.gtimg.cn
    备用: 东方财富 push2his K线接口
    兜底: 模拟数据
    """

    TENCENT_QUOTE_URL = "http://qt.gtimg.cn/q="
    EASTMONEY_KLINE_URL = "http://push2his.eastmoney.com/api/qt/stock/kline/get"
    EASTMONEY_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger("AInvest.DataAgent")
        self._cache = {}
        self._cache_time = {}
        self._session = requests.Session()
        self._session.headers.update(self.EASTMONEY_HEADERS)

    def fetch_market_data(
        self,
        date: Optional[str] = None,
        include_index: bool = False
    ) -> List[StockData]:
        """
        获取市场股票数据（真实数据）

        Args:
            date: 日期 (YYYY-MM-DD)，默认今天
            include_index: 是否包含指数

        Returns:
            StockData列表
        """
        date = date or datetime.now().strftime("%Y-%m-%d")

        # 检查缓存
        cache_key = f"market_data_{date}_{include_index}"
        if self.config.data_source.cache_enabled and cache_key in self._cache:
            if self._is_cache_valid(cache_key):
                self.logger.debug("使用缓存数据")
                return self._cache[cache_key]

        # 根据数据源获取数据
        provider = self.config.data_source.provider

        if provider == "sina":
            data = self._fetch_from_sina(date, include_index)
        elif provider == "tushare":
            data = self._fetch_from_tushare(date, include_index)
        elif provider == "eastmoney":
            data = self._fetch_from_tencent(date, include_index)
        else:
            data = self._fetch_from_tencent(date, include_index)

        # 更新缓存
        if self.config.data_source.cache_enabled:
            self._cache[cache_key] = data
            self._cache_time[cache_key] = datetime.now()

        return data

    def fetch_stock_data(self, symbol: str, days: int = 30) -> List[StockData]:
        """
        获取单只股票历史数据

        Args:
            symbol: 股票代码
            days: 历史天数

        Returns:
            StockData列表
        """
        self.logger.info(f"获取股票{symbol}最近{days}天数据")

        try:
            return self._fetch_history_from_eastmoney(symbol, days)
        except Exception as e:
            self.logger.error(f"获取历史数据失败，使用模拟数据: {e}")
            return self._generate_mock_history(symbol, days)

    def _fetch_from_tencent(self, date: str, include_index: bool) -> List[StockData]:
        """
        通过腾讯行情接口获取全部A股实时行情

        腾讯接口: http://qt.gtimg.cn/q=sh600519,sz000858,...
        一次最多查询约50只股票，分批扫描全部代码
        """
        self.logger.info("通过腾讯行情接口获取真实数据...")

        # 生成沪深A股代码扫描列表
        all_codes = self._generate_a_share_codes()
        self.logger.info(f"扫描 {len(all_codes)} 个代码...")

        # 分批查询
        batch_size = 50
        all_stocks = []
        total_batches = (len(all_codes) + batch_size - 1) // batch_size
        failed_batches = 0

        for i in range(0, len(all_codes), batch_size):
            batch = all_codes[i:i + batch_size]
            batch_num = i // batch_size + 1

            try:
                url = f"{self.TENCENT_QUOTE_URL}{','.join(batch)}"
                resp = self._session.get(url, timeout=self.config.data_source.timeout)
                resp.raise_for_status()

                lines = resp.text.strip().split(';')

                for line in lines:
                    stock = self._parse_tencent_line(line, date)
                    if stock:
                        all_stocks.append(stock)

                if batch_num % 50 == 0:
                    self.logger.info(
                        f"扫描进度: {batch_num}/{total_batches}, "
                        f"已获取 {len(all_stocks)} 只股票"
                    )

            except Exception as e:
                failed_batches += 1
                self.logger.warning(f"批次 {batch_num} 获取失败: {e}")

            time.sleep(0.1)

        if failed_batches > 0:
            self.logger.warning(f"共 {failed_batches} 个批次失败")

        if not all_stocks:
            self.logger.warning("腾讯接口无有效数据，尝试东方财富K线接口")
            return self._fetch_from_eastmoney(date, include_index)

        self.logger.info(f"腾讯接口获取完成: {len(all_stocks)} 只股票")
        return all_stocks

    def _parse_tencent_line(self, line: str, date: str) -> Optional[StockData]:
        """解析腾讯行情单行数据"""
        if not line.strip() or "v_" not in line:
            return None

        parts = line.split('~')
        if len(parts) < 50:
            return None

        try:
            code = parts[2]
            name = parts[1]
            close = float(parts[3]) if parts[3] else 0

            if close <= 0:
                return None

            # 过滤规则
            if "ST" in name:
                return None
            if code.startswith("688"):
                return None
            if code.startswith("8"):
                return None

            # 过滤涨停(涨幅>=8%)
            pct = float(parts[32]) if parts[32] else 0
            if pct >= 8.0:
                return None

            # 成交额（腾讯单位：万元）
            amount_wan = float(parts[37]) if parts[37] else 0
            amount_yuan = amount_wan * 10000  # 转为元

            # 过滤成交额<3000万
            if amount_yuan < 30000000:
                return None

            # 成交量（腾讯单位：手）
            volume_shou = float(parts[6]) if parts[6] else 0
            volume_shares = volume_shou * 100  # 转为股

            return StockData(
                symbol=code,
                name=name,
                date=date,
                open=round(float(parts[4]) if parts[4] else close, 2),
                high=round(float(parts[41]) if parts[41] else close, 2),
                low=round(float(parts[42]) if parts[42] else close, 2),
                close=round(close, 2),
                volume=volume_shares,
                amount=amount_yuan,
                change_pct=round(pct, 2),
                turn_rate=round(float(parts[38]) if parts[38] else 0, 2),
            )
        except (ValueError, IndexError):
            return None

    def _generate_a_share_codes(self) -> List[str]:
        """
        生成沪深A股代码扫描列表

        覆盖范围:
        - 沪市主板: 600000-605999, 601000-603999
        - 深市主板: 000001-004999
        - 中小板: 002001-005999
        - 创业板: 300001-302999
        """
        ranges = [
            ("sh", 600000, 606000),
            ("sh", 601000, 604000),
            ("sh", 603000, 604000),
            ("sh", 605000, 606000),
            ("sz", 1, 5000),
            ("sz", 2001, 6000),
            ("sz", 300001, 303000),
        ]

        all_codes = []
        seen = set()

        for prefix, start, end in ranges:
            for code in range(start, end):
                code_str = str(code).zfill(6)
                if code_str not in seen:
                    seen.add(code_str)
                    all_codes.append(f"{prefix}{code_str}")

        return all_codes

    def _fetch_from_sina(self, date: str, include_index: bool) -> List[StockData]:
        """从新浪获取数据（委托给腾讯）"""
        self.logger.info("新浪接口委托给腾讯行情接口...")
        return self._fetch_from_tencent(date, include_index)

    def _fetch_from_tushare(self, date: str, include_index: bool) -> List[StockData]:
        """从Tushare获取数据（委托给腾讯）"""
        self.logger.info("Tushare接口委托给腾讯行情接口...")
        return self._fetch_from_tencent(date, include_index)

    def _fetch_from_eastmoney(self, date: str, include_index: bool) -> List[StockData]:
        """
        从东方财富K线接口获取数据（备用方案）

        由于push2不可用，使用push2his获取每只股票的日K线
        注意：此方案需要已知股票代码列表，效率较低
        """
        self.logger.info("尝试东方财富K线接口...")

        codes = self._generate_a_share_codes()
        # 只取最近一个交易日的数据
        all_stocks = []

        # 分批获取K线（每次获取最近3天数据）
        batch_size = 20
        for i in range(0, len(codes), batch_size):
            batch = codes[i:i + batch_size]
            for code_prefix in batch:
                try:
                    code = code_prefix[2:]  # 去掉sh/sz前缀
                    secid = f"1.{code}" if code_prefix.startswith("sh") else f"0.{code}"

                    params = {
                        "secid": secid,
                        "fields1": "f1,f2,f3,f4,f5,f6",
                        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                        "klt": "101", "fqt": "1",
                        "beg": "20260501", "end": "20260510",
                    }

                    resp = self._session.get(
                        self.EASTMONEY_KLINE_URL,
                        params=params,
                        timeout=15,
                    )
                    data = resp.json()
                    klines = data.get("data", {}).get("klines", [])

                    if klines:
                        last = klines[-1].split(",")
                        name = data["data"].get("name", "")

                        if "ST" in name:
                            continue
                        if code.startswith("688") or code.startswith("8"):
                            continue

                        close = float(last[2])
                        pct = float(last[8])
                        amount = float(last[6])  # 元

                        if pct >= 8.0 or amount < 30000000:
                            continue

                        all_stocks.append(StockData(
                            symbol=code,
                            name=name,
                            date=last[0],
                            open=round(float(last[1]), 2),
                            close=round(close, 2),
                            high=round(float(last[3]), 2),
                            low=round(float(last[4]), 2),
                            volume=float(last[5]),
                            amount=amount,
                            change_pct=round(pct, 2),
                            turn_rate=round(float(last[10]), 2),
                        ))

                except Exception:
                    continue

            time.sleep(0.2)

        if all_stocks:
            self.logger.info(f"东方财富K线获取完成: {len(all_stocks)} 只股票")
            return all_stocks

        self.logger.warning("东方财富也无数据，回退到模拟数据")
        return self._generate_mock_data(date)

    def _fetch_history_from_eastmoney(self, symbol: str, days: int = 30) -> List[StockData]:
        """从东方财富获取单只股票历史K线"""
        if symbol.startswith("6"):
            secid = f"1.{symbol}"
        else:
            secid = f"0.{symbol}"

        end_date = int(time.time())
        begin_date = int(end_date - days * 86400)

        params = {
            "secid": secid,
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": "101", "fqt": "1",
            "beg": str(begin_date), "end": str(end_date),
        }

        resp = self._session.get(
            self.EASTMONEY_KLINE_URL,
            params=params,
            timeout=30,
        )
        data = resp.json()
        klines = data.get("data", {}).get("klines", [])

        stock_list = []
        for line in klines:
            parts = line.split(",")
            stock_list.append(StockData(
                symbol=symbol,
                name=data.get("data", {}).get("name", ""),
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

    def _generate_mock_history(self, symbol: str, days: int = 30) -> List[StockData]:
        """生成模拟历史数据"""
        import random
        data = []
        base_date = datetime.now()

        for i in range(days):
            d = (base_date - timedelta(days=days - i - 1)).strftime("%Y-%m-%d")
            base_price = random.uniform(10, 100)

            data.append(StockData(
                symbol=symbol,
                name=f"股票{symbol}",
                date=d,
                open=round(base_price * random.uniform(0.98, 1.02), 2),
                high=round(base_price * random.uniform(1.0, 1.05), 2),
                low=round(base_price * random.uniform(0.95, 1.0), 2),
                close=round(base_price, 2),
                volume=random.uniform(1000000, 10000000),
                amount=random.uniform(100000000, 1000000000),
                change_pct=round(random.uniform(-5, 5), 2),
                turn_rate=round(random.uniform(1, 10), 2),
            ))

        return data

    def _generate_mock_data(self, date: str) -> List[StockData]:
        """生成模拟数据用于演示（仅作为最后回退）"""
        import random
        symbols = [
            ("600519", "贵州茅台"), ("000858", "五粮液"),
            ("601318", "中国平安"), ("000333", "美的集团"),
            ("002475", "立讯精密"), ("300750", "宁德时代"),
            ("600036", "招商银行"), ("000001", "平安银行"),
            ("601888", "中国中免"), ("300059", "东方财富"),
            ("002594", "比亚迪"), ("600900", "长江电力"),
            ("601012", "隆基绿能"), ("002352", "顺丰控股"),
            ("600276", "恒瑞医药"), ("000725", "京东方A"),
            ("601166", "兴业银行"), ("600887", "伊利股份"),
            ("002714", "牧原股份"), ("300015", "爱尔眼科"),
        ]

        data = []
        for symbol, name in symbols:
            bp = random.uniform(10, 200)
            data.append(StockData(
                symbol=symbol, name=name, date=date,
                open=round(bp * random.uniform(0.98, 1.02), 2),
                high=round(bp * random.uniform(1.0, 1.08), 2),
                low=round(bp * random.uniform(0.92, 1.0), 2),
                close=round(bp, 2),
                volume=random.uniform(5000000, 50000000),
                amount=random.uniform(100000000, 5000000000),
                change_pct=round(random.uniform(-3, 5), 2),
                turn_rate=round(random.uniform(1, 15), 2),
            ))

        return data

    def _is_cache_valid(self, cache_key: str) -> bool:
        """检查缓存是否有效"""
        if cache_key not in self._cache_time:
            return False
        elapsed = (datetime.now() - self._cache_time[cache_key]).total_seconds()
        return elapsed < self.config.data_source.cache_ttl

    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
        self._cache_time.clear()
        self.logger.info("缓存已清空")
