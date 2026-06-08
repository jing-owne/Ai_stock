# Marcus策略小助手 v2.6.5

> 基于 Agent 架构的 AI 量化策略分析平台 — 9大策略融合、市场立场判断、动态报告、自动邮件推送

---

## 项目简介

**Marcus策略小助手** 是一套面向 A 股市场的量化策略分析平台，采用模块化 Agent 架构：

- **9 大量化策略**：放量突破、成交额排名、多因子增强、AI技术面、箱体突破、均线趋势、底部反弹、连续小阳吸筹、资金净流入
- **加权融合评分**：综合 9 策略生成 Top 15 候选
- **5 维度市场立场判断**：输出激进/保守/观望三档操作立场
- **自动邮件推送**：HTML 报告 + MD 附件，每日定时发送
- **打新日历**：新股/新债独立分区，按申购日期降序展示

```
┌─────────────────────────────────────────────────┐
│              Marcus策略小助手 v2.6.5               │
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

## 项目结构

```
ai_stock_selector/
├── main.py                      # 程序入口
├── morning_task.py              # 早盘定时任务
├── new_bond_reminder.py         # 可转债打新提醒
├── configs/
│   └── settings.yaml            # 全局配置
├── src/
│   ├── agents/                  # 4大核心Agent
│   │   ├── data_agent.py       # 数据采集（腾讯/东财多源）
│   │   ├── market_agent.py     # 市场分析（5维度立场判断）
│   │   ├── strategy_agent.py   # 策略执行（多策略注册与调度）
│   │   └── report_agent.py     # 报告生成（HTML/MD + 邮件）
│   ├── core/                   # 核心引擎
│   │   ├── engine.py           # AInvestEngine 主引擎
│   │   ├── config.py           # 配置管理（YAML + fail-fast验证）
│   │   ├── types.py            # 核心数据类型与策略枚举
│   │   └── indicators/         # 技术指标模块（4子模块）
│   │       ├── compute.py      # SMA/RSI/MACD/BBANDS/VMA/重采样
│   │       ├── aggregator.py   # 40+指标聚合计算
│   │       ├── scores_basic.py # 技术面/形态/趋势/位置/防套/低吸 评分
│   │       └── scores_strategy.py  # 箱体/均线/回调/支撑/净流入/… 评分
│   ├── strategies/             # 策略模块（9大策略）
│   │   ├── base.py             # 策略基类
│   │   ├── registry.py         # 策略注册表
│   │   ├── composite_strategy.py  # 综合策略（9策略加权融合）
│   │   ├── momentum/           # 动量策略组
│   │   │   ├── volume_breakout.py     # 放量突破
│   │   │   ├── turnover_rank.py       # 成交额排名
│   │   │   ├── multi_factor.py        # 多因子增强
│   │   │   ├── consecutive_positive.py # 连续小阳吸筹
│   │   │   └── net_inflow.py          # 资金净流入
│   │   └── technical/          # 技术策略组
│   │       ├── ai_technical.py  # AI技术面
│   │       ├── box_breakout.py  # 箱体突破
│   │       ├── ma_trend.py      # 均线趋势
│   │       └── bottom_rebound.py # 底部反弹
│   ├── data/                   # 数据模块
│   │   ├── fetcher.py          # DataFetcher 包装层
│   │   ├── fetchers/           # 数据获取子模块
│   │   │   ├── news.py         # 每日一言 + 财经新闻
│   │   │   ├── calendar.py     # IPO + 可转债日历
│   │   │   └── market.py       # 市场态势
│   │   ├── kline_fetcher.py    # K线数据获取（东财/新浪）
│   │   ├── money_flow_fetcher.py   # 资金流向获取
│   │   └── daily_stock_filter.py   # 每日预过滤缓存（双源验证）
│   ├── reports/                # 报告模块
│   │   ├── generator.py        # 报告生成器
│   │   ├── email_sender.py     # 邮件发送器（SMTP + HTML）
│   │   └── templates/
│   └── cli/                    # 命令行入口
├── tests/unit/                 # 单元测试
├── output/                     # 报告输出
└── requirements.txt
```

---

## 核心特性

| 特性 | 说明 |
|------|------|
| 🤖 **Agent 架构** | 数据/市场/策略/报告 四大Agent独立运行，易扩展 |
| 📊 **9大策略融合** | 放量突破·成交额排名·多因子增强·AI技术面·箱体突破·均线趋势·底部反弹·连续小阳·资金净流入 |
| 🎯 **综合评分** | 按权重加权平均，策略命中数越多评分越高 |
| 🌡️ **市场立场判断** | 5维度量化评分（沪深300/iVIX/期货升贴水/成交量比/外盘情绪） |
| 📧 **自动邮件推送** | HTML报告 + MD附件，支持收件人/抄送人配置 |
| 🔄 **双源 Fallback** | K线数据东财→新浪智能切换，首次探测自动跳过不可用源 |
| 🛡️ **策略降级容错** | API失败自动降权，综合策略零结果兜底 |
| 💾 **每日预过滤缓存** | 首次扫描过滤股价>120/ST/688/退市/停牌，缓存复用 |
| 📋 **打新日历** | 新股 + 可转债独立分区，按申购日期降序 |
| 🏥 **健康检查** | 内置状态监控，快速定位故障 |

---

## 9大策略

### 综合策略（首选）

按权重加权融合 9 大策略，综合评分 = Σ(策略评分 × 权重)，策略命中数越多加分越多。

| 子策略 | 权重 | 类型 | 核心逻辑 |
|--------|:---:|------|----------|
| 放量突破 (volume_breakout) | 14% | 动量 | 量比≥2倍 + 突破新高/关键位 |
| 成交额排名 (turnover_rank) | 14% | 资金 | 全市场成交额 Top20 |
| 多因子增强 (multi_factor) | 17% | 综合 | 量/价/换手/机构多维度评分 |
| AI技术面 (ai_technical) | 8% | 形态 | K线形态识别 + 趋势置信度 |
| 箱体突破 (box_breakout) | 10% | 技术 | 30日箱体振幅<18% + 突破上沿 |
| 均线趋势 (ma_trend) | 12% | 趋势 | 多头排列 + 均线发散 |
| 底部反弹 (bottom_rebound) | 18% | 反转 | RSI超卖 + 底部形态确认 |
| 连续小阳 (consecutive_positive) | 4% | 吸筹 | 3-7天连续小阳线 + 温和放量 |
| 资金净流入 (net_inflow) | 3% | 资金 | 20日连续净流入天数统计 |

### 单一策略

```bash
# 使用综合策略扫描（推荐）
python main.py scan -s composite -l 15 --report --email

