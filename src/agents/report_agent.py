"""
报告生成Agent
负责生成各种格式的分析报告
"""
import os
import logging
from typing import List, Optional, Dict, Any
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
        timestamp = datetime.now().strftime("%y-%m-%d %H-%M")
        
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
    
    def generate_summary(
        self,
        results: List[ScanResult],
        market_state: Optional[str] = None,
        strategy_weights: Optional[Dict[str, float]] = None
    ) -> str:
        """
        生成丰富的文本摘要（用于邮件发送）
        
        Args:
            results: 扫描结果
            market_state: 市场状态（趋势上涨/下跌/震荡）
            strategy_weights: 各子策略权重
        """
        from datetime import datetime as dt
        
        lines = []
        today = dt.now().strftime('%Y年%m月%d日')
        now = dt.now().strftime('%H:%M')
        
        # ── 市场状态映射 ──────────────────────────────
        state_map = {
            "trend_up": "上涨趋势",
            "trend_down": "下跌趋势",
            "volatile": "震荡市",
        }
        state_desc = state_map.get(market_state, "震荡市") if market_state else "震荡市"
        
        # ── 策略权重映射 ──────────────────────────────
        weight_descs = {
            "volume_surge": "放量上涨",
            "turnover_rank": "成交额排名",
            "multi_factor": "多因子",
            "ai_technical": "AI技术面",
            "institution": "机构追踪",
        }
        w = strategy_weights or {}
        
        # ── 策略说明 ─────────────────────────────────
        lines.append("━" * 60)
        lines.append("【策略配置】")
        lines.append("━" * 60)
        lines.append(f"• 市场状态: {state_desc}（系统自动判断）")
        if w:
            weight_parts = [f"{weight_descs.get(k, k)} {v*100:.0f}%" for k, v in sorted(w.items(), key=lambda x: -x[1]) if v > 0]
            lines.append(f"• 策略权重: {' + '.join(weight_parts)}")
        else:
            lines.append("• 策略权重: 放量上涨 25% + 成交额排名 25% + 多因子 25% + AI技术面 15% + 机构追踪 10%")
        
        # ── 选股结果 ─────────────────────────────────
        lines.append("")
        lines.append("━" * 60)
        lines.append("【股票选择】（按综合评分降序排列）")
        lines.append("━" * 60)
        
        if not results:
            lines.append("今日暂无符合条件的股票。")
        else:
            up_count = sum(1 for r in results if r.data and r.data.change_pct > 0)
            avg_change = sum(r.data.change_pct if r.data else 0 for r in results) / len(results) if results else 0
            total_amount = sum(r.data.amount if r.data else 0 for r in results)
            
            lines.append("")
            lines.append(f"• 共筛选出 {len(results)} 只优质股票")
            lines.append(f"• 其中 {up_count} 只上涨，{len(results) - up_count} 只下跌/平盘")
            lines.append(f"• 平均涨幅: {avg_change:+.2f}%")
            lines.append(f"• 总成交额: {total_amount/1e8:.2f}亿")
            lines.append("")
            
            # Top 10 详细列表（多行展示信号）
            lines.append("▶ Top 10 推荐股票")
            lines.append("")
            
            # 表头
            lines.append("序号 | 股票名称 | 代码 | 评分 | 涨幅 | 成交额")
            lines.append("--- | --- | --- | --- | --- | ---")
            
            for i, result in enumerate(results[:10], 1):
                name = result.name
                symbol = result.symbol
                score = result.score
                
                if result.data:
                    change_pct = result.data.change_pct
                    amount = result.data.amount
                    amount_str = f"{amount/1e8:.2f}亿" if amount >= 1e8 else f"{amount/1e4:.0f}万"
                    change_str = f"{change_pct:+.2f}%"
                else:
                    amount_str = "N/A"
                    change_str = "N/A"
                
                lines.append(f"{i} | {name} | {symbol} | {score:.1f} | {change_str} | {amount_str}")
            
            # 入选信号说明（单独列在表格下方）
            lines.append("")
            lines.append("▶ 入选信号说明")
            all_signals = []
            for result in results[:10]:
                all_signals.extend(result.signals)
            # 统计各信号出现频次
            signal_count: Dict[str, int] = {}
            for s in all_signals:
                signal_count[s] = signal_count.get(s, 0) + 1
            top_signals = sorted(signal_count.items(), key=lambda x: -x[1])[:8]
            for sig, cnt in top_signals:
                lines.append(f"  • {sig}（命中 {cnt} 次）")
            
            if len(results) > 10:
                lines.append("")
                lines.append(f"• 还有 {len(results) - 10} 只备选股票（详见附件）")
        
        # ── 操作建议 ─────────────────────────────────
        lines.append("")
        lines.append("━" * 60)
        lines.append("【操作建议】")
        lines.append("━" * 60)
        
        if results:
            for i, result in enumerate(results[:3], 1):
                current_price = result.data.close if result.data else 0
                entry_price = current_price * 0.98
                stop_loss = current_price * 0.95
                take_profit = current_price * 1.08
                
                lines.append("")
                lines.append(f"▶ {i}. {result.name}({result.symbol})")
                lines.append(f"   当前价格: {current_price:.2f}元")
                lines.append(f"   买入参考: {entry_price:.2f}元（-2%）")
                lines.append(f"   止损位:   {stop_loss:.2f}元（-5%）")
                lines.append(f"   止盈位:   {take_profit:.2f}元（+8%）")
                lines.append(f"   综合评分: {result.score:.1f}")
                # 展示该股所有入选信号
                if result.signals:
                    sig_lines = " / ".join(result.signals)
                    lines.append(f"   入选信号: {sig_lines}")
        
        # ── 风险提示 ─────────────────────────────────
        lines.append("")
        lines.append("━" * 60)
        lines.append("【风险提示】")
        lines.append("━" * 60)
        lines.append("• 以上仅供参考，不构成投资建议")
        lines.append("• 股市有风险，投资需谨慎")
        lines.append("• 建议分散持仓，单只仓位不超过总资金的20%")
        lines.append("• 必须设置止损位（建议-5%），严格执行")
        lines.append("• 量化模型有局限性，请结合个人判断决策")
        
        return '\n'.join(lines)
    
    def send_email(
        self,
        results: List[ScanResult],
        analysis: Optional[MarketAnalysis] = None,
        strategy_name: str = "量化选股",
        format: str = "html",
        strategy_context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        生成报告并发送邮件
        
        Args:
            results: 扫描结果
            analysis: 市场分析
            strategy_name: 策略名称
            format: 报告格式
            strategy_context: 策略上下文（market_state, weights 等）
            
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
        
        # 生成摘要（带策略上下文）
        ctx = strategy_context or {}
        summary = self.generate_summary(
            results,
            market_state=ctx.get("market_state"),
            strategy_weights=ctx.get("weights")
        )
        
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
