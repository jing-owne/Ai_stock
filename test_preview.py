"""
测试脚本 - 生成邮件预览
使用模拟数据生成完整的邮件预览，方便在浏览器中查看iPhone效果
"""
import sys
import os
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.reports.email_sender import format_email_html_responsive, EmailSender
from src.core.config import EmailConfig
from src.core.types import StockData, ScanResult, StrategyType


def create_mock_results():
    """创建模拟的扫描结果"""
    results = []
    today = datetime.now().strftime('%Y-%m-%d')
    
    stock_data = [
        ('000001.SZ', '平安银行', 12.45, 2.30, 1500000000, 85.5, ['放量上涨', '资金净流入', '趋势向上']),
        ('600036.SH', '招商银行', 35.67, 1.80, 2800000000, 82.3, ['放量上涨', '成交额排名', '趋势向上']),
        ('601318.SH', '中国平安', 48.23, 1.50, 2200000000, 78.9, ['多因子', '趋势向上', 'AI形态突破']),
        ('600519.SH', '贵州茅台', 1650.00, 0.80, 3500000000, 88.2, ['成交额排名', '机构追踪', '资金净流入']),
        ('000858.SZ', '五粮液', 128.50, -0.50, 1800000000, 76.4, ['放量上涨', 'AI形态突破']),
        ('300750.SZ', '宁德时代', 215.30, 3.20, 4200000000, 91.0, ['放量上涨', '成交额排名', '多因子', '趋势向上']),
        ('002594.SZ', '比亚迪', 268.40, 2.10, 3100000000, 84.7, ['放量上涨', '资金净流入', '多因子']),
        ('601012.SH', '隆基绿能', 28.90, -1.20, 900000000, 72.1, ['AI形态突破']),
        ('000333.SZ', '美的集团', 62.80, 0.60, 1600000000, 79.8, ['成交额排名', '机构追踪']),
        ('002475.SZ', '立讯精密', 35.20, 4.50, 2500000000, 86.3, ['放量上涨', '多因子', '趋势向上', 'AI形态突破']),
        ('603259.SH', '药明康德', 52.10, -0.80, 1200000000, 71.5, ['机构追踪']),
        ('600900.SH', '长江电力', 28.50, 0.30, 800000000, 74.2, ['成交额排名']),
        ('002352.SZ', '顺丰控股', 42.60, 1.90, 1100000000, 77.6, ['放量上涨', '趋势向上']),
        ('601888.SH', '中国中免', 85.20, -2.10, 1900000000, 68.9, ['资金净流入']),
        ('300059.SZ', '东方财富', 16.80, 3.80, 5000000000, 83.1, ['放量上涨', '成交额排名', '多因子', '趋势向上']),
    ]
    
    for symbol, name, close, change_pct, amount, score, signals in stock_data:
        data = StockData(
            symbol=symbol,
            name=name,
            date=today,
            close=close,
            open=round(close * (1 - change_pct / 200), 2),
            high=round(close * (1 + abs(change_pct) / 100), 2),
            low=round(close * (1 - abs(change_pct) / 150), 2),
            volume=round(amount / close, 0),
            amount=amount,
            change_pct=change_pct,
            turn_rate=2.5,
        )
        
        result = ScanResult(
            symbol=symbol,
            name=name,
            score=score,
            signals=signals,
            data=data,
            strategy=StrategyType.COMPOSITE,
        )
        results.append(result)
    
    return results


def main():
    """主函数"""
    print("=" * 60)
    print("生成邮件预览")
    print("=" * 60)
    
    # 创建模拟结果
    results = create_mock_results()
    
    # 创建邮件发送器
    config = EmailConfig(
        enabled=True,
        smtp_server='smtp.qq.com',
        smtp_port=465,
        smtp_user='test@qq.com',
        smtp_password='test',
        to_emails=['test@example.com'],
        cc_emails=[],
        debug_mode=True
    )
    
    sender = EmailSender(config)
    
    # 模拟策略上下文
    strategy_context = {
        'market_state': 'volatile',
        'weights': {
            'volume_surge': 0.30,
            'turnover_rank': 0.25,
            'multi_factor': 0.25,
            'ai_technical': 0.10,
            'institution': 0.10,
        }
    }
    
    # 使用 ReportAgent 生成摘要内容
    from src.agents.report_agent import ReportAgent
    from src.core.config import Config
    
    app_config = Config()
    report_agent = ReportAgent(app_config)
    
    print("\n1. 生成邮件内容摘要...")
    summary = report_agent.generate_summary(
        results=results,
        market_state=strategy_context.get('market_state'),
        strategy_weights=strategy_context.get('weights')
    )
    
    # 格式化为HTML（响应式版）
    print("2. 格式化为HTML（响应式）...")
    date_str = datetime.now().strftime('%Y-%m-%d')
    title = f"[Marcus量化选股小助手] {date_str} 动态策略报告"
    html_responsive = format_email_html_responsive(summary, title)
    
    # 保存响应式预览
    preview_file = "preview_email.html"
    with open(preview_file, 'w', encoding='utf-8') as f:
        f.write(html_responsive)
    print(f"   ✅ 响应式预览已保存: {preview_file}")
    
    # 生成iPhone 12模拟预览
    print("3. 生成iPhone 12模拟预览...")
    generate_iphone12_preview(html_responsive, title)
    
    print("\n" + "=" * 60)
    print("预览生成完成！")
    print("=" * 60)
    print(f"\n请在浏览器中打开 preview_iphone12.html 查看iPhone预览效果")
    print(f"直接查看 preview_email.html 可查看完整邮件效果")


