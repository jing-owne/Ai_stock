"""
通达信(TDX) K线数据获取模块
只使用通达信通道获取标的数据
"""

import logging
from typing import Optional, List, Dict

logger = logging.getLogger("AInvest.TdxFetcher")


class TdxFetcher:
    """通达信数据获取器（单例模式）"""
    
    _instance = None
    _client = None
    _connected = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def _ensure_connected(self) -> bool:
        """确保TDX客户端已连接"""
        if self._connected and self._client:
            return True
        
        try:
            from mootdx.quotes import Quotes
            self._client = Quotes.factory(market='std')
            self._connected = True
            logger.info("TDX客户端连接成功")
            return True
        except Exception as e:
            logger.warning(f"TDX客户端连接失败: {e}")
            self._connected = False
            return False
    
    def get_kline(self, symbol: str, frequency: int = 4,
                  offset: int = 60, start: int = 0) -> Optional[List[Dict]]:
        """
        获取K线数据
        
        Args:
            symbol: 标的代码（如 000001, 600001）
            frequency: 周期 4=日线, 8=分钟线, 9=周线, 10=月线
            offset: 获取条数
            start: 起始位置
            
        Returns:
            K线数据列表 或 None
        """
        if not self._ensure_connected():
            logger.warning(f"[{symbol}] TDX客户端未连接，无法获取K线")
            return None
        
        try:
            market, code = self._make_market_code(symbol)
            logger.debug(f"[{symbol}] TDX K线请求: market={market}, code={code}, freq={frequency}")
            
            df = self._client.bars(
                symbol=code,
                frequency=frequency,
                start=start,
                offset=offset
            )
            
            if df is None:
                logger.warning(f"[{symbol}] TDX K线返回 None")
                return None
            if len(df) == 0:
                logger.warning(f"[{symbol}] TDX K线返回空DataFrame")
                return None
            
            # 转换为统一格式
            result = []
            for idx, row in df.iterrows():
                # TDX返回列: datetime, open, close, high, low, vol, amount
                datetime_str = str(row.get('datetime', ''))
                # 成交量使用 vol 列
                vol = float(row.get('vol', row.get('volume', 0)))
                
                result.append({
                    'date': datetime_str,
                    'open': float(row.get('open', 0)),
                    'close': float(row.get('close', 0)),
                    'high': float(row.get('high', 0)),
                    'low': float(row.get('low', 0)),
                    'volume': vol,
                    'amount': float(row.get('amount', 0)),
                })
            
            logger.debug(f"[{symbol}] TDX K线返回 {len(result)} 条数据")
            return result
            
        except Exception as e:
            logger.warning(f"[{symbol}] TDX K线获取失败: {e}")
            return None
    
    @staticmethod
    def _make_market_code(symbol: str) -> tuple:
        """将标的代码转换为TDX市场代码"""
        symbol = symbol.strip()
        if symbol.startswith('6') or symbol.startswith('5'):
            return 1, symbol  # 上海
        else:
            return 0, symbol  # 深圳


def get_tdx_fetcher() -> Optional[TdxFetcher]:
    """获取TDX获取器实例"""
    try:
        fetcher = TdxFetcher()
        if fetcher._ensure_connected():
            return fetcher
        return None
    except Exception as e:
        logger.warning(f"创建TDX获取器失败: {e}")
        return None
