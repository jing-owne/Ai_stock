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

    # ── 新增：位置百分位（当前价在N日K线中的位置，0=最低，100=最高）──
    if n >= 20:
        close_20 = close[-20:]
        low_20 = np.min(close_20)
        high_20 = np.max(close_20)
        range_20 = high_20 - low_20
        if range_20 > 0:
            result["position_20d"] = float((close[-1] - low_20) / range_20 * 100)
        else:
            result["position_20d"] = 50.0
        # 距20日高点距离
        result["dist_from_20d_high"] = float((high_20 - close[-1]) / close[-1] * 100)
        # 距20日低点距离
        result["dist_from_20d_low"] = float((close[-1] - low_20) / close[-1] * 100)

    if n >= 60:
        close_60 = close[-60:]
        low_60 = np.min(close_60)
        high_60 = np.max(close_60)
        range_60 = high_60 - low_60
        if range_60 > 0:
            result["position_60d"] = float((close[-1] - low_60) / range_60 * 100)
        result["dist_from_60d_high"] = float((high_60 - close[-1]) / close[-1] * 100)

    # ── 新增：连续上涨/下跌天数 ──
    consecutive_up = 0
    consecutive_down = 0
    for i in range(n - 1, 0, -1):
        if close[i] > close[i - 1]:
            if consecutive_down == 0:
                consecutive_up += 1
            else:
                break
        elif close[i] < close[i - 1]:
            if consecutive_up == 0:
                consecutive_down += 1
            else:
                break
        else:
            break
    result["consecutive_up"] = consecutive_up
    result["consecutive_down"] = consecutive_down

    # ── 新增：收盘在日内K线的位置（0=最低，100=最高）──
    if high is not None and low is not None and n > 0:
        today_high = float(high[-1])
        today_low = float(low[-1])
        today_range = today_high - today_low
        if today_range > 0:
            result["close_position_today"] = float((close[-1] - today_low) / today_range * 100)
        else:
            result["close_position_today"] = 50.0

    # ── 新增：近N日平均振幅 ──
    if high is not None and low is not None and n >= 5:
        amplitudes = []
        for i in range(max(n - 5, 0), n):
            if close[i] > 0:
                amp = (high[i] - low[i]) / close[i] * 100
                amplitudes.append(amp)
        if amplitudes:
            result["avg_amplitude_5d"] = float(np.mean(amplitudes))

    # ── 新增：箱体检测指标 ──
    if n >= 30:
        close_30 = close[-30:]
        box_high_30 = float(np.max(close_30))
        box_low_30 = float(np.min(close_30))
        box_range = box_high_30 - box_low_30
        if box_low_30 > 0:
            # 30日箱体振幅（百分比）
            result["box_range_30d"] = float(box_range / box_low_30 * 100)
            # 当前价突破箱体上沿幅度
            result["breakout_pct"] = float((close[-1] - box_high_30) / box_high_30 * 100)
            result["box_high_30"] = box_high_30
            result["box_low_30"] = box_low_30
            # 30日均换手率（用于判断是否缩量横盘）
            if volume is not None and n >= 35:
                vol_30_avg = float(np.mean(volume[-35:-5]))
                vol_5_avg = float(np.mean(volume[-6:-1]))
                if vol_30_avg > 0:
                    result["box_vol_ratio"] = float(vol_5_avg / vol_30_avg)

    # ── 新增：均线粘合度指标 ──
    if n >= 20:
        close_20 = close[-20:]
        sma5_series = calc_sma(close, 5)
        sma10_series = calc_sma(close, 10)
        sma20_series = calc_sma(close, 20)
        # 近20天均线距离（越小越粘合）
        last_20_idx = list(range(max(0, n - 20), n))
        distances = []
        for i in last_20_idx:
            if (not np.isnan(sma5_series[i]) and
                not np.isnan(sma10_series[i]) and
                not np.isnan(sma20_series[i])):
                max_ma = max(sma5_series[i], sma10_series[i], sma20_series[i])
                min_ma = min(sma5_series[i], sma10_series[i], sma20_series[i])
                if min_ma > 0:
                    dist = (max_ma - min_ma) / min_ma * 100
                    distances.append(dist)
        if distances:
            result["ma_convergence_20d"] = float(np.mean(distances))
            # 粘合天数（均线距离<2%为粘合）
            result["ma_convergence_days"] = sum(1 for d in distances if d < 2.0)

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


