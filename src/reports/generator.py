"""
报告生成器
生成HTML、Markdown、JSON格式的报告
"""
from typing import List, Dict, Any, Optional
from datetime import datetime

from ..core.types import ScanResult, MarketAnalysis
from ..core.config import Config
from .formatter import ReportFormatter


class ReportGenerator:
    """
    报告生成器
    
    支持多种模板和格式
    """
    
    def __init__(self, template: str = "default", config: Optional[Config] = None):
        self.template = template
        self.config = config or Config()
        self.formatter = ReportFormatter()
    
    def generate(
        self,
        results: List[ScanResult],
        analysis: Optional[MarketAnalysis] = None,
        format: str = "html"
    ) -> str:
        """
        生成报告
        
        Args:
            results: 扫描结果
            analysis: 市场分析
            format: 输出格式
            
        Returns:
            报告内容
        """
        if format == "html":
            return self._generate_html(results, analysis)
        elif format == "markdown":
            return self._generate_markdown(results, analysis)
        elif format == "json":
            return self._generate_json(results, analysis)
        else:
            raise ValueError(f"不支持的格式: {format}")
    
    def _generate_html(
        self,
        results: List[ScanResult],
        analysis: Optional[MarketAnalysis]
    ) -> str:
        """生成HTML报告"""
        from .templates.report_template import get_html_template
        return get_html_template(results, analysis)
    
    def _generate_markdown(
        self,
        results: List[ScanResult],
        analysis: Optional[MarketAnalysis]
    ) -> str:
        """生成Markdown报告"""
        lines = [
            "# AInvest 股票扫描报告",
            "",
            f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]
        
        if analysis:
            lines.extend([
                "## 市场分析",
                "",
                f"- **市场情绪**: {analysis.market_sentiment}",
                f"- **风险等级**: {analysis.risk_level}",
                f"- **总结**: {analysis.summary}",
                "",
            ])
        
        lines.extend([
            "## 扫描结果",
            "",
            f"共发现 **{len(results)}** 只符合条件的股票:",
            "",
        ])
        
        for i, result in enumerate(results[:20], 1):
            signals = ", ".join(result.signals[:3])
            lines.append(
                f"{i}. **{result.name}** ({result.symbol}) - "
                f"评分: {result.score:.1f} - 信号: {signals}"
            )
        
        return "\n".join(lines)
    
    def _generate_json(
        self,
        results: List[ScanResult],
        analysis: Optional[MarketAnalysis]
    ) -> str:
        """生成JSON报告"""
        import json
        
        data = {
            "timestamp": datetime.now().isoformat(),
            "total_count": len(results),
            "results": [r.to_dict() for r in results],
        }
        
        if analysis:
            data["analysis"] = analysis.to_dict()
        
        return json.dumps(data, ensure_ascii=False, indent=2)
