"""
技术指标计算包 (v2.6.5 拆分版)
├── compute.py      — 基础计算: SMA/RSI/EMA/MACD/BBANDS/VMA/重采样
├── aggregator.py   — calc_all_indicators() 聚合器
├── scores_basic.py — 基础评分: technical/pattern/trend/position/anti_trap/low_absorb
└── scores_strategy.py — 策略评分: box_breakout/ma_divergence/pullback/ma_support/...

所有函数均从此处重新导出，保证向后兼容。
"""
from .compute import (
    calc_sma, calc_rsi, calc_ema, calc_macd, calc_bbands, calc_volume_ma,
    resample_to_weekly, resample_to_monthly,
)
from .aggregator import calc_all_indicators
from .scores_basic import (
    calc_technical_score, calc_pattern_score, calc_trend_score,
    calc_position_score, calc_anti_trap_penalty, calc_low_absorb_score,
    calc_volume_surge_bonus,
)
from .scores_strategy import (
    calc_box_breakout_score, calc_ma_divergence_score,
    calc_pullback_confirm_score, calc_ma_support_score,
    calc_net_inflow_score, calc_sustained_uptrend_score,
    calc_bottom_rebound_score,
)

__all__ = [
    # 基础计算
    "calc_sma", "calc_rsi", "calc_ema", "calc_macd", "calc_bbands",
    "calc_volume_ma", "resample_to_weekly", "resample_to_monthly",
    # 聚合器
    "calc_all_indicators",
    # 基础评分
    "calc_technical_score", "calc_pattern_score", "calc_trend_score",
    "calc_position_score", "calc_anti_trap_penalty", "calc_low_absorb_score",
    "calc_volume_surge_bonus",
    # 策略评分
    "calc_box_breakout_score", "calc_ma_divergence_score",
    "calc_pullback_confirm_score", "calc_ma_support_score",
    "calc_net_inflow_score", "calc_sustained_uptrend_score",
    "calc_bottom_rebound_score",
]
