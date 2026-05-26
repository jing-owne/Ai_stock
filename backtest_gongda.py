"""回测共达电声 002655 4/5-4/10 是否被v2.1策略选中"""
import sys
sys.path.insert(0, 'src')

# 手动构建K线数据，模拟 calc_all_indicators 的输入
# 格式: (date, open, high, low, close, volume, amount, turnover)

raw_data = []
data_lines = """2026-02-02 | 12.80 | 12.93 | 12.41 | 12.45 | 113808
2026-02-03 | 12.66 | 12.76 | 12.55 | 12.72 | 97833
2026-02-04 | 12.68 | 12.93 | 12.63 | 12.83 | 93509
2026-02-05 | 12.78 | 12.84 | 12.56 | 12.59 | 70721
2026-02-06 | 12.57 | 12.78 | 12.42 | 12.63 | 74579
2026-02-09 | 12.78 | 12.84 | 12.64 | 12.80 | 67517
2026-02-10 | 12.99 | 14.08 | 12.88 | 14.08 | 610140
2026-02-11 | 13.79 | 14.23 | 13.70 | 14.00 | 682483
2026-02-12 | 14.20 | 14.86 | 14.06 | 14.60 | 570754
2026-02-13 | 14.60 | 16.00 | 14.49 | 15.50 | 593265
2026-02-24 | 15.92 | 16.00 | 15.31 | 15.82 | 462451
2026-02-25 | 15.93 | 16.15 | 15.50 | 15.58 | 394591
2026-02-26 | 15.50 | 15.71 | 15.30 | 15.56 | 273878
2026-02-27 | 15.41 | 17.12 | 15.08 | 17.12 | 515456
2026-03-02 | 16.75 | 18.45 | 16.75 | 17.75 | 795454
2026-03-03 | 18.10 | 18.15 | 16.75 | 16.89 | 481946
2026-03-04 | 16.50 | 17.28 | 16.50 | 16.63 | 264430
2026-03-05 | 16.96 | 17.13 | 16.17 | 16.29 | 261652
2026-03-06 | 16.27 | 17.60 | 15.82 | 16.86 | 420631
2026-03-09 | 16.83 | 17.49 | 16.25 | 17.29 | 350246
2026-03-10 | 17.55 | 17.75 | 17.13 | 17.44 | 269802
2026-03-11 | 17.45 | 17.75 | 17.23 | 17.38 | 242447
2026-03-12 | 17.49 | 17.68 | 16.80 | 17.12 | 246581
2026-03-13 | 16.99 | 17.23 | 16.68 | 16.77 | 163220
2026-03-16 | 16.75 | 18.28 | 16.28 | 17.78 | 417689
2026-03-17 | 17.85 | 18.05 | 17.10 | 17.18 | 232468
2026-03-18 | 17.27 | 18.43 | 17.11 | 18.07 | 354431
2026-03-19 | 17.90 | 18.11 | 17.48 | 17.66 | 284459
2026-03-20 | 17.84 | 17.94 | 17.13 | 17.22 | 268679
2026-03-23 | 16.86 | 17.35 | 16.20 | 16.41 | 316088
2026-03-24 | 16.60 | 17.65 | 16.38 | 17.59 | 305453
2026-03-25 | 17.62 | 17.85 | 17.42 | 17.69 | 201097
2026-03-26 | 17.54 | 17.80 | 17.33 | 17.60 | 175306
2026-03-27 | 17.51 | 17.96 | 16.95 | 17.66 | 241297
2026-03-30 | 17.38 | 18.05 | 16.80 | 17.50 | 274569
2026-03-31 | 17.52 | 19.14 | 17.17 | 18.10 | 469474
2026-04-01 | 17.99 | 18.78 | 17.81 | 18.68 | 522572
2026-04-02 | 18.45 | 18.48 | 18.02 | 18.33 | 325290
2026-04-03 | 18.33 | 19.50 | 18.22 | 18.75 | 434669
2026-04-07 | 18.79 | 19.89 | 18.57 | 19.01 | 433565
2026-04-08 | 19.01 | 20.15 | 18.95 | 19.99 | 488317
2026-04-09 | 19.60 | 21.99 | 19.44 | 21.16 | 706059
2026-04-10 | 21.45 | 22.52 | 21.15 | 21.58 | 616039
"""

