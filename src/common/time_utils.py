"""
统一日期时间格式化工具

项目内所有 datetime.now().strftime(...) 散落代码的统一出口。

用法：
    from src.common.time_utils import now_str, today_str, fmt_date

    now_str()      # → "2026-06-02 14:30"
    today_str()    # → "2026-06-02"
    fmt_date("human")     # → "2026年06月02日 14:30"
    fmt_date("compact")   # → "06-02"
    fmt_date("yy-mm-dd")  # → "26-06-02 14-30"
"""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional


# 预设格式
FORMATS = {
    "human":     "%Y年%m月%d日 %H:%M",
    "iso":       "%Y-%m-%d",
    "iso_time":  "%Y-%m-%d %H:%M",
    "compact":   "%m-%d",
    "yy-mm-dd":  "%y-%m-%d %H-%M",
    "ymd_int":   "%Y%m%d",
    "time_only": "%H:%M",
}


def fmt_date(
    preset: str = "iso",
    dt: Optional[datetime] = None,
) -> str:
    """
    按预设格式返回当前日期时间字符串

    Args:
        preset: 预设名（"human" "iso" "iso_time" "compact" "yy-mm-dd" "ymd_int" "time_only"）
                或自定义 strftime 格式
        dt: 指定时间对象，默认当前时间

    Returns:
        格式化的日期字符串

    Examples:
        fmt_date("human")     → "2026年06月02日 14:30"
        fmt_date("iso")       → "2026-06-02"
        fmt_date("compact")   → "06-02"
        fmt_date("%Y/%m/%d")  → "2026/06/02"  (自定义格式)
    """
    fmt = FORMATS.get(preset, preset)
    d = dt or datetime.now()
    return d.strftime(fmt)


def now_str() -> str:
    """快捷: 当前时间 ISO 格式 "2026-06-02 14:30" """
    return fmt_date("iso_time")


def today_str() -> str:
    """快捷: 今天日期 "2026-06-02" """
    return fmt_date("iso")


def today_date() -> date:
    """快捷: 今天 date 对象"""
    return date.today()


def now_dt() -> datetime:
    """快捷: 当前 datetime 对象"""
    return datetime.now()
