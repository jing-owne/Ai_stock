# -*- coding: utf-8 -*-
"""
AI分析模块 - 调用大模型进行股票分析
参考: go-stock AI分析模块
"""

import json
import time
import requests
from config import AI_CONFIG


class AIAnalyzer:
    """AI分析器"""

    def __init__(self):
        self.config = AI_CONFIG
        self.enabled = AI_CONFIG.get('enabled', False)
        self.api_key = AI_CONFIG.get('api_key', '')

    def analyze_stocks(self, stocks, news=None):
        """
        AI分析股票列表
        参考: go-stock AI智能分析功能
        """
        if not self.enabled:
            print("⚠️ AI分析未启用")
            return self._default_analysis(stocks)

        if not self.api_key:
            print("⚠️ 未配置API密钥，使用默认分析")
            return self._default_analysis(stocks)

        print("\n🤖 正在调用AI分析...")

        try:
            # 构建分析提示
            prompt = self._build_analysis_prompt(stocks, news)

            # 调用API
            response = self._call_ai(prompt)

            if response:
                print("✅ AI分析完成")
                return response
            else:
                return self._default_analysis(stocks)

        except Exception as e:
            print(f"❌ AI分析失败: {e}")
            return self._default_analysis(stocks)

    def _build_analysis_prompt(self, stocks, news):
        """构建分析提示词"""
        # 股票信息
        stock_info = "\n".join([
            f"{i+1}. {s['name']}({s['code']}) - "
            f"现价:{s.get('price', 0):.2f} "
            f"涨幅:{s.get('change_pct', 0):.2f}% "
            f"换手:{s.get('turnover_rate', 0):.2f}% "
            f"PE:{s.get('pe', 0):.1f} "
            f"PB:{s.get('pb', 0):.1f}"
            for i, s in enumerate(stocks[:10])
        ])

        # 新闻摘要
        news_info = ""
        if news:
            news_info = "\n今日市场新闻:\n" + "\n".join([
                f"- {n.get('title', '')[:50]}" for n in news[:10]
            ])

        prompt = f"""你是一位专业的A股量化分析师，请分析以下股票并给出操作建议。

## 候选股票（按综合评分排序）
{stock_info}

{news_info}

## 分析要求
1. 从中选择3-5只最值得关注的股票
2. 分析每只股票的优势和风险点
3. 给出具体的操作建议（买入区间、止损位、目标位）
4. 提示当日市场整体情绪和注意事项

## 输出格式（简洁专业）
```
【精选股票】
1. [股票名称](代码)：推荐理由，简短操作建议
...

【市场情绪】
一句话描述当日市场整体情况

【风险提示】
需要关注的风险点
```

请用中文回复，保持简洁专业。"""

        return prompt

    def _call_ai(self, prompt):
        """调用AI API"""
        if self.config.get('provider') == 'deepseek':
            return self._call_deepseek(prompt)
        elif self.config.get('provider') == 'openai':
            return self._call_openai(prompt)
        else:
            return self._call_deepseek(prompt)

    def _call_deepseek(self, prompt):
        """调用DeepSeek API"""
        url = f"{self.config.get('base_url', 'https://api.deepseek.com')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.config.get('model', 'deepseek-chat'),
            "messages": [
                {"role": "system", "content": "你是一位专业的A股量化分析师，擅长技术分析和基本面分析。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": self.config.get('temperature', 0.7),
            "max_tokens": self.config.get('max_tokens', 2000)
        }

        try:
            response = requests.post(url, headers=headers, json=data, timeout=60)
            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content']
            else:
                print(f"❌ API调用失败: {response.status_code}")
                return None
        except Exception as e:
            print(f"❌ API调用异常: {e}")
            return None

    def _call_openai(self, prompt):
        """调用OpenAI API"""
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.config.get('model', 'gpt-3.5-turbo'),
            "messages": [
                {"role": "system", "content": "你是一位专业的A股量化分析师。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": self.config.get('temperature', 0.7),
            "max_tokens": self.config.get('max_tokens', 2000)
        }

        try:
            response = requests.post(url, headers=headers, json=data, timeout=60)
            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content']
            else:
                print(f"❌ API调用失败: {response.status_code}")
                return None
        except Exception as e:
            print(f"❌ API调用异常: {e}")
            return None

    def _default_analysis(self, stocks):
        """默认分析（当AI不可用时）"""
        if not stocks:
            return "今日暂无符合条件的股票。"

        # 统计分析
        up_count = sum(1 for s in stocks if s.get('change_pct', 0) > 0)
        avg_change = sum(s.get('change_pct', 0) for s in stocks) / len(stocks)
        avg_win_rate = sum(s.get('win_rate', 0) for s in stocks) / len(stocks)
        high_change = sum(1 for s in stocks if s.get('change_pct', 0) > 7)
        
        # 风险评估
        high_risk = sum(1 for s in stocks if s.get('risk_level') == '高风险')
        
        analysis = "【市场情绪分析】\n"
        analysis += f"- 今日选股{len(stocks)}只全部上涨，平均涨幅{avg_change:+.1f}%\n"
        analysis += f"- 平均预判胜率{avg_win_rate:.1f}%，整体质量较好\n"
        analysis += f"- 其中{high_change}只涨幅超过7%，{high_risk}只属高风险标的\n\n"
        
        analysis += "【综合建议】\n"
        analysis += "- 今日市场整体偏强势，但追高需谨慎\n"
        analysis += "- 建议重点关注🟡中风险标的，兼顾收益与安全\n"
        analysis += "- 严格设置止损位（-5%），控制单只仓位不超15%\n"
        analysis += "- 可考虑分批建仓，避免一次性全仓介入\n"

        return analysis


def generate_operation_advice(stock):
    """
    生成单只股票的操作建议
    参考: northstar 风险管理模块
    """
    advice = {}

    # 导入配置
    from config import STRATEGY_NORTHSTAR

    price = stock.get('price', 0)
    change_pct = stock.get('change_pct', 0)

    # 买入区间
    if price > 0:
        if change_pct > 5:
            # 涨幅过大，等待回调
            advice['action'] = '观望'
            advice['entry'] = f"建议等待回调至 {price * 0.97:.2f} 附近介入"
        elif change_pct > 0:
            # 小幅上涨，可以考虑
            advice['action'] = '轻仓'
            advice['entry'] = f"现价 {price:.2f} 可考虑轻仓介入"
        else:
            # 下跌或平盘
            advice['action'] = '关注'
            advice['entry'] = f"等待企稳，参考 {price:.2f} 附近"
    else:
        advice['action'] = '无法分析'
        advice['entry'] = "无实时价格数据"

    # 止损位
    risk = STRATEGY_NORTHSTAR.get('modules', {}).get('risk_management', {})
    stop_loss = risk.get('stop_loss', 0.05)
    advice['stop_loss'] = f"{price * (1 - stop_loss):.2f} (下跌{stop_loss*100:.0f}%)"

    # 止盈位
    take_profit = risk.get('take_profit', 0.15)
    advice['take_profit'] = f"{price * (1 + take_profit):.2f} (上涨{take_profit*100:.0f}%)"

    # 仓位建议
    if advice['action'] == '轻仓':
        advice['position'] = "10%-20%"
    elif advice['action'] == '观望':
        advice['position'] = "5%-10%"
    else:
        advice['position'] = "10%以内"

    return advice