for line in data_lines.strip().split('\n'):
    parts = line.strip().split(' | ')
    date = parts[0].strip()
    o = float(parts[1])
    h = float(parts[2])
    l = float(parts[3])
    c = float(parts[4])
    v = int(parts[5])
    raw_data.append({'date': date, 'open': o, 'high': h, 'low': l, 'close': c, 'volume': v})

print(f"共 {len(raw_data)} 条K线数据")
print(f"日期范围: {raw_data[0]['date']} ~ {raw_data[-1]['date']}")

# Find index for each target date
target_dates = [
    '2026-02-10', '2026-02-27',  # early breakouts
    '2026-03-31', '2026-04-01', '2026-04-02', '2026-04-03',  # pre-清明
    '2026-04-07', '2026-04-08', '2026-04-09', '2026-04-10',  # 4/5-4/10 window
]
date_indices = {}
for i, row in enumerate(raw_data):
    if row['date'] in target_dates:
        date_indices[row['date']] = i

import numpy as np

def calc_sma(arr, period):
    result = np.full(len(arr), np.nan)
    for i in range(period - 1, len(arr)):
        result[i] = np.mean(arr[i - period + 1 : i + 1])
    return result

def calc_ema(arr, period):
    result = np.full(len(arr), np.nan)
    result[period - 1] = np.mean(arr[:period])
    alpha = 2 / (period + 1)
    for i in range(period, len(arr)):
        result[i] = alpha * arr[i] + (1 - alpha) * result[i - 1]
    return result

