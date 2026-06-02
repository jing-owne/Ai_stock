#!/usr/bin/env python3
"""
A股交易日检查脚本（动态版）
- 优先使用 akshare.tool_trade_date_hist_sina 动态判断
- API 覆盖不到的未来日期 → 周末 + 法定节假日降级
- 检查当前是否在交易时段 (9:15-15:30)
- 支持 --force 强制执行

用法：
    python check_trading.py           # 正常检查
    python check_trading.py --force   # 强制通过
    python check_trading.py --list    # 列出全年休市安排

返回值：
    0 = 可以执行（交易日 + 交易时段）
    1 = 跳过（非交易日）
    2 = 跳过（非交易时段）

函数导出：
    from check_trading import is_trading_day, is_trading_hour
"""

import datetime
import sys
import json
import urllib.request
import urllib.error
from typing import Tuple, Set, Optional

# ═══════════════════════════════════════════════════
# 交易时段
# ═══════════════════════════════════════════════════

TRADING_START = datetime.time(9, 15)
TRADING_END = datetime.time(15, 30)

# ═══════════════════════════════════════════════════
# 法定节假日（降级方案：API 覆盖不到的未来日期使用）
# 每年需更新一次（上交所通常12月发布下一年安排）
# ═══════════════════════════════════════════════════

HOLIDAYS_BY_YEAR = {
    2026: [
        ("元旦",     datetime.date(2026, 1, 1),  datetime.date(2026, 1, 3)),
        ("春节",     datetime.date(2026, 2, 15), datetime.date(2026, 2, 23)),
        ("清明节",   datetime.date(2026, 4, 4),  datetime.date(2026, 4, 6)),
        ("劳动节",   datetime.date(2026, 5, 1),  datetime.date(2026, 5, 5)),
        ("端午节",   datetime.date(2026, 6, 19), datetime.date(2026, 6, 21)),
        ("中秋节",   datetime.date(2026, 9, 25), datetime.date(2026, 9, 27)),
        ("国庆节",   datetime.date(2026, 10, 1), datetime.date(2026, 10, 7)),
    ],
}

# 已知额外周末休市（降级用）
EXTRA_WEEKEND_CLOSED = {
    datetime.date(2026, 1, 4),
    datetime.date(2026, 2, 14),
    datetime.date(2026, 2, 28),
    datetime.date(2026, 5, 9),
    datetime.date(2026, 9, 20),
    datetime.date(2026, 10, 10),
}

# ═══════════════════════════════════════════════════
# 动态交易日历缓存
# ═══════════════════════════════════════════════════

_trading_days_cache: Optional[Set[datetime.date]] = None
_cache_max_date: Optional[datetime.date] = None


def _load_trading_calendar() -> Tuple[Set[datetime.date], Optional[datetime.date]]:
    """
    从 akshare 加载动态交易日历
    返回 (交易日集合, 最大覆盖日期)
    """
    global _trading_days_cache, _cache_max_date

    if _trading_days_cache is not None:
        return _trading_days_cache, _cache_max_date

    try:
        import akshare as ak
        df = ak.tool_trade_date_hist_sina()
        dates = set()
        max_date = None
        for d in df['trade_date']:
            if isinstance(d, datetime.date):
                dates.add(d)
                if max_date is None or d > max_date:
                    max_date = d
        _trading_days_cache = dates
        _cache_max_date = max_date
        return dates, max_date
    except Exception:
        # akshare 不可用，使用降级方案
        return set(), None


def invalidate_cache():
    """清除交易日历缓存（强制下次重新加载）"""
    global _trading_days_cache, _cache_max_date
    _trading_days_cache = None
    _cache_max_date = None


def is_trading_day(date_obj: datetime.date = None) -> Tuple[bool, str]:
    """
    检查是否为A股交易日（动态版）

    优先级：
      1. akshare 动态交易日历（覆盖 1990～约2026年底）
      2. 周末判断（周六日休市）
      3. 法定节假日降级（硬编码，仅用于API未覆盖的年份）

    返回 (是否交易日, 原因说明)
    """
    if date_obj is None:
        date_obj = datetime.date.today()

    # ── 优先：动态交易日历 ──
    trading_days, max_date = _load_trading_calendar()
    if trading_days and (max_date is None or date_obj <= max_date):
        if date_obj in trading_days:
            return True, "交易日（动态日历）"
        else:
            # 在日历覆盖范围内但不在交易日集合中
            # 尝试识别具体假期
            holiday_name = _find_holiday_name(date_obj)
            if holiday_name:
                return False, f"{holiday_name}假期休市（动态日历）"
            return False, f"非交易日（动态日历）"

    # ── 降级：周末 + 法定节假日 ──
    if date_obj.weekday() >= 5:
        day_name = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][date_obj.weekday()]
        return False, f"{day_name}休市（降级判断）"

    holiday_name = _find_holiday_name(date_obj)
    if holiday_name:
        return False, f"{holiday_name}假期休市（降级判断）"

    return True, "交易日（降级判断）"


def _find_holiday_name(date_obj: datetime.date) -> Optional[str]:
    """在硬编码节假日中查找日期"""
    for year, holidays in HOLIDAYS_BY_YEAR.items():
        for name, start, end in holidays:
            if start <= date_obj <= end:
                return name
    # 额外周末休市
    if date_obj in EXTRA_WEEKEND_CLOSED:
        return "调休"
    return None


def is_trading_hour(now: datetime.datetime = None) -> Tuple[bool, str]:
    """
    检查是否在交易时段内
    返回 (是否在交易时段, 原因说明)
    """
    if now is None:
        now = datetime.datetime.now()
    t = now.time()
    if t < TRADING_START:
        return False, f"尚未开盘(当前{t.strftime('%H:%M')}，开盘{TRADING_START.strftime('%H:%M')})"
    if t > TRADING_END:
        return False, f"已收盘(当前{t.strftime('%H:%M')}，收盘{TRADING_END.strftime('%H:%M')})"
    return True, "交易时段"


# ═══════════════════════════════════════════════════
# 命令行入口
# ═══════════════════════════════════════════════════

def main():
    force = "--force" in sys.argv
    list_holidays = "--list" in sys.argv

    if list_holidays:
        print("=" * 60)
        print("  A股交易日历（动态 + 降级）")
        print("=" * 60)
        trading_days, max_date = _load_trading_calendar()
        if trading_days:
            print(f"  动态日历: {len(trading_days)} 个交易日")
            if max_date:
                print(f"  覆盖范围: 1990-12-19 ~ {max_date}")
        print()
        for year in sorted(HOLIDAYS_BY_YEAR.keys()):
            print(f"  {year}年法定节假日（降级方案）:")
            for name, start, end in HOLIDAYS_BY_YEAR[year]:
                days = (end - start).days + 1
                print(f"    {name}: {start} ~ {end} ({days}天)")
        return

    if force:
        print(f"[强制执行] 跳过交易日检查，直接执行")
        sys.exit(0)

    now = datetime.datetime.now()
    today = now.date()

    # 1. 交易日判断
    is_td, reason = is_trading_day(today)
    if not is_td:
        print(f"[跳过] {today} {reason}")
        sys.exit(1)

    # 2. 交易时段判断
    is_th, time_reason = is_trading_hour(now)
    if not is_th:
        print(f"[跳过] {today} 交易日但{time_reason}")
        sys.exit(2)

    print(f"[执行] {today} {now.strftime('%H:%M')} {reason}，{time_reason}")
    sys.exit(0)


if __name__ == "__main__":
    main()
