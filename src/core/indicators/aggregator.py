"""
指标聚合器 — calc_all_indicators()
一次性计算所有技术指标，返回最新值字典

v2.6.5 指标集（40+个）:
  SMA(5/10/20/60/120), 5日均量, 量比, 20/60日位置, 距高低点距离
  连续涨跌天数, 日内收盘位置, 5日平均振幅
  30日箱体(振幅/突破/均量比), 20日均线粘合度, RSI14
  突破前高检测(20/60日), 累计涨幅(5/10日), MACD(DIF/DEA/柱/金叉)
  布林带(上/中/下/突破), 均线多头排列, 距MA10/MA20距离
  前N日涨跌幅(1/2/3日前), 回调确认, 持续上涨, MA5拐头向上
"""
import numpy as np
from typing import Dict, Optional
from .compute import (
    calc_sma, calc_rsi, calc_macd, calc_bbands,
)


def calc_all_indicators(
    close: np.ndarray,
    volume: np.ndarray,
    high: Optional[np.ndarray] = None,
    low: Optional[np.ndarray] = None,
) -> Dict[str, float]:
    n = len(close)
    result: Dict[str, float] = {}

    # SMA
    if n >= 5:
        result["sma5"] = float(np.mean(close[-5:]))
    if n >= 10:
        result["sma10"] = float(np.mean(close[-10:]))
    if n >= 20:
        result["sma20"] = float(np.mean(close[-20:]))
    if n >= 60:
        result["sma60"] = float(np.mean(close[-60:]))
    if n >= 120:
        result["sma120"] = float(np.mean(close[-120:]))

    # 5日均量
    if n >= 6:
        vol_ma5 = float(np.mean(volume[-6:-1]))
        vol_today = float(volume[-1])
        result["vol_ma5"] = vol_ma5
        result["volume_ratio"] = vol_today / vol_ma5 if vol_ma5 > 0 else 1.0
    elif n >= 5:
        result["vol_ma5"] = float(np.mean(volume[-5:]))
        result["volume_ratio"] = 1.0

    # 位置百分位
    if n >= 20:
        close_20 = close[-20:]
        low_20 = np.min(close_20)
        high_20 = np.max(close_20)
        range_20 = high_20 - low_20
        if range_20 > 0:
            result["position_20d"] = float((close[-1] - low_20) / range_20 * 100)
        else:
            result["position_20d"] = 50.0
        result["dist_from_20d_high"] = float((high_20 - close[-1]) / close[-1] * 100)
        result["dist_from_20d_low"] = float((close[-1] - low_20) / close[-1] * 100)

    if n >= 60:
        close_60 = close[-60:]
        low_60 = np.min(close_60)
        high_60 = np.max(close_60)
        range_60 = high_60 - low_60
        if range_60 > 0:
            result["position_60d"] = float((close[-1] - low_60) / range_60 * 100)
        result["dist_from_60d_high"] = float((high_60 - close[-1]) / close[-1] * 100)

    # 连续上涨/下跌天数
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

    # 连续放量天数（v2.6.7新增）
    # 统计连续N日成交量超过前5日均量的天数，预判潜在上涨
    consecutive_volume_up = 0
    if n >= 11:  # 需要至少10天量能历史
        for i in range(n - 1, max(n - 11, 0), -1):
            start_idx = max(0, i - 5)
            if start_idx >= i:
                break
            vol_ma5 = float(np.mean(volume[start_idx:i]))
            if vol_ma5 > 0 and volume[i] > vol_ma5 * 1.05:  # 超5日均量5%
                consecutive_volume_up += 1
            else:
                break
    result["consecutive_volume_up"] = consecutive_volume_up

    # 收盘在日内K线的位置
    if high is not None and low is not None and n > 0:
        today_high = float(high[-1])
        today_low = float(low[-1])
        today_range = today_high - today_low
        if today_range > 0:
            result["close_position_today"] = float((close[-1] - today_low) / today_range * 100)
        else:
            result["close_position_today"] = 50.0

    # 近N日平均振幅
    if high is not None and low is not None and n >= 5:
        amplitudes = []
        for i in range(max(n - 5, 0), n):
            if close[i] > 0:
                amp = (high[i] - low[i]) / close[i] * 100
                amplitudes.append(amp)
        if amplitudes:
            result["avg_amplitude_5d"] = float(np.mean(amplitudes))

    # 箱体检测
    if n >= 30:
        close_30 = close[-30:]
        box_high_30 = float(np.max(close_30))
        box_low_30 = float(np.min(close_30))
        box_range = box_high_30 - box_low_30
        if box_low_30 > 0:
            result["box_range_30d"] = float(box_range / box_low_30 * 100)
            result["breakout_pct"] = float((close[-1] - box_high_30) / box_high_30 * 100)
            result["box_high_30"] = box_high_30
            result["box_low_30"] = box_low_30
            if volume is not None and n >= 35:
                vol_30_avg = float(np.mean(volume[-35:-5]))
                vol_5_avg = float(np.mean(volume[-6:-1]))
                if vol_30_avg > 0:
                    result["box_vol_ratio"] = float(vol_5_avg / vol_30_avg)

    # 均线粘合度
    if n >= 20:
        sma5_series = calc_sma(close, 5)
        sma10_series = calc_sma(close, 10)
        sma20_series = calc_sma(close, 20)
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
            result["ma_convergence_days"] = sum(1 for d in distances if d < 2.0)

    # RSI
    rsi_arr = calc_rsi(close, 14)
    if not np.isnan(rsi_arr[-1]):
        result["rsi14"] = float(rsi_arr[-1])

    # 突破前高
    if n >= 20:
        close_20 = close[-21:-1]
        if len(close_20) > 0:
            high_20d = float(np.max(close_20))
            result["breakout_20d_high"] = bool(close[-1] > high_20d)
            result["dist_to_20d_high"] = float((close[-1] - high_20d) / high_20d * 100)
    if n >= 60:
        close_60 = close[-61:-1]
        if len(close_60) > 0:
            high_60d = float(np.max(close_60))
            result["breakout_60d_high"] = bool(close[-1] > high_60d)
            result["dist_to_60d_high"] = float((close[-1] - high_60d) / high_60d * 100)

    # 累计涨幅
    if n >= 4:
        price_3d_ago = float(close[-4]) if n >= 4 else float(close[0])
        if price_3d_ago > 0:
            result["cumulative_change_3d"] = float((close[-1] - price_3d_ago) / price_3d_ago * 100)
    if n >= 5:
        price_5d_ago = float(close[-6]) if n >= 6 else float(close[0])
        if price_5d_ago > 0:
            result["cumulative_change_5d"] = float((close[-1] - price_5d_ago) / price_5d_ago * 100)
    if n >= 8:
        price_7d_ago = float(close[-8]) if n >= 8 else float(close[0])
        if price_7d_ago > 0:
            result["cumulative_change_7d"] = float((close[-1] - price_7d_ago) / price_7d_ago * 100)
    if n >= 10:
        price_10d_ago = float(close[-11]) if n >= 11 else float(close[0])
        if price_10d_ago > 0:
            result["cumulative_change_10d"] = float((close[-1] - price_10d_ago) / price_10d_ago * 100)

    # MACD
    if n >= 35:
        macd_data = calc_macd(close)
        dif_last = macd_data["dif"][-1]
        dea_last = macd_data["dea"][-1]
        macd_last = macd_data["macd"][-1]
        if not np.isnan(dif_last):
            result["macd_dif"] = float(dif_last)
            result["macd_dea"] = float(dea_last)
            result["macd_hist"] = float(macd_last)
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

    # 距均线距离
    close_last = float(close[-1])
    if "sma10" in result:
        result["dist_to_ma10"] = abs(close_last - result["sma10"]) / result["sma10"] * 100
    if "sma20" in result:
        result["dist_to_ma20"] = abs(close_last - result["sma20"]) / result["sma20"] * 100

    # 前N日涨跌幅
    if n >= 3:
        result["daily_change_1d_ago"] = float((close[-2] - close[-3]) / close[-3] * 100) if close[-3] != 0 else 0
    if n >= 4:
        result["daily_change_2d_ago"] = float((close[-3] - close[-4]) / close[-4] * 100) if close[-4] != 0 else 0
    if n >= 5:
        result["daily_change_3d_ago"] = float((close[-4] - close[-5]) / close[-5] * 100) if close[-5] != 0 else 0

    # 回调确认
    if n >= 5:
        today_change_pct = float((close[-1] - close[-2]) / close[-2] * 100) if close[-2] != 0 else 0
        is_stable = today_change_pct >= -0.5
        pullback_count = 0
        for offset in range(1, 4):
            if n > offset + 1:
                prev_change = float((close[-(offset+1)] - close[-(offset+2)]) / close[-(offset+2)] * 100) if close[-(offset+2)] != 0 else 0
                if -5 <= prev_change <= -1:
                    pullback_count += 1
                else:
                    break
        result["pullback_confirm"] = pullback_count >= 1 and is_stable
    else:
        result["pullback_confirm"] = False

    # 持续上涨
    if "sma20" in result and "sma60" in result and "sma120" in result:
        result["sustained_uptrend"] = (
            close_last > result["sma20"] > result["sma60"] > result["sma120"]
        )

    # MA5拐头向上
    if n >= 8:
        sma5_now = float(np.mean(close[-5:]))
        sma5_3d_ago = float(np.mean(close[-8:-3]))
        result["ma5_turning_up"] = sma5_now > sma5_3d_ago


    # ── v2.6.9 新增: RSI动量强度 ─────────────────────────────────
    # RSI动量 = RSI今日值 - RSI N日前值（反映RSI从低位回升的强度）
    if n >= 35:  # 至少需要21天计算RSI动量
        rsi_arr_full = calc_rsi(close, 14)
        rsi_today = rsi_arr_full[-1]
        rsi_5d_ago = rsi_arr_full[-6] if n >= 6 and not np.isnan(rsi_arr_full[-6]) else None
        rsi_10d_ago = rsi_arr_full[-11] if n >= 11 and not np.isnan(rsi_arr_full[-11]) else None
        if not np.isnan(rsi_today):
            result["rsi_momentum_5d"] = float(rsi_today - rsi_5d_ago) if rsi_5d_ago is not None and not np.isnan(rsi_5d_ago) else 0.0
            result["rsi_momentum_10d"] = float(rsi_today - rsi_10d_ago) if rsi_10d_ago is not None and not np.isnan(rsi_10d_ago) else 0.0
            # RSI由弱转强: 5日RSI动量>0 说明短期强势在积累
            result["rsi_strengthening"] = result["rsi_momentum_5d"] > 0

    # ── v2.6.9 新增: 30日累计涨幅 ─────────────────────────────────
    if n >= 31:
        price_30d_ago = float(close[-31])
        if price_30d_ago > 0:
            result["cumulative_change_30d"] = float((close[-1] - price_30d_ago) / price_30d_ago * 100)
    # ─────────────────────────────────────────────────────────────

    return result
