"""
技术指标计算模块 (基于 numpy，零外部依赖)

设计目标：
- 替代 pandas-ta（冷启动18秒，单只14ms）
- numpy 手动计算：单只 0.38ms，快 41 倍
- 支持：SMA / RSI / MACD / 5日均量 / 布林带
- 输入：close/volume/high/low 的 numpy 数组或 list
- 输出：dict，每个指标返回完整序列和最新值
"""

import numpy as np
from typing import Dict, Optional


def calc_sma(close: np.ndarray, period: int = 5) -> np.ndarray:
    """简单移动平均线"""
    if len(close) < period:
        return np.array([])
    cumsum = np.cumsum(close)
    result = np.empty(len(close))
    result[:period - 1] = np.nan
    result[period - 1:] = (cumsum[period - 1:] - np.concatenate([[0], cumsum[:-period]])) / period
    return result


def calc_rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    """RSI 相对强弱指标"""
    n = len(close)
    if n < period + 1:
        return np.full(n, np.nan)

    delta = np.diff(close)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)

    # Wilder 平滑法
    rsi = np.full(n, np.nan)
    avg_gain = np.mean(gain[:period])
    avg_loss = np.mean(loss[:period])

    if avg_loss == 0:
        rsi[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi[period] = 100.0 - 100.0 / (1.0 + rs)

    for i in range(period, len(gain)):
        avg_gain = (avg_gain * (period - 1) + gain[i]) / period
        avg_loss = (avg_loss * (period - 1) + loss[i]) / period
        if avg_loss == 0:
            rsi[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i + 1] = 100.0 - 100.0 / (1.0 + rs)

    return rsi


def calc_ema(data: np.ndarray, period: int = 12) -> np.ndarray:
    """指数移动平均线"""
    n = len(data)
    if n < period:
        return np.full(n, np.nan)

    ema = np.empty(n)
    ema[:period - 1] = np.nan
    ema[period - 1] = np.mean(data[:period])

    multiplier = 2.0 / (period + 1)
    for i in range(period, n):
        ema[i] = data[i] * multiplier + ema[i - 1] * (1 - multiplier)

    return ema


def calc_macd(
    close: np.ndarray,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9
) -> Dict[str, np.ndarray]:
    """MACD 指标"""
    ema_fast = calc_ema(close, fast)
    ema_slow = calc_ema(close, slow)

    dif = ema_fast - ema_slow
    dea = calc_ema(np.nan_to_num(dif, nan=0.0), signal)
    macd_hist = 2.0 * (dif - dea)

    return {"dif": dif, "dea": dea, "macd": macd_hist}


def calc_bbands(
    close: np.ndarray,
    period: int = 20,
    std_dev: float = 2.0
) -> Dict[str, np.ndarray]:
    """布林带"""
    n = len(close)
    if n < period:
        nan_arr = np.full(n, np.nan)
        return {"upper": nan_arr, "middle": nan_arr, "lower": nan_arr}

    middle = calc_sma(close, period)
    std = np.full(n, np.nan)
    for i in range(period - 1, n):
        std[i] = np.std(close[i - period + 1:i + 1])

    upper = middle + std_dev * std
    lower = middle - std_dev * std

    return {"upper": upper, "middle": middle, "lower": lower}


def calc_volume_ma(volume: np.ndarray, period: int = 5) -> np.ndarray:
    """成交量移动平均"""
    return calc_sma(volume, period)


def calc_all_indicators(
    close: np.ndarray,
    volume: np.ndarray,
    high: Optional[np.ndarray] = None,
    low: Optional[np.ndarray] = None,
) -> Dict[str, float]:
    """
    一次性计算所有指标，返回最新值字典

    用于策略评分，只需要每个指标的最新值，不需要完整序列
    """
    n = len(close)
    result = {}

    # SMA
    if n >= 5:
        result["sma5"] = float(np.mean(close[-5:]))
    if n >= 10:
        result["sma10"] = float(np.mean(close[-10:]))
    if n >= 20:
        result["sma20"] = float(np.mean(close[-20:]))

    # 5日均量
    if n >= 6:
        vol_ma5 = float(np.mean(volume[-6:-1]))  # 前5日均量
        vol_today = float(volume[-1])
        result["vol_ma5"] = vol_ma5
        result["volume_ratio"] = vol_today / vol_ma5 if vol_ma5 > 0 else 1.0
    elif n >= 5:
        result["vol_ma5"] = float(np.mean(volume[-5:]))
        result["volume_ratio"] = 1.0

    # RSI
    rsi_arr = calc_rsi(close, 14)
    if not np.isnan(rsi_arr[-1]):
        result["rsi14"] = float(rsi_arr[-1])

    # MACD
    if n >= 35:  # MACD(12,26,9) 至少需要 35 根 K 线
        macd_data = calc_macd(close)
        dif_last = macd_data["dif"][-1]
        dea_last = macd_data["dea"][-1]
        macd_last = macd_data["macd"][-1]
        if not np.isnan(dif_last):
            result["macd_dif"] = float(dif_last)
            result["macd_dea"] = float(dea_last)
            result["macd_hist"] = float(macd_last)
            # 金叉判断: DIF > DEA 且前一天 DIF <= DEA
            if n >= 2 and not np.isnan(macd_data["dif"][-2]):
                result["macd_golden_cross"] = (
                    macd_data["dif"][-1] > macd_data["dea"][-1] and
                    macd_data["dif"][-2] <= macd_data["dea"][-2]
                )
            result["macd_above_signal"] = dif_last > dea_last

    # 布林带
    if n >= 20 and high is not None and low is not None:
        bb = calc_bbands(close, 20, 2.0)
        if not np.isnan(bb["upper"][-1]):
            result["bb_upper"] = float(bb["upper"][-1])
            result["bb_lower"] = float(bb["lower"][-1])
            result["bb_middle"] = float(bb["middle"][-1])
            close_last = float(close[-1])
            result["above_bb_upper"] = close_last > result["bb_upper"]
            result["below_bb_lower"] = close_last < result["bb_lower"]

    # 均线多头排列
    if "sma5" in result and "sma10" in result and "sma20" in result:
        result["ma_bullish_align"] = (
            result["sma5"] > result["sma10"] > result["sma20"]
        )
        close_last = float(close[-1])
        result["above_sma5"] = close_last > result["sma5"]
        result["above_sma20"] = close_last > result["sma20"]

    return result


def calc_technical_score(indicators: Dict[str, float]) -> float:
    """
    基于技术指标计算技术面综合评分 (0-100)

    评分逻辑:
    - 基础分 50
    - 均线多头排列 +15
    - 价格站上MA5 +10
    - RSI适中(40-70) +10, 超卖(<30) +5
    - MACD金叉/DIF>DEA +15
    - 布林带突破上轨 +10
    """
    score = 50.0

    # 均线多头排列
    if indicators.get("ma_bullish_align"):
        score += 15

    # 价格站上MA5
    if indicators.get("above_sma5"):
        score += 10

    # RSI
    rsi = indicators.get("rsi14")
    if rsi is not None:
        if 40 < rsi < 70:
            score += 10
        elif rsi < 30:
            score += 5  # 超卖可能反弹

    # MACD
    if indicators.get("macd_golden_cross"):
        score += 15
    elif indicators.get("macd_above_signal"):
        score += 8

    # 布林带突破
    if indicators.get("above_bb_upper"):
        score += 10
    elif indicators.get("below_bb_lower"):
        score += 3  # 触下轨可能反弹

    return min(score, 100.0)


def calc_pattern_score(indicators: Dict[str, float], volume_ratio: float) -> float:
    """
    形态评分 (0-100)，用于 AI技术面策略

    评分逻辑:
    - 基础分 50
    - 布林带突破上轨 +15
    - 放量突破(volume_ratio > 2) +10
    - 均线多头排列 +10
    - MACD金叉 +15
    """
    score = 50.0

    if indicators.get("above_bb_upper"):
        score += 15
    if indicators.get("below_bb_lower"):
        score += 5  # 触下轨反弹

    if volume_ratio >= 3.0:
        score += 10
    elif volume_ratio >= 2.0:
        score += 5

    if indicators.get("ma_bullish_align"):
        score += 10

    if indicators.get("macd_golden_cross"):
        score += 15
    elif indicators.get("macd_above_signal"):
        score += 5

    return min(score, 100.0)


def calc_trend_score(indicators: Dict[str, float]) -> float:
    """
    趋势评分 (0-100)，用于 AI技术面策略

    评分逻辑:
    - 基础分 50
    - 均线多头排列 +20
    - 价格站上MA20 +15
    - MACD > 0 +10
    - RSI > 50 +5
    """
    score = 50.0

    if indicators.get("ma_bullish_align"):
        score += 20

    if indicators.get("above_sma20"):
        score += 15

    macd_hist = indicators.get("macd_hist")
    if macd_hist is not None and macd_hist > 0:
        score += 10

    rsi = indicators.get("rsi14")
    if rsi is not None and rsi > 50:
        score += 5

    return min(score, 100.0)
