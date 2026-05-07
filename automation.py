# -*- coding: utf-8 -*-
"""
定时任务入口 - 用于配置自动化任务
包含交易日判断：周六日、法定节假日、非开盘日不发送邮件
"""
import sys
import os
import json
import urllib.request
from datetime import datetime, date

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import AISStockSelector
from config import EMAIL_CONFIG, AI_CONFIG


# ========== 2026年A股法定节假日 ==========
# 来源：沪深交易所公告，每年更新
HOLIDAYS_2026 = {
    # 元旦
    date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3),
    # 春节
    date(2026, 2, 16), date(2026, 2, 17), date(2026, 2, 18),
    date(2026, 2, 19), date(2026, 2, 20),
    # 清明节
    date(2026, 4, 4), date(2026, 4, 5), date(2026, 4, 6),
    # 劳动节
    date(2026, 5, 1), date(2026, 5, 2), date(2026, 5, 3),
    date(2026, 5, 4), date(2026, 5, 5),
    # 端午节
    date(2026, 6, 19), date(2026, 6, 20), date(2026, 6, 21),
    # 中秋节
    date(2026, 9, 25), date(2026, 9, 26), date(2026, 9, 27),
    # 国庆节
    date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3),
    date(2026, 10, 4), date(2026, 10, 5), date(2026, 10, 6),
    date(2026, 10, 7),
}

# 周末补班日（这些日期虽然是周末但开盘）
MAKEUP_WORKDAYS_2026 = {
    # 春节前补班
    date(2026, 2, 14),  # 周六补班
    # 国庆前补班
    date(2026, 9, 27),  # 周日补班（如与中秋重叠则调整）
}


def is_trading_day(check_date=None):
    """
    判断是否为A股交易日
    
    规则：
    1. 周六日不开盘（除非是补班日）
    2. 法定节假日不开盘
    3. 通过交易所接口验证（可选，作为二次确认）
    
    Args:
        check_date: 要检查的日期，默认为今天
    
    Returns:
        (bool, str): (是否交易日, 原因说明)
    """
    if check_date is None:
        check_date = date.today()
    
    # 1. 检查周末
    weekday = check_date.weekday()  # 0=周一, 6=周日
    if weekday >= 5:  # 周六(5)或周日(6)
        if check_date in MAKEUP_WORKDAYS_2026:
            return True, "周末补班日，正常开盘"
        return False, f"{'周六' if weekday == 5 else '周日'}，非交易日"
    
    # 2. 检查法定节假日
    if check_date in HOLIDAYS_2026:
        return False, f"法定节假日，非交易日"
    
    # 3. 尝试通过交易所接口验证（轻量级检查）
    try:
        url = "http://push2.eastmoney.com/api/qt/stock/get?secid=1.000001&fields=f43,f86&ut=fa5fd1943c7b386f172d6893dbfd32"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data and data.get('data'):
                f43 = data['data'].get('f43')
                # f43为0或空表示休市
                if f43 and f43 != 0:
                    return True, "交易所确认交易日"
                else:
                    return False, "交易所数据为空，休市日"
    except Exception:
        pass  # 网络请求失败不影响判断，继续使用本地规则
    
    return True, "工作日，正常交易日"


def is_trading_hours():
    """
    判断当前是否在A股交易时段内
    
    A股交易时间：
    - 上午：09:15 ~ 11:30（集合竞价+早盘）
    - 下午：13:00 ~ 15:30（午盘+收盘后15分钟内仍可发报告）
    
    允许发邮件的时段：09:15 ~ 15:30
    超出此时段即使是交易日也不发邮件
    
    Returns:
        (bool, str): (是否交易时段, 原因说明)
    """
    now = datetime.now()
    current_time = now.time()
    
    # 交易时段：09:15 ~ 15:30
    from datetime import time as dt_time
    trading_start = dt_time(9, 15)
    trading_end = dt_time(15, 30)
    
    if current_time < trading_start:
        return False, f"当前{current_time.strftime('%H:%M')}，早于开盘时间09:15"
    if current_time > trading_end:
        return False, f"当前{current_time.strftime('%H:%M')}，晚于收盘时间15:30"
    
    return True, f"当前{current_time.strftime('%H:%M')}，在交易时段内"


def run_selection():
    """
    定时任务执行函数
    用于自动化平台调用
    自动判断：1.是否交易日 2.是否交易时段，任一不满足不发邮件
    """
    print("=" * 60)
    print("AI智能选股系统 - 定时任务")
    print("=" * 60)
    
    today = date.today()
    is_trading, reason = is_trading_day(today)
    
    print(f"📅 今日: {today.strftime('%Y-%m-%d %A')}")
    print(f"📊 交易日判断: {'✅ 是' if is_trading else '❌ 否'} - {reason}")
    
    if not is_trading:
        print(f"⏭️  非交易日({reason})，跳过选股和邮件发送")
        return None
    
    # 新增：交易时段判断
    is_hours, hours_reason = is_trading_hours()
    print(f"🕐 时段判断: {'✅ 是' if is_hours else '❌ 否'} - {hours_reason}")
    
    if not is_hours:
        print(f"⏭️  非交易时段({hours_reason})，跳过选股和邮件发送")
        return None
    
    selector = AISStockSelector()
    results = selector.run(send_email=True)
    
    return results


def run_selection_force():
    """
    强制执行选股（不判断交易日）
    用于手动触发或特殊需求
    """
    print("=" * 60)
    print("AI智能选股系统 - 强制执行（忽略交易日判断）")
    print("=" * 60)
    
    selector = AISStockSelector()
    results = selector.run(send_email=True)
    
    return results


if __name__ == "__main__":
    # 设置UTF-8编码
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    
    import argparse
    parser = argparse.ArgumentParser(description='AI智能选股定时任务')
    parser.add_argument('--force', action='store_true', help='强制执行（忽略交易日判断）')
    args = parser.parse_args()
    
    if args.force:
        run_selection_force()
    else:
        run_selection()
