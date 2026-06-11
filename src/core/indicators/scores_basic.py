"""
基础评分函数 (v2.6.7)
- calc_technical_score: 技术面综合评分
- calc_pattern_score: 形态评分
- calc_trend_score: 趋势评分
- calc_position_score: 位置评分
- calc_anti_trap_penalty: 防套惩罚（大幅放宽，核心逻辑转向成交量信号）
- calc_volume_surge_bonus: ⭐新增 连续放量加分（替代价格上涨作为主要信号）
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
    """v2.6.7: 放宽位置评分，允许30天上涨50%的标的"""
    pos = indicators.get("position_20d", 50)
    if pos < 30:
        return 15.0
    elif pos < 50:
        return 10.0
    elif pos < 70:
        return 5.0
    elif pos < 90:
        return 0.0
    else:
        return -5.0  # was -20.0, 仅轻微扣分


def calc_anti_trap_penalty(
    indicators: Dict[str, float],
    change_pct: float,
    turn_rate: float,
    amount: float,
) -> float:
    """v2.6.7: 大幅放宽防套惩罚，核心逻辑转向成交量信号

    核心理念变更：
    - 旧版：惩罚连续上涨+放量（认为高位出货）
    - 新版：当前市场无连续上涨趋势，连续放量是预判上涨的核心信号
    - 仅对极端情况施加轻微惩罚
    """
    penalty = 0.0
    pos_20 = indicators.get("position_20d", 50)
    consecutive_up = indicators.get("consecutive_up", 0)
    is_low = pos_20 < 40
    is_high = pos_20 > 92  # was 80

    # ── 连续上涨惩罚（阈值 6→10，大幅放宽）──
    if consecutive_up >= 10:  # was 6
        extra_days = consecutive_up - 9  # was -5
        if is_high:
            p = min(extra_days * 3, 12)  # was 5, 25 → 减半
        elif is_low:
            p = min(extra_days * 1, 3)  # was 2, 8
        else:
            p = min(extra_days * 2, 8)  # was 3, 16
        penalty += p

    # ── 接近20日高点（放宽）──
    dist_high = indicators.get("dist_from_20d_high", 100)
    if dist_high is not None and dist_high < 1.0 and change_pct > 5:  # was 2.0, 3
        penalty += 5  # was 10

    # ── 高换手+大涨（阈值大幅放宽）──
    if turn_rate > 12 and change_pct > 9:  # was 8, 7
        if is_high:
            penalty += 8  # was 15
        elif is_low:
            penalty += 2  # was 5
        else:
            penalty += 5  # was 10

    # ── 单日涨幅过大 ──
    if change_pct > 12:  # was 9
        penalty += 5  # was 10

    # ── 高位+高振幅 ──
    avg_amp = indicators.get("avg_amplitude_5d", 3)
    if pos_20 > 98 and avg_amp > 12:  # was 95, 8
        penalty += 5  # was 10

    # ── 尾盘拉高出货 ──
    close_pos = indicators.get("close_position_today", 50)
    if close_pos < 30 and change_pct > 1:
        penalty += 10  # 保留：尾盘拉高确实危险

    # ⚠️ v2.6.7 删除：连续上涨+放量 不再惩罚
    # 旧版规则被证明在当前市场环境下过度过滤
    # 当前无连续上涨趋势，连续放量反而是预判上涨的核心信号

    return round(min(penalty, 20), 1)  # was 40


def calc_volume_surge_bonus(indicators: Dict[str, float]) -> float:
    """v2.6.7 新增: 连续放量加分

    核心理念：当前市场无连续上涨趋势，连续成交量放大
    是预判潜在连续上涨的最可靠信号。

    加分规则：
    - 连续2天放量: +3
    - 连续3-4天放量: +6
    - 连续5天以上放量: +10
    - 配合量比递增: 额外+2~+5
    """
    cv_up = indicators.get("consecutive_volume_up", 0)
    vol_ratio = indicators.get("volume_ratio", 1.0)
    bonus = 0.0

    if cv_up >= 5:
        bonus += 10
    elif cv_up >= 3:
        bonus += 6
    elif cv_up >= 2:
        bonus += 3

    # 量比递增加分（放量在加速）
    if vol_ratio >= 2.0 and cv_up >= 2:
        bonus += 5
    elif vol_ratio >= 1.5 and cv_up >= 2:
        bonus += 2

    return round(bonus, 1)


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
