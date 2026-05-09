"""
AInvest核心引擎
协调所有Agent和策略
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from .types import StockData, ScanResult, MarketAnalysis, StrategyType
from .config import Config
from ..agents.data_agent import DataAgent
from ..agents.strategy_agent import StrategyAgent
from ..agents.market_agent import MarketAgent
from ..agents.report_agent import ReportAgent


class AInvestEngine:
    """
    AInvest量化分析引擎
    
    协调数据采集、策略执行、市场分析和报告生成
    """
    
    def __init__(self, config: Optional[Config] = None):
        """
        初始化引擎
        
        Args:
            config: 配置对象，默认使用全局配置
        """
        self.config = config or Config()
        self.logger = self._setup_logger()
        
        # 初始化Agent
        self.data_agent = DataAgent(self.config)
        self.strategy_agent = StrategyAgent(self.config)
        self.market_agent = MarketAgent(self.config)
        self.report_agent = ReportAgent(self.config)
        
        self.logger.info("AInvest引擎初始化完成")
    
    def _setup_logger(self) -> logging.Logger:
        """配置日志"""
        logger = logging.getLogger("AInvest")
        logger.setLevel(getattr(logging, self.config.log_level))
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def scan(
        self,
        strategy: StrategyType,
        limit: int = 20,
        **kwargs
    ) -> List[ScanResult]:
        """
        执行股票扫描
        
        Args:
            strategy: 策略类型
            limit: 返回结果数量限制
            **kwargs: 传递给策略的额外参数
            
        Returns:
            ScanResult列表，按评分降序排列
        """
        self.logger.info(f"开始执行{strategy.value}策略扫描...")
        
        # 1. 数据采集
        market_data = self.data_agent.fetch_market_data()
        self.logger.info(f"获取市场数据: {len(market_data)}只股票")
        
        # 2. 策略执行
        results = self.strategy_agent.execute(strategy, market_data, **kwargs)
        self.logger.info(f"策略执行完成: {len(results)}个候选股票")
        
        # 3. 排序和筛选
        results.sort(key=lambda x: x.score, reverse=True)
        results = results[:limit]
        
        self.logger.info(f"扫描完成，返回{len(results)}个结果")
        return results
    
    def multi_strategy_scan(
        self,
        strategies: List[StrategyType],
        limit_per_strategy: int = 10
    ) -> Dict[StrategyType, List[ScanResult]]:
        """
        多策略并行扫描
        
        Args:
            strategies: 策略列表
            limit_per_strategy: 每个策略返回的结果数
            
        Returns:
            策略到结果列表的映射
        """
        self.logger.info(f"开始多策略扫描: {[s.value for s in strategies]}")
        
        results = {}
        for strategy in strategies:
            try:
                results[strategy] = self.scan(strategy, limit_per_strategy)
            except Exception as e:
                self.logger.error(f"策略{strategy.value}执行失败: {e}")
                results[strategy] = []
        
        return results
    
    def analyze_market(self) -> MarketAnalysis:
        """
        分析当前市场状态
        
        Returns:
            市场分析报告
        """
        self.logger.info("开始市场分析...")
        
        # 获取市场数据
        market_data = self.data_agent.fetch_market_data()
        
        # 执行市场分析
        analysis = self.market_agent.analyze(market_data)
        
        self.logger.info(f"市场分析完成: {analysis.market_sentiment}")
        return analysis
    
    def generate_report(
        self,
        results: List[ScanResult],
        analysis: Optional[MarketAnalysis] = None,
        format: str = "html"
    ) -> str:
        """
        生成分析报告
        
        Args:
            results: 扫描结果
            analysis: 市场分析(可选)
            format: 报告格式(html/markdown/json)
            
        Returns:
            报告文件路径
        """
        self.logger.info(f"生成{format}格式报告...")
        
        output_path = self.report_agent.generate(
            results=results,
            analysis=analysis,
            format=format
        )
        
        self.logger.info(f"报告已生成: {output_path}")
        return output_path
    
    def health_check(self) -> Dict[str, Any]:
        """
        健康检查
        
        Returns:
            健康状态字典
        """
        return {
            "status": "healthy",
            "version": "1.0.0",
            "timestamp": datetime.now().isoformat(),
            "config": {
                "log_level": self.config.log_level,
                "max_workers": self.config.max_workers,
                "data_provider": self.config.data_source.provider,
            }
        }
