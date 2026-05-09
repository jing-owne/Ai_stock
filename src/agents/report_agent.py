"""
报告生成Agent
负责生成各种格式的分析报告
"""
import os
import logging
from typing import List, Optional
from datetime import datetime
from pathlib import Path

from ..core.types import ScanResult, MarketAnalysis
from ..core.config import Config
from ..reports.generator import ReportGenerator
from ..reports.email_sender import EmailSender


class ReportAgent:
    """
    报告生成Agent
    
    支持HTML、Markdown、JSON格式报告，以及邮件发送
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger("AInvest.ReportAgent")
        
        # 确保输出目录存在
        output_dir = Path(config.report.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化邮件发送器
        self.email_sender = EmailSender(config.email)
        
    def generate(
        self,
        results: List[ScanResult],
        analysis: Optional[MarketAnalysis] = None,
        format: str = "html",
        template: Optional[str] = None
    ) -> str:
        """
        生成分析报告
        
        Args:
            results: 扫描结果
            analysis: 市场分析
            format: 报告格式 (html/markdown/json)
            template: 模板名称
            
        Returns:
            报告文件路径
        """
        self.logger.info(f"生成{format}格式报告...")
        
        template = template or self.config.report.template
        
        # 创建报告生成器
        generator = ReportGenerator(
            template=template,
            config=self.config
        )
        
        # 生成报告
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if format == "html":
            filename = f"scan_report_{timestamp}.html"
        elif format == "markdown":
            filename = f"scan_report_{timestamp}.md"
        elif format == "json":
            filename = f"scan_report_{timestamp}.json"
        else:
            raise ValueError(f"不支持的格式: {format}")
        
        output_path = Path(self.config.report.output_dir) / filename
        
        # 生成内容
        content = generator.generate(
            results=results,
            analysis=analysis,
            format=format
        )
        
        # 写入文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        self.logger.info(f"报告已保存: {output_path}")
        
        return str(output_path)
    
    def generate_summary(self, results: List[ScanResult]) -> str:
        """
        生成丰富的文本摘要（用于邮件发送）
        
        参考参考项目的邮件格式
        """
        from datetime import datetime
        
        lines = []
        today = datetime.now().strftime('%Y年%m月%d日')
        now = datetime.now().strftime('%H:%M:%S')
        
        # ==================== 报告标题 ====================
        lines.append("=" * 60)
        lines.append("【Marcus量化选股系统】")
        lines.append(f"报告日期: {today} {now}")
        lines.append("=" * 60)
        
        # ==================== 策略说明 ====================
        lines.append("")
        lines.append("-" * 60)
        lines.append("【策略说明】")
        lines.append("-" * 60)
        lines.append("• 放量上涨策略: 基于成交量突增筛选强势股票")
        lines.append("• 评分机制: 综合涨幅、成交额、量比等因素")
        lines.append("• 筛选条件: 放量倍数≥2.0, 涨幅≥1%, 成交额≥1亿")
        
        # ==================== 选股结果 ====================
        lines.append("")
        lines.append("-" * 60)
        lines.append("【股票选择】（按综合评分排序）")
        lines.append("-" * 60)
        
        if not results:
            lines.append("今日暂无符合条件的股票。")
        else:
            # 统计数据
            up_count = sum(1 for r in results if r.data and r.data.change_pct > 0)
            avg_change = sum(r.data.change_pct if r.data else 0 for r in results) / len(results) if results else 0
            total_amount = sum(r.data.amount if r.data else 0 for r in results)
            
            # 简要统计
            lines.append("")
            lines.append(f"• 共筛选出 {len(results)} 只优质股票")
            lines.append(f"• 其中 {up_count} 只上涨，{len(results) - up_count} 只下跌/平盘")
            lines.append(f"• 平均涨幅: {avg_change:+.2f}%")
            lines.append(f"• 总成交额: {total_amount/1e8:.2f}亿")
            lines.append("")
            
            # Top 10 详细列表
            lines.append("▶ Top 10 推荐股票")
            lines.append("")
            
            # 表头
            lines.append("序号 | 股票名称 | 代码 | 评分 | 涨幅 | 成交额 | 入选信号")
            lines.append("-" * 60)
            
            for i, result in enumerate(results[:10], 1):
                name = result.name
                symbol = result.symbol
                score = result.score
                signals = ", ".join(result.signals[:2])
                
                if result.data:
                    change_pct = result.data.change_pct
                    amount = result.data.amount
                    amount_str = f"{amount/1e8:.2f}亿" if amount >= 1e8 else f"{amount/1e4:.0f}万"
                    change_str = f"{change_pct:+.2f}%"
                else:
                    amount_str = "N/A"
                    change_str = "N/A"
                
                lines.append(f"{i} | {name} | {symbol} | {score:.1f} | {change_str} | {amount_str} | {signals}")
            
            # 更多股票概览
            if len(results) > 10:
                lines.append("")
                lines.append(f"• 还有 {len(results) - 10} 只备选股票（详见附件）")
        
        # ==================== 操作建议 ====================
        lines.append("")
        lines.append("-" * 60)
        lines.append("【操作建议】")
        lines.append("-" * 60)
        
        if results:
            # Top 3 操作建议
            for i, result in enumerate(results[:3], 1):
                # 使用 close 作为当前价格
                current_price = result.data.close if result.data else 0
                entry_price = current_price * 0.98  # 参考买入价（-2%）
                stop_loss = current_price * 0.95    # 止损价（-5%）
                take_profit = current_price * 1.08  # 止盈价（+8%）
                
                lines.append("")
                lines.append(f"▶ {i}. {result.name}({result.symbol})")
                lines.append(f"   操作建议: 关注")
                lines.append(f"   当前价格: {current_price:.2f}元")
                lines.append(f"   买入参考价: {entry_price:.2f}元（参考-2%）")
                lines.append(f"   止损位: {stop_loss:.2f}元（-5%）")
                lines.append(f"   止盈位: {take_profit:.2f}元（+8%）")
                lines.append(f"   综合评分: {result.score:.1f}")
                lines.append(f"   入选信号: {', '.join(result.signals[:3])}")
        
        # ==================== 风险提示 ====================
        lines.append("")
        lines.append("=" * 60)
        lines.append("【风险提示】")
        lines.append("=" * 60)
        lines.append("• 以上仅供参考，不构成投资建议")
        lines.append("• 股市有风险，投资需谨慎")
        lines.append("• 建议分散持仓，单只仓位不超过总资金的20%")
        lines.append("• 必须设置止损位（建议-5%），严格执行")
        lines.append("• 量化模型有局限性，请结合个人判断决策")
        
        lines.append("")
        lines.append("=" * 60)
        
        return '\n'.join(lines)
    
    def send_email(
        self,
        results: List[ScanResult],
        analysis: Optional[MarketAnalysis] = None,
        strategy_name: str = "量化选股",
        format: str = "html"
    ) -> bool:
        """
        生成报告并发送邮件
        
        Args:
            results: 扫描结果
            analysis: 市场分析
            strategy_name: 策略名称
            format: 报告格式
            
        Returns:
            发送是否成功
        """
        # 生成报告文件
        report_path = self.generate(results, analysis, format)
        
        # 同时生成Markdown版本作为附件
        md_path = None
        if format == "html":
            md_path = self.generate(results, analysis, "markdown")
        
        # 读取HTML内容
        with open(report_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # 生成摘要
        summary = self.generate_summary(results)
        
        # 准备附件列表
        attachments = [md_path] if md_path else []
        
        # 发送邮件（带附件）
        success = self.email_sender.send_report(
            results_summary=summary,
            html_content=html_content,
            strategy_name=strategy_name,
            attachments=attachments
        )
        
        if success:
            self.logger.info(f"报告已发送邮件: {report_path}")
            if md_path:
                self.logger.info(f"MD附件已发送: {md_path}")
        else:
            self.logger.error("邮件发送失败")
        
        return success
    
    def test_email(self) -> bool:
        """
        测试邮件配置
        
        Returns:
            测试是否成功
        """
        return self.email_sender.test_connection()
