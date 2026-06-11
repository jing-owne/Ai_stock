"""
策略级评分函数
- calc_box_breakout_score: 箱体突破
- calc_ma_divergence_score: 均线多头发散
- calc_pullback_confirm_score: 回调确认
- calc_ma_support_score: 均线支撑
- calc_net_inflow_score: 资金净流入
- calc_sustained_uptrend_score: 持续上涨
- calc_bottom_rebound_score: 触底反弹
"""
import numpy as np
from typing import Dict
from .compute import calc_macd


def calc_box_breakout_score(indicators: Dict[str, float]) -> float:
    score = 0.0
    box_range = indicators.get("box_range_30d")
    if box_range is not None:
        if box_range < 15:
            score += 20
        elif box_range < 25:
            score += 10
    else:
        return 0.0
    breakout = indicators.get("breakout_pct", -1)
    if breakout is not None and breakout >= 0:
        score += 25
    elif breakout is not None and breakout > -2:
        score += 10
    box_vol = indicators.get("box_vol_ratio", 1.0)
    if box_vol >= 2.0:
        score += 20
    elif box_vol >= 1.5:
        score += 10
    pos_20 = indicators.get("position_20d", 50)
    if pos_20 < 60:
        score += 15
    elif pos_20 >= 99:  # was 95
        score -= 5  # was 10
    if indicators.get("macd_golden_cross"):
        score += 15
    rsi = indicators.get("rsi14")
    if rsi is not None and 50 < rsi < 70:
        score += 10
    elif rsi is not None and rsi >= 70:
        score -= 5
    return max(0.0, min(score, 100.0))


def calc_ma_divergence_score(indicators: Dict[str, float]) -> float:
    score = 0.0
    convergence = indicators.get("ma_convergence_20d")
    if convergence is None:
        return 0.0
    if convergence < 2.0:
        score += 25
    elif convergence < 4.0:
        score += 15
    elif convergence >= 8.0:
        return 0.0
    conv_days = indicators.get("ma_convergence_days", 0)
    if conv_days >= 5:
        score += 10
    elif conv_days >= 3:
        score += 5
    if indicators.get("ma_bullish_align"):
        score += 20
    if indicators.get("macd_golden_cross"):
        score += 15
    elif indicators.get("macd_above_signal"):
        score += 5
    vol_ratio = indicators.get("volume_ratio", 1.0)
    if vol_ratio >= 1.5:
        score += 10
    elif vol_ratio >= 1.2:
        score += 5
    pos_20 = indicators.get("position_20d", 50)
    if pos_20 < 50:
        score += 15
    elif pos_20 < 70:
        score += 5
    elif pos_20 >= 99:  # was 95
        score -= 5  # was 10
    consecutive_up = indicators.get("consecutive_up", 0)
    if 2 <= consecutive_up <= 3:
        score += 5
    return max(0.0, min(score, 100.0))


def calc_pullback_confirm_score(indicators: Dict[str, float]) -> float:
    if indicators.get("pullback_confirm"):
        return 5.0
    return 0.0


def calc_ma_support_score(indicators: Dict[str, float]) -> float:
    dist10 = indicators.get("dist_to_ma10", 999)
    dist20 = indicators.get("dist_to_ma20", 999)
    if dist10 < 3.0 or dist20 < 3.0:
        return 5.0
    return 0.0


def calc_net_inflow_score(consecutive_inflow_days: int) -> float:
    if consecutive_inflow_days >= 18:
        return 10.0
    elif consecutive_inflow_days >= 15:
        return 8.0
    elif consecutive_inflow_days >= 13:
        return 5.0
    elif consecutive_inflow_days >= 10:
        return 3.0
    return 0.0


def calc_sustained_uptrend_score(indicators: Dict[str, float]) -> float:
    if indicators.get("sustained_uptrend"):
        return 10.0
    return 0.0


def calc_bottom_rebound_score(
    daily_close: np.ndarray,
    daily_volume: np.ndarray,
) -> float:
    from .compute import resample_to_weekly, resample_to_monthly
    n = len(daily_close)
    if n < 132:
        return 0.0
    sma5_now = float(np.mean(daily_close[-5:]))
    sma5_3d_ago = float(np.mean(daily_close[-8:-3]))
    if sma5_now <= sma5_3d_ago:
        return 0.0
    weekly_close = resample_to_weekly(daily_close)
    if len(weekly_close) < 20:
        return 0.0
    sma5_w = float(np.mean(weekly_close[-5:]))
    sma10_w = float(np.mean(weekly_close[-10:]))
    sma20_w = float(np.mean(weekly_close[-20:]))
    if not (sma5_w > sma10_w > sma20_w):
        return 0.0
    monthly_close = resample_to_monthly(daily_close)
    if len(monthly_close) < 35:
        return 0.0
    macd_data = calc_macd(monthly_close)
    macd_hist_last = macd_data["macd"][-1]
    if np.isnan(macd_hist_last) or macd_hist_last <= 0.618:
        return 0.0
    return 8.0