# 单一策略
python main.py scan -s volume_breakout -l 15
python main.py scan -s bottom_rebound -l 15
```

---

## 市场立场判断

系统每日报告输出三档市场立场：

| 立场 | 含义 | 操作建议 |
|------|------|----------|
| 🟢 激进买入 | 市场强势，做多胜率高 | 可提高仓位 |
| 🟡 保守买入 | 市场中性，谨慎做多 | 控制仓位 |
| 🔴 持币观望 | 市场弱势，风险大于机会 | 轻仓或空仓 |

### 5维度评分

| # | 维度 | 数据来源 | 判断逻辑 |
|---|------|----------|----------|
| 1 | 沪深300指数 | 000300.SH | 涨跌幅 + 5日均线趋势 |
| 2 | iVIX 中国波指 | 波动率指数 | <15 贪婪 / 15-25 中性 / >25 恐慌 |
| 3 | 股指期货升贴水 | IH/IF 期货 | 升水=多头，贴水=空头 |
| 4 | 全市场成交量 | 沪深总成交额 | vs 5日均量比值 |
| 5 | 外盘情绪 | 富时A50 + 恒生科技 | 盘前期货走势 |

```
综合得分 ≥ 3  → 🟢 激进买入
综合得分 0~2 → 🟡 保守买入
综合得分 < 0 → 🔴 持币观望
```

---

## CLI 命令

```bash
python main.py scan -s <策略> -l <数量> [--report] [--email]
python main.py market          # 市场分析
python main.py backtest        # 策略回测
python main.py list            # 列出所有策略
python main.py health          # 健康检查
python main.py email           # 测试邮件配置
```

**常用示例：**

```bash
# 综合策略扫描15只 + 生成报告 + 发送邮件（首选）
python main.py scan -s composite -l 15 --report --email

