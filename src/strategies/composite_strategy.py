"""
综合策略 (Composite Strategy) v2.6.5

整合9大独立量化策略，按动态权重分配综合评分。
所有策略均为独立模块，支持单独增删和测试。

架构:
- composite_strategy.py: 编排层（K线预取、指标共享、权重计算、综合评分）
- strategies/momentum/*.py: 动量类策略
- strategies/technical/*.py: 技术类策略

策略权重（根据市场状态自动调整，总和=1.0）：
- 上涨趋势 (trend_up):   动量策略加码
- 下跌趋势 (trend_down): 防守策略加码
- 震荡市 (volatile):     技术面均衡
"""
from typing import List, Dict, Any, Optional
import logging

from .base import BaseStrategy
from ..core.types import StockData, ScanResult, StrategyType
from ..core.indicators import (
    calc_all_indicators, calc_position_score, calc_anti_trap_penalty,
    calc_low_absorb_score, calc_pullback_confirm_score, calc_ma_support_score
)
from ..data.kline_fetcher import KlineFetcher
from ..data.money_flow_fetcher import MoneyFlowFetcher

# ── 9大独立策略 ──
from .momentum.volume_breakout import VolumeBreakoutStrategy
from .momentum.turnover_rank import TurnoverRankStrategy
from .momentum.multi_factor import MultiFactorStrategy
from .momentum.consecutive_positive import ConsecutivePositiveStrategy
from .momentum.net_inflow import NetInflowStrategy
from .technical.ai_technical import AITechnicalStrategy
from .technical.box_breakout import BoxBreakoutStrategy
from .technical.ma_trend import MATrendStrategy
from .technical.bottom_rebound import BottomReboundStrategy


# ── 9大策略权重 (v2.6.5) ──
MARKET_STATE_WEIGHTS = {
    "trend_up": {
        "volume_breakout": 0.18,       # 放量突破（上涨趋势机会多）
        "turnover_rank": 0.14,         # 成交额排名
        "multi_factor": 0.14,          # 多因子增强
        "ai_technical": 0.12,          # AI技术面
        "box_breakout": 0.10,          # 箱体突破
        "ma_trend": 0.12,              # 均线趋势（顺势）
        "bottom_rebound": 0.05,        # 底部反弹（上涨趋势机会少）
        "consecutive_positive": 0.08,  # 连续小阳
        "net_inflow": 0.07,            # 资金净流入
    },
    "trend_down": {
        "volume_breakout": 0.08,       # 放量突破（下跌趋势谨慎）
        "turnover_rank": 0.14,         # 成交额排名
        "multi_factor": 0.17,          # 多因子增强（基数大）
        "ai_technical": 0.10,          # AI技术面
        "box_breakout": 0.06,          # 箱体突破（下跌趋势谨慎）
        "ma_trend": 0.08,              # 均线趋势
        "bottom_rebound": 0.18,        # 底部反弹（下跌趋势重点！）
        "consecutive_positive": 0.09,  # 连续小阳（下跌末期吸筹）
        "net_inflow": 0.10,            # 资金净流入（逆势流入=护盘）
    },
    "volatile": {
        "volume_breakout": 0.14,       # 放量突破
        "turnover_rank": 0.10,         # 成交额排名
        "multi_factor": 0.14,          # 多因子增强
        "ai_technical": 0.12,          # AI技术面
        "box_breakout": 0.12,          # 箱体突破（震荡市机会多）
        "ma_trend": 0.12,              # 均线趋势
        "bottom_rebound": 0.10,        # 底部反弹
        "consecutive_positive": 0.08,  # 连续小阳
        "net_inflow": 0.08,            # 资金净流入
    },
}


def detect_market_state(market_data: List[StockData]) -> str:
    """根据市场数据自动判断市场状态"""
    if not market_data:
        return "volatile"
    up_count = sum(1 for s in market_data if s.change_pct > 0)
    total = len(market_data)
    if total == 0:
        return "volatile"
    up_ratio = up_count / total
    if up_ratio > 0.60:
        return "trend_up"
    elif up_ratio < 0.40:
        return "trend_down"
    else:
        return "volatile"


