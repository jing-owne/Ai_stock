"""
综合策略 (Composite Strategy)
整合5大选股策略，按照动态权重分配综合评分

策略权重（根据市场状态自动调整）：
- 上涨趋势 (trend_up):   放量25% 成交额25% 多因子30% AI技术20% 机构0%
- 下跌趋势 (trend_down): 放量15% 成交额25% 多因子30% AI技术20% 机构10%
- 震荡市 (volatile):     放量25% 成交额20% 多因子25% AI技术20% 机构10%

基本面筛选（可选，基于行情数据）：
- 排除 ST / * 股（数据层已过滤）
- 排除停牌股（成交量=0，数据层已过滤）
- 可选：PE/PB筛选（需配置第三方数据源）
"""

from typing import List, Dict, Any
import random
import logging

from .base import BaseStrategy
from ..core.types import StockData, ScanResult, StrategyType


# 市场状态 → 动态权重
MARKET_STATE_WEIGHTS = {
    "trend_up": {    # 上涨趋势 → 动量策略加码
        "volume_surge": 0.25,
        "turnover_rank": 0.25,
        "multi_factor": 0.30,
        "ai_technical": 0.20,
        "institution": 0.00,   # 上涨时机构策略参考价值低
    },
    "trend_down": {  # 下跌趋势 → 机构和多因子加码
        "volume_surge": 0.15,
        "turnover_rank": 0.25,
        "multi_factor": 0.30,
        "ai_technical": 0.20,
        "institution": 0.10,
    },
    "volatile": {     # 震荡市 → 技术面加码
        "volume_surge": 0.25,
        "turnover_rank": 0.20,
        "multi_factor": 0.25,
        "ai_technical": 0.20,
        "institution": 0.10,
    },
}


def detect_market_state(market_data: List[StockData]) -> str:
    """根据市场数据自动判断市场状态"""
    if not market_data:
        return "volatile"

    up_count = sum(1 for s in market_data if s.change_pct > 0)
    down_count = sum(1 for s in market_data if s.change_pct < 0)
    total = len(market_data)

    if total == 0:
        return "volatile"

    up_ratio = up_count / total

    # 涨跌比明显偏向一方 → 趋势市
    if up_ratio > 0.60:
        return "trend_up"
    elif up_ratio < 0.40:
        return "trend_down"
    else:
        return "volatile"


