"""
收益计算器（含涨跌停约束）

锚点：发送时价格 rec.send_price
收益序列：D+1..D+10 相对锚点的收益率（close[k]/send_price - 1）
模拟交易：
  - fast（快进快出）：D 买 → D+1 卖；若 D 涨停不可买→不建仓；若 D+1 跌停不可卖→顺延至可卖日(最多顺延5天)
  - long（长期持有）：D 买 → D+5 卖；卖日跌停则顺延
"""
import logging
from typing import List, Optional

from ..core.types import StockData
from .models import RecommendationRecord, HoldStyle
from .limiter import can_buy, can_sell

logger = logging.getLogger("AInvest.Returns")


class ReturnCalculator:
    def __init__(self, kline_fetcher):
        self.f = kline_fetcher

    def _find_buy_index(self, kline: List[StockData], send_date: str) -> int:
        """返回最后一个 date<=send_date 的索引（发送日那根 bar）"""
        idx = -1
        sd = str(send_date)[:10]
        for i, bar in enumerate(kline):
            if str(bar.date)[:10] <= sd:
                idx = i
            else:
                break
        return idx

    def compute(self, rec: RecommendationRecord, max_window: int = 10) -> RecommendationRecord:
        """计算该记录的逐日收益 + 模拟交易收益，原地更新 rec 并返回。"""
        rec.returns = {}
        rec.trade_executed = True
        rec.trade_return = None
        rec.return_since_buy = None
        rec.max_return = None
        rec.max_drawdown = None
        rec.exit_day = None
        rec.exit_reason = ""
        rec.stop_loss_hit = False
        rec.take_profit_hit = False
        rec.trailing_stop_hit = False
        rec.notes = ""

        kline = self.f.fetch_one(rec.symbol, days=120, as_of=None)
        if not kline:
            rec.notes = "无K线数据"
            rec.observed_days = max_window
            return rec

        bi = self._find_buy_index(kline, rec.date)
        if bi < 0:
            rec.notes = "发送日无对应K线"
            rec.observed_days = max_window
            return rec

        buy_bar = kline[bi]
        buy_price = rec.send_price if rec.send_price > 0 else buy_bar.close

        # 涨停不可买 → 无法建仓（仍记录逐日观测，仅不参与交易）
        if not can_buy(buy_bar):
            rec.trade_executed = False
            rec.notes = f"买入日涨停({buy_bar.change_pct:+.1f}%)，无法建仓"
            self._fill_observation(rec, kline, bi, buy_price, max_window)
            rec.observed_days = min(max_window, len(kline) - 1 - bi)
            return rec

        self._fill_observation(rec, kline, bi, buy_price, max_window)
        rec.observed_days = min(max_window, len(kline) - 1 - bi)
        rec.trade_return = self._simulate_trade(rec, kline, bi, buy_price, rec.hold_style)
        return rec

    def _fill_observation(self, rec, kline, bi, buy_price, max_window):
        max_ret = None
        min_ret = None
        for n in range(1, max_window + 1):
            j = bi + n
            if j >= len(kline):
                break
            bar = kline[j]
            rec.returns[n] = round((bar.close / buy_price - 1) * 100, 2)
            high_ret = (bar.high / buy_price - 1) * 100
            low_ret = (bar.low / buy_price - 1) * 100
            max_ret = high_ret if max_ret is None else max(max_ret, high_ret)
            min_ret = low_ret if min_ret is None else min(min_ret, low_ret)
        rec.max_return = round(max_ret, 2) if max_ret is not None else None
        rec.max_drawdown = round(min_ret, 2) if min_ret is not None else None
        # 自买入价(发送价)至今最新涨跌幅%：取观测窗口内最后一根 bar
        if rec.returns:
            rec.return_since_buy = rec.returns[max(rec.returns.keys())]
        else:
            rec.return_since_buy = None

    def _simulate_trade(self, rec, kline, bi, buy_price, hold_style) -> Optional[float]:
        target_map = {
            HoldStyle.FAST.value: 1,
            HoldStyle.LONG.value: 5,
            HoldStyle.T3.value: 3,
            HoldStyle.T5.value: 5,
            HoldStyle.T10.value: 10,
            HoldStyle.STOP.value: 5,
            HoldStyle.TRAILING.value: 10,
        }
        target = target_map.get(hold_style, 1)
        stop_loss_price = buy_price * 0.95
        take_profit_price = buy_price * 1.08
        first_profit_price = buy_price * 1.05
        peak_price = buy_price
        for n in range(1, target + 6):   # 最多顺延5天找可卖日
            j = bi + n
            if j >= len(kline):
                return None
            sell_bar = kline[j]
            peak_price = max(peak_price, sell_bar.high)
            if not can_sell(sell_bar):
                continue

            if hold_style in (HoldStyle.STOP.value, HoldStyle.TRAILING.value):
                if sell_bar.low <= stop_loss_price:
                    rec.exit_day = n
                    rec.exit_reason = "stop_loss"
                    rec.stop_loss_hit = True
                    return -5.0
                if sell_bar.high >= take_profit_price:
                    rec.exit_day = n
                    rec.exit_reason = "take_profit"
                    rec.take_profit_hit = True
                    return 8.0

            if hold_style == HoldStyle.TRAILING.value and peak_price >= first_profit_price:
                trailing_price = peak_price * 0.96
                if sell_bar.low <= trailing_price:
                    rec.exit_day = n
                    rec.exit_reason = "trailing_stop"
                    rec.trailing_stop_hit = True
                    return round((trailing_price / buy_price - 1) * 100, 2)

            if n >= target:
                rec.exit_day = n
                rec.exit_reason = "time_exit"
                return round((sell_bar.close / buy_price - 1) * 100, 2)
        return None
