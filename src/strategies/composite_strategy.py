"""
综合策略 (Composite Strategy) v2.8

整合4大聚合策略，按动态权重分配综合评分。

架构:
- composite_strategy.py: 编排层（K线预取、指标共享、权重计算、Bottom↔Trend互斥）
- strategies/aggregated/*.py: 4个聚合策略（各含2-3个子策略）
- strategies/momentum/*.py: 动量类子策略（_DEPRECATED v2.6，仅供 aggregated 内部引用）
- strategies/technical/*.py: 技术类子策略（_DEPRECATED v2.6，仅供 aggregated 内部引用）

策略权重（根据市场状态自动调整，总和=1.0）：
- 上涨趋势 (trend_up):   追涨+资金加码
- 下跌趋势 (trend_down): 底部+资金防守
- 震荡市 (volatile):     四策略均衡
"""
from typing import List, Dict, Any, Optional
import logging

from .base import BaseStrategy
from ..core.types import StockData, ScanResult, StrategyType
from ..core.indicators import (
    calc_position_score, calc_anti_trap_penalty,
    calc_low_absorb_score, calc_pullback_confirm_score, calc_ma_support_score,
    calc_volume_surge_bonus
)
from ..data.kline_fetcher import KlineFetcher
from ..data.money_flow_fetcher import MoneyFlowFetcher

# ── 4个聚合策略（v2.8）──
from .aggregated.bottom_strategy import BottomStrategy
from .aggregated.launch_strategy import LaunchStrategy
from .aggregated.trend_strategy import TrendStrategy
from .aggregated.money_strategy import MoneyStrategy
from .momentum.volume_breakout import VolumeBreakoutStrategy
from .momentum.turnover_rank import TurnoverRankStrategy
from .momentum.multi_factor import MultiFactorStrategy
from .momentum.consecutive_positive import ConsecutivePositiveStrategy
from .momentum.net_inflow import NetInflowStrategy
from .momentum.trend_confirmation import TrendConfirmationStrategy
from .technical.ai_technical import AITechnicalStrategy
from .technical.box_breakout import BoxBreakoutStrategy
from .technical.ma_trend import MATrendStrategy
from .technical.bottom_rebound import BottomReboundStrategy


# ── 4聚合策略权重表 (v2.8) ──
MARKET_STATE_WEIGHTS = {
    "trend_up": {
        "bottom": 0.05,
        "launch": 0.15,
        "trend": 0.35,
        "money": 0.30,
    },
    "trend_down": {
        "bottom": 0.45,
        "launch": 0.10,
        "trend": 0.20,
        "money": 0.25,
    },
    "volatile": {
        "bottom": 0.30,
        "launch": 0.20,
        "trend": 0.25,
        "money": 0.25,
    },
}

MARKET_STATE_WEIGHTS_OLD = {
    "trend_up": {
        "volume_breakout": 0.15,
        "turnover_rank": 0.15,
        "multi_factor": 0.15,
        "ai_technical": 0.12,
        "box_breakout": 0.10,
        "ma_trend": 0.10,
        "bottom_rebound": 0.08,
        "consecutive_positive": 0.07,
        "net_inflow": 0.08,
        "trend_confirmation": 0.05,
    },
    "trend_down": {
        "bottom_rebound": 0.20,
        "consecutive_positive": 0.15,
        "ma_trend": 0.15,
        "volume_breakout": 0.12,
        "box_breakout": 0.10,
        "multi_factor": 0.10,
        "ai_technical": 0.08,
        "turnover_rank": 0.08,
        "net_inflow": 0.05,
        "trend_confirmation": 0.02,
    },
    "volatile": {
        "volume_breakout": 0.14,
        "turnover_rank": 0.14,
        "multi_factor": 0.14,
        "ai_technical": 0.12,
        "box_breakout": 0.10,
        "ma_trend": 0.10,
        "bottom_rebound": 0.10,
        "consecutive_positive": 0.08,
        "net_inflow": 0.08,
        "trend_confirmation": 0.08,
    },
}


