"""
报告格式化器
"""


class ReportFormatter:
    """
    报告格式化器
    
    提供各种格式化方法
    """
    
    @staticmethod
    def format_score(score: float) -> str:
        """格式化评分"""
        if score >= 80:
            return f'<span class="score-high">{score:.1f}</span>'
        elif score >= 60:
            return f'<span class="score-medium">{score:.1f}</span>'
        else:
            return f'<span class="score-low">{score:.1f}</span>'
    
    @staticmethod
    def format_change(change_pct: float) -> str:
        """格式化涨跌幅"""
        if change_pct > 0:
            return f'<span class="rise">+{change_pct:.2f}%</span>'
        elif change_pct < 0:
            return f'<span class="fall">{change_pct:.2f}%</span>'
        else:
            return f'<span class="flat">{change_pct:.2f}%</span>'
    
    @staticmethod
    def format_amount(amount: float) -> str:
        """格式化成交额"""
        if amount >= 1_000_000_000:
            return f"{amount/1_000_000_000:.2f}亿"
        elif amount >= 1_000_000:
            return f"{amount/1_000_000:.2f}万"
        else:
            return f"{amount:.0f}"
    
    @staticmethod
    def format_signal(signal: str) -> str:
        """格式化信号标签"""
        signal_map = {
            "巨量突破": "signal-breakout",
            "强势涨停": "signal-strong",
            "资金净流入": "signal-capital",
            "AI形态突破": "signal-ai",
        }
        css_class = signal_map.get(signal, "signal-default")
        return f'<span class="{css_class}">{signal}</span>'
