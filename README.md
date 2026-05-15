# Marcus 策略小助手 (AInvest) v2.1.0

> 基于 Agent 架构的 AI 量化选股平台，多策略融合、市场立场判断、动态报告、自动推送一体化
> v2.1 新增：K线双源智能切换（东财→新浪 Fallback）、策略降级容错、CLI bug 修复

---

## 📌 项目简介

**Marcus 策略小助手 (AInvest)** 是一套面向 A 股市场的 **AI 量化策略选股平台**，采用模块化 Agent 架构设计，整合**放量上涨、成交额排名、多因子、AI 技术面、机构追踪**等 5 大选股策略，通过加权融合生成综合评分，并基于 5 维度市场分析输出**激进/保守/观望**三档操作立场。每日自动采集财经动态、推送精选 TOP15 股票与操作建议，结果通过邮件自动推送。

```
┌─────────────────────────────────────────────────┐
│                 AInvest 系统                     │
│                                                 │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐       │
│  │ Data    │  │ Market  │  │Strategy │       │
│  │ Agent   │→ │ Agent   │→ │ Agent   │       │
│  └─────────┘  └─────────┘  └────┬────┘       │
│                                   │            │
│                              ┌────▼────┐       │
│                              │ Report  │       │
│                              │ Agent   │       │
│                              └─────────┘       │
└─────────────────────────────────────────────────┘
```

---

## 🏗️ 系统架构

```
ai_stock_selector/
├── main.py                     # 程序入口
├── configs/
│   └── settings.yaml           # 全局配置文件
├── src/
│   ├── agents/                 # Agent 模块（4大核心Agent）
│   │   ├── data_agent.py      # 数据采集Agent（腾讯/东财多源）
│   │   ├── market_agent.py    # 市场分析Agent（5维度立场判断）
│   │   ├── strategy_agent.py  # 策略执行Agent（多策略注册与执行）
│   │   └── report_agent.py    # 报告生成Agent（HTML/MD/JSON + 邮件）
│   ├── core/                  # 核心引擎
│   │   ├── engine.py          # AInvestEngine 主引擎
│   │   ├── config.py          # 配置管理（YAML加载 + fail-fast验证）
│   │   └── types.py          # 核心数据类型（StockData/ScanResult等）
│   ├── strategies/            # 策略模块
│   │   ├── base.py            # 策略基类（StrategyBase）
│   │   ├── registry.py        # 策略注册表（单例模式）
│   │   ├── strategy_type.py   # 策略类型枚举
│   │   ├── composite_strategy.py  # 综合策略（5策略加权融合）
│   │   ├── momentum/          # 动量策略组
│   │   │   ├── volume_surge.py    # 放量上涨策略
│   │   │   ├── turnover_rank.py   # 成交额排名策略
│   │   │   └── multi_factor.py    # 多因子策略
│   │   └── technical/         # 技术策略组
│   │       ├── ai_technical.py   # AI技术面策略
│   │       └── institution.py    # 机构追踪策略
│   ├── data/
│   │   └── source.py          # 数据源抽象层
│   ├── reports/               # 报告模块
│   │   ├── generator.py       # 报告生成器
│   │   ├── formatter.py       # 格式化工具（评分/涨跌幅/成交额）
│   │   ├── email_sender.py    # 邮件发送器（SMTP + HTML模板）
│   │   └── templates/
│   │       └── report_template.py  # HTML邮件模板
│   └── cli/                   # 命令行入口
│       ├── main.py            # CLI主程序（argparse）
│       └── interactive.py     # 交互模式
├── tests/unit/                # 单元测试
├── output/                    # 报告输出目录
├── requirements.txt
└── LICENSE                    # MIT License
```

---

## 🎯 核心特性

| 特性 | 说明 |
|------|------|
| 🤖 **Agent 架构** | 数据/市场/策略/报告四大Agent独立运行，易扩展 |
| 📊 **5大策略融合** | 放量上涨·成交额排名·多因子·AI技术面·机构追踪 |
| 🎯 **综合策略** | 按权重加权平均，基本面二次筛选（ROE≥8% 等） |
| 🌡️ **市场立场判断** | 5维度量化评分，输出激进/保守/观望三档立场 |
| 📧 **自动邮件推送** | 精美HTML报告 + 纯文本双格式，支持收件人/抄送人配置 |
| 🔄 **双源 Fallback** | K线数据东财→新浪智能切换，首次探测自动跳过不可用源 |
| 🛡️ **策略降级容错** | K线不可用时子策略自动降级，综合策略零结果兜底 |
| 💾 **智能缓存** | TTL缓存机制，减少重复请求，提升响应速度 |
| 📈 **回测功能** | 策略历史表现评估（收益率·胜率·夏普比率） |
| 🏥 **健康检查** | 内置系统状态监控，快速定位故障 |

