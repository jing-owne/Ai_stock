"""
基础评分函数
- calc_technical_score: 技术面综合评分
- calc_pattern_score: 形态评分
- calc_trend_score: 趋势评分
- calc_position_score: 位置评分
- calc_anti_trap_penalty: 防套惩罚
- calc_low_absorb_score: 低吸评分
"""
from typing import Dict


def calc_technical_score(indicators: Dict[str, float]) -> float:
    score = 50.0
    if indicators.get("ma_bullish_align"):
        score += 15
    if indicators.get("above_sma5"):
        score += 10
    rsi = indicators.get("rsi14")
    if rsi is not None:
        if 40 < rsi < 70:
            score += 10
        elif rsi < 30:
            score += 5
    if indicators.get("macd_golden_cross"):
        score += 15
    elif indicators.get("macd_above_signal"):
        score += 8
    if indicators.get("above_bb_upper"):
        score += 10
    elif indicators.get("below_bb_lower"):
        score += 3
    return min(score, 100.0)


def calc_pattern_score(indicators: Dict[str, float], volume_ratio: float) -> float:
    score = 50.0
    if indicators.get("above_bb_upper"):
        score += 15
    if indicators.get("below_bb_lower"):
        score += 5
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


def calc_position_score(indicators: Dict[str, float]) -> float:
    pos = indicators.get("position_20d", 50)
    if pos < 30:
        return 20.0
    elif pos < 50:
        return 10.0
    elif pos < 70:
        return 0.0
    elif pos < 90:
        return -10.0
    else:
        return -20.0


def calc_anti_trap_penalty(
    indicators: Dict[str, float],
    change_pct: float,
    turn_rate: float,
    amount: float,
) -> float:
    penalty = 0.0
    pos_20 = indicators.get("position_20d", 50)
    consecutive_up = indicators.get("consecutive_up", 0)
    is_low = pos_20 < 40
    is_high = pos_20 > 80

    if consecutive_up >= 6:
        extra_days = consecutive_up - 5
        if is_high:
            p = min(extra_days * 5, 25)
        elif is_low:
            p = min(extra_days * 2, 8)
        else:
            p = min(extra_days * 3, 16)
        penalty += p

    dist_high = indicators.get("dist_from_20d_high", 100)
    if dist_high is not None and dist_high < 2.0 and change_pct > 3:
        penalty += 10

    if turn_rate > 8 and change_pct > 7:
        if is_high:
            penalty += 15
        elif is_low:
            penalty += 5
        else:
            penalty += 10

    if change_pct > 9:
        penalty += 10

    avg_amp = indicators.get("avg_amplitude_5d", 3)
    if pos_20 > 95 and avg_amp > 8:
        penalty += 10

    close_pos = indicators.get("close_position_today", 50)
    if close_pos < 30 and change_pct > 1:
        penalty += 10

    vol_ratio = indicators.get("volume_ratio", 1.0)
    if consecutive_up >= 5 and vol_ratio > 3.0:
        if is_high:
            penalty += 10
        elif is_low:
            pass
        else:
            penalty += 5

    return round(min(penalty, 40), 1)


def calc_low_absorb_score(indicators: Dict[str, float]) -> float:
    score = 0.0
    consecutive_down = indicators.get("consecutive_down", 0)
    if consecutive_down >= 4:
        score += 25
    elif consecutive_down >= 2:
        score += 15
    pos_20 = indicators.get("position_20d", 50)
    if pos_20 < 30:
        score += 20
    rsi = indicators.get("rsi14")
    if rsi is not None and rsi < 35:
        score += 15
    if indicators.get("macd_golden_cross"):
        score += 20
    close_pos = indicators.get("close_position_today", 50)
    if close_pos > 70:
        score += 10
    return min(score, 100.0)