def simulate_indicators(idx):
    """Simulate calc_all_indicators for the stock at given index (0-based, last data point)"""
    n = idx + 1
    
    opens = np.array([r['open'] for r in raw_data[:n]])
    highs = np.array([r['high'] for r in raw_data[:n]])
    lows = np.array([r['low'] for r in raw_data[:n]])
    closes = np.array([r['close'] for r in raw_data[:n]])
    volumes = np.array([r['volume'] for r in raw_data[:n]], dtype=float)
    
    date = raw_data[idx]['date']
    change_pct = float((closes[-1] - closes[-2]) / closes[-2] * 100) if n >= 2 else 0
    turn_rate = 0  # we don't have turnover in this simulated data
    
    result = {}
    
    # MA
    result['ma5'] = float(np.mean(closes[-5:])) if n >= 5 else float(closes[-1])
    result['ma10'] = float(np.mean(closes[-10:])) if n >= 10 else float(closes[-1])
    result['ma20'] = float(np.mean(closes[-20:])) if n >= 20 else float(closes[-1])
    result['ma60'] = float(np.mean(closes[-60:])) if n >= 60 else float(closes[-1])
    
    # Volume ratio (vs 5-day average)
    if n >= 6:
        vol_5_avg = np.mean(volumes[-6:-1])
        result['volume_ratio'] = float(volumes[-1] / vol_5_avg) if vol_5_avg > 0 else 1.0
    else:
        result['volume_ratio'] = 1.0
    
    # Position in 20-day range
    if n >= 20:
        c20 = closes[-20:]
        result['position_20d'] = float((closes[-1] - c20.min()) / (c20.max() - c20.min()) * 100) if c20.max() > c20.min() else 50
    else:
        result['position_20d'] = 50
    
    # Position in 60-day range
    if n >= 60:
        c60 = closes[-60:]
        result['position_60d'] = float((closes[-1] - c60.min()) / (c60.max() - c60.min()) * 100) if c60.max() > c60.min() else 50
    elif n >= 30:
        c30 = closes[-30:]
        result['position_60d'] = float((closes[-1] - c30.min()) / (c30.max() - c30.min()) * 100) if c30.max() > c30.min() else 50
    else:
        result['position_60d'] = 50
    
    # Distance from 20-day high/low
    if n >= 20:
        c20 = closes[-20:]
        h20 = c20.max()
        l20 = c20.min()
        result['dist_from_20d_high'] = float((h20 - closes[-1]) / h20 * 100)
        result['dist_from_20d_low'] = float((closes[-1] - l20) / l20 * 100)
    else:
        result['dist_from_20d_high'] = 0
        result['dist_from_20d_low'] = 0
    
    # Consecutive up/down days
    consecutive_up = 0
    consecutive_down = 0
    i = n - 1
    while i > 0 and closes[i] > closes[i-1]:
        consecutive_up += 1
        i -= 1
    i = n - 1
    while i > 0 and closes[i] < closes[i-1]:
        consecutive_down += 1
        i -= 1
    result['consecutive_up'] = consecutive_up
    result['consecutive_down'] = consecutive_down
    
    # Close position today (intraday)
    if highs[-1] > lows[-1]:
        result['close_position_today'] = float((closes[-1] - lows[-1]) / (highs[-1] - lows[-1]) * 100)
    else:
        result['close_position_today'] = 50
    
    # 30-day box range
    if n >= 30:
        c30 = closes[-30:]
        box_high = c30.max()
        box_low = c30.min()
        result['box_range_30d'] = float((box_high - box_low) / box_low * 100)
        result['breakout_pct'] = float((closes[-1] - box_high) / box_high * 100)
        result['box_high_30'] = float(box_high)
        result['box_low_30'] = float(box_low)
        # Box volume ratio: 5-day avg volume vs earlier 30-day avg
        if n >= 35:
            vol_recent = np.mean(volumes[-6:-1])
            vol_earlier = np.mean(volumes[-35:-5])
            result['box_vol_ratio'] = float(vol_recent / vol_earlier) if vol_earlier > 0 else 1.0
    
    # MA convergence (20-day average distance between MA5/MA10/MA20)
    if n >= 20:
        sma5 = calc_sma(closes, 5)
        sma10 = calc_sma(closes, 10)
        sma20_ma = calc_sma(closes, 20)
        distances = []
        for j in range(max(0, n - 20), n):
            if not (np.isnan(sma5[j]) or np.isnan(sma10[j]) or np.isnan(sma20_ma[j])):
                max_ma = max(sma5[j], sma10[j], sma20_ma[j])
                min_ma = min(sma5[j], sma10[j], sma20_ma[j])
                if min_ma > 0:
                    dist = (max_ma - min_ma) / min_ma * 100
                    distances.append(dist)
        if distances:
            result['ma_convergence_20d'] = float(np.mean(distances))
            result['ma_convergence_days'] = sum(1 for d in distances if d < 2.0)
    
    # MA bullish align (MA5 > MA10 > MA20)
    if n >= 20:
        result['ma_bullish_align'] = bool(
            result.get('ma5', 0) > result.get('ma10', 0) > result.get('ma20', 0)
        )
    
    # Average amplitude 5d
    if n >= 5:
        amps = []
        for j in range(max(0, n - 5), n):
            if closes[j] > 0:
                amps.append((highs[j] - lows[j]) / closes[j] * 100)
        result['avg_amplitude_5d'] = float(np.mean(amps)) if amps else 3.0
    
    # MACD (simplified)
    if n >= 26:
        ema12 = calc_ema(closes, 12)
        ema26 = calc_ema(closes, 26)
        dif = ema12 - ema26
        dea = calc_ema(dif, 9)
        # Golden cross: DIF crossed above DEA recently
        if n >= 3:
            prev_dif = ema12[-2] - ema26[-2]
            prev_dea = calc_ema(dif[:-1], 9)[-1] if len(dif) > 9 else dea[-1]
            cur_dif = ema12[-1] - ema26[-1]
            cur_dea = dea[-1]
            result['macd_golden_cross'] = bool(prev_dif <= prev_dea and cur_dif > cur_dea)
            result['macd_above_signal'] = bool(cur_dif > cur_dea)
    
    return result, change_pct, turn_rate