---

## 🎯 市场立场判断系统

系统在每日报告中的 **「今日总结」** 栏目输出三档市场立场，辅助投资决策。

### 三档立场

| 立场 | 含义 | 操作建议 |
|------|------|----------|
| 🟢 **激进买入** (Aggressive Buy) | 市场强势，做多胜率高 | 可提高仓位，关注高弹性标的 |
| 🟡 **保守买入** (Conservative Buy) | 市场中性，谨慎做多 | 控制仓位，精选优质标的 |
| 🔴 **持币观望** (Hold / Cash) | 市场弱势，风险大于机会 | 轻仓或空仓，等待机会 |

### 判断依据（5个维度）

| # | 维度 | 数据来源 | 判断逻辑 |
|---|------|----------|----------|
| 1 | **沪深300指数** | 000300.SH | 涨跌幅 + 5日均线趋势方向 |
| 2 | **iVIX 中国波指** | 波动率指数 | <15 贪婪 / 15-25 中性 / >25 恐慌 |
| 3 | **股指期货升贴水** | IH / IF 期货 | 升水 = 多头信号，贴水 = 空头信号 |
| 4 | **全市场成交量** | 沪深总成交额 | vs 5日均量比值（量能趋势） |
| 5 | **外盘情绪** | 富时A50 + 恒生科技 | 盘前期货走势，A股领先指标 |

### 评分规则

```
综合得分 = Σ(各维度得分)

各维度得分:
- 沪深300: 涨幅>+1% 得+1分，跌幅>-1% 得0分，跌幅≤-1% 得-1分；站上5日均线再加+1分
- iVIX:    <15 得+2分，15-25 得0分，>25 得-2分
- 升贴水:  升水 得+1分，贴水 得-1分
- 成交量比: >1.2 得+2分，0.8-1.2 得0分，<0.8 得-2分
- 外盘:    A50+恒科全涨 +2分，涨跌各半 0分，全跌 -2分

立场判定:
  综合得分 ≥ 3  → 🟢 激进买入
  综合得分 0~2  → 🟡 保守买入
  综合得分 < 0   → 🔴 持币观望
```

### 邮件输出示例

```
════════════════════════════════════════
         📊 今日市场总结
════════════════════════════════════════

🎯 市场立场: 🟢 激进买入

📈 沪深300:  +1.23% ↑ (站上5日均线)
📉 iVIX指数: 18.5   (中性区域)
📊 期货升贴水: 升水 +0.15%
💹 成交量比:   1.35   (放量，量能充沛)
🌐 外盘情绪:   A50 +0.8%  恒科 +1.2%

综合评分: 6分 | 建议仓位: 60-80%

════════════════════════════════════════
```

---

## 📊 选股策略详解

### 综合策略（推荐）

**Composite Strategy** — 整合5大策略，按权重分配综合评分，叠加基本面筛选。

| 子策略 | 权重 | 类型 |
|--------|------|------|
| 放量上涨 (volume_surge) | 35% | 动量策略 |
| 成交额排名 (turnover_rank) | 30% | 资金策略 |
| 多因子 (multi_factor) | 15% | 综合评分 |
| AI技术面 (ai_technical) | 10% | 形态识别 |
| 机构追踪 (institution) | 10% | 主力动向 |

**基本面筛选门槛：**
- ROE ≥ 8%
- 营收增长 ≥ 5%
- 净利润增长 ≥ 10%
- 负债率 ≤ 60%
- 胜率门槛 ≥ 65%

```bash
# 使用综合策略扫描
python main.py scan -s composite -l 20
```

### 单一策略

| 策略标识 | 名称 | 核心逻辑 | 关键参数 |
|----------|------|----------|----------|
| `volume_surge` | 放量上涨 | 成交量突增 + 价格上涨 | 放量倍数≥2.0，涨幅≥1%，成交额≥1亿 |
| `turnover_rank` | 成交额排名 | 选取全市场成交额前N名 | top_n=20，最小成交额=5亿 |
| `multi_factor` | 多因子评分 | 量/价/换手/技术面加权 | volume=0.2, price=0.3, turnover=0.25, tech=0.25 |
| `ai_technical` | AI技术面 | K线形态识别 + 趋势置信度 | 形态阈值=75%，趋势置信度=70% |
| `institution` | 机构追踪 | 机构持股数量与比例 | 最少机构数=3，最低持股比例=5% |

---

## 🖥️ CLI 使用指南

### 全局参数

```bash
python main.py --help

-c, --config   配置文件路径  (默认: configs/settings.yaml)
--log-level    日志级别      (DEBUG/INFO/WARNING/ERROR, 默认 INFO)
```

### 子命令一览

