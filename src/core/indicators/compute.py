"""
基础计算模块 — 纯数学指标计算，零外部依赖
SMA / RSI / EMA / MACD / BBANDS / VMA / 重采样
"""
import numpy as np
from typing import Dict


def calc_sma(close: np.ndarray, period: int = 5) -> np.ndarray:
    if len(close) < period:
        return np.array([])
    cumsum = np.cumsum(close)
    result = np.empty(len(close))
    result[:period - 1] = np.nan
    result[period - 1:] = (cumsum[period - 1:] - np.concatenate([[0], cumsum[:-period]])) / period
    return result


def calc_rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(close)
    if n < period + 1:
        return np.full(n, np.nan)
    delta = np.diff(close)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
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


def calc_macd(close: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, np.ndarray]:
    ema_fast = calc_ema(close, fast)
    ema_slow = calc_ema(close, slow)
    dif = ema_fast - ema_slow
    dea = calc_ema(np.nan_to_num(dif, nan=0.0), signal)
    macd_hist = 2.0 * (dif - dea)
    return {"dif": dif, "dea": dea, "macd": macd_hist}


def calc_bbands(close: np.ndarray, period: int = 20, std_dev: float = 2.0) -> Dict[str, np.ndarray]:
    n = len(close)
    if n < period:
        nan_arr = np.full(n, np.nan)
        return {"upper": nan_arr, "middle": nan_arr, "lower": nan_arr}
    middle = calc_sma(close, period)
    std = np.full(n, np.nan)
    for i in range(period - 1, n):
        std[i] = np.std(close[i - period + 1:i + 1])
    return {"upper": middle + std_dev * std, "middle": middle, "lower": middle - std_dev * std}


def calc_volume_ma(volume: np.ndarray, period: int = 5) -> np.ndarray:
    return calc_sma(volume, period)


# ── 重采样 ──

def resample_to_weekly(daily_close: np.ndarray) -> np.ndarray:
    if len(daily_close) < 5:
        return np.array([])
    weekly = []
    for i in range(4, len(daily_close), 5):
        weekly.append(float(daily_close[i]))
    if len(daily_close) % 5 > 0 and len(daily_close) > 5:
        weekly.append(float(daily_close[-1]))
    return np.array(weekly)


def resample_to_monthly(daily_close: np.ndarray) -> np.ndarray:
    if len(daily_close) < 22:
        return np.array([])
    monthly = []
    for i in range(21, len(daily_close), 22):
        monthly.append(float(daily_close[i]))
    if len(daily_close) % 22 > 0 and len(daily_close) > 22:
        monthly.append(float(daily_close[-1]))
    return np.array(monthly)
