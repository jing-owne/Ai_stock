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
        format: str = "html",
        strategy_context: Optional[Dict] = None
    ) -> str:
        """
        生成报告
        
        Args:
            results: 扫描结果
            analysis: 市场分析
            format: 输出格式
            strategy_context: 策略上下文（含子策略 Top 10）
            
        Returns:
            报告内容
        """
        if format == "html":
            return self._generate_html(results, analysis)
        elif format == "markdown":
            return self._generate_markdown(results, analysis, strategy_context)
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
        analysis: Optional[MarketAnalysis],
        strategy_context: Optional[Dict] = None
    ) -> str:
        """生成Markdown报告（含各子策略 Top 10）"""
        now = datetime.now()
        date_str = now.strftime('%Y年%m月%d日 %H:%M')
        today = now.strftime('%Y-%m-%d')

        lines = [
            "# 📈 Marcus策略小助手 · 策略详细报告",
            "",
            f"> 生成时间：{date_str}",
            "",
        ]

        ctx = strategy_context or {}
        market_state = ctx.get("market_state", "volatile")
        weights: Dict = ctx.get("weights", {})
        sub_top10: Dict = ctx.get("sub_top10", {})

        # 市场状态
        state_map = {"trend_up": "📈 上涨趋势", "trend_down": "📉 下跌趋势", "volatile": "📊 震荡市"}
        state_desc = state_map.get(market_state, "📊 震荡市")
        lines += [
            "## 一、市场状态 & 策略权重",
            "",
            f"- **市场状态**：{state_desc}",
        ]
        if weights:
            weight_names = {
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
                # 向后兼容旧名称
                "volume_surge": "放量突破",
                "institution": "多因子增强",
                "ma_divergence": "均线趋势",
            }
            for k, v in sorted(weights.items(), key=lambda x: -x[1]):
                if v > 0:
                    lines.append(f"- **{weight_names.get(k, k)}**：{v*100:.0f}%")
        lines.append("")

        # 各子策略 Top 15（v2.6.5: 9大策略）
        if sub_top10:
            strategy_display = {
                "volume_breakout": ("🚀 放量突破策略", "筛选条件：量比≥2倍突破、涨幅1-8%、成交额≥1亿"),
                "turnover_rank": ("💰 成交额排名策略", "筛选条件：成交额 Top20、成交额≥5亿"),
                "multi_factor": ("📐 多因子增强策略", "筛选条件：量价换手+机构综合评分≥50"),
                "ai_technical": ("🤖 AI技术面策略", "筛选条件：AI形态+趋势综合评分≥75"),
                "box_breakout": ("📦 箱体突破策略", "筛选条件：30日箱体振幅<18%、突破上沿、放量确认"),
                "ma_trend": ("📈 均线趋势策略", "筛选条件：多头排列/均线发散、量能配合"),
                "bottom_rebound": ("🔄 底部反弹策略", "筛选条件：RSI超卖反弹/底部形态、放量确认"),
                "consecutive_positive": ("🌱 连续小阳吸筹策略", "筛选条件：3-7天连续小阳线、温和放量"),
                "net_inflow": ("💵 资金净流入策略", "筛选条件：20日连续净流入>10天、量价配合"),
                "trend_confirmation": ("✅ 追涨确认策略", "筛选条件：RSI>55 + MA多头 + 放量 + 连涨≥3天"),
            }
            lines += ["## 二、各子策略 Top 15 明细", ""]

            for sname, (title, desc) in strategy_display.items():
                items = sub_top10.get(sname, [])
                lines += [f"### {title}", f"> {desc}", ""]
                if not items:
                    lines += ["*本策略今日无符合条件的标的*", ""]
                    continue
                lines += [
                    "| 排名 | 名称 | 代码 | 评分 | 涨幅 | 成交额 | 命中信号 |",
                    "|:---:|:---|:---|:---:|:---:|:---:|:---|",
                ]
                for i, r in enumerate(items, 1):
                    if r.data:
                        change_str = f"{r.data.change_pct:+.2f}%"
                        amt = r.data.amount
                        amt_str = f"{amt/1e8:.2f}亿" if amt >= 1e8 else f"{amt/1e4:.0f}万"
                    else:
                        change_str = "N/A"
                        amt_str = "N/A"
                    sigs = " / ".join(r.signals[:3]) if r.signals else "-"
                    lines.append(
                        f"| {i} | {r.name} | `{r.symbol}` | **{r.score:.1f}** | {change_str} | {amt_str} | {sigs} |"
                    )
                lines.append("")

        # 综合 Top 15
        lines += [
            "## 三、当日策略命中 Top 15",
            "",
            "综合10大策略加权评分后，Top 15 策略标的：",
            "",
            "| 排名 | 名称 | 代码 | 综合评分 | 涨幅 | 成交额 | 命中策略 |",
            "|:---:|:---|:---|:---:|:---:|:---:|:---|",
        ]
        for i, r in enumerate(results[:15], 1):
            if r.data:
                change_str = f"{r.data.change_pct:+.2f}%"
                amt = r.data.amount
                amt_str = f"{amt/1e8:.2f}亿" if amt >= 1e8 else f"{amt/1e4:.0f}万"
            else:
                change_str = "N/A"
                amt_str = "N/A"
            # 优先展示命中策略名称
            hit_strategies = r.metadata.get("hit_strategies", [])
            strategy_count = r.metadata.get("strategy_count", 0)
            if hit_strategies:
                sigs = " / ".join(hit_strategies) + f"（{strategy_count}策略）"
            else:
                sigs = " / ".join(r.signals[:3]) if r.signals else "-"
            # 轨道标签(emoji)放在命中策略末尾
            source_track = r.metadata.get("source_track", "")
            track_emoji = f" {source_track}" if source_track else ""
            lines.append(
                f"| {i} | {r.name} | `{r.symbol}` | **{r.score:.1f}** | {change_str} | {amt_str} | {sigs}{track_emoji} |"
            )
        lines.append("")

        # 风险提示
        lines += [
            "---",
            "",
            "> ⚠️ **免责声明**：本报告由 Marcus策略小助手自动生成，基于技术面量化模型，",
            "> 不构成任何投资建议。股市有风险，投资需谨慎，请根据自身判断独立决策。",
            "",
        ]

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
