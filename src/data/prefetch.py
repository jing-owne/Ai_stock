"""
K线预取与指标计算 — 公共工具函数
消除 StrategyAgent 和 CompositeStrategy 之间的代码重复
"""
import gc
import logging
from typing import Dict, List, Optional, Tuple

from .kline_fetcher import KlineFetcher
from ..core.indicators import calc_all_indicators

logger = logging.getLogger("AInvest.Prefetch")


def prefetch_kline_indicators(
    symbols: List[str],
    kline_fetcher: Optional[KlineFetcher] = None,
    days: int = 600,  # 600日K ≈ 30月线 → 满足MACD(12,26,9)的26月最低要求
    keep_kline: bool = False,
    log_prefix: str = "",
    as_of: Optional[str] = None,
) -> Tuple[Dict[str, Dict], Dict[str, list], int]:
    """
    预取K线并计算技术指标（逐只处理，防OOM）

    Args:
        symbols: 标的代码列表
        kline_fetcher: KlineFetcher 实例，为 None 时自动创建
        days: 拉取天数
        keep_kline: 是否保留原始K线列表（供底部反弹周线/月线分析使用）
        log_prefix: 日志前缀

    Returns:
        (indicator_cache, kline_cache, calc_count)
        - indicator_cache: symbol → 指标字典
        - kline_cache: symbol → K线列表（仅当 keep_kline=True 时填充，否则空字典）
        - calc_count: 成功计算的标的数
    """
    if kline_fetcher is None:
        kline_fetcher = KlineFetcher()

    total = len(symbols)
    pf = f"[{log_prefix}] " if log_prefix else ""
    logger.info(f"{pf}预获取 {total} 只K线（逐只处理）...")

    indicator_cache: Dict[str, Dict] = {}
    kline_cache: Dict[str, list] = {}
    calc_count = 0

    for i, symbol in enumerate(symbols, 1):
        if i % 50 == 0:
            logger.info(f"{pf}K线进度: {i}/{total}")
            gc.collect()

        kline_list = kline_fetcher.fetch_batch([symbol], days=days, as_of=as_of).get(symbol, [])
        if not kline_list:
            continue

        arrays = kline_fetcher.get_numpy_arrays(kline_list)
        if arrays:
            indicator_cache[symbol] = calc_all_indicators(
                arrays["close"], arrays["volume"],
                arrays["high"], arrays["low"]
            )
            if keep_kline:
                kline_cache[symbol] = kline_list
            calc_count += 1
            del arrays

    logger.info(f"{pf}指标计算完成: {calc_count}/{total} 只")
    return indicator_cache, kline_cache, calc_count
