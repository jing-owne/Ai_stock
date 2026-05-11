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
        template: Optional[str] = None,
        strategy_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        生成分析报告
        
        Args:
            results: 扫描结果
            analysis: 市场分析
            format: 报告格式 (html/markdown/json)
            template: 模板名称
            strategy_context: 策略上下文（含子策略 Top 10，用于 MD 附件）
            
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
            format=format,
            strategy_context=strategy_context
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
        包含：每日一言、财经动态、策略配置、建议操作(胜率Top5)、策略命中TOP15、今日总结、风险&提示(含打新日历)
        """
        from datetime import datetime as dt
        from ..data.fetcher import DataFetcher

        lines = []
        fetcher = DataFetcher()

        # ── 每日一言 ──────────────────────────────────
        lines.append("【每日一言】")
        lines.append("")
        daily_quote = fetcher.get_daily_quote()
        lines.append(f"💡 {daily_quote}")
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")

        # ── 财经动态 ──────────────────────────────────
        lines.append("【财经动态】")
        lines.append("")
        news_list = fetcher.fetch_all_news()
        if news_list:
            for i, news in enumerate(news_list[:10], 1):
                title = news.get('title', '')
                lines.append(f"{i}. {title}")
        else:
            lines.append("暂无财经动态更新")
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")

        # ── 策略配置 ──────────────────────────────────
        state_map = {
            "trend_up": "上涨趋势",
            "trend_down": "下跌趋势",
            "volatile": "震荡市",
        }
        state_desc = state_map.get(market_state, "震荡市") if market_state else "震荡市"

        weight_descs = {
            "volume_surge": "放量上涨",
            "turnover_rank": "成交额排名",
            "multi_factor": "多因子",
            "ai_technical": "AI技术面",
            "institution": "机构追踪",
        }
        w = strategy_weights or {}

        lines.append("【策略配置】")
        lines.append("")
        lines.append(f"• 市场状态: {state_desc}（系统自动判断）")
        if w:
            weight_parts = [f"{weight_descs.get(k, k)} {v*100:.0f}%" for k, v in sorted(w.items(), key=lambda x: -x[1]) if v > 0]
            lines.append(f"• 策略权重: {' + '.join(weight_parts)}")
        else:
            lines.append("• 策略权重: 放量上涨 25% + 成交额排名 25% + 多因子 25% + AI技术面 15% + 机构追踪 10%")
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")

        # ── 建议操作-胜率排行Top5 ──────────────────────
        lines.append("【建议操作-胜率排行Top5】")
        lines.append("")

        if not results:
            lines.append("今日暂无符合条件的股票。")
        else:
            # 按胜率排序取 Top5
            scored_results = []
            for result in results[:15]:
                score = result.score
                sig_count = len(result.signals)
                change_pct = result.data.change_pct if result.data else 0
                base_win_rate = 50 + (score - 60) / 40 * 30 if score >= 60 else 50
                bonus = min(sig_count * 3, 15)
                price_bonus = min(max(change_pct, 0) * 0.5, 5)
                win_rate = min(round(base_win_rate + bonus + price_bonus, 1), 90.0)
                scored_results.append((result, win_rate))

            scored_results.sort(key=lambda x: -x[1])
            top5 = scored_results[:5]

            for i, (result, win_rate) in enumerate(top5, 1):
                current_price = result.data.close if result.data else 0
                change_pct = result.data.change_pct if result.data else 0
                suggest_buy_price = current_price * 0.98
                stop_loss = current_price * 0.95
                take_profit = current_price * 1.08

                change_str = f"{change_pct:+.2f}%"
                sig_str = " / ".join(result.signals[:3]) if result.signals else "-"

                # 第1行：股票名称
                lines.append(f"▶ {i}. {result.name}（{result.symbol}）评分：{result.score:.1f} | 预估胜率：{win_rate:.1f}%")
                # 第2行：现价 + 涨跌幅
                lines.append(f"   现价：{current_price:.2f}元 ({change_str})")
                # 第3行：建议买入价 | 止损 | 止盈
                lines.append(f"   建议买入价：{suggest_buy_price:.2f}元 | 止损：{stop_loss:.2f}元 | 止盈：{take_profit:.2f}元")
                # 第4行：命中策略
                lines.append(f"   命中策略：{sig_str}")
                lines.append("")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")

        # ── 策略命中TOP15 ─────────────────────────────
        lines.append("【策略命中TOP15】")
        lines.append("")

        if results:
            for i, result in enumerate(results[:15], 1):
                current_price = result.data.close if result.data else 0
                change_pct = result.data.change_pct if result.data else 0
                amount = result.data.amount if result.data else 0
                change_str = f"{change_pct:+.2f}%"
                amount_str = f"{amount/1e8:.2f}亿" if amount >= 1e8 else f"{amount/1e4:.0f}万" if amount > 0 else "N/A"
                sig_str = " / ".join(result.signals[:3]) if result.signals else "-"

                lines.append(f"▶ {i}. {result.name}（{result.symbol}）评分：{result.score:.1f}")
                lines.append(f"   现价：{current_price:.2f}元 | 涨跌幅：{change_str} | 成交额：{amount_str}")
                lines.append(f"   命中策略：{sig_str}")
                lines.append("")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")

        # ── 今日总结 ──────────────────────────────────
        lines.append("【今日总结】")
        lines.append("")

        if results:
            up_count = sum(1 for r in results if r.data and r.data.change_pct > 0)
            avg_score = sum(r.score for r in results[:15]) / min(15, len(results)) if results else 0
            top3 = results[:3]
            top3_names = "、".join([f"{r.name}({r.score:.1f}分)" for r in top3])

            lines.append(f"▶ 今日综合策略共筛选出 {len(results[:15])} 只优质股票")
            lines.append(f"▶ 平均评分：{avg_score:.1f}分，上涨家数：{up_count} 只")
            lines.append(f"▶ 重点推荐：{top3_names}")
            lines.append(f"▶ 建议：逢低关注前3只股票，设置好止损位")

        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")

        # ── 风险&提示（含打新日历） ─────────────────────
        lines.append("【风险&提示】")
        lines.append("")
        lines.append("• 以上仅供参考，不构成投资建议")
        lines.append("• 股市有风险，投资需谨慎")
        lines.append("• 建议分散持仓，单只仓位不超过总资金的20%")
        lines.append("• 必须设置止损位（建议-5%），严格执行")
        lines.append("")

        # 打新日历
        ipo_list = fetcher.get_ipo_calendar(max_days=7)
        if ipo_list:
            lines.append(f"📋 近期打新日历（未来7天）：")
            for ipo in ipo_list:
                lines.append(f"  • {ipo['apply_date']}  {ipo['stock_name']}（{ipo['stock_code']}）申购代码：{ipo['apply_code']} | 发行价：{ipo['price']} | 顶格市值：{ipo['market_cap_needed']}万")
        else:
            lines.append("📋 近7天暂无新股申购安排")

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
        
        # 策略上下文（含子策略 Top 10）
        ctx = strategy_context or {}
        
        # 同时生成Markdown版本作为附件（含各子策略 Top 10）
        md_path = None
        if format == "html":
            md_path = self.generate(
                results, analysis, "markdown",
                strategy_context=ctx
            )
        
        # 读取HTML内容
        with open(report_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # 生成摘要（带策略上下文）
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