# Simulate for each target date
for tdate in target_dates:
    idx = date_indices[tdate]
    indicators, change_pct, turn_rate = simulate_indicators(idx)
    
    print(f"\n{'='*60}")
    print(f"📅 {tdate} (数据点 #{idx})")
    print(f"{'='*60}")
    print(f"收盘: {raw_data[idx]['close']:.2f} | 涨幅: {change_pct:+.2f}% | 成交额: {raw_data[idx]['volume']*100:,.0f}")
    print(f"开盘: {raw_data[idx]['open']:.2f} | 最高: {raw_data[idx]['high']:.2f} | 最低: {raw_data[idx]['low']:.2f}")
    
    # Key indicators
    print(f"\n📊 关键指标:")
    print(f"  MA5/10/20: {indicators.get('ma5', 'N/A'):.2f} / {indicators.get('ma10', 'N/A'):.2f} / {indicators.get('ma20', 'N/A'):.2f}")
    print(f"  MA多头排列: {indicators.get('ma_bullish_align', False)}")
    print(f"  20日位置: {indicators.get('position_20d', 'N/A'):.1f}%")
    print(f"  60日位置: {indicators.get('position_60d', 'N/A'):.1f}%")
    print(f"  连续上涨: {indicators.get('consecutive_up', 0)}天")
    print(f"  量比: {indicators.get('volume_ratio', 'N/A'):.2f}x")
    print(f"  5日平均振幅: {indicators.get('avg_amplitude_5d', 'N/A'):.1f}%")
    print(f"  MACD金叉: {indicators.get('macd_golden_cross', False)}")
    print(f"  MACD>信号线: {indicators.get('macd_above_signal', False)}")
    
    # Box breakout indicators
    if 'box_range_30d' in indicators:
        print(f"\n📦 箱体突破指标:")
        print(f"  30日箱体振幅: {indicators['box_range_30d']:.1f}%")
        print(f"  箱体上沿: {indicators['box_high_30']:.2f}")
        print(f"  箱体下沿: {indicators['box_low_30']:.2f}")
        print(f"  突破幅度: {indicators['breakout_pct']:+.2f}%")
        if 'box_vol_ratio' in indicators:
            print(f"  箱体量比: {indicators['box_vol_ratio']:.2f}x")
    
    # MA convergence
    if 'ma_convergence_20d' in indicators:
        print(f"\n📈 均线粘合指标:")
        print(f"  20日均线粘合度: {indicators['ma_convergence_20d']:.2f}%")
        print(f"  粘合天数(d<2%): {indicators.get('ma_convergence_days', 0)}天")
    
    # Now apply scoring
    from src.core.indicators import calc_box_breakout_score, calc_ma_divergence_score, calc_position_score, calc_anti_trap_penalty
    
    box_score = calc_box_breakout_score(indicators)
    ma_score = calc_ma_divergence_score(indicators)
    pos_score = calc_position_score(indicators)
    trap_penalty = calc_anti_trap_penalty(indicators, change_pct, turn_rate, 0)
    
    print(f"\n🎯 策略评分:")
    print(f"  箱体突破评分: {box_score:.1f}/100 {'✅ 命中' if box_score >= 40 else '❌ 未命中'}")
    print(f"  均线发散评分: {ma_score:.1f}/100 {'✅ 命中' if ma_score >= 35 else '❌ 未命中'}")
    print(f"  位置评分: {pos_score:+.1f}")
    print(f"  防套惩罚: -{trap_penalty:.1f}")
    
    # volume_surge filter check (v2.1 仓位感知)
    print(f"\n🚀 放量策略过滤检查:")
    vs_filter = False
    reasons = []
    consecutive_up = indicators.get('consecutive_up', 0)
    pos_20d = indicators.get('position_20d', 50)
    # 仓位感知的涨幅上限：低位（position_20d < 50）放宽到10%，高位保持8%
    vs_max_change = 10.0 if pos_20d < 50 else 8.0
    if change_pct < 1.0:
        reasons.append(f"涨幅{change_pct:+.1f}% 低于1%")
        vs_filter = True
    elif change_pct > vs_max_change:
        reasons.append(f"涨幅{change_pct:+.1f}% 超出上限{vs_max_change}% (仓位{pos_20d:.0f}%)")
        vs_filter = True
    if consecutive_up > 3 and pos_20d > 60:
        reasons.append(f"连涨{consecutive_up}天+高位{pos_20d:.0f}%")
        vs_filter = True
    if pos_20d > 85:
        reasons.append(f"高位{pos_20d:.0f}% > 85%")
        vs_filter = True
    avg_amp = indicators.get('avg_amplitude_5d', 3)
    if avg_amp > 8 and pos_20d > 50:
        reasons.append(f"振幅{avg_amp:.1f}% > 8%")
        vs_filter = True
    if vs_filter:
        print(f"  ❌ 被过滤: {'; '.join(reasons)}")
    else:
        print(f"  ✅ 通过过滤")

print("\n" + "="*60)
print("📋 汇总：共达电声能否在4/5-4/10被v2.1策略选中？")