class CompositeStrategy(BaseStrategy):
    """综合策略：多策略加权 + 动态权重 + 可选基本面过滤"""

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("AInvest.CompositeStrategy")
        self._last_market_state: str = "volatile"
        self._last_weights: Dict[str, float] = {}

    @property
    def name(self) -> str:
        return "综合策略"

    @property
    def strategy_type(self) -> StrategyType:
        return StrategyType.COMPOSITE

    def execute(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> List[ScanResult]:
        """执行综合策略"""
        # 自动判断市场状态
        market_state = detect_market_state(market_data)
        self.logger.info(f"检测市场状态: {market_state}")

        # 获取动态权重
        weights = self._get_weights(params, market_state)

        # 保存到实例属性，供 StrategyAgent.execute_with_context() 读取
        self._last_market_state = market_state
        self._last_weights = dict(weights)

        # 执行各子策略
        sub_results = self._execute_sub_strategies(market_data, params)

        # 计算综合评分
        stock_scores = self._calculate_composite_scores(sub_results, weights)

        # 应用基本面筛选（可选，默认关闭）
        filtered_symbols = self._apply_fundamental_filter(
            stock_scores, params
        )

        # 生成最终结果
        results = self._generate_results(
            filtered_symbols, stock_scores, sub_results
        )

        results.sort(key=lambda x: x.score, reverse=True)
        self.logger.info(
            f"综合策略选股完成: {len(results)} 只股票 "
            f"(市场: {market_state}, 权重: {weights})"
        )
        return results

    # ─────────────────────────────────────────────
    # 权重计算
    # ─────────────────────────────────────────────

    def _get_weights(self, params: Dict[str, Any], market_state: str) -> Dict[str, float]:
        """
        获取策略权重（支持动态 + 手动覆盖）

        优先级：
        1. configs 中 manual_weights 手动指定的
        2. 根据市场状态自动选择
        3. 配置中 composite_strategy 的备用默认值

        配置示例（configs/settings.yaml）：
        ```yaml
        composite_strategy:
          dynamic_weights: true      # 开启动态权重
          manual_weights:            # 手动覆盖（可选）
            volume_surge: 0.30
            # 未指定的策略继续使用动态权重
        ```
        """
        composite = params.get("composite_strategy", {}) if params else {}

        # 是否开启动态权重
        use_dynamic = composite.get("dynamic_weights", True)

        # 手动覆盖权重
        manual = composite.get("manual_weights", {}) or {}

        if not use_dynamic:
            # 关闭动态 → 使用固定权重
            self.logger.info("动态权重已关闭，使用固定权重")
            return {
                "volume_surge": composite.get("volume_surge_weight", 0.25),
                "turnover_rank": composite.get("turnover_rank_weight", 0.25),
                "multi_factor": composite.get("multi_factor_weight", 0.25),
                "ai_technical": composite.get("ai_technical_weight", 0.20),
                "institution": composite.get("institution_weight", 0.05),
            }

        # 动态权重
        weights = dict(MARKET_STATE_WEIGHTS.get(
            market_state, MARKET_STATE_WEIGHTS["volatile"]
        ))

        # 手动覆盖（部分覆盖也支持）
        if manual:
            weights.update(manual)
            self.logger.info(f"权重已手动覆盖: {manual}")

        # 归一化（确保总和为1.0）
        total = sum(weights.values())
        if total > 0 and abs(total - 1.0) > 0.01:
            weights = {k: v / total for k, v in weights.items()}
            self.logger.info(f"权重已归一化: sum={sum(weights.values()):.2f}")

        self.logger.info(f"最终权重({market_state}): {weights}")
        return weights

    # ─────────────────────────────────────────────
    # 子策略执行
    # ─────────────────────────────────────────────

    def _execute_sub_strategies(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> Dict[str, Dict[str, ScanResult]]:
        """执行5个子策略，返回 {symbol: {strategy_name: result}}"""
        sub_results: Dict[str, Dict[str, ScanResult]] = {}

        for result in self._execute_volume_surge(market_data, params):
            sub_results.setdefault(result.symbol, {})["volume_surge"] = result

        for result in self._execute_turnover_rank(market_data, params):
            sub_results.setdefault(result.symbol, {})["turnover_rank"] = result

        for result in self._execute_multi_factor(market_data, params):
            sub_results.setdefault(result.symbol, {})["multi_factor"] = result

        for result in self._execute_ai_technical(market_data, params):
            sub_results.setdefault(result.symbol, {})["ai_technical"] = result

        for result in self._execute_institution(market_data, params):
            sub_results.setdefault(result.symbol, {})["institution"] = result

        return sub_results

    def _execute_volume_surge(self, market_data, params) -> List[ScanResult]:
        """放量上涨策略"""
        cfg = params.get("volume_surge", {}) if params else {}
        min_ratio = cfg.get("min_volume_ratio", 2.0)
        min_change = cfg.get("min_price_change", 1.0)
        min_amount = cfg.get("min_amount", 100_000_000)

        results = []
        max_amount = max((s.amount for s in market_data), default=1)

        for stock in market_data:
            if stock.change_pct < min_change or stock.amount < min_amount:
                continue
            volume_ratio = random.uniform(1.5, 4.0)
            if volume_ratio < min_ratio:
                continue

            volume_score = min(volume_ratio / min_ratio * 20, 40)
            change_score = min(stock.change_pct * 10, 30)
            amount_score = min(stock.amount / max_amount * 30, 30)
            score = round(volume_score + change_score + amount_score, 1)

            signals = []
            sfx = "「放量」"
            if volume_ratio >= 3.0:
                signals.append("巨量突破" + sfx)
            elif volume_ratio >= 2.0:
                signals.append("温和放量" + sfx)
            if stock.change_pct >= 5.0:
                signals.append("强势上涨" + sfx)
            elif stock.change_pct >= 3.0:
                signals.append("大幅上涨" + sfx)

            results.append(ScanResult(
                symbol=stock.symbol,
                name=stock.name,
                strategy=StrategyType.VOLUME_SURGE,
                score=score,
                signals=signals,
                data=stock,
                metadata={"volume_ratio": round(volume_ratio, 2)}
            ))

        results.sort(key=lambda x: x.score, reverse=True)
        return results

    def _execute_turnover_rank(self, market_data, params) -> List[ScanResult]:
        """成交额排名策略"""
        cfg = params.get("turnover_rank", {}) if params else {}
        top_n = cfg.get("top_n", 20)
        min_amount = cfg.get("min_amount", 500_000_000)

        sorted_stocks = sorted(market_data, key=lambda x: x.amount, reverse=True)
        top_stocks = [s for s in sorted_stocks[:top_n] if s.amount >= min_amount]

        results = []
        max_amount = max((s.amount for s in top_stocks), default=1)

        for rank, stock in enumerate(top_stocks, 1):
            rank_score = max(50 - (rank - 1) * 2.5, 10)
            amount_score = (stock.amount / max_amount) * 30
            change_score = min(max(stock.change_pct, 0) * 5, 20)
            score = round(rank_score + amount_score + change_score, 1)

            signals = []
            sfx = "「成交额」"
            if rank <= 5:
                signals.append("成交额TOP5" + sfx)
            elif rank <= 10:
                signals.append("成交活跃" + sfx)
            if stock.change_pct > 0:
                signals.append("资金净流入" + sfx)

            results.append(ScanResult(
                symbol=stock.symbol,
                name=stock.name,
                strategy=StrategyType.TURNOVER_RANK,
                score=score,
                signals=signals,
                data=stock,
                metadata={"rank": rank, "amount": stock.amount}
            ))

        return results

    def _execute_multi_factor(self, market_data, params) -> List[ScanResult]:
        """多因子策略"""
        cfg = params.get("multi_factor", {}) if params else {}
        v_weight = cfg.get("volume_weight", 0.25)
        p_weight = cfg.get("price_weight", 0.25)
        t_weight = cfg.get("turnover_weight", 0.25)
        tech_weight = cfg.get("tech_weight", 0.25)
        min_score = cfg.get("min_score", 50)

        max_amount = max((s.amount for s in market_data), default=1)
        max_change = max((abs(s.change_pct) for s in market_data), default=1) or 1

        results = []
        for stock in market_data:
            factors = {
                "volume": (stock.amount / max_amount) * 100,
                "price": max(0, min(stock.change_pct / max_change * 100, 100)),
                "turnover": min(stock.turn_rate * 10, 100),
                "technical": random.uniform(60, 90),
            }
            total = (
                factors["volume"] * v_weight +
                factors["price"] * p_weight +
                factors["turnover"] * t_weight +
                factors["technical"] * tech_weight
            )
            if total < min_score:
                continue

            signals = []
            sfx = "「多因子」"
            if factors["volume"] >= 80:
                signals.append("量能充沛" + sfx)
            if factors["price"] >= 80:
                signals.append("涨幅领先" + sfx)

            results.append(ScanResult(
                symbol=stock.symbol,
                name=stock.name,
                strategy=StrategyType.MULTI_FACTOR,
                score=round(total, 1),
                signals=signals,
                data=stock,
                metadata={"factors": {k: round(v, 1) for k, v in factors.items()}}
            ))

        results.sort(key=lambda x: x.score, reverse=True)
        return results

    def _execute_ai_technical(self, market_data, params) -> List[ScanResult]:
        """AI技术面策略（模拟）"""
        cfg = params.get("ai_technical", {}) if params else {}
        threshold = cfg.get("pattern_threshold", 0.75) * 100

        results = []
        for stock in market_data:
            pattern_score = random.uniform(60, 95)
            trend_score = random.uniform(55, 90)

            if stock.change_pct > 2:
                pattern_score += 5
            if stock.volume > 50_000_000:
                pattern_score += 3
            if stock.change_pct > 0:
                trend_score += 5

            pattern_score = min(pattern_score, 100)
            trend_score = min(trend_score, 100)
            total_score = pattern_score * 0.5 + trend_score * 0.5

            if total_score < threshold:
                continue

            signals = []
            sfx = "「AI技术」"
            if pattern_score >= 85:
                signals.append("AI形态突破" + sfx)
            elif pattern_score >= 75:
                signals.append("AI形态良好" + sfx)
            if trend_score >= 80:
                signals.append("上升趋势确认" + sfx)

            results.append(ScanResult(
                symbol=stock.symbol,
                name=stock.name,
                strategy=StrategyType.AI_TECHNICAL,
                score=round(total_score, 1),
                signals=signals,
                data=stock,
                metadata={
                    "pattern_score": round(pattern_score, 1),
                    "trend_score": round(trend_score, 1),
                }
            ))

        results.sort(key=lambda x: x.score, reverse=True)
        return results

    def _execute_institution(self, market_data, params) -> List[ScanResult]:
        """机构追踪策略（模拟）"""
        cfg = params.get("institution", {}) if params else {}
        min_count = cfg.get("min_inst_count", 3)
        min_ratio = cfg.get("min_inst_ratio", 0.05)

        results = []
        for stock in market_data:
            inst_count = random.randint(1, 10)
            inst_ratio = random.uniform(0.02, 0.15)
            inst_change = random.uniform(-5, 10)

            if inst_count < min_count or inst_ratio < min_ratio:
                continue

            count_score = min(inst_count * 3, 30)
            ratio_score = min(inst_ratio * 200, 30)
            change_score = max(10 + inst_change * 2, 0) if inst_change > 0 else max(10 + inst_change, 0)
            price_score = min(max(stock.change_pct * 4, 0), 20)
            score = round(count_score + ratio_score + change_score + price_score, 1)

            signals = []
            sfx = "「机构」"
            if inst_count >= 7:
                signals.append("多家机构重仓" + sfx)
            elif inst_count >= 4:
                signals.append("机构关注" + sfx)
            if inst_change >= 5:
                signals.append("机构大幅增持" + sfx)
            elif inst_change >= 2:
                signals.append("机构温和增持" + sfx)

            results.append(ScanResult(
                symbol=stock.symbol,
                name=stock.name,
                strategy=StrategyType.INSTITUTION,
                score=score,
                signals=signals,
                data=stock,
                metadata={
                    "inst_count": inst_count,
                    "inst_ratio": round(inst_ratio * 100, 2),
                    "inst_change": round(inst_change, 2),
                }
            ))

        results.sort(key=lambda x: x.score, reverse=True)
        return results

    # ─────────────────────────────────────────────
    # 综合评分计算
    # ─────────────────────────────────────────────

    def _calculate_composite_scores(
        self,
        sub_results: Dict[str, Dict[str, ScanResult]],
        weights: Dict[str, float]
    ) -> Dict[str, float]:
        """计算每只股票的综合评分 = Σ(子策略评分 × 权重)"""
        scores = {}
        for symbol, strategies in sub_results.items():
            total, total_weight = 0.0, 0.0
            for sname, result in strategies.items():
                w = weights.get(sname, 0.0)
                total += min(result.score, 100) * w
                total_weight += w
            if total_weight > 0:
                scores[symbol] = round(total / total_weight, 2)
        return scores

    # ─────────────────────────────────────────────
    # 基本面过滤（可选，默认关闭）
    # ─────────────────────────────────────────────

    def _apply_fundamental_filter(
        self,
        stock_scores: Dict[str, float],
        params: Dict[str, Any]
    ) -> List[str]:
        """
        应用基本面筛选，返回通过的股票代码列表

        当前版本：数据层已过滤 ST/停牌股，
        此函数仅做可选的 PE/PB 过滤（需要配置第三方数据源）。

        配置（configs/settings.yaml）：
        ```yaml
        fundamental_filter:
          enable: false   # 默认关闭（当前无可靠PE/PB数据源）
          max_pe: 100
          max_pb: 10
          min_market_cap: 3e9  # 30亿
        ```
        """
        composite = params.get("composite_strategy", {}) if params else {}
        ff = params.get("fundamental_filter", {}) if params else {}

        enable = ff.get("enable", False)

        if not enable:
            self.logger.info("基本面过滤已关闭（enable=false），保留所有股票")
            return list(stock_scores.keys())

        max_pe = ff.get("max_pe", 100)
        max_pb = ff.get("max_pb", 10)
        min_cap = ff.get("min_market_cap", 3e9)

        passed = []
        for symbol in stock_scores:
            # TODO: 从可靠数据源获取 PE/PB/市值
            # 当前使用模拟数据（仅演示）
            pe = random.uniform(5, 150)
            pb = random.uniform(0.5, 15)
            cap = random.uniform(1e9, 1e11)

            if 0 < pe <= max_pe and 0 < pb <= max_pb and cap >= min_cap:
                passed.append(symbol)

        self.logger.info(
            f"基本面过滤: PE≤{max_pe}, PB≤{max_pb}, "
            f"市值≥{min_cap/1e8:.0f}亿 → 通过 {len(passed)} 只"
        )
        return passed if passed else list(stock_scores.keys())

    # ─────────────────────────────────────────────
    # 生成最终结果
    # ─────────────────────────────────────────────

    def _generate_results(
        self,
        filtered_symbols: List[str],
        stock_scores: Dict[str, float],
        sub_results: Dict[str, Dict[str, ScanResult]]
    ) -> List[ScanResult]:
        """将综合评分转换为 ScanResult 列表"""
        results = []
        for symbol in filtered_symbols:
            if symbol not in stock_scores:
                continue
            score = stock_scores[symbol]

            all_signals = []
            strategy_count = 0
            for sname, result in sub_results.get(symbol, {}).items():
                all_signals.extend(result.signals)
                strategy_count += 1

            metadata = {
                "composite_score": score,
                "strategy_count": strategy_count,
            }
            for sname, result in sub_results.get(symbol, {}).items():
                metadata[f"{sname}_score"] = result.score

            results.append(ScanResult(
                symbol=symbol,
                name=next((r.data.name for r in sub_results.get(symbol, {}).values() if r.data), symbol),
                strategy=StrategyType.COMPOSITE,
                score=score,
                signals=list(set(all_signals))[:5],
                data=next((r.data for r in sub_results.get(symbol, {}).values() if r.data), None),
                metadata=metadata
            ))
        return results