| 命令 | 说明 |
|------|------|
| `scan` | 执行股票扫描（核心功能） |
| `market` | 分析当前市场状态 |
| `backtest` | 回测策略历史表现 |
| `email` | 测试邮件配置 |
| `list` | 列出所有可用策略 |
| `health` | 系统健康检查 |

### scan — 股票扫描

```bash
python main.py scan -s <策略> -l <数量> [--report] [-f <格式>] [--email]

参数:
  -s, --strategy   策略类型  (volume_surge/turnover_rank/multi_factor/ai_technical/institution/composite)
  -l, --limit      返回数量  (默认 20)
  --report          生成报告文件
  -f, --format     报告格式  (html/markdown/json, 默认 html)
  --email           发送邮件报告
```

**使用示例：**
```bash
# 综合策略扫描20只 + 生成报告 + 发送邮件（推荐）
python main.py scan -s composite -l 20 --report --email

# 放量上涨策略，扫描20只
python main.py scan -s volume_surge -l 20

# 多因子策略，生成HTML报告
python main.py scan -s multi_factor -l 20 --report -f html

# AI技术面策略，发送邮件
python main.py scan -s ai_technical -l 20 --report --email
```

### market — 市场分析

```bash
python main.py market
```

输出：市场情绪、板块热度、风险等级、5维度立场判断。

### backtest — 策略回测

```bash
python main.py backtest -s <策略> --start YYYY-MM-DD --end YYYY-MM-DD
```

### email — 邮件测试

```bash
python main.py email
```

### list — 策略列表

```bash
python main.py list
```

### health — 健康检查

```bash
python main.py health
```

---

## ⚙️ 配置文件 (configs/settings.yaml)

```yaml
# ==================== 数据源配置 ====================
data_source:
  provider: eastmoney           # 数据提供商: sina / tushare / eastmoney
  timeout: 30                   # 请求超时(秒)
  retry_times: 3                # 重试次数
  cache_enabled: true           # 启用缓存
  cache_ttl: 300                # 缓存TTL(秒)

# ==================== 策略配置 ====================
strategy:
  volume_surge:
    min_volume_ratio: 2.0       # 最小放量倍数
    min_price_change: 1.0       # 最小涨幅(%)
    min_amount: 100000000       # 最小成交额(元, 1亿)

  turnover_rank:
    top_n: 20                   # 取前N名
    min_amount: 500000000       # 最小成交额(元, 5亿)
    sort_desc: true             # 降序排列

  multi_factor:
    volume_weight: 0.2          # 成交量因子权重
    price_weight: 0.3           # 价格因子权重
    turnover_weight: 0.25       # 换手率因子权重
    tech_weight: 0.25           # 技术面因子权重
    min_score: 60               # 最低评分门槛

  ai_technical:
    pattern_threshold: 0.75     # 形态识别阈值
    trend_confidence: 0.70      # 趋势置信度

  institution:
    min_inst_count: 3           # 最少机构数
    min_inst_ratio: 0.05        # 最少机构持股比例

  composite_strategy:
    strategy_count_weight: 0.35 # 放量上涨权重
    myhhub_weight: 0.30         # 成交额排名权重
    hikyuu_weight: 0.15         # 多因子权重
    northstar_weight: 0.10       # AI技术面权重
    institution_weight: 0.10     # 机构追踪权重
    base_win_rate: 0.50          # 胜率基础值
    min_win_rate: 0.65           # 胜率门槛

  fundamental_filter:
    min_roe: 0.08               # ROE门槛 ≥8%
    min_revenue_growth: 0.05     # 营收增长 ≥5%
    min_profit_growth: 0.10      # 净利润增长 ≥10%
    max_debt_ratio: 0.60        # 最大负债率 ≤60%

# ==================== 报告配置 ====================
report:
  format: html                  # 报告格式: html / markdown / json
  include_charts: true          # 包含图表
  output_dir: ./output          # 输出目录
  max_stocks: 50               # 最大股票数

# ==================== 邮件配置 ====================
email:
  enabled: true                 # 启用邮件发送
  debug_mode: true              # 调试模式（跳过抄送，只发to_emails）
  skip_money_flow: true         # 跳过耗时资金流向查询
  sender_name: "Marcus策略师"
  smtp_server: "smtp.qq.com"
  smtp_port: 465                # SSL端口(推荐) / 587(TLS)
  smtp_user: "your_email@qq.com"
  smtp_password: "your_auth_code"
  to_emails:
    - "receiver@example.com"
  cc_emails:
    - "cc@example.com"
  subject_prefix: ""  # 已废弃，邮件标题由代码直接生成

# ==================== 全局设置 ====================
log_level: INFO                 # 日志级别
max_workers: 4                  # 最大并发数
enable_cache: true              # 启用缓存
```

---

## 📋 邮件报告示例