def generate_iphone12_preview(html_content: str, title: str):
    """生成iPhone 12模拟预览"""
    preview_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>iPhone 12 邮件预览</title>
    <style>
        body {{
            margin: 0;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            min-height: 100vh;
        }}
        
        .iphone-frame {{
            max-width: 390px;
            margin: 20px auto;
            background: white;
            border-radius: 40px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
            position: relative;
        }}
        
        .iphone-notch {{
            background: #000;
            height: 30px;
            width: 150px;
            margin: 0 auto;
            border-radius: 0 0 20px 20px;
            position: relative;
            z-index: 10;
        }}
        
        .iphone-status-bar {{
            background: #000;
            color: white;
            padding: 8px 20px;
            display: flex;
            justify-content: space-between;
            font-size: 12px;
            font-weight: 600;
        }}
        
        .iphone-mail-header {{
            background: #F8F8F8;
            padding: 12px 16px;
            border-bottom: 1px solid #E5E5EA;
            display: flex;
            align-items: center;
        }}
        
        .iphone-mail-subject {{
            background: white;
            padding: 12px 16px;
            border-bottom: 1px solid #E5E5EA;
            font-size: 16px;
            font-weight: 600;
            color: #000;
        }}
        
        .email-content {{
            max-height: 75vh;
            overflow-y: auto;
            -webkit-overflow-scrolling: touch;
        }}
        
        .info {{
            text-align: center;
            color: white;
            margin: 20px 0;
            font-size: 14px;
        }}
        
        .bottom-nav {{
            background: #F8F8F8;
            padding: 8px 16px 20px 16px;
            border-top: 1px solid #E5E5EA;
            display: flex;
            justify-content: space-around;
            font-size: 10px;
            color: #8E8E93;
        }}
        
        .bottom-nav .active {{
            color: #007AFF;
        }}
        
        .bottom-nav div {{
            text-align: center;
        }}
        
        .bottom-nav .icon {{
            font-size: 20px;
            margin-bottom: 2px;
        }}
    </style>
</head>
<body>
    <div class="info">
        <h2 style="margin: 0 0 8px 0;">📱 iPhone 12 邮件预览</h2>
        <p style="margin: 0; opacity: 0.8;">以下是邮件在iPhone 12邮件应用中的显示效果</p>
    </div>
    
    <div class="iphone-frame">
        <div class="iphone-status-bar">
            <span>9:41</span>
            <span style="display: flex; align-items: center; gap: 4px;">
                <span>5G</span>
                <span>📶</span>
                <span>100%</span>
                <span>🔋</span>
            </span>
        </div>
        
        <div class="iphone-mail-header">
            <span style="font-size: 24px; margin-right: 12px; color: #007AFF;">‹</span>
            <div style="flex: 1;">
                <div style="font-weight: 600; font-size: 17px;">全部邮件</div>
                <div style="font-size: 12px; color: #8E8E93;">收件箱</div>
            </div>
            <span style="font-size: 20px; color: #007AFF;">✏️</span>
        </div>
        
        <div class="iphone-mail-subject">
            {title}
        </div>
        
        <div class="email-content">
            {html_content}
        </div>
        
        <div class="bottom-nav">
            <div class="active">
                <div class="icon">📧</div>
                <div>邮件</div>
            </div>
            <div>
                <div class="icon">📅</div>
                <div>日历</div>
            </div>
            <div>
                <div class="icon">📸</div>
                <div>照片</div>
            </div>
            <div>
                <div class="icon">⚙️</div>
                <div>设置</div>
            </div>
        </div>
    </div>
    
    <div class="info" style="margin-top: 30px; padding: 20px; background: rgba(255,255,255,0.1); border-radius: 16px;">
        <h3 style="margin: 0 0 12px 0;">✨ 本次优化项</h3>
        <div style="text-align: left; display: inline-block; max-width: 500px;">
            <p>1. 每日一言 - 使用hitokoto API</p>
            <p>2. 财经动态 - 整合金十数据、第一财经，智能过滤</p>
            <p>3. 策略配置 - 显示市场状态和策略权重</p>
            <p>4. 股票选择 - TOP15表格展示，统一底色</p>
            <p>5. 操作建议 - 现价/涨跌幅 + 建议买入价/止损/止盈</p>
            <p>6. 今日总结 - 综合分析和重点推荐</p>
            <p>7. 邮件标题 - [Marcus量化选股小助手] 日期 动态策略报告</p>
            <p>8. 风险提示 - 追加量化模型免责声明</p>
            <p>9. iPhone优化 - 标题色差区分、底色优化</p>
        </div>
    </div>
</body>
</html>"""
    
    with open("preview_iphone12.html", 'w', encoding='utf-8') as f:
        f.write(preview_html)
    
    print(f"   ✅ iPhone 12模拟预览已保存: preview_iphone12.html")


if __name__ == "__main__":
    main()
