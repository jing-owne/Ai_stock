"""
市场分析Agent
负责分析整体市场状态和情绪
"""
import logging
import requests
from typing import List, Dict, Any, Optional
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
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        })
        
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
        """分析板块热度 — 优先从东财接口获取真实数据，失败则从行情数据推算"""
        # 尝试从东财获取真实板块涨跌数据
        real_heat = self._fetch_real_sector_heat()
        if real_heat:
            return real_heat

        # 回退: 从行情数据按名称简单归类推算
        return self._estimate_sector_heat_from_data(market_data)

    def _fetch_real_sector_heat(self) -> Optional[Dict[str, float]]:
        """从东方财富获取真实板块涨跌数据"""
        try:
            url = "http://push2.eastmoney.com/api/qt/clist/get"
            params = {
                "pn": "1", "pz": "30", "po": "1", "np": "1",
                "ut": "b955e6154c27a7de8ee4dc42d7ba41cc",
                "fltt": "2", "invt": "2",
                "fid": "f3",
                "fs": "m:90+t:2",
                "fields": "f2,f3,f4,f12,f14",
            }
            resp = self._session.get(url, params=params, timeout=10)
            data = resp.json()
            items = data.get("data", {}).get("diff", [])

            if not items:
                return None

            heat = {}
            for item in items:
                name = item.get("f14", "")
                pct = item.get("f3", 0)
                # 将涨跌幅映射到0-1热度: 跌5%→0, 涨5%→1
                heat[name] = round(max(0, min(1, (pct + 5) / 10)), 2)

            return heat

        except Exception as e:
            self.logger.debug(f"获取板块数据失败: {e}")
            return None

    def _estimate_sector_heat_from_data(self, market_data: List[StockData]) -> Dict[str, float]:
        """从行情数据推算板块热度（无API数据时的回退方案）"""
        # 按涨跌幅分布推算整体热度
        if not market_data:
            return {"市场整体": 0.5}

        avg_pct = sum(s.change_pct for s in market_data) / len(market_data)
        heat = max(0, min(1, (avg_pct + 5) / 10))

        return {"市场整体": round(heat, 2)}
    
    def _evaluate_risk_level(
        self,
        market_data: List[StockData],
        rise_ratio: float
    ) -> str:
        """评估风险等级 — 基于波动率和涨跌比"""
        if not market_data:
            return "中"

        # 计算平均波动
        avg_volatility = sum(abs(s.change_pct) for s in market_data) / len(market_data)

        # 计算涨跌幅标准差（波动分散度）
        pcts = [s.change_pct for s in market_data]
        if len(pcts) > 1:
            import numpy as np
            std_pct = float(np.std(pcts))
        else:
            std_pct = avg_volatility

        if avg_volatility > 3 or rise_ratio < 0.35 or std_pct > 4:
            return "高"
        elif avg_volatility > 1.5 or std_pct > 2.5:
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