```
============================================================
【Marcus策略小助手】
报告日期: 2026年05月09日 15:30:00
============================================================

【策略说明】
- 综合策略: 整合5大策略，按权重综合评分
- 基本面筛选: ROE≥8%, 营收增长≥5%
- 评分机制: 综合评分 = Σ(策略评分 × 权重)

【市场立场】 🟢 激进买入（综合评分: 6分）

【股票选择】（按综合评分排序）
- 共筛选出 20 只优质股票
- 其中 15 只上涨，5 只下跌/平盘
- 平均涨幅: +2.35%
- 总成交额: 125.60亿

▶ Top 10 推荐股票
序号  股票名称      代码     综合评分  涨幅    成交额    入选信号
----------------------------------------------------------------
1     浪莎股份     600137   88.5     +3.66%  3.52亿   放量上涨,资金流入
2     安彩高科     600207   85.2     +5.14%  5.21亿   放量上涨,换手活跃
...

【操作建议】
▶ 1. 浪莎股份(600137)
   操作建议: 关注
   当前价格: 12.50元
   买入参考价: 12.25元（参考-2%）
   止损位: 11.88元（-5%）
   止盈位: 13.50元（+8%）

【风险提示】
- 以上仅供参考，不构成投资建议
- 股市有风险，投资需谨慎
```

---

## 🚀 快速开始

### 环境要求

```bash
Python 3.8+
pip install -r requirements.txt
```

### requirements.txt

```
requests>=2.28.0
pyyaml>=6.0
pytest>=7.0.0
black>=22.0.0
```

### 配置邮件（可选）

1. 开启QQ邮箱 SMTP：`设置 → 账户 → POP3/SMTP服务 → 开启`
2. 获取授权码（16位）
3. 填入 `configs/settings.yaml` 的 `email` 部分

### 首次运行

```bash
# 查看所有策略
python main.py list

# 测试邮件配置
python main.py email

# 运行综合策略（推荐）
python main.py scan -s composite -l 20 --report --email
```

---

## 📖 数据流

```
用户CLI输入
    │
    ▼
┌─────────────────┐
│  AInvestEngine  │  ← 主引擎协调
└──┬──────┬──────┘
   │      │
   ▼      ▼
DataAgent    StrategyAgent
获取数据  →  执行选股策略
   │           │
   ▼           ▼
MarketAgent  ← 获取市场数据
分析立场         │
   │           ▼
   │      ReportAgent
   │      生成报告 + 发送邮件
   ▼           ▼
 输出结果    邮件推送
```

---

## 🙏 致谢 / 参考项目

本项目在设计与实现过程中，参考了以下优秀的开源量化项目，在此致以诚挚的谢意：

| 项目 | 地址 | 参考内容 |
|------|------|----------|
| **stock (myhhub)** | [github.com/myhhub/stock](https://github.com/myhhub/stock) | 选股策略设计思路、实盘策略参考 |
| **star (hustcer)** | [github.com/hustcer/star](https://github.com/hustcer/star) | A股量化回测框架设计思路 |
| **stock (Rockyzsu)** | [github.com/Rockyzsu/stock](https://github.com/Rockyzsu/stock) | 多因子选股与评分模型参考 |
| **go-stock (ArvinLovegood)** | [github.com/ArvinLovegood/go-stock](https://github.com/ArvinLovegood/go-stock) | Go语言量化框架设计思路 |
| **zvt (foolcage)** | [gitee.com/foolcage/zvt](https://gitee.com/foolcage/zvt) | 金融数据框架、技术指标计算方式 |
| **Hikyuu 海阔量化** | [github.com/fasiondog/hikyuu](https://github.com/fasiondog/hikyuu) | 多因子策略设计、技术指标计算 |
| **东方财富 OpenAPI** | 公开数据接口 | K线数据、资金流向接口设计 |
| **腾讯行情接口** (qt.gtimg.cn) | 公开数据接口 | 免费实时行情数据获取方式 |

若您认为本项目的任何实现与您的开源项目有相似之处，欢迎联系，我们将在后续版本中补充完整的引用说明。

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
| **v2.0.0** | 2026-05-11 | 系统更名为"Marcus策略小助手"；新增每日一言、财经动态(金十/第一财经)、策略配置、今日总结模块；TOP15统一表格；操作建议优化；iPhone 12适配；版本号统一 |
| v1.5.0 | 2026-05-09 | 新增综合策略(5策略加权融合)；新增市场立场判断系统(5维度)；重写README文档 |
| v1.2.0 | 2026-04-20 | 新增AI技术面策略；新增机构追踪策略；邮件HTML模板优化 |
| v1.0.0 | 2026-04-08 | 初始版本；放量上涨+成交额排名+多因子策略；基础邮件推送 |

---

## 📄 License

[MIT License](LICENSE) — Copyright (c) 2024-2026 Marcus策略小助手 (AInvest)

---

**Built with ❤️ for A股量化研究**
