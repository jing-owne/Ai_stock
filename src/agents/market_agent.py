"""
市场分析Agent
负责分析整体市场状态和情绪
"""
import logging
import random
from typing import List, Dict, Any
from collections import defaultdict

from ..core.types import StockData, MarketAnalysis
from ..core.config import Config


class MarketAgent:
    """
    市场分析Agent
    
    分析市场情绪、板块热度、风险等级等
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger("AInvest.MarketAgent")
        
    def analyze(self, market_data: List[StockData]) -> MarketAnalysis:
        """
        分析市场状态
        
        Args:
            market_data: 市场股票数据
            
        Returns:
            MarketAnalysis市场分析报告
        """
        self.logger.info("开始市场分析...")
        
        # 计算市场统计
        total_stocks = len(market_data)
        rising_stocks = sum(1 for s in market_data if s.change_pct > 0)
        falling_stocks = sum(1 for s in market_data if s.change_pct < 0)
        
        # 计算涨跌比
        rise_ratio = rising_stocks / total_stocks if total_stocks > 0 else 0.5
        
        # 确定市场情绪
        if rise_ratio > 0.6:
            sentiment = "乐观"
        elif rise_ratio > 0.4:
            sentiment = "中性"
        else:
            sentiment = "悲观"
        
        # 分析板块热度
        sector_heat = self._analyze_sector_heat(market_data)
        
        # 评估风险等级
        risk_level = self._evaluate_risk_level(market_data, rise_ratio)
        
        # 生成建议
        recommendations = self._generate_recommendations(
            sentiment, sector_heat, risk_level
        )
        
        # 生成总结
        summary = self._generate_summary(
            sentiment, rising_stocks, falling_stocks, risk_level
        )
        
        return MarketAnalysis(
            date=market_data[0].date if market_data else "",
            market_sentiment=sentiment,
            sector_heat=sector_heat,
            risk_level=risk_level,
            recommendations=recommendations,
            summary=summary
        )
    
    def _analyze_sector_heat(self, market_data: List[StockData]) -> Dict[str, float]:
        """分析板块热度"""
        # 简化的板块分析
        sectors = {
            "新能源": 0.85,
            "消费": 0.72,
            "科技": 0.68,
            "医药": 0.55,
            "金融": 0.45,
            "地产": 0.30,
        }
        return sectors
    
    def _evaluate_risk_level(
        self,
        market_data: List[StockData],
        rise_ratio: float
    ) -> str:
        """评估风险等级"""
        # 计算平均波动
        avg_volatility = sum(abs(s.change_pct) for s in market_data) / len(market_data)
        
        if avg_volatility > 3 or rise_ratio < 0.35:
            return "高"
        elif avg_volatility > 1.5:
            return "中"
        else:
            return "低"
    
    def _generate_recommendations(
        self,
        sentiment: str,
        sector_heat: Dict[str, float],
        risk_level: str
    ) -> List[str]:
        """生成投资建议"""
        recommendations = []
        
        # 情绪建议
        if sentiment == "乐观":
            recommendations.append("市场情绪较好，可适当增配股票仓位")
            recommendations.append("关注突破新高的强势股")
        elif sentiment == "悲观":
            recommendations.append("建议控制仓位，谨慎操作")
            recommendations.append("关注防御性板块如医药、消费")
        else:
            recommendations.append("市场分化，精选个股为主")
        
        # 板块建议
        hot_sectors = [s for s, h in sector_heat.items() if h > 0.7]
        if hot_sectors:
            recommendations.append(f"热点板块: {', '.join(hot_sectors)}")
        
        # 风险建议
        if risk_level == "高":
            recommendations.append("注意控制仓位，防范回调风险")
        
        return recommendations
    
    def _generate_summary(
        self,
        sentiment: str,
        rising: int,
        falling: int,
        risk_level: str
    ) -> str:
        """生成市场总结"""
        total = rising + falling
        
        return (
            f"今日市场{sentiment}，涨跌股票比{rising}:{falling}。"
            f"市场风险{risk_level}等级。"
            f"建议投资者密切关注热点板块轮动，控制仓位风险。"
        )