class CompositeStrategy(BaseStrategy):
    """综合策略：纯编排层，所有子策略均为独立模块"""

    # ── 策略名映射 ──
    STRATEGY_NAMES = {
        "volume_breakout": "放量突破",
        "turnover_rank": "成交额排名",
        "multi_factor": "多因子增强",
        "ai_technical": "AI技术面",
        "box_breakout": "箱体突破",
        "ma_trend": "均线趋势",
        "bottom_rebound": "底部反弹",
        "consecutive_positive": "连续小阳",
        "net_inflow": "资金净流入",
    }

    # 子策略注册表（策略key → 策略实例 + 执行方法引用）
    SUB_STRATEGIES = [
        ("volume_breakout", VolumeBreakoutStrategy),
        ("turnover_rank", TurnoverRankStrategy),
        ("multi_factor", MultiFactorStrategy),
        ("ai_technical", AITechnicalStrategy),
        ("box_breakout", BoxBreakoutStrategy),
        ("ma_trend", MATrendStrategy),
        ("bottom_rebound", BottomReboundStrategy),
        ("consecutive_positive", ConsecutivePositiveStrategy),
        ("net_inflow", NetInflowStrategy),
    ]

    def __init__(self, kline_fetcher: Optional[KlineFetcher] = None):
        super().__init__()
        self.logger = logging.getLogger("AInvest.CompositeStrategy")
        self._last_market_state: str = "volatile"
        self._last_weights: Dict[str, float] = {}
        self._kline_fetcher = kline_fetcher or KlineFetcher(max_workers=8, delay_per_request=0.02)
        # 缓存
        self._kline_cache: Dict[str, List[StockData]] = {}
        self._indicator_cache: Dict[str, Dict[str, float]] = {}
        # ── 实例化所有子策略 ──
        self._strategies: Dict[str, BaseStrategy] = {}
        for key, cls in self.SUB_STRATEGIES:
            instance = cls()
            self._strategies[key] = instance
        # 资金流向获取器（独立缓存，仅net_inflow使用）
        self._money_flow_fetcher = MoneyFlowFetcher(max_workers=4)
        # API失败追踪
        self._api_failed: set = set()

    @property
    def name(self) -> str:
        return "综合策略"

    @property
    def strategy_type(self) -> StrategyType:
        return StrategyType.COMPOSITE

    # ═══════════════════════════════════════════════════════════════
    # 主入口
    # ═══════════════════════════════════════════════════════════════

    def execute(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> List[ScanResult]:
        """执行综合策略（编排层）"""
        market_state = detect_market_state(market_data)
        self.logger.info(f"市场状态: {market_state}")

        # 1. 计算动态权重
        weights = self._get_weights(params, market_state)
        self._last_market_state = market_state
        self._last_weights = dict(weights)

        # 2. 预获取K线 + 计算指标（一次性，所有策略共享）
        self._prefetch_kline_and_indicators(market_data)
        self._inject_shared_cache()

        # 3. 执行所有子策略（独立模块，可增删）
        sub_results: Dict[str, Dict[str, ScanResult]] = {}
        for key, strategy in self._strategies.items():
            try:
                for result in strategy.execute(market_data, params):
                    sub_results.setdefault(result.symbol, {})[key] = result
            except Exception as e:
                self._api_failed.add(key)
                self.logger.warning(f"策略 [{key}] 执行失败: {e}，已降权")

        # 存储子策略结果（供 engine 提取各策略 Top 15）
        self._last_sub_results = sub_results

        # 4. 综合评分
        stock_scores = self._calculate_composite_scores(sub_results, weights)

        # 5. 生成结果
        results = self._generate_results(
            list(stock_scores.keys()), stock_scores, sub_results
        )
        results.sort(key=lambda x: x.score, reverse=True)

        self.logger.info(
            f"综合策略完成: {len(results)} 只 "
            f"(市场: {market_state}, 活跃策略: {len(self._strategies) - len(self._api_failed)}/{len(self._strategies)})"
        )
        return results

    # ═══════════════════════════════════════════════════════════════
    # 权重计算
    # ═══════════════════════════════════════════════════════════════

    def _get_weights(self, params: Dict[str, Any], market_state: str) -> Dict[str, float]:
        composite = params.get("composite_strategy", {}) if params else {}
        use_dynamic = composite.get("dynamic_weights", True)
        manual = composite.get("manual_weights", {}) or {}

        if not use_dynamic:
            return {
                "volume_breakout": composite.get("volume_breakout_weight", 0.14),
                "turnover_rank": composite.get("turnover_rank_weight", 0.14),
                "multi_factor": composite.get("multi_factor_weight", 0.14),
                "ai_technical": composite.get("ai_technical_weight", 0.12),
                "box_breakout": composite.get("box_breakout_weight", 0.10),
                "ma_trend": composite.get("ma_trend_weight", 0.10),
                "bottom_rebound": composite.get("bottom_rebound_weight", 0.10),
                "consecutive_positive": composite.get("consecutive_positive_weight", 0.08),
                "net_inflow": composite.get("net_inflow_weight", 0.08),
            }

        weights = dict(MARKET_STATE_WEIGHTS.get(market_state, MARKET_STATE_WEIGHTS["volatile"]))

        if manual:
            weights.update(manual)

        # ── API失败的策略降权到0，权重重新分配 ──
        if self._api_failed:
            removed_weight = 0
            for key in list(weights.keys()):
                if key in self._api_failed:
                    removed_weight += weights.pop(key, 0)
            if removed_weight > 0 and weights:
                total = sum(weights.values())
                for k in weights:
                    weights[k] += removed_weight * weights[k] / total
            self.logger.info(f"API失败策略已降权: {self._api_failed}")

        # 归一化
        total = sum(weights.values())
        if total > 0 and abs(total - 1.0) > 0.01:
            weights = {k: v / total for k, v in weights.items()}
        return weights

    # ═══════════════════════════════════════════════════════════════
    # K线预获取 + 指标共享
    # ═══════════════════════════════════════════════════════════════

    def _prefetch_kline_and_indicators(self, market_data: List[StockData]) -> None:
        """预获取K线数据并计算技术指标（并发，所有策略共享）"""
        symbols = list({s.symbol for s in market_data if s.amount >= 100_000_000})
        self.logger.info(f"预获取 {len(symbols)} 只K线...")

        self._kline_cache = self._kline_fetcher.fetch_batch(symbols, days=60)
        self._kline_available = len(self._kline_cache) > 0

        if not self._kline_available:
            self.logger.warning(f"K线获取失败({len(symbols)}只)，策略将降级")
            return

        import numpy as np
        calc_count = 0
        for symbol, kline_list in self._kline_cache.items():
            arrays = self._kline_fetcher.get_numpy_arrays(kline_list)
            if arrays:
                indicators = calc_all_indicators(
                    arrays["close"], arrays["volume"],
                    arrays["high"], arrays["low"]
                )
                self._indicator_cache[symbol] = indicators
                calc_count += 1

        self.logger.info(f"指标计算完成: {calc_count} 只")

    def _inject_shared_cache(self):
        """将K线缓存和指标缓存注入到各子策略"""
        for key, strategy in self._strategies.items():
            if hasattr(strategy, '_indicators'):
                strategy._indicators = self._indicator_cache
            if hasattr(strategy, '_kline_cache'):
                strategy._kline_cache = self._kline_cache
            if hasattr(strategy, '_kline_available'):
                strategy._kline_available = self._kline_available

    # ═══════════════════════════════════════════════════════════════
    # 综合评分计算
    # ═══════════════════════════════════════════════════════════════

    def _calculate_composite_scores(
        self,
        sub_results: Dict[str, Dict[str, ScanResult]],
        weights: Dict[str, float]
    ) -> Dict[str, float]:
        """综合评分: 策略共识分 + 位置/低吸/回调/均线/防套/多样性"""
        scores = {}
        for symbol, strategies in sub_results.items():
            # 策略共识分
            strategy_total = 0.0
            for sname, result in strategies.items():
                w = weights.get(sname, 0.0)
                strategy_total += min(result.score, 100) * w

            indicators = self._indicator_cache.get(symbol, {})

            # 位置评分
            position_score = calc_position_score(indicators)
            # 低吸评分
            low_absorb_score = min(calc_low_absorb_score(indicators), 20)
            # 回调确认
            pullback_bonus = calc_pullback_confirm_score(indicators)
            # 均线支撑
            ma_support_bonus = calc_ma_support_score(indicators)

            # 防套惩罚
            stock_data = None
            for result in strategies.values():
                if result.data:
                    stock_data = result.data
                    break
            anti_trap = 0.0
            if stock_data and indicators:
                anti_trap = calc_anti_trap_penalty(
                    indicators, stock_data.change_pct,
                    stock_data.turn_rate, stock_data.amount
                )

            # 策略数量加分（无上限）
            count = len(strategies)
            diversity_bonus = count * 1.5

            total = round(
                strategy_total + position_score + low_absorb_score +
                pullback_bonus + ma_support_bonus + diversity_bonus - anti_trap, 2
            )
            scores[symbol] = total

        return scores

    # ═══════════════════════════════════════════════════════════════
    # 结果生成
    # ═══════════════════════════════════════════════════════════════

    def _generate_results(
        self,
        filtered_symbols: List[str],
        stock_scores: Dict[str, float],
        sub_results: Dict[str, Dict[str, ScanResult]]
    ) -> List[ScanResult]:
        """生成ScanResult列表"""
        results = []
        for symbol in filtered_symbols:
            if symbol not in stock_scores:
                continue
            score = stock_scores[symbol]
            strat_map = sub_results.get(symbol, {})

            all_signals = []
            hit_strategies = []
            for sname, result in strat_map.items():
                all_signals.extend(result.signals)
                hit_strategies.append(self.STRATEGY_NAMES.get(sname, sname))

            strategy_signal = "+".join(hit_strategies)

            indicators = self._indicator_cache.get(symbol, {})
            stock_data = next((r.data for r in strat_map.values() if r.data), None)

            # 风险标签
            trap_flags = []
            if stock_data and indicators:
                penalty = calc_anti_trap_penalty(
                    indicators, stock_data.change_pct,
                    stock_data.turn_rate, stock_data.amount
                )
                if penalty >= 20:
                    trap_flags.append("高风险")
                elif penalty >= 10:
                    trap_flags.append("中风险")
                elif penalty > 0:
                    trap_flags.append("注意")
                else:
                    trap_flags.append("安全")
                pos_20 = indicators.get("position_20d", 50)
                if pos_20 > 80:
                    trap_flags.append("高位")
                elif pos_20 < 30:
                    trap_flags.append("低位")

            metadata = {
                "composite_score": score,
                "strategy_count": len(strat_map),
                "hit_strategies": hit_strategies,
                "position_20d": round(indicators.get("position_20d", 50), 1),
                "consecutive_up": int(indicators.get("consecutive_up", 0)),
                "pullback_confirm": bool(indicators.get("pullback_confirm", False)),
                "ma_support": calc_ma_support_score(indicators) > 0,
                "trap_flags": trap_flags,
            }
            for sname, result in strat_map.items():
                metadata[f"{sname}_score"] = result.score

            results.append(ScanResult(
                symbol=symbol,
                name=next((r.data.name for r in strat_map.values() if r.data), symbol),
                strategy=StrategyType.COMPOSITE,
                score=score,
                signals=[strategy_signal] + list(set(all_signals))[:4],
                data=next((r.data for r in strat_map.values() if r.data), None),
                metadata=metadata
            ))
        return results
