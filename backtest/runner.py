"""
回测脚本 — 对指定标的在指定时间段内逐日评估策略命中与评分
用法: python backtest/runner.py --symbol 000001 --start 2025-12-15 --end 2026-02-02
"""
import argparse
import logging
import sys
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import akshare as ak
import pandas as pd
import numpy as np

from src.core.indicators import (
    calc_all_indicators,
    calc_position_score,
    calc_anti_trap_penalty,
    calc_volume_surge_bonus,
    calc_low_absorb_score,
    calc_pullback_confirm_score,
    calc_ma_support_score,
    calc_box_breakout_score,
    calc_ma_divergence_score,
    calc_bottom_rebound_score,
    calc_net_inflow_score,
    calc_technical_score,
    calc_pattern_score,
    calc_trend_score,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("Backtest")

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')

# ── 策略定义 ──
STRATEGIES = [
    ("放量突破", "volume_breakout"),
    ("成交额排名", "turnover_rank"),
    ("多因子增强", "multi_factor"),
    ("AI技术面", "ai_technical"),
    ("箱体突破", "box_breakout"),
    ("均线趋势", "ma_trend"),
    ("底部反弹", "bottom_rebound"),
    ("连续小阳", "consecutive_positive"),
    ("资金净流入", "net_inflow"),
]

WEIGHTS = {
    "放量突破": 0.14, "成交额排名": 0.10, "多因子增强": 0.14,
    "AI技术面": 0.12, "箱体突破": 0.12, "均线趋势": 0.12,
    "底部反弹": 0.10, "连续小阳": 0.08, "资金净流入": 0.08,
}

THRESHOLDS = {
    "放量突破": 36, "成交额排名": 24, "多因子增强": 50,
    "AI技术面": 75, "箱体突破": 40, "均线趋势": 35,
    "底部反弹": 30, "连续小阳": 30, "资金净流入": 30,
}


def score_volume_breakout(indicators: dict, change_pct: float, amount: float, max_amount: float) -> float:
    """放量突破评分（简化）"""
    vr = indicators.get("volume_ratio", 1.0)
    pos = indicators.get("position_20d", 50)
    vol_score = min(vr / 2.0 * 30, 30)
    breakthrough = 40 if indicators.get("box_breakout", False) else (20 if pos < 30 else 10)
    chg_score = min(change_pct * 5, 20) if change_pct > 0 else 0
    amt_score = min(amount / max(max_amount, 1) * 10, 10)
    return round(vol_score + breakthrough + chg_score + amt_score, 1)


def score_turnover_rank(indicators: dict, change_pct: float, amount: float) -> float:
    """成交额排名评分"""
    s = 0.0
    if amount >= 50e8: s += 40
    elif amount >= 20e8: s += 30
    elif amount >= 5e8: s += 20
    elif amount >= 1e8: s += 10
    vr = indicators.get("volume_ratio", 1)
    if vr > 1.5: s += 15
    elif vr > 1.0: s += 10
    if 0 < change_pct <= 7: s += min(change_pct * 2, 15)
    elif -5 <= change_pct <= 0: s += max(change_pct, -10)
    return min(s, 70)


def score_consecutive_positive(indicators: dict, change_pct: float) -> float:
    """连续小阳评分（简化）"""
    cd = indicators.get("consecutive_up", 0)
    if cd < 3: return 0
    pos = indicators.get("position_20d", 50)
    s = min(cd * 5, 25)
    vr = indicators.get("volume_ratio", 1.0)
    if vr > 1.2: s += 5
    if pos > 80: s = max(s - 5, 0)
    avg_chg = indicators.get("avg_daily_change_5d", abs(change_pct))
    if avg_chg > 5: s = max(s - 5, 0)
    return min(s, 30)


def detect_signals(indicators: dict, strategy_name: str, score_val: float,
                   change_pct: float, amount: float) -> List[str]:
    """检测策略信号"""
    signals = []
    pos = indicators.get("position_20d", 50)
    vr = indicators.get("volume_ratio", 1.0)

    if strategy_name == "放量突破":
        if vr >= 3: signals.append("巨量突破「放量突破」")
        if pos < 30: signals.append("低位启动「放量突破」")
        if vr >= 2 and vr < 3: signals.append("温和放量「放量突破」")
    elif strategy_name == "成交额排名":
        amt_yi = amount / 1e8
        if amt_yi >= 50: signals.append("成交额TOP5「成交额」")
        elif amt_yi >= 20: signals.append("成交活跃「成交额」")
        if score_val >= 30: signals.append("资金活跃「成交额」")
    elif strategy_name == "多因子增强":
        if score_val >= 60: signals.append("技术面强势「多因子」")
        if vr > 1.5: signals.append("量能充沛「多因子」")
        if amount >= 5e8: signals.append("机构特征明显「多因子」")
    elif strategy_name == "AI技术面":
        if score_val >= 85: signals.append("AI形态突破「AI技术」")
        elif score_val >= 75: signals.append("AI形态良好「AI技术」")
        if indicators.get("macd_golden", False): signals.append("MACD金叉「AI技术」")
        if score_val >= 70: signals.append("上升趋势确认「AI技术」")
    elif strategy_name == "箱体突破":
        if score_val >= 50: signals.append("突破箱体上沿「箱体」")
        if vr >= 2: signals.append("放量突破「箱体」")
    elif strategy_name == "均线趋势":
        stick = indicators.get("ma_stickiness", 100)
        if stick < 3: signals.append("均线高度粘合「均线」")
        elif stick < 6: signals.append("均线粘合「均线」")
        if indicators.get("ma_bullish", False): signals.append("多头排列发散「均线」")
        if vr >= 1.5: signals.append("放量配合「均线」")
    elif strategy_name == "底部反弹":
        rsi = indicators.get("rsi_14", 50)
        if rsi < 25: signals.append(f"RSI超卖({int(rsi)})「底部」")
        if score_val >= 30: signals.append("日线拐头向上「底部」")
        if pos < 20: signals.append("极端低位「底部」")
    elif strategy_name == "连续小阳":
        cd = indicators.get("consecutive_up", 0)
        if cd >= 3: signals.append(f"连续{cd}日小阳「连续小阳」")
        if vr > 1.2: signals.append("温和放量吸筹「连续小阳」")
    elif strategy_name == "资金净流入":
        if score_val >= 30: signals.append("连续净流入「资金净流入」")

    return signals[:3]


# ── 数据获取 ──

def fetch_kline_history(symbol: str, start: str, end: str) -> pd.DataFrame:
    """获取历史日K线数据（新浪源，自动计算涨跌幅）"""
    code_clean = symbol
    if symbol.startswith('6'):
        full_sym = f'sh{code_clean}'
    elif symbol.startswith('0') or symbol.startswith('3'):
        full_sym = f'sz{code_clean}'
    else:
        full_sym = f'sz{code_clean}'

    try:
        df = ak.stock_zh_a_daily(symbol=full_sym, start_date=start.replace('-', ''),
                                  end_date=end.replace('-', ''), adjust='qfq')
        if df is not None and not df.empty:
            if 'change_pct' not in df.columns:
                df['change_pct'] = df['close'].pct_change() * 100
                df['change_pct'] = df['change_pct'].fillna(0)
            logger.info(f"获取到 {len(df)} 条K线 (新浪)")
            return df
    except Exception as e:
        logger.warning(f"新浪K线失败: {e}")
    return pd.DataFrame()


def build_daily_series(df: pd.DataFrame) -> List[Dict]:
    """将K线DataFrame转为每日字典列表（兼容中英文列名）"""
    result = []
    if df.empty:
        return result
    col_map = {'日期': 'date', 'date': 'date',
               '开盘': 'open', 'open': 'open',
               '收盘': 'close', 'close': 'close',
               '最高': 'high', 'high': 'high',
               '最低': 'low', 'low': 'low',
               '成交量': 'volume', 'volume': 'volume',
               '成交额': 'amount', 'amount': 'amount',
               '涨跌幅': 'change_pct', 'change_pct': 'change_pct',
               '换手率': 'turnover', 'turnover': 'turnover'}
    df_r = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
    for i in range(len(df_r)):
        row = df_r.iloc[i]
        date_val = row.get('date', '')
        if isinstance(date_val, pd.Timestamp):
            date_str = date_val.strftime('%Y-%m-%d')
        elif hasattr(date_val, 'strftime'):
            date_str = date_val.strftime('%Y-%m-%d')
        else:
            date_str = str(date_val)[:10]
        close = float(row.get('close', 0))
        if close <= 0: continue
        result.append({
            'date': date_str,
            'close': close,
            'open': float(row.get('open', 0)),
            'high': float(row.get('high', 0)),
            'low': float(row.get('low', 0)),
            'volume': float(row.get('volume', 0)),
            'amount': float(row.get('amount', 0)),
            'change_pct': float(row.get('change_pct', 0)),
            'turnover': float(row.get('turnover', 0)) if pd.notna(row.get('turnover', 0)) else 0,
        })
    return result


def analyze_day(day_data: Dict, all_data: List[Dict], idx: int) -> Optional[Dict]:
    """对单个交易日进行全策略分析"""
    if idx < 60:
        return None

    lookback = all_data[max(0, idx-120):idx+1]
    closes = np.array([d['close'] for d in lookback], dtype=float)
    volumes = np.array([d['volume'] for d in lookback], dtype=float)
    highs = np.array([d['high'] for d in lookback], dtype=float)
    lows = np.array([d['low'] for d in lookback], dtype=float)

    change_pct = day_data['change_pct']
    amount = day_data['amount']
    turnover = day_data.get('turnover', 0)

    if change_pct < -5 or change_pct > 7:
        return None
    if amount < 30_000_000:
        return None

    try:
        indicators = calc_all_indicators(closes, volumes, highs, lows)
    except Exception as e:
        logger.debug(f"{day_data['date']} 指标失败: {e}")
        return None

    vr = indicators.get("volume_ratio", 1.0)
    indicators['volume_ratio'] = vr

    max_amount = max(d['amount'] for d in all_data[max(0, idx-20):idx+1])

    # 各策略评分
    scores = {}
    scores["放量突破"] = score_volume_breakout(indicators, change_pct, amount, max_amount)
    scores["成交额排名"] = score_turnover_rank(indicators, change_pct, amount)
    scores["多因子增强"] = calc_technical_score(indicators)
    scores["AI技术面"] = calc_pattern_score(indicators, vr) + calc_trend_score(indicators)
    scores["箱体突破"] = calc_box_breakout_score(indicators)
    scores["均线趋势"] = calc_ma_divergence_score(indicators)
    scores["底部反弹"] = calc_bottom_rebound_score(closes, volumes)
    scores["连续小阳"] = score_consecutive_positive(indicators, change_pct)
    scores["资金净流入"] = calc_net_inflow_score(int(indicators.get("consecutive_inflow", 0)))

    # 命中策略
    hit = []
    all_sigs = []
    for name, _ in STRATEGIES:
        s = scores.get(name, 0)
        if s >= THRESHOLDS.get(name, 30):
            hit.append(name)
            all_sigs.extend(detect_signals(indicators, name, s, change_pct, amount))

    if not hit:
        return None

    # 综合评分
    strategy_total = sum(scores.values())
    pos_score = min(calc_position_score(indicators), 20)
    low_abs = min(calc_low_absorb_score(indicators), 20)
    pullback = calc_pullback_confirm_score(indicators)
    ma_sup = calc_ma_support_score(indicators)
    anti = calc_anti_trap_penalty(indicators, change_pct, turnover, amount)
    vol_bonus = calc_volume_surge_bonus(indicators)
    div = len(hit) * 1.5

    composite = round(strategy_total + pos_score + low_abs + pullback + ma_sup + div + vol_bonus - anti, 2)

    # 风险
    p20 = indicators.get("position_20d", 50)
    if anti >= 20: risk = "🔴 高风险"
    elif anti >= 10: risk = "🟡 中风险"
    elif anti > 0: risk = "🟢 注意"
    else: risk = "🟢 安全"
    if p20 > 80: risk += " · 高位"
    elif p20 < 30: risk += " · 低位"

    return {
        'date': day_data['date'],
        'close': day_data['close'],
        'change_pct': change_pct,
        'amount': amount,
        'hit_strategies': hit,
        'signals': list(set(all_sigs)),
        'scores': scores,
        'composite_score': composite,
        'position_20d': p20,
        'consecutive_up': int(indicators.get("consecutive_up", 0)),
        'consecutive_volume_up': int(indicators.get("consecutive_volume_up", 0)),
        'volume_bonus': vol_bonus,
        'risk': risk,
        'rsi_14': round(indicators.get("rsi_14", 50), 1),
        'vol_ratio': round(vr, 2),
    }


# ── 报告 ──

def generate_report(symbol: str, name: str, start: str, end: str,
                    results: List[Dict], price_range: Tuple[float, float]) -> str:
    lines = []
    lines.append(f"# 📊 回测报告: {name}({symbol})")
    lines.append("")
    lines.append(f"- **回测区间**: {start} → {end}")
    lines.append(f"- **命中策略天数**: {len(results)} 个交易日")
    lines.append(f"- **价格区间**: {price_range[0]:.2f} ~ {price_range[1]:.2f}")
    lines.append("")

    if not results:
        lines.append("> 该区间内无任何交易日命中策略。")
        return '\n'.join(lines)

    scores_list = [r['composite_score'] for r in results]
    changes = [r['change_pct'] for r in results]
    up_days = sum(1 for c in changes if c > 0)
    down_days = sum(1 for c in changes if c <= 0)

    lines.append("## 📈 汇总统计")
    lines.append("")
    lines.append(f"| 指标 | 数值 |")
    lines.append(f"|:---|---:|")
    lines.append(f"| 最高综合评分 | {max(scores_list):.1f} |")
    lines.append(f"| 平均综合评分 | {sum(scores_list)/len(scores_list):.1f} |")
    lines.append(f"| 最大单日涨幅 | {max(changes):+.2f}% |")
    lines.append(f"| 最大单日跌幅 | {min(changes):+.2f}% |")
    lines.append(f"| 平均涨跌 | {sum(changes)/len(changes):+.2f}% |")
    lines.append(f"| 上涨日 | {up_days} ({up_days/len(changes)*100:.0f}%) |")
    lines.append(f"| 下跌日 | {down_days} ({down_days/len(changes)*100:.0f}%) |")
    lines.append("")

    # 策略命中频率
    hit_counts = {}
    for r in results:
        for s in r['hit_strategies']:
            hit_counts[s] = hit_counts.get(s, 0) + 1
    lines.append("## 🎯 策略命中频率")
    lines.append("")
    lines.append(f"| 策略 | 命中次数 | 命中率 |")
    lines.append(f"|:---|---:|---:|")
    for name, _ in STRATEGIES:
        cnt = hit_counts.get(name, 0)
        pct = cnt / len(results) * 100
        bar = "█" * int(pct / 5)
        lines.append(f"| {name} | {cnt} | {bar} {pct:.0f}% |")
    lines.append("")

    # 风险分布
    risk_map = {}
    for r in results:
        rb = r['risk'].split(' · ')[0]
        risk_map[rb] = risk_map.get(rb, 0) + 1
    lines.append("## ⚠️ 风险分布")
    for rl, cnt in sorted(risk_map.items()):
        lines.append(f"- {rl}: {cnt}天")
    lines.append("")

    # 逐日明细
    lines.append("## 📋 逐日明细")
    lines.append("")
    lines.append("| 日期 | 收盘 | 涨跌 | 综合分 | 策略数 | RSI | vol比 | 风险 | 命中策略 |")
    lines.append("|:---|---:|---:|---:|---:|---:|---:|:---|:---|")
    for r in results:
        ds = r['date'][5:]
        strategies_short = ' + '.join(r['hit_strategies'][:4])
        lines.append(
            f"| {ds} | {r['close']:.2f} | {r['change_pct']:+.2f}% | "
            f"{r['composite_score']:.1f} | {len(r['hit_strategies'])} | "
            f"{r['rsi_14']:.0f} | {r['vol_ratio']:.1f} | "
            f"{r['risk']} | {strategies_short} |"
        )

    # 高分日详细
    lines.append("")
    lines.append("## 🔍 Top 5 高分日详细分析")
    top5 = sorted(results, key=lambda x: x['composite_score'], reverse=True)[:5]
    for r in top5:
        lines.append(f"\n### {r['date']} — 综合评分 {r['composite_score']:.1f}")
        lines.append(f"- 收盘: {r['close']:.2f} | 涨跌: {r['change_pct']:+.2f}% | 20日位置: {r['position_20d']:.1f}%")
        lines.append(f"- 风险: {r['risk']}")
        lines.append(f"- 命中策略: {' + '.join(r['hit_strategies'])}")
        if r['signals']:
            lines.append(f"- 关键信号: {' / '.join(r['signals'][:5])}")
        lines.append(f"- 各策略评分:")
        for sname, sval in sorted(r['scores'].items(), key=lambda x: -x[1]):
            if sval > 0:
                mark = "✓" if sname in r['hit_strategies'] else " "
                lines.append(f"  - [{mark}] {sname}: {sval:.1f}")

    lines.append("")
    lines.append("---")
    lines.append("> ⚠️ 回测仅供参考，不构成投资建议。")

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='单股全策略逐日回测工具')
    parser.add_argument("--symbol", required=True, help="股票代码（6位数字）")
    parser.add_argument("--start", required=True, help="起始日期 YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="结束日期 YYYY-MM-DD")
    args = parser.parse_args()

    symbol = args.symbol.zfill(6)
    start = args.start
    end = args.end

    logger.info(f"回测: {symbol}  {start} → {end}")

    # 获取名称
    name = symbol
    try:
        info = ak.stock_individual_info_em(symbol=symbol)
        if info is not None and not info.empty:
            nr = info[info['item'] == '股票简称']
            if not nr.empty:
                name = str(nr['value'].iloc[0])
    except Exception:
        pass

    # 获取K线（前后扩展180天用于指标计算）
    s_dt = datetime.strptime(start, '%Y-%m-%d')
    e_dt = datetime.strptime(end, '%Y-%m-%d')
    fetch_start = (s_dt - timedelta(days=200)).strftime('%Y-%m-%d')
    fetch_end = end

    df = fetch_kline_history(symbol, fetch_start, fetch_end)
    if df.empty:
        logger.error("无K线数据")
        return

    all_data = build_daily_series(df)
    logger.info(f"共 {len(all_data)} 条日线数据")

    # 逐日分析
    results = []
    closes_in_range = []
    for idx, day in enumerate(all_data):
        ds = day['date']
        if ds < start or ds > end:
            continue
        if idx >= 60:
            closes_in_range.append(day['close'])
        r = analyze_day(day, all_data, idx)
        if r:
            results.append(r)
            logger.info(f"  {ds}: {r['composite_score']:.1f}分 "
                       f"{r['change_pct']:+.2f}% | {len(r['hit_strategies'])}策略 | {r['risk']}")

    price_range = (min(closes_in_range), max(closes_in_range)) if closes_in_range else (0, 0)
    report = generate_report(symbol, name, start, end, results, price_range)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_file = os.path.join(OUTPUT_DIR, f'backtest_{start}_{end}.md')
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write(report)

    print("\n" + "=" * 60)
    print(f"回测: {name}({symbol})  {start} → {end}")
    print(f"命中策略天数: {len(results)}")
    print(f"报告: {out_file}")
    if results:
        print(f"\nTop 5:")
        for r in sorted(results, key=lambda x: x['composite_score'], reverse=True)[:5]:
            print(f"  {r['date']}: {r['composite_score']:.1f}分 {r['change_pct']:+.2f}% "
                  f"| {'+'.join(r['hit_strategies'][:3])}")
    print("=" * 60)


if __name__ == "__main__":
    main()
