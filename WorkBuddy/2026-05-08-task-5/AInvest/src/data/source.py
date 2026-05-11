"""
数据源接口定义和实现
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import logging


class DataSource(ABC):
    """
    数据源抽象基类
    
    定义数据获取接口
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.logger = logging.getLogger(f"AInvest.{self.__class__.__name__}")
    
    @abstractmethod
    def get_stock_data(self, symbol: str, date: Optional[str] = None) -> Dict[str, Any]:
        """获取股票数据"""
        pass
    
    @abstractmethod
    def get_market_data(self, date: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取市场数据"""
        pass
    
    @abstractmethod
    def get_index_data(self, index_code: str, date: Optional[str] = None) -> Dict[str, Any]:
        """获取指数数据"""
        pass


class SinaDataSource(DataSource):
    """新浪数据源"""
    
    def get_stock_data(self, symbol: str, date: Optional[str] = None) -> Dict[str, Any]:
        """获取新浪股票数据"""
        self.logger.debug(f"从新浪获取股票数据: {symbol}")
        # 实际实现调用新浪API
        return {}
    
    def get_market_data(self, date: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取市场数据"""
        self.logger.debug("从新浪获取市场数据")
        return []
    
    def get_index_data(self, index_code: str, date: Optional[str] = None) -> Dict[str, Any]:
        """获取指数数据"""
        self.logger.debug(f"从新浪获取指数数据: {index_code}")
        return {}


class TushareDataSource(DataSource):
    """Tushare数据源"""
    
    def get_stock_data(self, symbol: str, date: Optional[str] = None) -> Dict[str, Any]:
        """获取Tushare股票数据"""
        self.logger.debug(f"从Tushare获取股票数据: {symbol}")
        return {}
    
    def get_market_data(self, date: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取市场数据"""
        self.logger.debug("从Tushare获取市场数据")
        return []
    
    def get_index_data(self, index_code: str, date: Optional[str] = None) -> Dict[str, Any]:
        """获取指数数据"""
        self.logger.debug(f"从Tushare获取指数数据: {index_code}")
        return {}


class EastMoneyDataSource(DataSource):
    """东方财富数据源"""
    
    def get_stock_data(self, symbol: str, date: Optional[str] = None) -> Dict[str, Any]:
        """获取东方财富股票数据"""
        self.logger.debug(f"从东方财富获取股票数据: {symbol}")
        return {}
    
    def get_market_data(self, date: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取市场数据"""
        self.logger.debug("从东方财富获取市场数据")
        return []
    
    def get_index_data(self, index_code: str, date: Optional[str] = None) -> Dict[str, Any]:
        """获取指数数据"""
        self.logger.debug(f"从东方财富获取指数数据: {index_code}")
        return {}


class TencentDataSource(DataSource):
    """
    腾讯财经数据源
    行情接口：https://stockapp.finance.qq.com/mstats/#mod=list&id=sh_a&module=SH&type=sha
    实时报价：https://qt.gtimg.cn/q=sh600519
    分时/K线：https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_dayfq&param=sh600519,day,,,20,qfq
    市场涨跌统计：https://stockapp.finance.qq.com/mstats/api/getListInfo
    使用说明：
      - 无需登录/Token，适合行情快照和单票查询
      - get_stock_data() symbol 格式：sh600519 / sz000858
      - get_index_data() index_code 格式：sh000001（上证）/ sz399001（深证）/ sz399006（创业板）
    """

    _BASE_QT = "https://qt.gtimg.cn/q={symbol}"
    _BASE_KLINE = (
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        "?_var=kline_dayfq&param={symbol},day,,,{count},qfq"
    )

    def _request(self, url: str) -> str:
        import urllib.request
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Referer": "https://stockapp.finance.qq.com/",
            }
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.read().decode("gbk", errors="replace")

    def get_stock_data(self, symbol: str, date: Optional[str] = None) -> Dict[str, Any]:
        """
        获取腾讯财经实时行情快照
        symbol: sz000858 / sh600519 格式
        返回字段: symbol, name, price, change_pct, volume, amount, open, high, low, close
        """
        self.logger.debug(f"从腾讯财经获取股票数据: {symbol}")
        try:
            raw = self._request(self._BASE_QT.format(symbol=symbol))
            # 格式: v_sh600519="1~贵州茅台~600519~1700.00~..."
            import re
            m = re.search(r'"([^"]+)"', raw)
            if not m:
                return {}
            parts = m.group(1).split("~")
            if len(parts) < 50:
                return {}
            return {
                "symbol": parts[2],
                "name": parts[1],
                "price": float(parts[3]) if parts[3] else None,
                "close": float(parts[3]) if parts[3] else None,
                "open": float(parts[5]) if parts[5] else None,
                "close_yesterday": float(parts[4]) if parts[4] else None,
                "high": float(parts[33]) if parts[33] else None,
                "low": float(parts[34]) if parts[34] else None,
                "volume": float(parts[36]) * 100 if parts[36] else None,  # 手→股
                "amount": float(parts[37]) * 10000 if parts[37] else None,  # 万元→元
                "change_pct": float(parts[32]) if parts[32] else None,
                "turn_rate": float(parts[38]) if parts[38] else None,
            }
        except Exception as e:
            self.logger.warning(f"腾讯财经获取{symbol}数据失败: {e}")
            return {}

    def get_market_data(self, date: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取市场数据（腾讯财经暂不支持全市场批量拉取，返回空）"""
        self.logger.debug("腾讯财经不支持全量市场数据拉取，跳过")
        return []

    def get_index_data(self, index_code: str, date: Optional[str] = None) -> Dict[str, Any]:
        """
        获取指数实时行情
        index_code: sh000001 / sz399001 / sz399006
        """
        self.logger.debug(f"从腾讯财经获取指数数据: {index_code}")
        return self.get_stock_data(index_code)


class TonghuashuDataSource(DataSource):
    """
    同花顺数据源
    主站：https://www.10jqka.com.cn/
    实时行情（iFind）：https://d.10jqka.com.cn/v2/realtime/hs_{code}/last.js
    个股资金流向：https://d.10jqka.com.cn/v2/fflow/hs_{code}/last.js
    板块行情：https://q.10jqka.com.cn/index/index/board/all/field/zdf/order/desc/page/1/ajax/1/
    使用说明：
      - 无需登录，适合资金流向、板块排行等辅助分析
      - symbol 格式：纯6位代码，如 600519 / 000858
      - 返回 JS 格式响应，需正则提取 JSON 内容
    """

    _BASE_RT = "https://d.10jqka.com.cn/v2/realtime/hs_{code}/last.js"
    _BASE_FF = "https://d.10jqka.com.cn/v2/fflow/hs_{code}/last.js"

    def _request(self, url: str) -> str:
        import urllib.request
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Referer": "https://www.10jqka.com.cn/",
            }
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.read().decode("gbk", errors="replace")

    def _extract_json(self, raw: str) -> Dict[str, Any]:
        """从 JS 变量赋值中提取 JSON 对象"""
        import re, json
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        return {}

    def get_stock_data(self, symbol: str, date: Optional[str] = None) -> Dict[str, Any]:
        """
        获取同花顺实时行情
        symbol: 纯6位代码 600519 / 000858
        """
        code = symbol.lstrip("shSHszSZ")  # 兼容带前缀格式
        self.logger.debug(f"从同花顺获取股票数据: {code}")
        try:
            raw = self._request(self._BASE_RT.format(code=code))
            data = self._extract_json(raw)
            items = data.get("items", [])
            if not items:
                return {}
            row = items[0]
            # items 字段顺序参见同花顺 iFind 文档
            # [date, open, high, low, close, volume, amount, turn_rate, change_pct, ...]
            return {
                "symbol": code,
                "date": row[0] if len(row) > 0 else None,
                "open": float(row[1]) if len(row) > 1 and row[1] else None,
                "high": float(row[2]) if len(row) > 2 and row[2] else None,
                "low": float(row[3]) if len(row) > 3 and row[3] else None,
                "close": float(row[4]) if len(row) > 4 and row[4] else None,
                "volume": float(row[5]) if len(row) > 5 and row[5] else None,
                "amount": float(row[6]) if len(row) > 6 and row[6] else None,
                "turn_rate": float(row[7]) if len(row) > 7 and row[7] else None,
                "change_pct": float(row[8]) if len(row) > 8 and row[8] else None,
            }
        except Exception as e:
            self.logger.warning(f"同花顺获取{code}数据失败: {e}")
            return {}

    def get_fund_flow(self, symbol: str) -> Dict[str, Any]:
        """
        获取个股资金流向（同花顺专有扩展接口）
        返回: main_in（主力流入）、main_out、retail_in、retail_out 等
        """
        code = symbol.lstrip("shSHszSZ")
        self.logger.debug(f"从同花顺获取资金流向: {code}")
        try:
            raw = self._request(self._BASE_FF.format(code=code))
            return self._extract_json(raw)
        except Exception as e:
            self.logger.warning(f"同花顺获取{code}资金流向失败: {e}")
            return {}

    def get_market_data(self, date: Optional[str] = None) -> List[Dict[str, Any]]:
        """同花顺不支持全量市场数据批量拉取，返回空"""
        self.logger.debug("同花顺不支持全量市场数据拉取，跳过")
        return []

    def get_index_data(self, index_code: str, date: Optional[str] = None) -> Dict[str, Any]:
        """
        获取指数数据
        index_code: sh000001 / sz399001 格式，自动去前缀
        """
        self.logger.debug(f"从同花顺获取指数数据: {index_code}")
        return self.get_stock_data(index_code)


class XueqiuDataSource(DataSource):
    """
    雪球数据源
    主站：https://xueqiu.com/
    K线/行情：https://stock.xueqiu.com/v5/stock/chart/kline.json?symbol=SH600519&begin={ts}&period=day&type=before&count=-30&indicator=kline
    实时快照：https://stock.xueqiu.com/v5/stock/realtime/quotec.json?symbol=SH600519
    使用说明：
      - 需要携带 cookie（xq_a_token），可通过访问 https://xueqiu.com 获得，匿名也可尝试
      - symbol 格式：SH600519 / SZ000858（大写）
      - 部分接口需登录，建议先用匿名 Token，失败后降级
      - get_stock_data() 返回最新一日行情快照
    """

    _BASE_QUOTE = "https://stock.xueqiu.com/v5/stock/realtime/quotec.json?symbol={symbol}"
    _BASE_KLINE = (
        "https://stock.xueqiu.com/v5/stock/chart/kline.json"
        "?symbol={symbol}&begin={begin}&period=day&type=before&count=-{count}&indicator=kline"
    )

    def _normalize_symbol(self, symbol: str) -> str:
        """将 sh600519 / 600519 统一转换为雪球格式 SH600519"""
        s = symbol.strip()
        if s[:2].lower() in ("sh", "sz"):
            return s[:2].upper() + s[2:]
        # 根据代码段判断市场
        if s.startswith(("6", "5")):
            return "SH" + s
        return "SZ" + s

    def _request(self, url: str) -> str:
        import urllib.request
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://xueqiu.com/",
                "Accept": "application/json, text/plain, */*",
            }
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode("utf-8")

    def get_stock_data(self, symbol: str, date: Optional[str] = None) -> Dict[str, Any]:
        """
        获取雪球实时行情快照
        symbol: sh600519 / SH600519 / 600519 均可
        返回字段: symbol, name, current(现价), change_pct, volume, amount, open, high, low
        """
        import json
        xq_symbol = self._normalize_symbol(symbol)
        self.logger.debug(f"从雪球获取股票数据: {xq_symbol}")
        try:
            raw = self._request(self._BASE_QUOTE.format(symbol=xq_symbol))
            data = json.loads(raw)
            items = data.get("data", [])
            if not items:
                return {}
            q = items[0]
            return {
                "symbol": q.get("symbol", xq_symbol),
                "name": q.get("name", ""),
                "close": q.get("current"),
                "price": q.get("current"),
                "open": q.get("open"),
                "high": q.get("high"),
                "low": q.get("low"),
                "volume": q.get("volume"),
                "amount": q.get("amount"),
                "change_pct": q.get("percent"),
                "turn_rate": q.get("turnover_rate"),
                "pe_ttm": q.get("pe_ttm"),
                "pb": q.get("pb"),
                "market_cap": q.get("market_capital"),
            }
        except Exception as e:
            self.logger.warning(f"雪球获取{xq_symbol}数据失败: {e}")
            return {}

    def get_kline(self, symbol: str, count: int = 30) -> List[Dict[str, Any]]:
        """
        获取雪球 K 线数据（扩展接口）
        返回最近 count 个交易日的 OHLCV 数据
        """
        import json, time
        xq_symbol = self._normalize_symbol(symbol)
        begin = int(time.time() * 1000)
        self.logger.debug(f"从雪球获取K线: {xq_symbol} count={count}")
        try:
            url = self._BASE_KLINE.format(symbol=xq_symbol, begin=begin, count=count)
            raw = self._request(url)
            data = json.loads(raw)
            columns = data.get("data", {}).get("column", [])
            items = data.get("data", {}).get("item", [])
            return [dict(zip(columns, row)) for row in items]
        except Exception as e:
            self.logger.warning(f"雪球获取{xq_symbol} K线失败: {e}")
            return []

    def get_market_data(self, date: Optional[str] = None) -> List[Dict[str, Any]]:
        """雪球不支持全量市场数据批量拉取，返回空"""
        self.logger.debug("雪球不支持全量市场数据拉取，跳过")
        return []

    def get_index_data(self, index_code: str, date: Optional[str] = None) -> Dict[str, Any]:
        """
        获取指数数据
        index_code: sh000001 / SH000001 / 000001 均可
        """
        self.logger.debug(f"从雪球获取指数数据: {index_code}")
        return self.get_stock_data(index_code)