def calc_position_score(indicators: Dict[str, float]) -> float:
    """
    位置评分 (0-100)
    核心逻辑：低位加分，高位扣分。避免追高被套。

    - 20日位置 < 30%: 身处低位 +20（低吸良机）
    - 20日位置 30-50%: 中等偏低 +10
    - 20日位置 50-70%: 中等偏高 +0
    - 20日位置 70-90%: 接近高位 -10
    - 20日位置 > 90%: 高位风险 -20（极易被套）
    """
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
    """
    防套惩罚分 (负值，0表示无风险)
    检测导致"今天买明天套"的典型陷阱模式。

    v2.1 优化: 区分高位陷阱 vs 低位启动
    - 低位(<40%)的连涨视为底部启动，减轻惩罚
    - 高位(>70%)的连涨视为追高风险，加重惩罚

    惩罚规则:
    - 连续上涨>=4天 + 高位: -5/天（第4天起）
    - 连续上涨>=4天 + 低位: -2/天（底部启动不重罚）
    - 距20日高点<2% + 涨幅>3%: -15（高位追涨）
    - 换手率>8% + 涨幅>5% + 高位: -20（投机性放量出货）
    - 换手率>8% + 涨幅>5% + 低位: -10（可能是启动放量）
    - 涨幅>7%（接近涨停）: -15（追板风险大）
    - 20日位置>85% + 振幅>6%: -15（高位巨震出货）
    - 收盘在日内低位(<30%): -10（尾盘跳水，次日大概率低开）
    - 连续上涨3天 + 放量>3倍 + 高位: -10（高潮放量=见顶信号）
    - 连续上涨3天 + 放量>3倍 + 低位: 不惩罚（底部放量可能是启动信号）
    """
    penalty = 0.0
    pos_20 = indicators.get("position_20d", 50)
    consecutive_up = indicators.get("consecutive_up", 0)
    is_low = pos_20 < 40
    is_high = pos_20 > 70

    # 1. 连续上涨过多
    if consecutive_up >= 4:
        extra_days = consecutive_up - 3
        if is_high:
            p = min(extra_days * 6, 25)  # 高位加重
        elif is_low:
            p = min(extra_days * 2, 8)   # 低位减轻
        else:
            p = min(extra_days * 4, 16)
        penalty += p

    # 2. 距20日高点太近 + 涨幅不小
    dist_high = indicators.get("dist_from_20d_high", 100)
    if dist_high is not None and dist_high < 2.0 and change_pct > 3:
        penalty += 15

    # 3. 换手率畸高 + 大涨
    if turn_rate > 8 and change_pct > 5:
        if is_high:
            penalty += 20  # 高位出逃
        elif is_low:
            penalty += 5   # 低位可能是启动
        else:
            penalty += 10

    # 4. 接近涨停
    if change_pct > 7:
        penalty += 15

    # 5. 高位巨震
    avg_amp = indicators.get("avg_amplitude_5d", 3)
    if pos_20 > 85 and avg_amp > 6:
        penalty += 15

    # 6. 尾盘跳水（收盘在日内低位）
    close_pos = indicators.get("close_position_today", 50)
    if close_pos < 30 and change_pct > 1:
        penalty += 10

    # 7. 连涨+放量高潮 — 区分高位见顶 vs 低位启动
    vol_ratio = indicators.get("volume_ratio", 1.0)
    if consecutive_up >= 3 and vol_ratio > 3.0:
        if is_high:
            penalty += 15  # 高位放量=见顶
        elif is_low:
            pass  # 低位放量=启动信号，不惩罚
        else:
            penalty += 5

    return round(min(penalty, 50), 1)


def calc_low_absorb_score(indicators: Dict[str, float]) -> float:
    """
    低吸评分 (0-100)
    识别适合低吸的信号：回调到位、底部企稳

    加分规则:
    - 连续下跌2-3天: +15（回调中）
    - 连续下跌>=4天: +25（深度回调，超跌反弹概率大）
    - 20日位置<30: +20（处于低位）
    - RSI<35: +15（超卖）
    - MACD金叉: +20（趋势反转信号）
    - 收盘在日内高位(>70%): +10（日内企稳信号）
    """
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


def calc_box_breakout_score(indicators: Dict[str, float]) -> float:
    """
    箱体突破评分 (0-100)
    检测长期横盘缩量后放量突破箱体上沿

    加分规则:
    - 30日箱体振幅<15%: +20（箱体整理充分）
    - 箱体振幅15-25%: +10
    - 收盘突破箱体上沿>0%: +25（突破确认）
    - 5日均量比30日>2倍: +20（放量突破）
    - 均量比1.5-2倍: +10
    - 20日位置<60%: +15（不是高位突破）
    - MACD金叉: +15
    - RSI 50-70: +10（强势不超买）
    """
    score = 0.0

    box_range = indicators.get("box_range_30d")
    if box_range is not None:
        if box_range < 15:
            score += 20
        elif box_range < 25:
            score += 10
    else:
        return 0.0  # 没有箱体数据，无法评分

    breakout = indicators.get("breakout_pct", -1)
    if breakout is not None and breakout >= 0:
        score += 25
    elif breakout is not None and breakout > -2:
        score += 10  # 接近上沿也算

    box_vol = indicators.get("box_vol_ratio", 1.0)
    if box_vol >= 2.0:
        score += 20
    elif box_vol >= 1.5:
        score += 10

    pos_20 = indicators.get("position_20d", 50)
    if pos_20 < 60:
        score += 15
    elif pos_20 >= 85:
        score -= 10  # 高位突破扣分

    if indicators.get("macd_golden_cross"):
        score += 15

    rsi = indicators.get("rsi14")
    if rsi is not None and 50 < rsi < 70:
        score += 10
    elif rsi is not None and rsi >= 70:
        score -= 5  # 超买风险

    return max(0.0, min(score, 100.0))


def calc_ma_divergence_score(indicators: Dict[str, float]) -> float:
    """
    均线多头发散评分 (0-100)
    检测均线从粘合到多头发散的过程

    加分规则:
    - 20日均线粘合度<2%: +25（高度粘合）
    - 粘合度2-4%: +15
    - 粘合天数>=5天: +10（持续粘合）
    - 均线多头排列: +20（发散确认）
    - MACD金叉: +15（趋势确认）
    - 放量(volume_ratio>1.5): +10（量能配合）
    - 20日位置<50%: +15（低位启动）
    - 连续上涨2-3天: +5（温和启动）
    """
    score = 0.0

    convergence = indicators.get("ma_convergence_20d")
    if convergence is None:
        return 0.0

    if convergence < 2.0:
        score += 25
    elif convergence < 4.0:
        score += 15
    elif convergence >= 8.0:
        return 0.0  # 均线太分散，不符合策略

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
    elif pos_20 >= 90:
        score -= 10  # 高位发散扣分

    consecutive_up = indicators.get("consecutive_up", 0)
    if 2 <= consecutive_up <= 3:
        score += 5

    return max(0.0, min(score, 100.0))
