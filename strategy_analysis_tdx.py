"""
策略分析脚本 - TDX通道
只使用通达信(TDX)通道获取数据进行策略分析

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


def analyze_symbol(symbol: str, cost: float = None) -> dict:
    """
    分析单个标的
    
    Args:
        symbol: 标的代码
        cost: 持仓成本（None表示自选，不需要盈亏分析）
        
    Returns:
        分析结果字典
    """
    fetcher = KlineFetcher(source='tdx')
    klines = fetcher.fetch_one(symbol, days=60)
    
    if not klines or len(klines) < 20:
        return {
            'symbol': symbol,
            'error': f'K线数据不足({len(klines) if klines else 0}条)'
        }
    
    closes = [k.close for k in klines]
    volumes = [k.volume for k in klines]
    
    current_price = closes[-1]
    
    # 计算技术指标
    ma5 = calculate_ma(closes, 5)
    ma10 = calculate_ma(closes, 10)
    ma20 = calculate_ma(closes, 20)
    rsi = calculate_rsi(closes, 14)
    
    # 成交量比
    vol_ma5 = sum(volumes[-5:]) / 5
    vol_ratio = volumes[-1] / vol_ma5 if vol_ma5 > 0 else 1
    
    result = {
        'symbol': symbol,
        'current_price': current_price,
        'ma5': ma5,
        'ma10': ma10,
        'ma20': ma20,
        'rsi': rsi,
        'vol_ratio': vol_ratio,
    }
    
    # 如果有成本，计算盈亏
    if cost is not None:
        pnl_pct = (current_price - cost) / cost * 100
        pnl_amt = current_price - cost
        result['cost'] = cost
        result['pnl_amt'] = pnl_amt
        result['pnl_pct'] = pnl_pct
    
    # 趋势判断
    if current_price > ma5 > ma10 > ma20 and rsi > 50:
        trend = '强势上涨'
        trend_emoji = '🔴'
    elif current_price < ma5 < ma10 < ma20 and rsi < 50:
        trend = '弱势下跌'
        trend_emoji = '🟢'
    else:
        trend = '震荡整理'
        trend_emoji = '🟡'
    
    result['trend'] = trend
    result['trend_emoji'] = trend_emoji
    
    # 建议
    if rsi < 30:
        suggestion = '超卖区间，可关注'
        suggestion_emoji = '📈'
    elif rsi > 70:
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
    
    print('=' * 70)
    print('策略分析 (TDX通道)')
    print('=' * 70)
    
    # 测试TDX连接
    tdx = get_tdx_fetcher()
    if not tdx:
        print('❌ TDX客户端未连接，无法进行分析')
        return
    
    print('✅ TDX客户端连接成功')
    print()
    
    # 加载配置
    config = load_config()
    holdings = config.get('holdings', [])
    watchlist = config.get('watchlist', [])
    
    # ── 持仓分析 ──
    if holdings:
        print('=' * 70)
        print('📊 持仓分析（含成本）')
        print('=' * 70)
        print()
        
        results = []
        for item in holdings:
            symbol = item['symbol']
            cost = item.get('cost')
            print(f'正在分析 {symbol} (成本: {cost})...')
            result = analyze_symbol(symbol, cost)
            results.append(result)
            
            if 'error' in result:
                print(f'  ❌ {result["error"]}')
            else:
                pnl_emoji = '🔴' if result['pnl_pct'] < 0 else '🟢'
                print(f'  现价: {result["current_price"]:.2f}')
                print(f'  盈亏: {pnl_emoji} {result["pnl_pct"]:+.1f}%')
                print(f'  RSI: {result["rsi"]:.1f}')
                print(f'  趋势: {result["trend_emoji"]} {result["trend"]}')
                print(f'  建议: {result["suggestion_emoji"]} {result["suggestion"]}')
            print()
        
        # 持仓汇总
        print('=' * 70)
        print('持仓汇总')
        print('=' * 70)
        for r in results:
            if 'error' in r:
                print(f'{r["symbol"]}: ❌ {r["error"]}')
            else:
                pnl_emoji = '🔴' if r['pnl_pct'] < 0 else '🟢'
                print(f'{r["symbol"]}: {pnl_emoji} {r["pnl_pct"]:+.1f}% | '
                      f'RSI={r["rsi"]:.1f} | {r["suggestion_emoji"]} {r["suggestion"]}')
        print('=' * 70)
        print()
    
    # ── 自选分析 ──
    if watchlist:
        print('=' * 70)
        print('👁️ 自选分析（无成本）')
        print('=' * 70)
        print()
        
        results = []
        for item in watchlist:
            symbol = item['symbol']
            print(f'正在分析 {symbol}...')
            result = analyze_symbol(symbol, cost=None)
            results.append(result)
            
            if 'error' in result:
                print(f'  ❌ {result["error"]}')
            else:
                print(f'  现价: {result["current_price"]:.2f}')
                print(f'  RSI: {result["rsi"]:.1f}')
                print(f'  趋势: {result["trend_emoji"]} {result["trend"]}')
                print(f'  建议: {result["suggestion_emoji"]} {result["suggestion"]}')
            print()
        
        # 自选汇总
        print('=' * 70)
        print('自选汇总')
        print('=' * 70)
        for r in results:
            if 'error' in r:
                print(f'{r["symbol"]}: ❌ {r["error"]}')
            else:
                print(f'{r["symbol"]}: RSI={r["rsi"]:.1f} | '
                      f'{r["trend_emoji"]} {r["trend"]} | {r["suggestion_emoji"]} {r["suggestion"]}')
        print('=' * 70)


if __name__ == '__main__':
    main()