def detect_market_state(market_data: List[StockData]) -> str:
    """根据市场数据自动判断市场状态（多维度融合）

    维度1: 涨跌比 — 上涨标的占比
    维度2: 平均波动率 — |涨跌幅|均值
    维度3: 涨跌幅标准差 — 波动分散度
    维度4: 大涨/大跌极端比 — 涨>5% vs 跌>5% 数量比
    维度5: 成交额集中度 — TOP10%成交额占比
    """
    if not market_data:
        return "volatile"
    total = len(market_data)
    if total == 0:
        return "volatile"
    up_count = sum(1 for s in market_data if s.change_pct > 0)
    down_count = sum(1 for s in market_data if s.change_pct < 0)
    up_ratio = up_count / total
    import numpy as np
    pcts = np.array([s.change_pct for s in market_data])
    avg_volatility = float(np.mean(np.abs(pcts)))
    std_pct = float(np.std(pcts)) if total > 1 else avg_volatility
    big_up = sum(1 for s in market_data if s.change_pct > 5)
    big_down = sum(1 for s in market_data if s.change_pct < -5)
    extreme_ratio = big_up / max(big_down, 1)
    amounts = sorted([s.amount for s in market_data], reverse=True)
    top_10pct = amounts[:max(1, total // 10)]
    total_amount = sum(amounts)
    concentration = sum(top_10pct) / max(total_amount, 1) if total_amount > 0 else 0.5
    if up_ratio > 0.55 and avg_volatility < 3.5 and extreme_ratio > 1.5:
        return "trend_up"
    if up_ratio < 0.45 and (avg_volatility > 3.0 or extreme_ratio < 0.5):
        return "trend_down"
    if std_pct > 4.0:
        return "volatile"
    if up_ratio > 0.50 and avg_volatility < 2.0 and concentration > 0.3:
        return "trend_up"
    return "volatile"


class CompositeStrategy(BaseStrategy):
    """综合策略：纯编排层，4个聚合策略为子模块"""

    # ── 4聚合策略注册表 ──
    SUB_STRATEGIES = [
        ("bottom", BottomStrategy),
        ("launch", LaunchStrategy),
        ("trend", TrendStrategy),
        ("money", MoneyStrategy),
    ]

    STRATEGY_NAMES = {
        "bottom": "底部策略",
        "launch": "启动策略",
        "trend": "追涨策略",
        "money": "资金策略",
    }

    SUB_STRATEGIES_OLD = [
        ("volume_breakout", VolumeBreakoutStrategy),
        ("turnover_rank", TurnoverRankStrategy),
        ("multi_factor", MultiFactorStrategy),
        ("ai_technical", AITechnicalStrategy),
        ("box_breakout", BoxBreakoutStrategy),
        ("ma_trend", MATrendStrategy),
        ("bottom_rebound", BottomReboundStrategy),
        ("consecutive_positive", ConsecutivePositiveStrategy),
        ("net_inflow", NetInflowStrategy),
        ("trend_confirmation", TrendConfirmationStrategy),
    ]

    STRATEGY_NAMES_OLD = {
        "volume_breakout": "放量突破",
        "turnover_rank": "成交额排名",
        "multi_factor": "多因子",
        "ai_technical": "AI技术面",
        "box_breakout": "箱体突破",
        "ma_trend": "均线趋势",
        "bottom_rebound": "底部反弹",
        "consecutive_positive": "连续小阳",
        "net_inflow": "资金净流入",
        "trend_confirmation": "追涨确认",
    }

    def __init__(self, kline_fetcher: Optional[KlineFetcher] = None):
        super().__init__()
        self.logger = logging.getLogger("AInvest.CompositeStrategy")
        self._last_market_state: str = "volatile"
        self._last_weights: Dict[str, float] = {}
        self._last_sub_results: Dict[str, Dict[str, ScanResult]] = {}
        self._kline_fetcher = kline_fetcher or KlineFetcher(max_workers=8, delay_per_request=0.015)
        self._kline_cache: Dict[str, List[StockData]] = {}
        self._indicator_cache: Dict[str, Dict[str, float]] = {}
        self._money_flow_fetcher = MoneyFlowFetcher(max_workers=4)
        self._api_failed: set = set()
        self._skip_money_flow = False
        self._legacy_mode = False
        self._strategy_names: Dict[str, str] = {}
        self._load_strategy_config()
        self._sub_strategy_defs = self._build_strategy_bundle(self._legacy_mode)
        self._strategies: Dict[str, BaseStrategy] = {}
        for key, cls in self._sub_strategy_defs:
            self._strategies[key] = cls()

    def _load_strategy_config(self):
        from ..core.config import load_runtime_config
        _cfg = load_runtime_config()
        if _cfg.get('skip_money_flow', False):
            self._skip_money_flow = True
            self.logger.info('配置跳过资金策略（skip_money_flow=true）')
        if _cfg.get('legacy_mode', False):
            self._legacy_mode = True
            self.logger.info('启用旧策略模式（legacy_mode=true）')

    def _build_strategy_bundle(self, legacy_mode: bool):
        if legacy_mode:
            self._strategy_names = dict(self.STRATEGY_NAMES_OLD)
            return list(self.SUB_STRATEGIES_OLD)
        self._strategy_names = dict(self.STRATEGY_NAMES)
        return list(self.SUB_STRATEGIES)

    def _rebuild_strategy_bundle(self, legacy_mode: bool) -> None:
        if legacy_mode == self._legacy_mode and self._strategies:
            return
        self._legacy_mode = legacy_mode
        self._api_failed.clear()
        self._sub_strategy_defs = self._build_strategy_bundle(self._legacy_mode)
        self._strategies = {key: cls() for key, cls in self._sub_strategy_defs}

    @property
    def name(self) -> str:
        return "综合策略"

    @property
    def strategy_type(self) -> StrategyType:
        return StrategyType.COMPOSITE

    # ═══════════════════════════════════════════════════════════════
    # StrategyContext 访问器
    # ═══════════════════════════════════════════════════════════════

    @property
    def last_weights(self) -> Dict[str, float]:
        return dict(self._last_weights)

    @property
    def last_sub_results(self) -> Dict[str, Dict[str, ScanResult]]:
        return dict(self._last_sub_results)

    @property
    def last_market_state(self) -> str:
        return self._last_market_state

    # ═══════════════════════════════════════════════════════════════
    # 主入口
    # ═══════════════════════════════════════════════════════════════

    def execute(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> List[ScanResult]:
        params = params or {}
        if isinstance(params.get("legacy_mode"), bool):
            self._rebuild_strategy_bundle(params["legacy_mode"])

        # 修复A: 每次运行重置失败集合，避免子策略偶发一次异常被永久降权（跨多次定时运行累积）
        self._api_failed.clear()

        market_state = detect_market_state(market_data)
        self.logger.info(f"市场状态: {market_state}")
        self._last_market_state = market_state

        filtered_data = [s for s in market_data if s.amount >= 200_000_000]
        self.logger.info(f"成交额过滤: {len(market_data)} -> {len(filtered_data)} 只")
        del market_data
        import gc; gc.collect()
        try:
            import ctypes
            if hasattr(ctypes, 'CDLL'):
                ctypes.CDLL('libc.so.6').malloc_trim(0)
        except Exception:
            pass
        market_data = filtered_data

        self._prefetch_kline_and_indicators(market_data, as_of=params.get("as_of"))
        self._inject_shared_cache()

        sub_results: Dict[str, Dict[str, ScanResult]] = {}
        skip_keys = set()
        if self._skip_money_flow:
            skip_keys.add('money')
            skip_keys.add('net_inflow')
            self.logger.info('配置跳过资金策略（skip_money_flow=true）')
        for key, strategy in self._strategies.items():
            if key in skip_keys:
                continue
            try:
                for result in strategy.execute(market_data, params):
                    sub_results.setdefault(result.symbol, {})[key] = result
            except Exception as e:
                self._api_failed.add(key)
                self.logger.warning(f"策略 [{key}] 执行失败: {e}，本次运行降权")

        # 修复A: 权重在本次子策略运行后计算，仅对"本次"失败的策略降权（不再跨运行累积）
        weights = self._get_weights(params, market_state)
        self._last_weights = dict(weights)

        self._last_sub_results = sub_results
        stock_scores = self._calculate_composite_scores(sub_results, weights)
        results = self._generate_results(list(stock_scores.keys()), stock_scores, sub_results)
        results.sort(key=lambda x: x.score, reverse=True)

        if not self._legacy_mode:
            # Stage 互斥: Bottom ↔ Trend
            results = self._apply_stage_mutual_exclusion(results, sub_results)

        # 板块分散度
        sector_info = self._analyze_sector_diversity(results, top_n=15)
        if sector_info.get("warning"):
            self.logger.warning(sector_info["warning"])
        self.logger.info(
            f"板块分散度: {sector_info.get('diversity_ratio', 0):.2f} "
            f"(独立板块: {len(sector_info.get('sector_counts', {}))}个)"
        )
        self.logger.info(
            f"综合策略完成: {len(results)} 只 "
            f"(活跃策略: {len(self._strategies) - len(self._api_failed)}/{len(self._strategies)})"
        )
        return results

    # ═══════════════════════════════════════════════════════════════
    # 权重计算
    # ═══════════════════════════════════════════════════════════════

    def _get_weights(self, params: Dict[str, Any], market_state: str) -> Dict[str, float]:
        composite = params.get("composite_strategy", {}) if params else {}
        use_dynamic = composite.get("dynamic_weights", True)
        manual = composite.get("manual_weights", {}) or composite.get("weights", {}) or {}
        if manual and self._legacy_mode:
            manual_aliases = {
                "volume_surge": "volume_breakout",
                "ma_divergence": "ma_trend",
                "rsi_oversold": "bottom_rebound",
                "new_high_break": "volume_breakout",
                "institution": "net_inflow",
                "sustained_uptrend": "trend_confirmation",
            }
            manual = {manual_aliases.get(k, k): v for k, v in manual.items()}

        if not use_dynamic:
            if self._legacy_mode:
                weights = {
                    "volume_breakout": composite.get("volume_breakout_weight", composite.get("volume_surge_weight", 0.14)),
                    "turnover_rank": composite.get("turnover_rank_weight", 0.14),
                    "multi_factor": composite.get("multi_factor_weight", 0.14),
                    "ai_technical": composite.get("ai_technical_weight", 0.12),
                    "box_breakout": composite.get("box_breakout_weight", 0.10),
                    "ma_trend": composite.get("ma_trend_weight", composite.get("ma_divergence_weight", 0.10)),
                    "bottom_rebound": composite.get("bottom_rebound_weight", composite.get("rsi_oversold_weight", 0.10)),
                    "consecutive_positive": composite.get("consecutive_positive_weight", 0.08),
                    "net_inflow": composite.get("net_inflow_weight", composite.get("institution_weight", 0.08)),
                    "trend_confirmation": composite.get("trend_confirmation_weight", composite.get("sustained_uptrend_weight", 0.08)),
                }
            else:
                weights = {
                    "bottom": composite.get("bottom_weight", 0.25),
                    "launch": composite.get("launch_weight", 0.25),
                    "trend": composite.get("trend_weight", 0.25),
                    "money": composite.get("money_weight", 0.25),
                }
        elif self._legacy_mode:
            weights = dict(MARKET_STATE_WEIGHTS_OLD.get(market_state, MARKET_STATE_WEIGHTS_OLD["volatile"]))
        else:
            weights = dict(MARKET_STATE_WEIGHTS.get(market_state, MARKET_STATE_WEIGHTS["volatile"]))
        if manual:
            weights.update(manual)

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

        total = sum(weights.values())
        if total > 0 and abs(total - 1.0) > 1e-6:
            weights = {k: v / total for k, v in weights.items()}
        return weights

    # ═══════════════════════════════════════════════════════════════
    # K线预获取 + 指标共享
    # ═══════════════════════════════════════════════════════════════

    def _prefetch_kline_and_indicators(self, market_data: List[StockData], as_of: Optional[str] = None) -> None:
        from ..data.prefetch import prefetch_kline_indicators
        symbols = list({s.symbol for s in market_data if s.amount >= 200_000_000})
        ind, kln, cnt = prefetch_kline_indicators(
            symbols=symbols, kline_fetcher=self._kline_fetcher,
            keep_kline=True, log_prefix="Composite", as_of=as_of,
        )
        self._indicator_cache = ind
        self._kline_cache = kln
        self._kline_available = cnt > 0
        if not self._kline_available:
            self.logger.warning(f"K线获取失败({len(symbols)}只)，策略将降级")

    def _inject_shared_cache(self):
        for key, strategy in self._strategies.items():
            if hasattr(strategy, '_indicators'):
                strategy._indicators = self._indicator_cache
            if hasattr(strategy, '_kline_cache'):
                strategy._kline_cache = self._kline_cache
            if hasattr(strategy, '_kline_available'):
                strategy._kline_available = self._kline_available

    # ═══════════════════════════════════════════════════════════════
    # Stage 互斥: Bottom ↔ Trend
    # ═══════════════════════════════════════════════════════════════

    def _apply_stage_mutual_exclusion(
        self,
        results: List[ScanResult],
        sub_results: Dict[str, Dict[str, ScanResult]]
    ) -> List[ScanResult]:
        trend_direction = self._last_market_state
        filtered: List[ScanResult] = []
        for r in results:
            hit_keys = r.metadata.get("hit_strategy_keys", [])
            if trend_direction == "trend_down" and hit_keys == ["trend"]:
                continue
            if trend_direction == "trend_up" and hit_keys == ["bottom"]:
                continue
            if trend_direction not in ("trend_up", "trend_down"):
                if any(h in ("bottom", "trend") for h in hit_keys):
                    r.score = round(r.score * 0.7, 1)
            filtered.append(r)
        return filtered

    # ═══════════════════════════════════════════════════════════════
    # 综合评分计算
    # ═══════════════════════════════════════════════════════════════

    def _calculate_composite_scores(
        self,
        sub_results: Dict[str, Dict[str, ScanResult]],
        weights: Dict[str, float]
    ) -> Dict[str, float]:
        scores = {}
        for symbol, strategies in sub_results.items():
            strategy_total = 0.0
            for sname, result in strategies.items():
                w = weights.get(sname, 0.0)
                strategy_total += min(result.score, 100) * w

            indicators = self._indicator_cache.get(symbol, {})
            position_score = calc_position_score(indicators)
            low_absorb_score = min(calc_low_absorb_score(indicators), 20)
            pullback_bonus = calc_pullback_confirm_score(indicators)
            ma_support_bonus = calc_ma_support_score(indicators)

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

            count = len(strategies)
            diversity_bonus = count * 1.0
            volume_bonus = calc_volume_surge_bonus(indicators)
            sector_bonus = 1.0 if (stock_data and stock_data.sector) else 0.0

            total = round(
                strategy_total + position_score + low_absorb_score +
                pullback_bonus + ma_support_bonus + diversity_bonus +
                volume_bonus + sector_bonus - anti_trap, 2
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
        results = []
        for symbol in filtered_symbols:
            if symbol not in stock_scores:
                continue
            score = stock_scores[symbol]
            strat_map = sub_results.get(symbol, {})

            all_signals = []
            hit_strategies = []
            hit_strategy_keys = []
            for sname, result in strat_map.items():
                all_signals.extend(result.signals)
                hit_strategy_keys.append(sname)
                hit_strategies.append(self._strategy_names.get(sname, sname))

            strategy_signal = "+".join(hit_strategies)
            indicators = self._indicator_cache.get(symbol, {})
            stock_data = next((r.data for r in strat_map.values() if r.data), None)

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

            vol_bonus = calc_volume_surge_bonus(indicators)
            sector_name = stock_data.sector if stock_data else None

            metadata = {
                "composite_score": score,
                "strategy_count": len(strat_map),
                "hit_strategy_keys": hit_strategy_keys,
                "hit_strategies": hit_strategies,
                "position_20d": round(indicators.get("position_20d", 50), 1),
                "consecutive_up": int(indicators.get("consecutive_up", 0)),
                "consecutive_volume_up": int(indicators.get("consecutive_volume_up", 0)),
                "pullback_confirm": bool(indicators.get("pullback_confirm", False)),
                "ma_support": calc_ma_support_score(indicators) > 0,
                "trap_flags": trap_flags,
                "volume_bonus": round(vol_bonus, 1),
                "sector": sector_name,
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

    # ═══════════════════════════════════════════════════════════════
    # 板块分散度分析
    # ═══════════════════════════════════════════════════════════════

    def _analyze_sector_diversity(
        self,
        results: List[ScanResult],
        top_n: int = 15
    ) -> Dict[str, Any]:
        top = results[:top_n]
        sector_counts: Dict[str, int] = {}
        no_sector_count = 0
        for r in top:
            sector = r.metadata.get("sector")
            if sector:
                sector_counts[sector] = sector_counts.get(sector, 0) + 1
            else:
                no_sector_count += 1
        if not sector_counts:
            return {
                "sector_counts": {}, "max_sector": None, "max_count": 0,
                "diversity_ratio": 0.0, "warning": "无板块数据",
            }
        max_sector = max(sector_counts, key=sector_counts.get)
        max_count = sector_counts[max_sector]
        unique_sectors = len(sector_counts)
        diversity_ratio = unique_sectors / min(top_n, len(top)) if top else 0
        warning = None
        if max_count / min(top_n, len(top)) > 0.4:
            warning = f"板块集中度过高: {max_sector} 占 {max_count}/{len(top)}"
        return {
            "sector_counts": sector_counts, "max_sector": max_sector,
            "max_count": max_count, "diversity_ratio": round(diversity_ratio, 2),
            "warning": warning, "no_sector_count": no_sector_count,
        }
