"""
启动指纹策略

基于向量化指标和指纹挖掘结果进行选股，
使用启动前兆指纹预测上涨，顶部预警指纹识别回调风险。
"""
from typing import List, Dict, Any
import logging
import json
import os

from ..base import BaseStrategy
from ...core.types import StockData, ScanResult, StrategyType

sys_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if sys_path not in __import__('sys').path:
    __import__('sys').path.insert(0, sys_path)

try:
    from backtest.vectorized_indicator_extractor import (
        fetch_kline_from_tencent,
        calculate_vectorized_indicators,
        generate_tags,
        match_fingerprints,
        calculate_pullback_probability,
    )
except ImportError:
    fetch_kline_from_tencent = None
    calculate_vectorized_indicators = None
    generate_tags = None
    match_fingerprints = None
    calculate_pullback_probability = None


class LaunchFingerprintStrategy(BaseStrategy):
    """启动指纹策略"""

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("AInvest.LaunchFingerprint")
        self._indicators: Dict[str, Dict[str, float]] = {}
        self._kline_cache: Dict[str, List[StockData]] = {}
        self.fingerprints = None
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        self.fingerprint_path = os.path.join(base_dir, "fingerprints_280symbols.json")
        self._kline_cache: Dict[str, Any] = {}  # 由聚合层注入（KlineFetcher 统一缓存，含末根实时刷新）
        self._load_fingerprints()

    @property
    def name(self) -> str:
        return "启动指纹"

    @property
    def strategy_type(self) -> StrategyType:
        return StrategyType.LAUNCH_FINGERPRINT

    def _load_fingerprints(self):
        """加载指纹文件"""
        if os.path.exists(self.fingerprint_path):
            try:
                with open(self.fingerprint_path, "r", encoding="utf-8") as f:
                    self.fingerprints = json.load(f)
                self.logger.info(f"加载指纹成功: {len(self.fingerprints.get('launch_fingerprints', []))}个启动指纹, "
                               f"{len(self.fingerprints.get('top_fingerprints', []))}个顶部指纹")
            except Exception as e:
                self.logger.error(f"加载指纹失败: {e}")
                self.fingerprints = None
        else:
            self.logger.warning("指纹文件不存在，使用默认规则")

    def execute(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> List[ScanResult]:
        if fetch_kline_from_tencent is None:
            return self._execute_with_shared_indicators(market_data, params)

        cfg = params.get("launch_fingerprint", {}) if params else {}
        min_score = cfg.get("min_score", 40)
        source = cfg.get("source", "sina")
        max_pullback_prob = cfg.get("max_pullback_prob", 60)

        results = []
        for stock in market_data:
            try:
                # 修复E: 优先使用聚合层注入的统一K线缓存（KlineFetcher 磁盘缓存 + 末根实时刷新），
                # 避免每次冗余联网拉取，并与其他子策略保持数据一致；缓存未命中时回退原接口
                klines = self._kline_cache.get(stock.symbol) if getattr(self, '_kline_cache', None) else None
                if not klines or len(klines) < 60:
                    if fetch_kline_from_tencent is not None:
                        klines = fetch_kline_from_tencent(stock.symbol, days=120, source=source)
                if not klines or len(klines) < 60:
                    continue

                indicators = calculate_vectorized_indicators(klines)
                tags_data = generate_tags(klines)

                if indicators["features"]:
                    last_features = indicators["features"][-1]
                    feature_names = indicators["feature_names"]

                    recent_change = 0
                    if len(indicators["features"]) >= 5:
                        recent_change = last_features[0] - indicators["features"][-5][0]

                    pullback_info = calculate_pullback_probability(last_features, feature_names, recent_change)

                    launch_score = self._calculate_launch_score(last_features, feature_names, klines)

                    matched_fps = []
                    if self.fingerprints and tags_data["daily_tags"]:
                        matched_fps = match_fingerprints(tags_data, self.fingerprints.get("launch_fingerprints", []))

                    signals = []
                    if launch_score >= min_score:
                        signals.append(f"启动评分:{launch_score}")
                        if pullback_info["probability"] < max_pullback_prob:
                            signals.append("回调风险低")
                        else:
                            signals.append(f"回调风险高({pullback_info['level']})")

                    if matched_fps:
                        for fp in matched_fps:
                            signals.append(f"指纹命中:{'+'.join(fp['fingerprint'])}")

                    if signals:
                        results.append(ScanResult(
                            symbol=stock.symbol,
                            name=stock.name,
                            strategy=StrategyType.LAUNCH_FINGERPRINT,
                            score=round(launch_score, 1),
                            signals=signals,
                            data=stock,
                            metadata={
                                "pullback_prob": pullback_info["probability"],
                                "pullback_level": pullback_info["level"],
                                "pullback_warning": pullback_info["warning"],
                                "matched_fingerprints": [fp["fingerprint"] for fp in matched_fps],
                                "recent_change": round(recent_change, 2),
                            }
                        ))
            except Exception as e:
                self.logger.error(f"处理{stock.symbol}时出错: {e}")

        results.sort(key=lambda x: x.score, reverse=True)
        return results

    def _execute_with_shared_indicators(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> List[ScanResult]:
        cfg = params.get("launch_fingerprint", {}) if params else {}
        min_score = cfg.get("min_score", 40)
        max_pullback_prob = cfg.get("max_pullback_prob", 60)
        results: List[ScanResult] = []

        for stock in market_data:
            indicators = self._indicators.get(stock.symbol, {})
            if not indicators:
                continue

            volume_ratio = indicators.get("volume_ratio", 1.0)
            pos_20d = indicators.get("position_20d", 50)
            rsi14 = indicators.get("rsi14", 50)
            breakout = (
                indicators.get("breakout_20d_high", False)
                or indicators.get("breakout_60d_high", False)
                or indicators.get("breakout_20d", False)
                or indicators.get("breakout_60d", False)
            )
            pullback_confirm = indicators.get("pullback_confirm", False)
            ma_support = indicators.get("ma_support", False) or indicators.get("ma5_turning_up", False)

            score = 0.0
            signals = []
            if breakout:
                score += 25
                signals.append("突破指纹")
            if volume_ratio >= 2.0:
                score += 25
                signals.append(f"放量指纹:{volume_ratio:.1f}x")
            elif volume_ratio >= 1.3:
                score += 12
                signals.append(f"温和放量:{volume_ratio:.1f}x")
            if 45 <= rsi14 <= 70:
                score += 15
                signals.append(f"RSI启动区:{rsi14:.0f}")
            if pos_20d < 70:
                score += 15
                signals.append("位置未过热")
            if pullback_confirm or ma_support:
                score += 20
                signals.append("回踩确认")

            pullback_prob = max(0, min(100, pos_20d + max(stock.change_pct, 0) * 3))
            if pullback_prob > max_pullback_prob:
                signals.append("回调风险偏高")

            if score >= min_score:
                results.append(ScanResult(
                    symbol=stock.symbol,
                    name=stock.name,
                    strategy=StrategyType.LAUNCH_FINGERPRINT,
                    score=round(min(score, 100), 1),
                    signals=signals,
                    data=stock,
                    metadata={
                        "fallback": "shared_indicators",
                        "pullback_prob": round(pullback_prob, 1),
                        "volume_ratio": round(volume_ratio, 2),
                        "position_20d": round(pos_20d, 1),
                    },
                ))

        results.sort(key=lambda x: x.score, reverse=True)
        return results

    def _calculate_launch_score(self, features, feature_names, klines):
        score = 0

        if features[9] == 1:
            score += 20

        if features[10] == 1:
            score += 15

        if features[7] > 1.3:
            score += 15
        elif features[7] > 1.0:
            score += 5

        if features[8] > 50 and features[8] < 70:
            score += 10
        elif features[8] >= 70:
            score += 5

        if features[0] > 5:
            score += 15
        elif features[0] > 2:
            score += 5

        if features[6] < 50:
            score += 10

        if features[11] == 1:
            score += 10

        if features[7] > 2.0:
            score += 10

        if features[15] >= 3:
            score += 5

        if len(features) > 23 and features[23] == 1:
            score += 15

        if len(features) > 24 and features[24] < 30:
            score += 10

        return min(score, 100)
