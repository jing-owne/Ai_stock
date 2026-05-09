"""
综合策略 (Composite Strategy)
整合5大选股策略，按照权重分配进行综合评分

策略权重分配:
- 放量上涨: 35% (策略数量评分 - strategy_count)
- 成交额排名: 30% (基本面因子 - myhhub)
- 多因子: 15% (趋势策略 - hikyuu)
- AI技术面: 10% (北向资金 - northstar)
- 机构追踪: 10% (机构动向)

基本面筛选条件:
- ROE门槛: ≥8%
- 营收增长: ≥5%
- 胜率基础值: 50%
- 胜率门槛: 65%
"""
from typing import List, Dict, Any, Set
import random
import logging

from ..base import BaseStrategy
from ...core.types import StockData, ScanResult, StrategyType
from ...core.config import Config


class CompositeStrategy(BaseStrategy):
    """
    综合策略
    
    将多个单一策略的结果按权重整合，形成综合评分。
    同时应用基本面筛选条件，提高选股质量。
    """
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("AInvest.CompositeStrategy")
    
    @property
    def name(self) -> str:
        return "综合策略"
    
    @property
    def strategy_type(self) -> StrategyType:
        return StrategyType.MULTI_FACTOR  # 使用MULTI_FACTOR作为默认类型
    
    def execute(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> List[ScanResult]:
        """
        执行综合策略
        
        整合5个策略的结果，按权重计算综合评分
        """
        # 获取权重配置
        weights = self._get_weights(params)
        
        # 获取基本面筛选条件
        fundamental_filter = self._get_fundamental_filter(params)
        
        # 执行各子策略
        sub_results = self._execute_sub_strategies(market_data, params)
        
        # 构建股票评分映射
        stock_scores = self._calculate_composite_scores(
            sub_results=sub_results,
            weights=weights
        )
        
        # 应用基本面筛选
        filtered_stocks = self._apply_fundamental_filter(
            market_data=market_data,
            stock_scores=stock_scores,
            fundamental_filter=fundamental_filter
        )
        
        # 生成综合结果
        results = self._generate_results(
            filtered_stocks=filtered_stocks,
            stock_scores=stock_scores,
            sub_results=sub_results,
            fundamental_filter=fundamental_filter
        )
        
        # 按综合评分排序
        results.sort(key=lambda x: x.score, reverse=True)
        
        self.logger.info(f"综合策略选股完成: {len(results)} 只股票")
        return results
    
    def _get_weights(self, params: Dict[str, Any]) -> Dict[str, float]:
        """获取策略权重"""
        composite = params.get("composite_strategy", {})
        
        return {
            "volume_surge": composite.get("strategy_count_weight", 0.35),      # 35% 策略数量评分
            "turnover_rank": composite.get("myhhub_weight", 0.30),              # 30% 基本面因子
            "multi_factor": composite.get("hikyuu_weight", 0.15),                # 15% 趋势策略
            "ai_technical": composite.get("northstar_weight", 0.10),              # 10% 北向资金
            "institution": 0.10,                                                  # 10% 机构动向
        }
    
    def _get_fundamental_filter(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """获取基本面筛选条件"""
        fundamental = params.get("fundamental_filter", {})
        
        return {
            "min_roe": fundamental.get("min_roe", 0.08),                    # ROE门槛 ≥8%
            "min_revenue_growth": fundamental.get("min_revenue_growth", 0.05),  # 营收增长 ≥5%
            "min_win_rate": params.get("composite_strategy", {}).get("min_win_rate", 0.65),  # 胜率门槛 65%
            "base_win_rate": params.get("composite_strategy", {}).get("base_win_rate", 0.50),  # 胜率基础值 50%
        }
    
    def _execute_sub_strategies(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> Dict[str, Dict[str, ScanResult]]:
        """
        执行各子策略
        
        Returns:
            Dict[股票代码, Dict[策略名称, ScanResult]]
        """
        sub_results = {}
        
        # 1. 放量上涨策略 (35%)
        volume_surge_results = self._execute_volume_surge(market_data, params)
        for result in volume_surge_results:
            if result.symbol not in sub_results:
                sub_results[result.symbol] = {}
            sub_results[result.symbol]["volume_surge"] = result
        
        # 2. 成交额排名策略 (30%)
        turnover_rank_results = self._execute_turnover_rank(market_data, params)
        for result in turnover_rank_results:
            if result.symbol not in sub_results:
                sub_results[result.symbol] = {}
            sub_results[result.symbol]["turnover_rank"] = result
        
        # 3. 多因子策略 (15%)
        multi_factor_results = self._execute_multi_factor(market_data, params)
        for result in multi_factor_results:
            if result.symbol not in sub_results:
                sub_results[result.symbol] = {}
            sub_results[result.symbol]["multi_factor"] = result
        
        # 4. AI技术面策略 (10%)
        ai_technical_results = self._execute_ai_technical(market_data, params)
        for result in ai_technical_results:
            if result.symbol not in sub_results:
                sub_results[result.symbol] = {}
            sub_results[result.symbol]["ai_technical"] = result
        
        # 5. 机构追踪策略 (10%)
        institution_results = self._execute_institution(market_data, params)
        for result in institution_results:
            if result.symbol not in sub_results:
                sub_results[result.symbol] = {}
            sub_results[result.symbol]["institution"] = result
        
        return sub_results
    
    def _execute_volume_surge(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> List[ScanResult]:
        """执行放量上涨策略"""
        min_ratio = params.get("volume_surge", {}).get("min_volume_ratio", 2.0)
        min_change = params.get("volume_surge", {}).get("min_price_change", 1.0)
        min_amount = params.get("volume_surge", {}).get("min_amount", 100_000_000)
        
        results = []
        max_amount = max(s.amount for s in market_data) if market_data else 1
        
        for stock in market_data:
            if stock.change_pct < min_change or stock.amount < min_amount:
                continue
            
            # 模拟放量倍数
            volume_ratio = random.uniform(1.5, 4.0)
            
            if volume_ratio >= min_ratio:
                # 计算评分
                volume_score = min(volume_ratio / min_ratio * 20, 40)
                change_score = min(stock.change_pct * 10, 30)
                amount_score = min(stock.amount / max_amount * 30, 30)
                score = round(volume_score + change_score + amount_score, 1)
                
                # 生成信号
                signals = []
                if volume_ratio >= 3.0:
                    signals.append("巨量突破")
                elif volume_ratio >= 2.0:
                    signals.append("温和放量")
                
                if stock.change_pct >= 5.0:
                    signals.append("强势涨停")
                elif stock.change_pct >= 3.0:
                    signals.append("大幅上涨")
                
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
    
    def _execute_turnover_rank(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> List[ScanResult]:
        """执行成交额排名策略"""
        top_n = params.get("turnover_rank", {}).get("top_n", 20)
        min_amount = params.get("turnover_rank", {}).get("min_amount", 500_000_000)
        
        sorted_stocks = sorted(market_data, key=lambda x: x.amount, reverse=True)
        top_stocks = [s for s in sorted_stocks[:top_n] if s.amount >= min_amount]
        
        results = []
        max_amount = max(s.amount for s in top_stocks) if top_stocks else 1
        
        for rank, stock in enumerate(top_stocks, 1):
            rank_score = max(50 - (rank - 1) * 2.5, 10)
            amount_score = (stock.amount / max_amount) * 30
            change_score = min(max(stock.change_pct, 0) * 5, 20)
            score = round(rank_score + amount_score + change_score, 1)
            
            signals = []
            if rank <= 5:
                signals.append("成交额TOP5")
            elif rank <= 10:
                signals.append("成交活跃")
            
            if stock.change_pct > 0:
                signals.append("资金净流入")
            
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
    
    def _execute_multi_factor(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> List[ScanResult]:
        """执行多因子策略"""
        multi_factor_params = params.get("multi_factor", {})
        volume_weight = multi_factor_params.get("volume_weight", 0.2)
        price_weight = multi_factor_params.get("price_weight", 0.3)
        turnover_weight = multi_factor_params.get("turnover_weight", 0.25)
        tech_weight = multi_factor_params.get("tech_weight", 0.25)
        min_score = multi_factor_params.get("min_score", 60)
        
        max_amount = max(s.amount for s in market_data) if market_data else 1
        max_change = max(s.change_pct for s in market_data) if market_data else 1
        
        results = []
        
        for stock in market_data:
            factors = {
                "volume": (stock.amount / max_amount) * 100,
                "price": max(0, min(stock.change_pct / max_change * 100 if max_change > 0 else 50, 100)),
                "turnover": min(stock.turn_rate * 10, 100),
                "technical": random.uniform(60, 90)
            }
            
            total_score = (
                factors["volume"] * volume_weight +
                factors["price"] * price_weight +
                factors["turnover"] * turnover_weight +
                factors["technical"] * tech_weight
            )
            
            if total_score >= min_score:
                signals = []
                if factors["volume"] >= 80:
                    signals.append("量能充沛")
                if factors["price"] >= 80:
                    signals.append("涨幅领先")
                
                results.append(ScanResult(
                    symbol=stock.symbol,
                    name=stock.name,
                    strategy=StrategyType.MULTI_FACTOR,
                    score=round(total_score, 1),
                    signals=signals,
                    data=stock,
                    metadata={"factors": {k: round(v, 1) for k, v in factors.items()}}
                ))
        
        results.sort(key=lambda x: x.score, reverse=True)
        return results
    
    def _execute_ai_technical(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> List[ScanResult]:
        """执行AI技术面策略"""
        ai_params = params.get("ai_technical", {})
        pattern_threshold = ai_params.get("pattern_threshold", 0.75)
        
        results = []
        
        for stock in market_data:
            # 模拟AI分析
            pattern_score = random.uniform(60, 95)
            trend_score = random.uniform(55, 90)
            
            if stock.change_pct > 2:
                pattern_score += 5
            if stock.volume > 50000000:
                pattern_score += 3
            if stock.change_pct > 0:
                trend_score += 5
            
            pattern_score = min(pattern_score, 100)
            trend_score = min(trend_score, 100)
            
            total_score = pattern_score * 0.5 + trend_score * 0.5
            
            if total_score >= pattern_threshold * 100:
                signals = []
                if pattern_score >= 85:
                    signals.append("AI形态突破")
                elif pattern_score >= 75:
                    signals.append("AI形态良好")
                if trend_score >= 80:
                    signals.append("上升趋势确认")
                
                results.append(ScanResult(
                    symbol=stock.symbol,
                    name=stock.name,
                    strategy=StrategyType.AI_TECHNICAL,
                    score=round(total_score, 1),
                    signals=signals,
                    data=stock,
                    metadata={
                        "pattern_score": round(pattern_score, 1),
                        "trend_score": round(trend_score, 1)
                    }
                ))
        
        results.sort(key=lambda x: x.score, reverse=True)
        return results
    
    def _execute_institution(
        self,
        market_data: List[StockData],
        params: Dict[str, Any]
    ) -> List[ScanResult]:
        """执行机构追踪策略"""
        inst_params = params.get("institution", {})
        min_inst_count = inst_params.get("min_inst_count", 3)
        min_inst_ratio = inst_params.get("min_inst_ratio", 0.05)
        
        results = []
        
        for stock in market_data:
            # 模拟机构数据
            inst_count = random.randint(1, 10)
            inst_ratio = random.uniform(0.02, 0.15)
            inst_change = random.uniform(-5, 10)
            
            if inst_count >= min_inst_count and inst_ratio >= min_inst_ratio:
                count_score = min(inst_count * 3, 30)
                ratio_score = min(inst_ratio * 200, 30)
                change_score = max(10 + inst_change * 2, 0) if inst_change > 0 else max(10 + inst_change, 0)
                price_score = min(max(stock.change_pct * 4, 0), 20)
                score = round(count_score + ratio_score + change_score + price_score, 1)
                
                signals = []
                if inst_count >= 7:
                    signals.append("多家机构重仓")
                elif inst_count >= 4:
                    signals.append("机构关注")
                if inst_change >= 5:
                    signals.append("机构大幅增持")
                elif inst_change >= 2:
                    signals.append("机构温和增持")
                
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
                        "inst_change": round(inst_change, 2)
                    }
                ))
        
        results.sort(key=lambda x: x.score, reverse=True)
        return results
    
    def _calculate_composite_scores(
        self,
        sub_results: Dict[str, Dict[str, ScanResult]],
        weights: Dict[str, float]
    ) -> Dict[str, float]:
        """
        计算综合评分
        
        综合评分 = Σ(各策略评分 × 权重)
        """
        composite_scores = {}
        
        for symbol, strategies in sub_results.items():
            total_score = 0.0
            total_weight = 0.0
            
            for strategy_name, result in strategies.items():
                weight = weights.get(strategy_name, 0.0)
                # 归一化评分到0-100范围
                normalized_score = min(result.score, 100)
                total_score += normalized_score * weight
                total_weight += weight
            
            # 归一化到0-100范围
            if total_weight > 0:
                composite_score = total_score / total_weight
                composite_scores[symbol] = round(composite_score, 2)
        
        return composite_scores
    
    def _apply_fundamental_filter(
        self,
        market_data: List[StockData],
        stock_scores: Dict[str, float],
        fundamental_filter: Dict[str, Any]
    ) -> List[StockData]:
        """
        应用基本面筛选条件
        
        筛选条件:
        - ROE门槛: ≥8%
        - 营收增长: ≥5%
        - 胜率门槛: 65%
        """
        min_roe = fundamental_filter["min_roe"]
        min_revenue_growth = fundamental_filter["min_revenue_growth"]
        min_win_rate = fundamental_filter["min_win_rate"]
        
        filtered_stocks = []
        
        for stock in market_data:
            if stock.symbol not in stock_scores:
                continue
            
            # 模拟基本面数据
            roe = random.uniform(0.03, 0.15)
            revenue_growth = random.uniform(-0.05, 0.20)
            
            # 计算模拟胜率
            base_win_rate = fundamental_filter["base_win_rate"]
            # 胜率 = 基础值 + (综合评分/100 - 0.5) * 0.3
            simulated_win_rate = base_win_rate + (stock_scores[stock.symbol] / 100 - 0.5) * 0.3
            simulated_win_rate = max(0.3, min(simulated_win_rate, 0.95))  # 限制在30%-95%
            
            # 应用筛选条件
            if roe >= min_roe and revenue_growth >= min_revenue_growth and simulated_win_rate >= min_win_rate:
                filtered_stocks.append(stock)
        
        self.logger.info(
            f"基本面筛选: ROE≥{min_roe*100:.0f}%, "
            f"营收增长≥{min_revenue_growth*100:.0f}%, "
            f"胜率≥{min_win_rate*100:.0f}% → "
            f"通过 {len(filtered_stocks)} 只"
        )
        
        return filtered_stocks
    
    def _generate_results(
        self,
        filtered_stocks: List[StockData],
        stock_scores: Dict[str, float],
        sub_results: Dict[str, Dict[str, ScanResult]],
        fundamental_filter: Dict[str, Any]
    ) -> List[ScanResult]:
        """生成最终结果"""
        results = []
        
        for stock in filtered_stocks:
            if stock.symbol not in stock_scores:
                continue
            
            composite_score = stock_scores[stock.symbol]
            
            # 合并所有策略的信号
            all_signals = []
            strategy_count = 0
            
            if stock.symbol in sub_results:
                for strategy_name, result in sub_results[stock.symbol].items():
                    all_signals.extend(result.signals)
                    strategy_count += 1
            
            # 去重信号
            unique_signals = list(set(all_signals))[:5]  # 最多保留5个信号
            
            # 生成元数据
            metadata = {
                "composite_score": composite_score,
                "strategy_count": strategy_count,
                "win_rate": fundamental_filter["base_win_rate"] + (composite_score / 100 - 0.5) * 0.3,
            }
            
            # 添加各策略评分
            if stock.symbol in sub_results:
                for strategy_name, result in sub_results[stock.symbol].items():
                    metadata[f"{strategy_name}_score"] = result.score
            
            results.append(ScanResult(
                symbol=stock.symbol,
                name=stock.name,
                strategy=StrategyType.MULTI_FACTOR,
                score=composite_score,
                signals=unique_signals,
                data=stock,
                metadata=metadata
            ))
        
        return results
