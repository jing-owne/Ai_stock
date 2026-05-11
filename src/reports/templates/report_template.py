"""
HTML报告模板
"""
from typing import List
from datetime import datetime
from ...core.types import ScanResult, MarketAnalysis


def get_html_template(results: List[ScanResult], analysis: MarketAnalysis = None) -> str:
    """获取HTML报告模板"""
    
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Marcus策略小助手 (AInvest) 股票扫描报告</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        
        .header {{
            background: white;
            border-radius: 16px;
            padding: 30px;
            margin-bottom: 24px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }}
        
        .header h1 {{
            color: #333;
            font-size: 28px;
            margin-bottom: 10px;
        }}
        
        .header .subtitle {{
            color: #666;
            font-size: 14px;
        }}
        
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-top: 20px;
        }}
        
        .stat-card {{
            background: #f8f9fa;
            border-radius: 12px;
            padding: 20px;
            text-align: center;
        }}
        
        .stat-card .value {{
            font-size: 32px;
            font-weight: bold;
            color: #667eea;
        }}
        
        .stat-card .label {{
            color: #666;
            font-size: 14px;
            margin-top: 5px;
        }}
        
        .section {{
            background: white;
            border-radius: 16px;
            padding: 30px;
            margin-bottom: 24px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }}
        
        .section-title {{
            font-size: 20px;
            color: #333;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #667eea;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        
        th, td {{
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }}
        
        th {{
            background: #f8f9fa;
            font-weight: 600;
            color: #333;
        }}
        
        tr:hover {{
            background: #f8f9fa;
        }}
        
        .score {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-weight: bold;
        }}
        
        .score-high {{
            background: #d4edda;
            color: #155724;
        }}
        
        .score-medium {{
            background: #fff3cd;
            color: #856404;
        }}
        
        .score-low {{
            background: #f8d7da;
            color: #721c24;
        }}
        
        .signal {{
            display: inline-block;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 12px;
            margin: 2px;
        }}
        
        .signal-breakout {{
            background: #e7f3ff;
            color: #004085;
        }}
        
        .signal-strong {{
            background: #d4edda;
            color: #155724;
        }}
        
        .signal-capital {{
            background: #cce5ff;
            color: #004085;
        }}
        
        .rise {{
            color: #dc3545;
            font-weight: bold;
        }}
        
        .fall {{
            color: #28a745;
            font-weight: bold;
        }}
        
        .footer {{
            text-align: center;
            color: white;
            padding: 20px;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📈 Marcus策略小助手 (AInvest) 股票扫描报告</h1>
            <p class="subtitle">生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            
            <div class="stats">
                <div class="stat-card">
                    <div class="value">{len(results)}</div>
                    <div class="label">扫描结果</div>
                </div>
"""
    
    if analysis:
        html += f"""
                <div class="stat-card">
                    <div class="value">{analysis.market_sentiment}</div>
                    <div class="label">市场情绪</div>
                </div>
                <div class="stat-card">
                    <div class="value">{analysis.risk_level}</div>
                    <div class="label">风险等级</div>
                </div>
"""
    
    html += """
            </div>
        </div>
"""
    
    if analysis:
        html += f"""
        <div class="section">
            <h2 class="section-title">市场分析</h2>
            <p>{analysis.summary}</p>
        </div>
"""
    
    html += """
        <div class="section">
            <h2 class="section-title">扫描结果</h2>
            <table>
                <thead>
                    <tr>
                        <th>排名</th>
                        <th>股票代码</th>
                        <th>股票名称</th>
                        <th>评分</th>
                        <th>涨跌幅</th>
                        <th>成交额</th>
                        <th>信号</th>
                    </tr>
                </thead>
                <tbody>
"""
    
    for i, result in enumerate(results[:30], 1):
        score_class = "score-high" if result.score >= 80 else "score-medium" if result.score >= 60 else "score-low"
        change_pct = result.data.change_pct if result.data else 0
        change_class = "rise" if change_pct > 0 else "fall"
        amount = result.data.amount if result.data else 0
        amount_str = f"{amount/1e8:.2f}亿" if amount >= 1e8 else f"{amount/1e4:.2f}万"
        
        signals_html = "".join([f'<span class="signal signal-breakout">{s}</span>' for s in result.signals[:3]])
        
        html += f"""
                    <tr>
                        <td>{i}</td>
                        <td>{result.symbol}</td>
                        <td><strong>{result.name}</strong></td>
                        <td><span class="score {score_class}">{result.score:.1f}</span></td>
                        <td class="{change_class}">{change_pct:+.2f}%</td>
                        <td>{amount_str}</td>
                        <td>{signals_html}</td>
                    </tr>
"""
    
    html += """
                </tbody>
            </table>
        </div>
        
        <div class="footer">
            <p>由 Marcus策略小助手 (AInvest) 自动生成 | 仅供参考，不构成投资建议</p>
        </div>
    </div>
</body>
</html>
"""
    
    return html
