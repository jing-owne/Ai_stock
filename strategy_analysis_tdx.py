"""
策略分析脚本 - TDX通道
只使用通达信(TDX)通道获取数据进行策略分析

⚠️ 注意事项:
- TDX通道依赖WorkBuddy通达信应用，不可单独作为数据源使用
- 分析流程强制使用 source='tdx'，不走其他数据通道
- 选标的流程（生产）使用独立的东财+新浪+腾讯数据源，与此互不影响

配置文件: strategy_config.json
  - holdings: 持仓列表（含成本）
  - watchlist: 自选列表（不含成本）
"""

import sys
import os
import json
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.data.kline_fetcher import KlineFetcher
from src.data.tdx_fetcher import get_tdx_fetcher


def calculate_ma(closes: list, period: int) -> float:
    """计算移动平均线"""
    if len(closes) < period:
        return closes[-1] if closes else 0
    return sum(closes[-period:]) / period


def calculate_rsi(closes: list, period: int = 14) -> float:
    """计算RSI指标"""
    if len(closes) < period + 1:
        return 50.0

    gains = []
    losses = []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i-1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    if len(gains) < period:
        return 50.0

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_kdj(highs: list, lows: list, closes: list,
                  n: int = 9, m1: int = 3, m2: int = 3) -> dict:
    """
    计算KDJ指标

    Args:
        highs: 最高价列表
        lows: 最低价列表
        closes: 收盘价列表
        n: RSV周期 (默认9)
        m1: K值平滑周期 (默认3)
        m2: D值平滑周期 (默认3)

    Returns:
        {"k": K值, "d": D值, "j": J值, "k_list": [...], "d_list": [...], "has_golden_cross": bool}
    """
    if len(closes) < n + 1:
        return {"k": 50, "d": 50, "j": 50, "k_list": [], "d_list": [], "has_golden_cross": False}

    k_list = []
    d_list = []
    j_list = []

    prev_k = 50.0
    prev_d = 50.0

    for i in range(n - 1, len(closes)):
        # 计算n日最低价和最高价
        window_high = max(highs[i - n + 1:i + 1])
        window_low = min(lows[i - n + 1:i + 1])

        if window_high == window_low:
            rsv = 50.0
        else:
            rsv = (closes[i] - window_low) / (window_high - window_low) * 100

        # K = 2/3 * 前K + 1/3 * RSV  (m1=3)
        k = (prev_k * (m1 - 1) + rsv) / m1
        # D = 2/3 * 前D + 1/3 * K  (m2=3)
        d = (prev_d * (m2 - 1) + k) / m2
        # J = 3*K - 2*D
        j = 3 * k - 2 * d

        k_list.append(k)
        d_list.append(d)
        j_list.append(j)

        prev_k = k
        prev_d = d

    # 检测金叉: K线上穿D线
    has_golden_cross = False
    if len(k_list) >= 2 and len(d_list) >= 2:
        # 前一天 K < D, 今天 K > D
        if k_list[-2] < d_list[-2] and k_list[-1] > d_list[-1]:
            has_golden_cross = True

    return {
        "k": round(k_list[-1], 1) if k_list else 50,
        "d": round(d_list[-1], 1) if d_list else 50,
        "j": round(j_list[-1], 1) if j_list else 50,
        "k_list": k_list,
        "d_list": d_list,
        "has_golden_cross": has_golden_cross,
    }


