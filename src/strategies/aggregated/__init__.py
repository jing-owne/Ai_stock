"""
聚合策略层 (v2.8 Phase 1)

4个聚合策略 — 将旧10策略按语义合并：
- BottomStrategy: 底部反弹 + 连续小阳 (0.6:0.4)
- LaunchStrategy: 放量突破 + 箱体突破 + 启动指纹 (0.35:0.30:0.35)
- TrendStrategy: 追涨确认 + 均线趋势 + AI技术面 (0.35:0.35:0.30)
- MoneyStrategy: 资金净流入 + 成交额排名 + 多因子 (0.35:0.30:0.35)

基类: AggregatedStrategy — 统一编排循环（逐股加权聚合 + 缓存传播）
横截面例外: MoneyStrategy 重写 execute（子策略需全市场排名/归一化）
"""
from .base import AggregatedStrategy
from .bottom_strategy import BottomStrategy
from .launch_strategy import LaunchStrategy
from .trend_strategy import TrendStrategy
from .money_strategy import MoneyStrategy

__all__ = [
    "AggregatedStrategy",
    "BottomStrategy",
    "LaunchStrategy",
    "TrendStrategy",
    "MoneyStrategy",
]
