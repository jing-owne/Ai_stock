"""
A股 涨跌停约束工具

规则（v2.8 近似）：
  - 主板(60/000/001)、中小板(002) 涨跌停 ±10%
  - 创业板(300)、科创板(688) 涨跌停 ±20%
  - 北交所(8xx/4xx) 涨跌停 ±30%
  - ST 标的涨跌停 ±5%
  - 涨停：无法买入（无卖盘）；跌停：无法卖出（无买盘）
"""

from ..core.types import StockData

# 20% 涨跌停板块前缀
_LIMIT_20_PREFIXES = ("688", "300")
_LIMIT_30_PREFIXES = ("4", "8")


def is_st(name: str = "") -> bool:
    n = str(name or "").upper()
    return "ST" in n or "＊ST" in n or "*ST" in n


def limit_pct(symbol: str, name: str = "") -> float:
    """返回该标的涨跌停幅度（小数），默认 0.10"""
    s = str(symbol).upper()
    if is_st(name):
        return 0.05
    if s.startswith(_LIMIT_30_PREFIXES):
        return 0.30
    if s.startswith(_LIMIT_20_PREFIXES):
        return 0.20
    return 0.10


def is_suspended(bar: StockData) -> bool:
    """近似停牌：成交量和成交额均为0，或OHLC异常缺失。"""
    return (
        bar.volume <= 0
        and bar.amount <= 0
    ) or min(bar.open, bar.high, bar.low, bar.close) <= 0


def is_one_price_limit(bar: StockData) -> bool:
    """一字板近似判定：开高低收相同且触及涨/跌停。"""
    same_price = (
        abs(bar.open - bar.high) < 1e-6
        and abs(bar.high - bar.low) < 1e-6
        and abs(bar.low - bar.close) < 1e-6
    )
    return same_price and (is_limit_up(bar) or is_limit_down(bar))


def is_limit_up(bar: StockData, tol: float = 0.03) -> bool:
    # change_pct 为百分比(如 +10.0)，limit_pct 为小数(0.10)，需 ×100 对齐
    pct = limit_pct(bar.symbol, bar.name) * 100
    return bar.change_pct >= (pct - tol)


def is_limit_down(bar: StockData, tol: float = 0.03) -> bool:
    pct = limit_pct(bar.symbol, bar.name) * 100
    return bar.change_pct <= (-pct + tol)


def limit_status(bar: StockData) -> str:
    if is_suspended(bar):
        return "suspended"
    if is_limit_up(bar):
        return "limit_up_one_price" if is_one_price_limit(bar) else "limit_up"
    if is_limit_down(bar):
        return "limit_down_one_price" if is_one_price_limit(bar) else "limit_down"
    return "normal"


def can_buy(bar: StockData) -> bool:
    """涨停不可买"""
    return not is_suspended(bar) and not is_limit_up(bar)


def can_sell(bar: StockData) -> bool:
    """跌停不可卖"""
    return not is_suspended(bar) and not is_limit_down(bar)