def calculate_macd(closes: list, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """
    计算MACD指标

    Returns:
        {"dif": DIF值, "dea": DEA值, "macd_hist": MACD柱值,
         "dif_list": [...], "dea_list": [...], "hist_list": [...],
         "hist_shrinking": bool,  # 绿柱是否明显收缩
         "hist_turning": bool}    # 绿柱是否即将转红
    """
    if len(closes) < slow + signal:
        return {"dif": 0, "dea": 0, "macd_hist": 0,
                "dif_list": [], "dea_list": [], "hist_list": [],
                "hist_shrinking": False, "hist_turning": False}

    # 计算EMA
    def calc_ema(data: list, period: int) -> list:
        ema = [data[0]]
        multiplier = 2.0 / (period + 1)
        for i in range(1, len(data)):
            ema.append(data[i] * multiplier + ema[-1] * (1 - multiplier))
        return ema

    ema_fast = calc_ema(closes, fast)
    ema_slow = calc_ema(closes, slow)

    dif_list = [efa - esl for efa, esl in zip(ema_fast, ema_slow)]

    dea_list = [dif_list[0]]
    multiplier_signal = 2.0 / (signal + 1)
    for i in range(1, len(dif_list)):
        dea_list.append(dif_list[i] * multiplier_signal + dea_list[-1] * (1 - multiplier_signal))

    hist_list = [2 * (d - e) for d, e in zip(dif_list, dea_list)]

    # 检测绿柱收缩（空头衰竭）
    hist_shrinking = False
    hist_turning = False
    if len(hist_list) >= 5:
        recent_hist = hist_list[-5:]
        # 绿柱(负值)连续缩小 → 空头衰竭
        if all(h < 0 for h in recent_hist) and recent_hist[-1] > recent_hist[-3]:
            hist_shrinking = True
        # 绿柱转红（dif上穿dea）
        if len(dif_list) >= 3 and len(dea_list) >= 3:
            if dif_list[-2] < dea_list[-2] and dif_list[-1] > dea_list[-1]:
                hist_turning = True

    return {
        "dif": round(dif_list[-1], 3) if dif_list else 0,
        "dea": round(dea_list[-1], 3) if dea_list else 0,
        "macd_hist": round(hist_list[-1], 3) if hist_list else 0,
        "dif_list": dif_list,
        "dea_list": dea_list,
        "hist_list": hist_list,
        "hist_shrinking": hist_shrinking,
        "hist_turning": hist_turning,
    }


def analyze_symbol(symbol: str, cost: float = None) -> dict:
    """
    分析单个标的（仅使用TDX通道）

    Args:
        symbol: 标的代码
        cost: 持仓成本（None表示自选，不需要盈亏分析）

    Returns:
        分析结果字典
    """
    # ⚠️ 强制使用 TDX 通道，不走其他数据源
    fetcher = KlineFetcher(source='tdx')
    klines = fetcher.fetch_one(symbol, days=60)

    if not klines or len(klines) < 20:
        return {
            'symbol': symbol,
            'error': f'K线数据不足({len(klines) if klines else 0}条)'
        }

    closes = [k.close for k in klines]
    highs = [k.high for k in klines]
    lows = [k.low for k in klines]
    volumes = [k.volume for k in klines]

    current_price = closes[-1]
    yesterday_change = (closes[-1] - closes[-2]) / closes[-2] * 100 if len(closes) >= 2 else 0

    # 计算技术指标
    ma5 = calculate_ma(closes, 5)
    ma10 = calculate_ma(closes, 10)
    ma20 = calculate_ma(closes, 20)
    ma60 = calculate_ma(closes, 60)

    rsi_14 = calculate_rsi(closes, 14)
    rsi_5 = calculate_rsi(closes, 5)
    rsi_10 = calculate_rsi(closes, 10)

    kdj = calculate_kdj(highs, lows, closes)
    macd = calculate_macd(closes)

    # 成交量比
    vol_ma5 = sum(volumes[-5:]) / 5 if len(volumes) >= 5 else 1
    vol_ratio = volumes[-1] / vol_ma5 if vol_ma5 > 0 else 1

    # 振幅
    vol_high = max(highs[-20:]) if len(highs) >= 20 else current_price
    vol_low = min(lows[-20:]) if len(lows) >= 20 else current_price
    amplitude_20d = (vol_high - vol_low) / current_price * 100

    result = {
        'symbol': symbol,
        'current_price': round(current_price, 2),
        'yesterday_change': round(yesterday_change, 2),
        'ma5': round(ma5, 2),
        'ma10': round(ma10, 2),
        'ma20': round(ma20, 2),
        'ma60': round(ma60, 2),
        'rsi_14': round(rsi_14, 1),
        'rsi_5': round(rsi_5, 1),
        'rsi_10': round(rsi_10, 1),
        'kdj_k': kdj['k'],
        'kdj_d': kdj['d'],
        'kdj_j': kdj['j'],
        'kdj_golden_cross': kdj['has_golden_cross'],
        'macd_dif': macd['dif'],
        'macd_dea': macd['dea'],
        'macd_hist': macd['macd_hist'],
        'macd_hist_shrinking': macd['hist_shrinking'],
        'macd_hist_turning': macd['hist_turning'],
        'vol_ratio': round(vol_ratio, 2),
        'amplitude_20d': round(amplitude_20d, 1),
    }

    # 如果有成本，计算盈亏
    if cost is not None:
        pnl_pct = (current_price - cost) / cost * 100
        pnl_amt = current_price - cost
        result['cost'] = cost
        result['pnl_amt'] = round(pnl_amt, 2)
        result['pnl_pct'] = round(pnl_pct, 1)

    # ═══ 底部反弹信号检测 ═══
    signals = []

    # ① RSI超卖回升: RSI_14 < 45 且 RSI_5 > RSI_10
    if rsi_14 < 45 and rsi_5 > rsi_10:
        signals.append(f'✅ RSI超卖回升(RSI={rsi_14:.0f}, RSI5={rsi_5:.0f}>RSI10={rsi_10:.0f})')
    elif rsi_14 < 45 and rsi_5 <= rsi_10:
        signals.append(f'⚠️ RSI超卖但未回升(RSI={rsi_14:.0f}, RSI5={rsi_5:.0f}≤RSI10={rsi_10:.0f})')
    elif rsi_14 >= 45 and rsi_5 > rsi_10:
        signals.append(f'📊 RSI回升但不在低位(RSI={rsi_14:.0f})')

    # ② KDJ金叉
    if kdj['has_golden_cross']:
        signals.append(f'✅ KDJ金叉(K={kdj["k"]:.1f}↑D={kdj["d"]:.1f})')
    elif kdj['k'] < kdj['d']:
        signals.append(f'⚠️ KDJ未金叉(K={kdj["k"]:.1f}<D={kdj["d"]:.1f})')
    else:
        signals.append(f'⚠️ KDJ未金叉(K={kdj["k"]:.1f},D={kdj["d"]:.1f})')

    # ③ MACD绿柱收缩
    if macd['macd_hist'] > 0:
        signals.append('✅ MACD红柱(DIF>DEA)')
    elif macd['hist_turning']:
        signals.append('✅ MACD金叉(即将转红)')
    elif macd['hist_shrinking']:
        signals.append('✅ MACD绿柱收缩(空头衰竭)')
    else:
        signals.append('⚠️ MACD绿柱未收缩')

    # 三信号共振判断
    signal_count = sum(1 for s in signals if s.startswith('✅'))
    if signal_count >= 3:
        confirmation = '🔥 三信号共振！底部反弹确认'
    elif signal_count == 2:
        confirmation = '📊 两信号确认，接近底部'
    elif signal_count == 1:
        confirmation = '⏳ 单信号，继续观察'
    else:
        confirmation = '❄️ 无底部反弹信号'

    result['signals'] = signals
    result['signal_count'] = signal_count
    result['confirmation'] = confirmation

    # 综合趋势判断
    if current_price > ma5 > ma10 > ma20 and rsi_14 > 50:
        trend = '强势上涨'
        trend_emoji = '🔴'
    elif current_price < ma5 < ma10 < ma20 and rsi_14 < 50:
        trend = '弱势下跌'
        trend_emoji = '🟢'
    else:
        trend = '震荡整理'
        trend_emoji = '🟡'

    result['trend'] = trend
    result['trend_emoji'] = trend_emoji

    # 建议
    if confirmation.startswith('🔥'):
        suggestion = '底部反弹信号确认，可考虑介入'
        suggestion_emoji = '🎯'
    elif confirmation.startswith('📊'):
        suggestion = '接近底部，密切关注'
        suggestion_emoji = '👀'
    elif rsi_14 < 30:
        suggestion = '超卖区间，关注反弹'
        suggestion_emoji = '📈'
    elif rsi_14 > 70:
        suggestion = '超买区间，建议谨慎'
        suggestion_emoji = '📉'
    elif current_price > ma20:
        suggestion = '趋势向好，可持有/关注'
        suggestion_emoji = '✅'
    else:
        suggestion = '趋势偏弱，观望'
        suggestion_emoji = '⚠️'

    result['suggestion'] = suggestion
    result['suggestion_emoji'] = suggestion_emoji

    return result


def load_config(config_path: str = 'strategy_config.json') -> dict:
    """加载配置文件"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f'❌ 配置文件加载失败: {e}')
        return {'holdings': [], 'watchlist': []}


def main():
    """主函数"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    print('=' * 80)
    print(f'📊 策略分析 — 底部反弹信号检测 (TDX通道)')
    print(f'   时间: {now}')
    print('=' * 80)

    # 测试TDX连接
    tdx = get_tdx_fetcher()
    if not tdx:
        print('❌ TDX客户端未连接，无法进行分析')
        print('   ⚠️ 提示: TDX依赖WorkBuddy通达信应用，请确认已连接')
        return

    print('✅ TDX客户端连接成功')
    print()

    # 加载配置
    config = load_config()
    holdings = config.get('holdings', [])
    watchlist = config.get('watchlist', [])

    # ═══ 交叉验证 ═══
    all_symbols = [h['symbol'] for h in holdings] + [w['symbol'] for w in watchlist]
    if all_symbols:
        print('─' * 80)
        print('🔍 交叉验证 (TDX vs 东财 vs 新浪)')
        print('─' * 80)
        fetcher = KlineFetcher(source='tdx')
        try:
            cv_results = fetcher.cross_validate(all_symbols, days=5)
            valid_count = sum(1 for v in cv_results.values() if v['valid'])
            print(f'   结果: {valid_count}/{len(all_symbols)} 标的通过交叉验证')
            for sym, info in cv_results.items():
                status = '✅' if info['valid'] else '❌'
                print(f'   {status} {sym}: {info["detail"]}')
        except Exception as e:
            print(f'   ⚠️ 交叉验证失败: {e}')
        print()

    # ═══ 持仓分析 ═══
    if holdings:
        print('=' * 80)
        print('📊 持仓分析（含成本 + 底部反弹信号检测）')
        print('=' * 80)

        results = []
        for item in holdings:
            symbol = item['symbol']
            cost = item.get('cost')
            print(f'\n正在分析 {symbol} (成本: {cost})...')
            result = analyze_symbol(symbol, cost)
            results.append(result)

            if 'error' in result:
                print(f'  ❌ {result["error"]}')
                continue

            pnl_emoji = '🔴' if result['pnl_pct'] < 0 else '🟢'
            print(f'  现价: {result["current_price"]:.2f} | 盈亏: {pnl_emoji} {result["pnl_pct"]:+.1f}%')
            print(f'  昨日涨跌: {result["yesterday_change"]:+.2f}%')
            print(f'  MA: MA5={result["ma5"]:.2f} MA10={result["ma10"]:.2f} MA20={result["ma20"]:.2f}')

            # RSI
            print(f'  RSI: RSI14={result["rsi_14"]:.1f} | RSI5={result["rsi_5"]:.1f} vs RSI10={result["rsi_10"]:.1f}')

            # KDJ
            kdj_icon = '✅' if result['kdj_golden_cross'] else '⚠️'
            print(f'  KDJ: {kdj_icon} K={result["kdj_k"]:.1f} D={result["kdj_d"]:.1f} J={result["kdj_j"]:.1f} '
                  f'({"金叉" if result["kdj_golden_cross"] else "未金叉"})')

            # MACD
            if result['macd_hist'] > 0:
                macd_status = '红柱'
            elif result['macd_hist_turning']:
                macd_status = '即将转红'
            elif result['macd_hist_shrinking']:
                macd_status = '绿柱收缩'
            else:
                macd_status = '绿柱'
            print(f'  MACD: DIF={result["macd_dif"]:.3f} DEA={result["macd_dea"]:.3f} | {macd_status}')

            # 信号
            for sig in result['signals']:
                print(f'  {sig}')

            # 确认
            print(f'  → {result["confirmation"]}')
            print(f'  → 建议: {result["suggestion_emoji"]} {result["suggestion"]}')

        # 持仓汇总
        print()
        print('=' * 80)
        print('持仓汇总')
        print('=' * 80)
        print(f'{"代码":<10} {"盈亏":>8} {"RSI14":>6} {"KDJ":>10} {"MACD":>8} {"信号"}')
        print('─' * 80)
        for r in results:
            if 'error' in r:
                print(f'{r["symbol"]:<10} {"❌":>8}  数据错误')
                continue
            pnl_emoji = '🔴' if r['pnl_pct'] < 0 else '🟢'
            kdj_str = f'{r["kdj_k"]:.0f}/{r["kdj_d"]:.0f}'
            macd_str = '红柱' if r['macd_hist'] > 0 else ('绿缩' if r['macd_hist_shrinking'] else '绿柱')
            signal_str = f'{r["signal_count"]}/3共振' if r['signal_count'] > 0 else '无'
            print(f'{r["symbol"]:<10} {pnl_emoji}{r["pnl_pct"]:>+5.1f}%  '
                  f'RSI={r["rsi_14"]:>4.1f}  K={kdj_str:<4}  {macd_str:<4}  {signal_str}')
        print('=' * 80)
        print()

    # ═══ 自选分析 ═══
    if watchlist:
        print('=' * 80)
        print('👁️ 自选分析（无成本 + 底部反弹信号检测）')
        print('=' * 80)

        results = []
        for item in watchlist:
            symbol = item['symbol']
            print(f'\n正在分析 {symbol}...')
            result = analyze_symbol(symbol, cost=None)
            results.append(result)

            if 'error' in result:
                print(f'  ❌ {result["error"]}')
                continue

            print(f'  现价: {result["current_price"]:.2f} | 昨日涨跌: {result["yesterday_change"]:+.2f}%')
            print(f'  RSI: RSI14={result["rsi_14"]:.1f} | RSI5={result["rsi_5"]:.1f} vs RSI10={result["rsi_10"]:.1f}')
            kdj_icon = '✅' if result['kdj_golden_cross'] else '⚠️'
            print(f'  KDJ: {kdj_icon} K={result["kdj_k"]:.1f} D={result["kdj_d"]:.1f} J={result["kdj_j"]:.1f}')
            if result['macd_hist'] > 0:
                macd_status = '红柱'
            elif result['macd_hist_shrinking']:
                macd_status = '绿柱收缩'
            else:
                macd_status = '绿柱'
            print(f'  MACD: {macd_status} | 信号: {result["signal_count"]}/3')
            print(f'  → {result["confirmation"]}')

        # 自选汇总
        print()
        print('=' * 80)
        print('自选汇总')
        print('=' * 80)
        print(f'{"代码":<10} {"现价":>8} {"RSI14":>6} {"KDJ":>10} {"MACD":>8} {"信号"}')
        print('─' * 80)
        for r in results:
            if 'error' in r:
                print(f'{r["symbol"]:<10} {"❌":>8}  数据错误')
                continue
            kdj_str = f'{r["kdj_k"]:.0f}/{r["kdj_d"]:.0f}'
            macd_str = '红柱' if r['macd_hist'] > 0 else ('绿缩' if r['macd_hist_shrinking'] else '绿柱')
            signal_str = f'{r["signal_count"]}/3共振' if r['signal_count'] > 0 else '无'
            print(f'{r["symbol"]:<10} {r["current_price"]:>8.2f}  '
                  f'RSI={r["rsi_14"]:>4.1f}  K={kdj_str:<4}  {macd_str:<4}  {signal_str}')
        print('=' * 80)

    print(f'\n⏰ 分析完成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('⚠️ 免责声明: 以上分析基于技术指标，不构成投资建议，请理性决策。')


if __name__ == '__main__':
    main()
