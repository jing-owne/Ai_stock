# Marcus量化选股系统 v1.5.0

> **模块化AI量化分析平台**，基于Agent架构设计，支持多策略选股、市场分析、报告生成与自动推送。

## 📌 项目描述

**AInvest** 是一套基于 **Agent架构** 的AI量化选股系统，综合放量上涨、多因子评分、AI技术面分析、机构追踪等多种策略，通过模块化设计实现灵活扩展。

### 核心特性

| 特性 | 说明 |
|------|------|
| 🏗️ **Agent架构** | 模块化设计，数据/市场/策略/报告四大Agent独立运行 |
| 📊 **多策略支持** | 5大量化策略：放量上涨、多因子、AI技术面、机构追踪等 |
| 🤖 **AI技术分析** | 形态识别 + 趋势置信度分析 |
| 📈 **回测功能** | 策略历史表现评估（收益率、胜率、夏普比率） |
| 📧 **自动推送** | 支持HTML/Markdown/JSON多格式报告邮件推送 |
| 💾 **数据缓存** | 智能缓存机制，减少重复请求 |
| 🔧 **健康检查** | 内置系统状态监控 |

---

## 🏗️ 系统架构

```
AInvest/
├── src/
│   ├── agents/              # Agent模块
│   │   ├── data_agent.py    # 数据获取Agent（多数据源支持）
│   │   ├── market_agent.py  # 市场分析Agent（情绪/风险评估）
│   │   ├── strategy_agent.py # 策略执行Agent（多策略注册）
│   │   └── report_agent.py  # 报告生成Agent（邮件/文件）
│   ├── core/                # 核心引擎
│   │   ├── engine.py        # 主引擎（协调各Agent）
│   │   ├── config.py        # 配置管理
│   │   └── types.py         # 类型定义
│   ├── data/                # 数据层
│   │   └── source.py        # 数据源抽象
│   ├── reports/             # 报告模块
│   │   ├── generator.py     # 报告生成器
│   │   ├── formatter.py     # 格式化器
│   │   ├── email_sender.py  # 邮件发送
│   │   └── templates/       # 报告模板
│   ├── strategies/          # 策略模块
│   │   └── registry.py     # 策略注册表
│   └── cli/                 # 命令行入口
│       ├── main.py          # CLI主程序
│       └── interactive.py   # 交互模式
├── configs/
│   └── settings.yaml        # 全局配置
├── examples/                # 使用示例
├── tests/                   # 测试用例
├── main.py                  # 程序入口
└── pyproject.toml           # 项目配置
```

---

## 📊 支持的选股策略

### 综合策略（推荐）

**Composite Strategy** - 整合5大选股策略，按照权重分配进行综合评分

| 子策略 | 权重 | 说明 |
|--------|------|------|
| 放量上涨策略 | 35% | 策略数量评分 |
| 成交额排名策略 | 30% | 基本面因子 |
| 多因子策略 | 15% | 趋势策略 |
| AI技术面策略 | 10% | 北向资金 |
| 机构追踪策略 | 10% | 机构动向 |

**基本面筛选条件：**
- ROE门槛: ≥8%
- 营收增长: ≥5%
- 胜率基础值: 50%
- 胜率门槛: 65%

### 单一策略

| 策略 | 说明 | 关键参数 |
|------|------|----------|
| **volume_surge** | 放量上涨策略 | 放量倍数≥2.0、涨幅≥1%、成交额≥1亿 |
| **turnover_rank** | 成交额排名策略 | 取前N名、最小成交额5亿 |
| **multi_factor** | 多因子评分策略 | 量/价/换手/技术面权重可配 |
| **ai_technical** | AI技术面分析 | 形态识别阈值75%、趋势置信度70% |
| **institution** | 机构追踪策略 | 机构数≥3、持股比例≥5% |
| **composite** | 综合策略（推荐） | 整合5大策略，按权重分配 |

---

## ⏰ 功能模块

### 1. 股票扫描 (scan)

```bash
# 综合策略扫描（推荐）- 整合5大策略
python main.py scan -s composite -l 20

# 放量上涨策略，扫描20只
python main.py scan -s volume_surge -l 20

# 多因子策略，生成HTML报告
python main.py scan -s multi_factor -l 20 --report -f html

# AI技术面策略，发送邮件
python main.py scan -s ai_technical -l 20 --report --email
```

### 2. 市场分析 (market)

```bash
# 分析当前市场状态
python main.py market
```

### 3. 策略回测 (backtest)

```bash
# 回测多因子策略
python main.py backtest -s multi_factor --start 2026-01-01 --end 2026-05-01
```

### 4. 健康检查 (health)

```bash
# 系统健康状态检查
python main.py health
```

### 5. 邮件测试 (email)

```bash
# 测试SMTP配置
python main.py email
```

---

## 🚀 快速使用

### 环境要求

```bash
Python 3.8+
pip install -r requirements.txt
```

### 配置文件 (configs/settings.yaml)

```yaml
# 数据源配置
data_source:
  provider: sina              # sina/tushare/eastmoney
  timeout: 30
  cache_enabled: true

# 策略配置
strategy:
  volume_surge:
    min_volume_ratio: 2.0
    min_price_change: 1.0
    min_amount: 100000000

# 邮件配置
email:
  enabled: true
  debug_mode: true           # True: 调试模式（不抄送）
  smtp_server: "smtp.qq.com"
  smtp_port: 465
  smtp_user: "your_email@qq.com"
  smtp_password: "your_auth_code"
  to_emails:
    - "receiver@example.com"
  cc_emails:
    - "cc@example.com"
  subject_prefix: "[Marcus量化选股]"
```

---

## 📋 报告示例

```
【Marcus量化选股系统】
扫描完成: volume_surge

 1. 浪莎股份(600137) - 评分: 88.5
    信号: 放量上涨, 资金流入, 趋势向好
    涨幅: +3.66%  成交额: 3.52亿

 2. 安彩高科(600207) - 评分: 85.2
    信号: 放量上涨, 换手活跃
    涨幅: +5.14%  成交额: 5.21亿

...
```

---

## ⚠️ 免责声明

**本系统仅供学习研究使用，不构成任何投资建议。**

- A股市场有风险，入市需谨慎
- 所有分析结果基于技术面量化模型，不保证准确性
- 量化模型存在局限性，请结合个人判断决策
- 建议分散持仓，单只仓位不超过总资金的20%
- 必须设置止损位（建议-5%），严格执行

---

## 🔄 更新日志

| 版本 | 日期 | 更新内容 |
|------|------|----------|
| v1.5.0 | 2026-05-09 | 模块化重构、Agent架构设计、多策略支持 |
| v1.0.0 | 2026-04-08 | 初始版本 |

