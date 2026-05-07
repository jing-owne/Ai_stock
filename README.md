# AI智能选股系统

综合 **go-stock**、**myhhub/stock**、**zvt**、**hikyuu**、**northstar** 的选股方法论，生成的智能选股系统。

## 📌 功能特点

- **多策略融合**：综合5大量化仓库的选股策略
- **AI智能分析**：调用大模型进行股票分析
- **实时数据**：动态获取全市场股票数据
- **邮件推送**：支持邮件订阅选股报告
- **DEBUG模式**：先调试后发送

## 📁 文件结构

```
ai_stock_selector/
├── config.py          # 配置文件
├── data_fetcher.py    # 数据获取模块
├── strategy_engine.py  # 选股策略引擎
├── ai_analyzer.py     # AI分析模块
├── mail_sender.py     # 邮件发送模块
├── main.py            # 主程序
├── automation.py      # 定时任务入口
└── README.md          # 说明文档
```

## 🔧 配置说明

### 1. 邮件配置 (config.py)

```python
EMAIL_CONFIG = {
    "enabled": True,           # 启用邮件发送
    "debug_mode": True,        # DEBUG模式（不实际发送）
    "smtp_server": "smtp.139.com",
    "smtp_port": 465,
    "smtp_user": "你的邮箱@139.com",
    "smtp_password": "你的授权码",  # 不是邮箱密码！
    "to_emails": ["接收邮箱"],
    "subject_prefix": "[AI选股]",
}
```

### 2. AI配置 (config.py)

```python
AI_CONFIG = {
    "enabled": True,
    "provider": "deepseek",  # deepseek / openai
    "api_key": "你的API密钥",
    "model": "deepseek-chat",
    "base_url": "https://api.deepseek.com",
}
```

**获取DeepSeek API密钥**：
1. 访问 https://platform.deepseek.com
2. 注册并登录
3. 创建API密钥

## 🚀 使用方法

### 1. 本地运行

```bash
cd c:/Users/admin/WorkBuddy/Claw/ai_stock_selector
python main.py
```

### 2. DEBUG模式（不发送邮件）

```bash
python main.py --debug
```

### 3. 不发送邮件

```bash
python main.py --no-email
```

## ⏰ 配置定时任务

### 方法1: 使用系统任务计划程序 (Windows)

1. 打开"任务计划程序"
2. 创建基本任务
3. 设置触发器（每天9:25执行）
4. 设置操作：
   - 程序: `python`
   - 参数: `main.py --no-email`
   - 起始位置: `C:\Users\admin\WorkBuddy\Claw\ai_stock_selector`

### 方法2: 使用WorkBuddy自动化

参考主程序的 `automation_update` 工具创建自动化任务。

## 📊 选股策略

| 策略 | 参考项目 | 权重 | 说明 |
|------|---------|------|------|
| go-stock AI | go-stock | 25% | AI分析市场情绪、资金流向 |
| myhhub多因子 | myhhub/stock | 25% | PE、PB、ROE、量价因子 |
| zvt多因子 | zvt | 25% | 估值+动量+质量因子 |
| hikyuu量化 | hikyuu | 15% | 布林带、均线排列 |
| northstar专业 | northstar | 10% | 技术分析+风险管理 |

## 📋 输出格式

```
【AI智能选股系统】

「每日一言」
   xxx

【股票选择】（按综合评分排序）

▶ 1. 股票名称(代码)
   综合评分: 85.5 | 预判胜率: 78.3%
   现价: 12.50 | 涨幅: +2.35%
   入选理由: 低PE, 趋势向好, 成交活跃

【操作建议】

▶ 股票名称(代码)
   操作: 轻仓 | 建议仓位: 10%-20%
   买入参考: 现价 12.50 可考虑轻仓介入
   止损位: 11.88 (下跌5%)
   止盈位: 14.38 (上涨15%)

【今日总结】
...
```

## ⚠️ 注意事项

1. **投资有风险**：本系统仅供参考，不构成投资建议
2. **先调试**：首次使用建议使用 `--debug` 模式
3. **配置API**：需要配置邮箱和AI密钥才能发送邮件
4. **过滤规则**：默认过滤688（科创板）开头股票

## 🔄 更新日志

- v1.0.0 (2026-04-08): 初始版本
