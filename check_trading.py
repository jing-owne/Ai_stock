#!/usr/bin/env python3
"""
A股交易日检查脚本
- 检查今天是否为交易日（排除周六日 + 法定节假日 + 处理补班日）
- 检查当前是否在交易时段 (9:15-15:30)
- 支持 --force 强制执行（跳过检查）
- 支持东方财富接口二次验证

用法：
    python check_trading.py           # 正常检查
    python check_trading.py --force   # 强制通过
    python check_trading.py --list    # 列出全年休市安排

返回值：
    0 = 可以执行（交易日 + 交易时段）
    1 = 跳过（非交易日）
    2 = 跳过（非交易时段）
"""

import datetime
import sys
import json
import urllib.request
import urllib.error


# ═══════════════════════════════════════════════════
# 2026年A股休市安排（来源：上交所/深交所/北交所联合公告）
# ═══════════════════════════════════════════════════

HOLIDAYS_2026 = [
    # (名称, 开始日期, 结束日期)
    ("元旦",       datetime.date(2026, 1, 1),  datetime.date(2026, 1, 3)),
    ("春节",       datetime.date(2026, 2, 15), datetime.date(2026, 2, 23)),
    ("清明节",     datetime.date(2026, 4, 4),  datetime.date(2026, 4, 6)),
    ("劳动节",     datetime.date(2026, 5, 1),  datetime.date(2026, 5, 5)),
    ("端午节",     datetime.date(2026, 6, 19), datetime.date(2026, 6, 21)),
    ("中秋节",     datetime.date(2026, 9, 25), datetime.date(2026, 9, 27)),
    ("国庆节",     datetime.date(2026, 10, 1), datetime.date(2026, 10, 7)),
]

# 2026年补班交易日（周末但交易所开市）
# 上交所暂未公布2026年周末补班交易日，如有后续公告在此补充
# 格式：{datetime.date(2026, X, X), ...}
MAKEUP_TRADING_DAYS_2026: set = set()

# 额外已知周末休市（交易所公告明确标注的周末）
EXTRA_WEEKEND_CLOSED_2026 = {
    datetime.date(2026, 1, 4),    # 元旦后周日
    datetime.date(2026, 2, 14),   # 春节前周六
    datetime.date(2026, 2, 28),   # 春节后周六
    datetime.date(2026, 5, 9),    # 劳动节后周六
    datetime.date(2026, 9, 20),   # 国庆前周日
    datetime.date(2026, 10, 10),  # 国庆后周六
}

# 交易时段
TRADING_START = datetime.time(9, 15)
TRADING_END = datetime.time(15, 30)


# ═══════════════════════════════════════════════════
# 核心函数
# ═══════════════════════════════════════════════════

def is_holiday(date_obj: datetime.date) -> tuple:
    """检查是否为法定节假日休市，返回 (是否休市, 假期名称)"""
    for name, start, end in HOLIDAYS_2026:
        if start <= date_obj <= end:
            return True, name
    return False, None


def is_trading_day(date_obj: datetime.date = None) -> tuple:
    """
    检查是否为A股交易日
    返回 (是否交易日, 原因说明)
    """
    if date_obj is None:
        date_obj = datetime.date.today()

    # 补班交易日（周末但交易所开市）
    if date_obj in MAKEUP_TRADING_DAYS_2026:
        return True, "补班交易日"

    # 周六日休市
    if date_obj.weekday() >= 5:  # 5=周六, 6=周日
        day_name = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][date_obj.weekday()]
        return False, f"{day_name}休市"

    # 法定节假日休市
    holiday, name = is_holiday(date_obj)
    if holiday:
        return False, f"{name}假期休市"

    return True, "交易日"


def is_trading_hour(now: datetime.datetime = None) -> tuple:
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


def verify_with_eastmoney(date_obj: datetime.date) -> bool:
    """
    通过东方财富交易日历接口二次验证
    返回 True=交易日, False=非交易日, None=接口不可用
    """
    try:
        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        params = {
            "secid": "1.000001",  # 上证指数
            "fields1": "f1",
            "fields2": "f51,f52",
            "klt": "101",         # 日K
            "fqt": "1",
            "beg": date_obj.strftime("%Y%m%d"),
            "end": date_obj.strftime("%Y%m%d"),
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        full_url = f"{url}?{query}"

        req = urllib.request.Request(full_url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://quote.eastmoney.com/",
        })
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())

        klines = data.get("data", {}).get("klines", [])
        if klines:
            return True
        else:
            return False
    except Exception:
        return None  # 接口不可用，使用本地判断


# ═══════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════

def main():
    force = "--force" in sys.argv
    list_holidays = "--list" in sys.argv

    if list_holidays:
        print("=" * 60)
        print("  2026年A股休市安排")
        print("=" * 60)
        for name, start, end in HOLIDAYS_2026:
            days = (end - start).days + 1
            print(f"  {name:　<6s}  {start} ~ {end}  (共{days}天)")
        print()
        print("  补班交易日: " + ("暂无" if not MAKEUP_TRADING_DAYS_2026 else ", ".join(str(d) for d in sorted(MAKEUP_TRADING_DAYS_2026))))
        return

    if force:
        print(f"[强制执行] 跳过交易日检查，直接执行")
        sys.exit(0)

    now = datetime.datetime.now()
    today = now.date()

    # 1. 本地判断交易日
    is_td, reason = is_trading_day(today)
    if not is_td:
        print(f"[跳过] {today} {reason}")
        sys.exit(1)

    # 2. 本地判断交易时段
    is_th, time_reason = is_trading_hour(now)
    if not is_th:
        print(f"[跳过] {today} 交易日但{time_reason}")
        sys.exit(2)

    # 3. 东方财富接口二次验证（可选，失败不影响）
    eastmoney_result = verify_with_eastmoney(today)
    if eastmoney_result is False:
        print(f"[跳过] {today} 本地判断为交易日，但东方财富接口返回无交易数据，跳过")
        sys.exit(1)
    elif eastmoney_result is None:
        pass  # 接口不可用，忽略

    print(f"[执行] {today} {now.strftime('%H:%M')} {reason}，{time_reason}")
    sys.exit(0)


if __name__ == "__main__":
    main()
