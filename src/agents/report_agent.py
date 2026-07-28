"""
报告生成Agent
负责生成各种格式的分析报告
"""
import os
import logging
import re
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
        timestamp = datetime.now().strftime("%y-%m-%d %H-%M-%S")
        ctx = strategy_context or {}
        label_suffix = ""
        if ctx.get("mode_label"):
            safe_label = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", str(ctx["mode_label"])).strip("_")
            if safe_label:
                label_suffix = f"_{safe_label}"
        
        if format == "html":
            filename = f"scan_report{label_suffix}_{timestamp}.html"
        elif format == "markdown":
            filename = f"scan_report{label_suffix}_{timestamp}.md"
        elif format == "json":
            filename = f"scan_report{label_suffix}_{timestamp}.json"
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
        包含：每日一言、财经动态、策略配置、建议操作(胜率Top10)、策略命中TOP15、市场态势、今日总结、风险&提示(含打新日历)
        """
        from datetime import datetime as dt
        from ..data.fetcher import DataFetcher
        from concurrent.futures import ThreadPoolExecutor, as_completed

        lines = []
        fetcher = DataFetcher()

        # ── 并发获取所有外部数据（避免串行累加耗时）──
        # 每日一言 / 财经新闻 / 市场态势 / IPO日历 / 可转债日历 互相独立，并发拉取
        # 总耗时 = max(单个) 而非 sum，大幅缩短邮件摘要生成时间
        def _safe(fn, key):
            try:
                return (key, fn())
            except Exception as e:
                self.logger.debug(f"并发获取 {key} 失败: {e}")
                return (key, None)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(_safe, fetcher.get_daily_quote, "quote"),
                executor.submit(_safe, fetcher.fetch_all_news, "news"),
                executor.submit(_safe, fetcher.get_market_overview, "market"),
                executor.submit(_safe, lambda: fetcher.get_ipo_calendar(max_days=7), "ipo"),
                executor.submit(_safe, lambda: fetcher.get_bond_calendar(max_days=7), "bond"),
            ]
            data_results = {}
            for fut in as_completed(futures):
                k, v = fut.result()
                data_results[k] = v

        daily_quote = data_results.get("quote") or "暂无"
        news_list = data_results.get("news") or []
        overview = data_results.get("market") or {}
        ipo_list = data_results.get("ipo") or []
        bond_list = data_results.get("bond") or []

        # ── 每日一言 ──────────────────────────────────
        lines.append("【每日一言】")
        lines.append("")
        lines.append(f"💡 {daily_quote}")
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")


        # ── 财经动态 ──────────────────────────────────
        lines.append("【财经动态】")
        lines.append("")
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
            "volume_breakout": "放量突破",
            "turnover_rank": "成交额排名",
            "multi_factor": "多因子增强",
            "ai_technical": "AI技术面",
            "box_breakout": "箱体突破",
            "ma_trend": "均线趋势",
            "bottom_rebound": "底部反弹",
            "consecutive_positive": "连续小阳",
            "net_inflow": "资金净流入",
            "trend_confirmation": "追涨确认",
            # 向后兼容
            "volume_surge": "放量突破",
            "institution": "多因子增强",
            "ma_divergence": "均线趋势",
        }
        w = strategy_weights or {}

        lines.append("【策略配置】")
        lines.append("")
        lines.append(f"• 市场状态: {state_desc}（策略小助手自动判断）")
        if w:
            weight_parts = [f"{weight_descs.get(k, k)} {v*100:.0f}%" for k, v in sorted(w.items(), key=lambda x: -x[1]) if v > 0]
            lines.append(f"• 策略权重: {' + '.join(weight_parts)}")
        else:
            lines.append("• 策略权重: 放量上涨 25% + 成交额排名 25% + 多因子 25% + AI技术面 15% + 机构追踪 10%")
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")

        # ── 建议操作-胜率排行Top10 ─────────────────────
        lines.append("【建议操作-胜率排行Top10】")
        lines.append("")

        if not results:
            lines.append("今日暂无符合条件的标的。")
        else:
            # 按胜率排序取 Top10
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
            top10 = scored_results[:10]

            for i, (result, win_rate) in enumerate(top10, 1):
                current_price = result.data.close if result.data else 0
                change_pct = result.data.change_pct if result.data else 0
                suggest_buy_price = current_price * 0.98
                stop_loss = current_price * 0.95
                take_profit = current_price * 1.08

                change_str = f"{change_pct:+.2f}%"

                # 从 metadata 中获取命中策略名称
                hit_strategies = result.metadata.get("hit_strategies", [])
                if hit_strategies:
                    strategy_str = " / ".join(hit_strategies)
                else:
                    strategy_str = " / ".join(result.signals[:3]) if result.signals else "-"

                # 第1行：名称 + 预估胜率
                source_track = result.metadata.get("source_track", "")
                track_tag = f"{source_track} " if source_track else ""
                lines.append(f"▶ {i}. {result.name}（{result.symbol}）   预估胜率：<strong style='color:#DC2626;font-weight:bold;'>{win_rate:.1f}%</strong>")
                # 第2行：现价 + 建议买入价
                lines.append(f"   现价：{current_price:.2f}元 ({change_str})&nbsp;&nbsp;&nbsp;&nbsp;建议买入：{suggest_buy_price:.2f}元")
                # 第3行：止盈止损
                lines.append(f"   止损：{stop_loss:.2f}元（-5%）  止盈：{take_profit:.2f}元（+8%）")
                # 第4行：命中策略 + 轨道标签
                lines.append(f"   命中策略：{track_tag}{strategy_str}")
                lines.append("")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")

        # ── 策略命中TOP15 ─────────────────────────────
        lines.append("【策略命中TOP15】")
        lines.append("")

        if not results:
            lines.append("今日暂无策略命中标的。")
        else:
            for i, r in enumerate(results[:15], 1):
                current_price = r.data.close if r.data else 0
                change_pct = r.data.change_pct if r.data else 0
                amount = r.data.amount if r.data else 0
                change_str = f"{change_pct:+.2f}%"
                amount_str = f"{amount/1e8:.2f}亿" if amount >= 1e8 else f"{amount/1e4:.0f}万" if amount > 0 else "N/A"

                # 轨道标签放在命中策略行
                source_track = r.metadata.get("source_track", "")
                track_tag = f"{source_track} " if source_track else ""

                hit_strategies = r.metadata.get("hit_strategies", [])
                strategy_count = r.metadata.get("strategy_count", 0)
                if hit_strategies:
                    strategy_str = " / ".join(hit_strategies) + f"（{strategy_count}策略）"
                else:
                    strategy_str = " / ".join(r.signals[:3]) if r.signals else "-"

                # 第1行：名称 + 成交额
                lines.append(f"▶ {i}. {r.name}（{r.symbol}）  成交额：{amount_str}")
                # 第2行：评分 + 现价(涨跌幅)
                lines.append(f"   评分：<strong style='color:#E87722;font-weight:700;'>{r.score:.1f}分</strong>&nbsp;&nbsp;&nbsp;&nbsp;现价：{current_price:.2f}元 ({change_str})")
                # 第3行：命中策略 + 轨道标签
                lines.append(f"   命中策略：{track_tag}{strategy_str}")
                lines.append("")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")

        # ── 市场态势 ──────────────────────────────────
        lines.append("【市场态势】")
        lines.append("")

        # 根据市场状态确定立场
        stance_map = {
            "trend_up": ("🟢 激进买入", "市场处于上涨趋势，可适当增加仓位"),
            "trend_down": ("🔴 观望防守", "市场处于下跌趋势，建议控制仓位"),
            "volatile": ("🟡 稳健操作", "市场震荡，建议均衡配置"),
        }
        stance, stance_desc = stance_map.get(market_state, stance_map["volatile"]) if market_state else stance_map["volatile"]
        lines.append(f"🎯 市场立场: {stance}")

        # 获取市场宏观数据（已并发获取，overview 可能为空 dict 表示失败）
        try:
            # 沪深300
            if overview.get('csi300'):
                csi = overview['csi300']
                csi_chg = csi['change_pct']
                arrow = "↑" if csi_chg >= 0 else "↓"
                lines.append(f"📈 沪深300:  {csi_chg:+.2f}% {arrow}")

            # 创业板指
            if overview.get('cyb_index'):
                cyb = overview['cyb_index']
                cyb_chg = cyb['change_pct']
                arrow = "↑" if cyb_chg >= 0 else "↓"
                lines.append(f"📊 创业板指:  {cyb_chg:+.2f}% {arrow}")

            # 涨跌家数
            up_total = overview.get('up_count', 0)
            down_total = overview.get('down_count', 0)
            if up_total > 0 or down_total > 0:
                total = up_total + down_total
                up_ratio = up_total / total * 100 if total > 0 else 50
                lines.append(f"📊 涨跌家数:  上涨 {up_total} 家 / 下跌 {down_total} 家 (上涨占比 {up_ratio:.0f}%)")

            # 总成交额
            total_amt = overview.get('total_amount', 0)
            if total_amt > 0:
                amt_str = f"{total_amt/1e12:.2f}万亿" if total_amt >= 1e12 else f"{total_amt/1e8:.0f}亿"
                lines.append(f"💹 市场成交:  {amt_str}")

            # 市场态势数据为空时降级：用扫描结果估算
            if not overview and results:
                up_count_all = sum(1 for r in results if r.data and r.data.change_pct > 0)
                down_count_all = sum(1 for r in results if r.data and r.data.change_pct < 0)
                lines.append(f"📊 涨跌家数(样本):  上涨 {up_count_all} / 下跌 {down_count_all}")

        except Exception as e:
            self.logger.warning(f"市场态势数据构建失败，使用扫描结果估算: {e}")
            if results:
                up_count_all = sum(1 for r in results if r.data and r.data.change_pct > 0)
                down_count_all = sum(1 for r in results if r.data and r.data.change_pct < 0)
                lines.append(f"📊 涨跌家数(样本):  上涨 {up_count_all} / 下跌 {down_count_all}")

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

            lines.append(f"▶ 平均评分：{avg_score:.1f}分，上涨家数：{up_count} 只")
            lines.append(f"▶ 重点关注：{top3_names}")
            lines.append(f"▶ 建议：逢低关注前3只标的，设置好止损位")

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

        # ── 打新日历（新股） ──
        if ipo_list:
            lines.append(f"📋 近期新股申购（未来7天）：")
            for ipo in ipo_list:
                date_display = ipo.get('apply_date_display', ipo['apply_date'][5:])
                lines.append(f"  • {date_display}  {ipo['stock_name']}（{ipo['stock_code']}）申购代码：{ipo['apply_code']} | 发行价：{ipo['price']}")
        else:
            lines.append("📋 近7天暂无新股申购安排")
        lines.append("")

        # ── 可转债日历 ──
        if bond_list:
            # 按申购日期升序：日期最新的在最上面（与新股一致）
            bond_list.sort(key=lambda x: x.get('apply_date_full', x.get('apply_date', '')))
            lines.append(f"📋 近期可转债申购（未来7天）：")
            for bond in bond_list:
                conv_price = bond.get('conv_price', '待定')
                amount = bond.get('amount', '')
                amount_str = f' | 规模：{amount}' if amount and amount not in ('nan', '-', '') else ''
                lines.append(f"  • {bond['apply_date']}  {bond['bond_name']}（{bond['bond_code']}）正股：{bond['stock_name']} | 转股价：¥{conv_price}{amount_str}")
        else:
            lines.append("📋 近7天暂无新债申购安排")

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
        # 策略上下文（含子策略 Top 10）
        ctx = strategy_context or {}
        
        # 生成报告文件
        report_path = self.generate(results, analysis, format, strategy_context=ctx)
        
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
        if ctx.get("mode_label"):
            summary = f"【策略模式】{ctx['mode_label']}\n\n{summary}"
        tracking_strategy_name = strategy_name
        tracking_session = None
        try:
            from ..backtest.tracker import classify_trading_session
            tracking_session, _ = classify_trading_session()
            if ctx.get("mode_label") and tracking_session != "regular":
                tracking_strategy_name = f"非交易时间观察-{strategy_name}"
                summary = f"【非交易时间观察】本次结果不写入收益跟踪、不进入回测样本。\n\n{summary}"
        except Exception as e:
            self.logger.debug(f"交易时间门禁检查失败，继续发送邮件: {e}")
        
        # 准备附件列表
        attachments = [md_path] if md_path else []
        
        # 发送邮件（带附件）
        success = self.email_sender.send_report(
            results_summary=summary,
            html_content=html_content,
            strategy_name=tracking_strategy_name,
            attachments=attachments
        )

        # ── 跟踪钩子：邮件发送成功后，把本次推荐标的 + 发送时价格 追加记录 ──
        # 仅记录 composite 扫描结果（含 mode_label 区分新旧策略），失败不影响邮件。
        # 非交易时间由 RecommendationTracker.record() 门禁拦截，不进入收益样本。
        try:
            if ctx.get("mode_label"):
                from ..backtest.tracker import RecommendationTracker
                from ..backtest.models import StrategyMode
                mode = StrategyMode.from_label(ctx.get("mode_label", "")).value
                RecommendationTracker().record(
                    results,
                    mode=mode,
                    hold_style="fast",
                    strategy_name=strategy_name,
                    email_subject=getattr(self.email_sender, "last_subject", ""),
                    email_sent=success,
                    report_path=report_path,
                    md_attachment_path=md_path or "",
                )
        except Exception as e:
            self.logger.warning(f"推荐跟踪记录失败(不影响邮件): {e}")

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
