"""
邮件发送模块
使用SMTP发送分析报告
支持丰富的邮件内容格式
针对iPhone 12和移动端优化

重构：
  - SMTP发送 → src/common/smtp_sender.py（纯发送）
  - HTML渲染 → src/common/html_engine.py（纯渲染）
  - 本模块保留 format_* wrapper 兼容旧调用方，内部委托 html_engine
"""
import logging
from typing import List, Optional, Dict
from pathlib import Path
from datetime import datetime

from ..core.config import EmailConfig
from ..data.fetcher import DataFetcher
from ..common.smtp_sender import SMTPSender
from ..common.html_engine import render_email_html


# ── 兼容 wrapper：保留旧函数签名，内部委托 html_engine ──

def format_email_html(content: str, title: str = "【Marcus策略小助手】") -> str:
    """（兼容）文本 → HTML邮件，移动端优化版。委托 html_engine.render_email_html()"""
    return render_email_html(content, title=title, variant="mobile")


def format_email_html_responsive(content: str, title: str = "【Marcus策略小助手】") -> str:
    """（兼容）文本 → HTML邮件，响应式版。委托 html_engine.render_email_html()"""
    return render_email_html(content, title=title, variant="responsive")


class EmailSender:
    """
    邮件发送器（优化版）
    
    支持QQ邮箱SMTP发送，包含丰富的邮件格式
    针对移动端（特别是iPhone 12）优化
    """
    
    def __init__(self, config: EmailConfig):
        self.config = config
        self.logger = logging.getLogger("AInvest.EmailSender")
        self.data_fetcher = DataFetcher()
        self._smtp = SMTPSender(
            smtp_server=config.smtp_server,
            smtp_port=config.smtp_port,
            smtp_user=config.smtp_user,
            smtp_password=config.smtp_password,
            sender_name=config.sender_name,
        )
    
    def generate_email_content(self, stock_results: List[Dict], strategy_config: Dict = None) -> str:
        """
        生成完整的邮件内容
        
        Args:
            stock_results: 标的池结果列表
            strategy_config: 策略配置信息
            
        Returns:
            完整的邮件内容（纯文本格式，将由format_email_html处理）
        """
        content_lines = []
        
        # 1. 每日一言
        daily_quote = self.data_fetcher.get_daily_quote()
        content_lines.append("【每日一言】")
        content_lines.append("")
        content_lines.append(f"💡 {daily_quote}")
        content_lines.append("")
        content_lines.append("=" * 50)
        content_lines.append("")
        
        # 2. 财经动态
        content_lines.append("【财经动态】")
        content_lines.append("")
        
        news_list = self.data_fetcher.fetch_all_news()
        if news_list:
            for i, news in enumerate(news_list[:10], 1):
                title = news.get('title', '')
                # 去除时间，只保留标题
                content_lines.append(f"{i}. {title}")
        else:
            content_lines.append("暂无财经动态更新")
        
        content_lines.append("")
        content_lines.append("=" * 50)
        content_lines.append("")
        
        # 3. 策略配置
        content_lines.append("【策略配置】")
        content_lines.append("")
        
        if strategy_config:
            for strategy_name, weight in strategy_config.items():
                content_lines.append(f"• {strategy_name}: 权重 {weight}%")
        else:
            content_lines.append("• 默认策略: 权重 100%")
        
        content_lines.append("")
        content_lines.append("=" * 50)
        content_lines.append("")
        
        # 4. 策略命中TOP15
        content_lines.append("【策略命中TOP15】")
        content_lines.append("")

        if stock_results:
            for i, stock in enumerate(stock_results[:15], 1):
                symbol = stock.get('symbol', '')
                name = stock.get('name', '')
                current_price = stock.get('current_price', 0)
                change_pct = stock.get('change_pct', 0)
                score = stock.get('score', 0)
                amount = stock.get('amount', 0)
                signals = stock.get('signals', [])
                change_str = f"{change_pct:+.2f}%"
                amount_str = f"{amount/1e8:.2f}亿" if amount >= 1e8 else f"{amount/1e4:.0f}万" if amount > 0 else "N/A"
                sig_str = " / ".join(signals[:3]) if signals else "-"
                content_lines.append(f"▶ {i}. {name}（{symbol}）  成交额：{amount_str}")
                content_lines.append(f"   评分：{score:.1f}分&nbsp;&nbsp;&nbsp;&nbsp;现价：{current_price:.2f}元 ({change_str})")
                content_lines.append(f"   命中策略：{sig_str}")
                content_lines.append("")

        content_lines.append("=" * 50)
        content_lines.append("")

        # 5. 建议操作-胜率排行Top5
        content_lines.append("【建议操作-胜率排行Top5】")
        content_lines.append("")
        
        if stock_results:
            for i, stock in enumerate(stock_results[:5], 1):
                symbol = stock.get('symbol', '')
                name = stock.get('name', '')
                current_price = stock.get('current_price', 0)
                change_pct = stock.get('change_pct', 0)
                suggest_buy_price = stock.get('suggest_buy_price', current_price * 0.98)
                stop_loss = stock.get('stop_loss', suggest_buy_price * 0.95)
                take_profit = stock.get('take_profit', suggest_buy_price * 1.10)
                win_rate = stock.get('win_rate', 0)
                signals = stock.get('signals', [])
                sig_str = " / ".join(signals[:3]) if signals else "-"

                content_lines.append(f"▶ {i}. {name}（{symbol}）   预估胜率：<strong style='color:#DC2626;font-weight:bold;'>{win_rate:.1f}%</strong>")
                content_lines.append(f"   现价：{current_price:.2f}元 ({change_pct:+.2f}%)&nbsp;&nbsp;&nbsp;&nbsp;建议买入：{suggest_buy_price:.2f}元")
                content_lines.append(f"   止损：{stop_loss:.2f}元（-5%）  止盈：{take_profit:.2f}元（+8%）")
                content_lines.append(f"   命中策略：{sig_str}")
                content_lines.append("")
        
        content_lines.append("=" * 50)
        content_lines.append("")

        # 6. 市场态势
        content_lines.append("【市场态势】")
        content_lines.append("")

        try:
            overview = self.data_fetcher.get_market_overview()
            # 沪深300
            if overview.get('csi300'):
                csi = overview['csi300']
                csi_chg = csi['change_pct']
                arrow = "↑" if csi_chg >= 0 else "↓"
                content_lines.append(f"📈 沪深300:  {csi_chg:+.2f}% {arrow}")
            # 创业板指
            if overview.get('cyb_index'):
                cyb = overview['cyb_index']
                cyb_chg = cyb['change_pct']
                arrow = "↑" if cyb_chg >= 0 else "↓"
                content_lines.append(f"📊 创业板指:  {cyb_chg:+.2f}% {arrow}")
            # 涨跌家数
            up_total = overview.get('up_count', 0)
            down_total = overview.get('down_count', 0)
            if up_total > 0 or down_total > 0:
                total = up_total + down_total
                up_ratio = up_total / total * 100 if total > 0 else 50
                content_lines.append(f"📊 涨跌家数:  上涨 {up_total} 家 / 下跌 {down_total} 家 (上涨占比 {up_ratio:.0f}%)")
            # 总成交额
            total_amt = overview.get('total_amount', 0)
            if total_amt > 0:
                amt_str = f"{total_amt/1e12:.2f}万亿" if total_amt >= 1e12 else f"{total_amt/1e8:.0f}亿"
                content_lines.append(f"💹 市场成交:  {amt_str}")
        except Exception:
            if stock_results:
                up_count_all = sum(1 for s in stock_results[:15] if s.get('change_pct', 0) > 0)
                down_count_all = sum(1 for s in stock_results[:15] if s.get('change_pct', 0) < 0)
                content_lines.append(f"📊 涨跌家数(样本):  上涨 {up_count_all} / 下跌 {down_count_all}")

        content_lines.append("")
        content_lines.append("=" * 50)
        content_lines.append("")

        # 7. 今日总结
        content_lines.append("【今日总结】")
        content_lines.append("")

        if stock_results:
            avg_score = sum(s.get('score', 0) for s in stock_results[:15]) / min(15, len(stock_results))
            up_count = sum(1 for s in stock_results[:15] if s.get('change_pct', 0) > 0)

            content_lines.append(f"▶ 平均评分: {avg_score:.1f}")
            content_lines.append(f"▶ 上涨家数: {up_count} 只")
            content_lines.append(f"▶ 建议重点关注前3只标的")

        content_lines.append("")
        content_lines.append("=" * 50)
        content_lines.append("")

        # 7. 风险&提示
        content_lines.append("【风险&提示】")
        content_lines.append("")
        content_lines.append("• 以上仅供参考，不构成投资建议")
        content_lines.append("• 股市有风险，投资需谨慎")
        content_lines.append("• 建议分散持仓，单只仓位不超过总资金的20%")
        content_lines.append("• 必须设置止损位（建议-5%），严格执行")
        content_lines.append("")

        ipo_list = self.data_fetcher.get_ipo_calendar(max_days=7)
        if ipo_list:
            content_lines.append("📋 近期打新日历（未来7天）：")
            for ipo in ipo_list:
                content_lines.append(f"  • {ipo['apply_date']}  {ipo['stock_name']}（{ipo['stock_code']}）申购代码：{ipo['apply_code']} | 发行价：{ipo['price']} | 顶格市值：{ipo['market_cap_needed']}万")
        else:
            content_lines.append("📋 近7天暂无新股申购安排")

        return '\n'.join(content_lines)
    
    def send(
        self,
        subject: str,
        html_content: str,
        to_emails: Optional[List[str]] = None,
        cc_emails: Optional[List[str]] = None,
        attachments: Optional[List[str]] = None,
        use_responsive: bool = True
    ) -> bool:
        """发送邮件（渲染由本模块负责，发送委托 SMTPSender）"""
        if not self.config.enabled:
            self.logger.info("邮件发送已禁用")
            return False
        
        # 渲染HTML
        if use_responsive:
            rendered = format_email_html_responsive(html_content, subject)
        else:
            rendered = format_email_html(html_content, subject)
        
        recipients = to_emails or self.config.to_emails
        cc_list = cc_emails or self.config.cc_emails
        if not recipients:
            self.logger.error("没有配置收件人")
            return False
        
        debug = self.config.debug_mode
        if debug:
            self.logger.info("调试模式：跳过抄送")
        
        return self._smtp.send(
            subject=subject,
            html_content=rendered,
            to_emails=recipients,
            cc_emails=cc_list,
            attachments=attachments,
            debug=debug,
        )
    
    def send_report(
        self,
        results_summary: str,
        html_content: str,
        strategy_name: str,
        attachments: Optional[List[str]] = None,
        stock_results: List[Dict] = None,
        strategy_config: Dict = None
    ) -> bool:
        """
        发送策略报告
        
        Args:
            results_summary: 结果摘要（纯文本）
            html_content: HTML报告内容
            strategy_name: 策略名称
            attachments: 附件路径列表
            stock_results: 标的池结果列表
            strategy_config: 策略配置信息
            
        Returns:
            发送是否成功
        """
        # 构建邮件主题（新格式）
        date_str = datetime.now().strftime('%Y-%m-%d')
        subject = f"【Marcus策略小助手】{date_str} 动态策略报告"
        
        # 生成完整的邮件内容
        if stock_results:
            email_content = self.generate_email_content(stock_results, strategy_config)
        else:
            email_content = results_summary
        
        # 使用配置中的收件人
        to_emails = self.config.to_emails if self.config.to_emails else []
        cc_emails = self.config.cc_emails if self.config.cc_emails else []
        
        self.logger.info(f"准备发送邮件:")
        self.logger.info(f"  主题: {subject}")
        self.logger.info(f"  收件人: {to_emails}")
        self.logger.info(f"  附件: {attachments}")
        
        # 使用生成的内容发送邮件
        return self.send(
            subject=subject,
            html_content=email_content,
            to_emails=to_emails,
            cc_emails=cc_emails,
            attachments=attachments
        )
    
    def test_connection(self) -> bool:
        """测试SMTP连接（委托 SMTPSender）"""
        return self._smtp.test_connection()