# 放量突破策略，扫描15只
python main.py scan -s volume_breakout -l 15

# 底部反弹策略，生成HTML报告
python main.py scan -s bottom_rebound -l 15 --report -f html
```

---

## 快速开始

### 环境要求

```bash
Python 3.8+
pip install -r requirements.txt
```

### 配置邮件（可选）

1. 开启QQ邮箱 SMTP：设置 → 账户 → POP3/SMTP服务 → 开启
2. 获取授权码（16位）
3. 填入 `configs/settings.yaml` 的 `email` 部分

### 首次运行

```bash
python main.py list                    # 查看所有策略
python main.py email                   # 测试邮件配置
python main.py scan -s composite -l 15 --report --email   # 运行综合策略
```

---

## 数据流

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
获取数据  →  执行量化策略
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

## 更新日志

| 版本 | 日期 | 更新内容 |
|------|------|----------|
| **v2.6.5** | 2026-06-08 | 代码重构：indicators 拆4模块 + fetcher 拆3模块；删除6个已合并旧文件；9大策略全部独立模块化；架构图/文档/CLI统一更新 |
| v2.6.0 | 2026-05-26 | 新增箱体突破+均线发散策略(共7大策略)；K线双源智能切换(东财→新浪Fallback)；策略降级容错；防套过滤器 |
| v2.5.0 | 2026-05-11 | 更名为"Marcus策略小助手"；新增每日一言、财经动态、策略配置、今日总结模块；TOP15统一表格；版本号规范制定 |
| v2.4.0 | 2026-05-09 | 新增综合策略(5策略加权融合)；新增市场立场判断(5维度)；每日预过滤缓存 |
| v2.3.0 | 2026-05-07 | 新增箱体突破/均线发散/RSI超卖策略；公共模块重构(html_engine/logger/time_utils) |
| v2.0.0 | 2026-04-20 | 新增AI技术面策略；新增机构追踪策略；邮件HTML模板优化 |
| v1.0.0 | 2026-04-08 | 初始版本：放量上涨+成交额排名+多因子策略；基础邮件推送 |

---

## 致谢

本项目参考了以下优秀的开源量化项目，致以诚挚谢意：

| 项目 | 地址 | 参考内容 |
|------|------|----------|
| **stock (myhhub)** | [github.com/myhhub/stock](https://github.com/myhhub/stock) | 策略设计思路 |
| **star (hustcer)** | [github.com/hustcer/star](https://github.com/hustcer/star) | A股量化回测框架 |
| **stock (Rockyzsu)** | [github.com/Rockyzsu/stock](https://github.com/Rockyzsu/stock) | 多因子策略与评分模型 |
| **go-stock (ArvinLovegood)** | [github.com/ArvinLovegood/go-stock](https://github.com/ArvinLovegood/go-stock) | Go语言量化框架 |
| **zvt (foolcage)** | [gitee.com/foolcage/zvt](https://gitee.com/foolcage/zvt) | 金融数据框架 |
| **Hikyuu 海阔量化** | [github.com/fasiondog/hikyuu](https://github.com/fasiondog/hikyuu) | 技术指标计算 |
| **东方财富 OpenAPI** | 公开数据接口 | K线数据/资金流向 |
| **腾讯行情接口** | 公开数据接口 | 实时行情数据 |

---

## 免责声明

**本工具仅供学习研究使用，不构成任何投资建议。**

- A股市场有风险，入市需谨慎
- 所有分析结果基于技术面量化模型，不保证准确性
- 量化模型存在局限性，请结合个人判断决策
- 建议分散持仓，单只仓位不超过总资金的 20%
- 必须设置止损位（建议 -5%），严格执行

---

## License

[MIT License](LICENSE) — Copyright (c) 2024-2026 Marcus策略小助手
