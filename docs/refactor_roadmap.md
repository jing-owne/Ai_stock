# 策略重构与优化路线图（折中方案）

> 合并自: `strategy_refactor_plan.md` + `OPTIMIZE_PLAN.md`
> 版本: v2.0 | 日期: 2026-07-13 | 状态: 待执行

---

## 两方案对比与取舍

| 维度 | 用户方案 | 我的方案 | 折中选择 |
|------|---------|---------|---------|
| **策略目录名** | `aggregated/` | `stage/` | **`aggregated/`**（语义更清晰） |
| **旧策略文件** | 保留（备查） | 删除 | **保留备查，标记废弃** |
| **互斥逻辑** | 4级优先级（bottom>launch>trend>money） | 仅 bottom↔trend 互斥 | **取后者**（简单可靠） |
| **重构前提交** | 无明确要求 | Phase 0 先 commit baseline | **先提交基线** |
| **strategy_type.py** | 明确删除 | 未提 | **保留（下游可能依赖）** |
| **验证方式** | 单元测试+集成测试+回测 | walk-forward 回测+对比 | **两者都做** |
| **总时间估算** | 5-9天 | 10-13小时 | **2-3天** |

---

## 第零阶段：建立回测基线（0.5天）

> **目的**：在重构前建立回测基线，作为重构后的对比基准。必须在阶段1动手之前完成。

### Step 0.1 建立代码基线（git 分支）+ 运行回测基线

**① 建立 git 基线分支（2026-07-14 修正）**

> **分支模型（权威，用户 2026-07-14 15:58 定性）**：
> - `Releases` = **生产运行**（已部署生产分支）
> - `pro` = **本次重构新建基线**（重构执行落点，仅合入验证过的代码）
> - `dev` = **本地调试**（日常 WIP 在此，不污染 `pro`）
> - 重构按本方案执行时，**选中本地 `pro` 分支**；`origin` 暂不考虑提交代码（不 push）。

- 当前 `dev` 的 `HEAD = 8d16cde`（含 K线数据源重构 + TDX 数据源开关）即干净提交；`pro` 已从此拉出（`pro` = `8d16cde`）。
- ⚠️ **pro 已存在**：再次执行 `git branch pro` 会报 "already exists" 错误。统一用「确认/重置」写法：`git rev-parse --verify pro >/dev/null 2>&1 && echo "pro 已存在" || git branch pro 8d16cde`；若需强制对齐到 `8d16cde` 则 `git branch -f pro 8d16cde`。
- **为什么 `pro=8d16cde` 是合适基线**：它比 `Releases(0589535)` 更先进（含 K线重构 + TDX 开关），且本方案所有代码补丁（legacy_mode 整体切换、聚合基类横截面例外、`scan(as_of)` 前置依赖等）均对照 `8d16cde` 真实代码逐行核验，落基一致、风险最低。
  - 若要求重构**严格从生产干净线起基**（即 `Releases/0589535`），执行前重置：`git branch -f pro 0589535`；届时本方案部分补丁需重新对照 `0589535` 校验。
- ⚠️ **执行重构前，先把 `dev` 的 live 修复本地提交进 `pro`**（不 push origin）：
  - `bottom_rebound.py` 月线门槛 35→26、`launch_fingerprint` 的 `fp['fingerprint']` 修复（已修 bug，应进生产）；
  - 与"废弃 TDX 分支"一致的删除：`strategy_analysis_tdx.py`、`backtest/runner.py`。
  - 操作：`git checkout pro` → `git checkout dev -- <上述文件>`（或 `git cherry-pick` 对应提交）→ `git commit`，使重构建在**已修正**代码之上。

**② 运行回测基线（walk-forward legacy 模式，替代已删的 runner.py）**

```bash
python -m backtest.enhanced.walk_forward \
    --universe all --legacy-mode \
    --top-n 15 --horizons 5,10,20 --cadence daily \
    --start 2026-01-01 --end 2026-07-14
# 输出：cache/backtest/{end}/report.json（年化/回撤/胜率/选股数）
```

> 该基线指标填入 Step 0.2 表格，作为 P2 验收门禁（legacy vs stage 对比）的参照。

### Step 0.2 记录基线数据

| 指标 | 基线值 | 备注 |
|------|--------|------|
| 年化收益 | - | 旧10策略模式 |
| 最大回撤 | - | 旧10策略模式 |
| 选股数量 | - | 旧10策略模式 |
| 胜率 | - | 旧10策略模式 |

---

## 第一阶段：提交基线 + 清理遗留Bug（0.5天）

### Step 1.1 提交今日修复（15分钟）

```bash
git add -A
git commit -m "fix: 2026-07-13 Bug修复+优化"
git push origin dev
```

### Step 1.2 修复用户方案中未覆盖的问题（1小时）

以下问题已在本日修复，但用户方案中仍标注为"待修复"，此处确认：

| 用户方案中的 Bug | 实际状态 | 确认方式 |
|-----------------|---------|---------|
| `sustained_uptrend` 恒 False | ✅ 已修（预取 180→600） | `prefetch.py:18` 默认参数 days=600；`composite_strategy.py:389-394` 调用 prefetch_kline_indicators |
| `breakout_20d/60d` 键名不匹配 | ✅ 已修（兼容新老键名） | `volume_breakout.py:91-92` `indicators.get("breakout_20d_high", False) or indicators.get("breakout_20d", False)` |
| 单策略模式不注入 `_indicators` | ✅ 已修 | `strategy_agent.py:51-53` 调用 `_prefetch_and_inject_indicators`；`strategy_agent.py:68-82` 实现预取注入逻辑 |
| `_PARAM_MAP` 映射不全 | ✅ 已修 | `strategy_agent.py:159` 补充 `launch_fingerprint` 映射 |
| bottom_rebound 多周期确认失效 | ✅ 已修 | `prefetch.py:19` 默认参数 `keep_kline=True`；`strategy_agent.py:75` 单策略模式调用时 `keep_kline=False`（需注意） |
| 月线门槛太高 | ✅ 已修 35→26 | `bottom_rebound.py:92` |

### Step 1.3 修复尚未覆盖的问题（2小时）

| # | 问题 | 位置 | 修法 |
|---|------|------|------|
| 1 | `src/strategies/strategy_type.py` 废弃文件 | 根目录 | **暂不删除**（确认无 import 后再清） |
| 2 | `_PARAM_MAP` 中仍有旧映射名（`volume_surge`→`volume_breakout`） | `strategy_agent.py:130-137` | 统一映射名为策略类名 |
| 3 | `_get_strategy_params` 中仍用旧键名（`volume_surge`/`ma_divergence`） | `strategy_agent.py:145-146` | 改为 `volume_breakout`/`ma_trend` |
| 4 | bottom_rebound 单策略模式 `keep_kline=False` | `strategy_agent.py:75` | 改为 `keep_kline=True`，或根据策略类型动态决定 |
| 5 | 方案中的 `features[3]` 当涨幅 | `REFACTOR_PLAN.md` 示例代码 | 改为 `features[0]` |
| 6 | 方案中的月线门槛 `>=35` | `REFACTOR_PLAN.md` 示例代码 | 改为 `>=26` |

> **注意**：LaunchFingerprintStrategy 加入 SUB_STRATEGIES 的问题由阶段2方案A统一解决（仅在 LaunchStrategy 内部以0.35权重聚合，不入 SUB_STRATEGIES），此处不再处理。

---

## 第二阶段：创建聚合策略层（2天）

### 核心原则

- **保留旧策略文件**（移入 `archive/` 备查，不删除）
- **新建聚合策略** 在 `src/strategies/aggregated/` 下
- **旧策略注册表不变**，新增聚合策略映射
- **互斥逻辑简化**：仅 Bottom ↔ Trend 互斥，Launch/Money 不参与

### 目录结构

```
src/strategies/
├── aggregated/                  # 新建：聚合策略层
│   ├── __init__.py
│   ├── bottom_strategy.py       # 底部 + 连续小阳
│   ├── launch_strategy.py       # 放量突破 + 箱体 + 指纹
│   ├── trend_strategy.py        # 追涨 + 均线 + AI技术面
│   └── money_strategy.py        # 资金 + 成交额 + 多因子
├── momentum/                    # 保留（子策略不删）
├── technical/                   # 保留（子策略不删）
├── aggregated/ # 后续迁入 archive/
├── base.py
├── composite_strategy.py        # 修改：编排聚合策略 + 保留旧策略映射
└── registry.py                  # 修改：注册4个聚合策略
```

### Step 2.1 策略合并映射

| 聚合策略 | 子策略 | 内部权重 |
|---------|-------|---------|
| **BottomStrategy** | BottomRebound + ConsecutivePositive | 0.6 : 0.4 |
| **LaunchStrategy** | VolumeBreakout + BoxBreakout + LaunchFingerprint | 0.35 : 0.30 : 0.35 |
| **TrendStrategy** | TrendConfirmation + MATrend + AITechnical | 0.35 : 0.35 : 0.30 |
| **MoneyStrategy** | NetInflow + TurnoverRank + MultiFactor | 0.35 : 0.30 : 0.35 |

### Step 2.2 动态权重（市场状态驱动）

```python
# composite_strategy.py — MARKET_STATE_WEIGHTS 改为4聚合权重
MARKET_STATE_WEIGHTS = {
    "trend_up": {
        "bottom": 0.05,
        "launch": 0.15,
        "trend": 0.35,
        "money": 0.30,
    },
    "trend_down": {
        "bottom": 0.45,
        "launch": 0.10,
        "trend": 0.20,
        "money": 0.25,
    },
    "volatile": {
        "bottom": 0.30,
        "launch": 0.20,
        "trend": 0.25,
        "money": 0.25,
    },
}
```

### Step 2.3 互斥规则（仅 Bottom ↔ Trend）

```python
# composite_strategy.py — SUB_STRATEGIES 改为4项聚合策略
SUB_STRATEGIES = [
    ("bottom", BottomStrategy),
    ("launch", LaunchStrategy),
    ("trend", TrendStrategy),
    ("money", MoneyStrategy),
]

# STRATEGY_NAMES 同步更新为4聚合策略
STRATEGY_NAMES = {
    "bottom": "底部策略",
    "launch": "启动策略",
    "trend": "追涨策略",
    "money": "资金策略",
}
```

互斥规则：
- 连续下跌≥3天 → 抑制 Trend（保留 Bottom）
- 连续上涨≥3天 → 抑制 Bottom（保留 Trend）
- 其他情况 → 两策略均保留（分数折扣 0.7x）

### Step 2.3.0 CompositeStrategy._apply_mutual_exclusion 方法（互斥逻辑实现）

```python
# composite_strategy.py — 新增互斥逻辑
def _apply_mutual_exclusion(self, results: List[ScanResult], market_data: List[StockData]) -> List[ScanResult]:
    """
    应用互斥规则：Bottom ↔ Trend 互斥
    
    Args:
        results: 策略执行结果列表
        market_data: 市场数据（用于判断趋势）
    
    Returns:
        应用互斥规则后的结果列表
    """
    if self._legacy_mode:
        # 旧模式不应用互斥规则
        return results
    
    # 判断市场趋势（基于标的平均涨跌幅）
    trend_direction = self._detect_market_trend(market_data)
    
    if trend_direction == "down":
        # 连续下跌≥3天：抑制 Trend，保留 Bottom
        return [
            r for r in results 
            if r.strategy != StrategyType.TREND or r.strategy == StrategyType.BOTTOM
        ]
    elif trend_direction == "up":
        # 连续上涨≥3天：抑制 Bottom，保留 Trend
        return [
            r for r in results 
            if r.strategy != StrategyType.BOTTOM or r.strategy == StrategyType.TREND
        ]
    else:
        # 震荡行情：两策略均保留，分数折扣 0.7x
        for r in results:
            if r.strategy in [StrategyType.BOTTOM, StrategyType.TREND]:
                r.score = round(r.score * 0.7, 1)
        return results

def _detect_market_trend(self, market_data: List[StockData]) -> str:
    """
    判断市场趋势
    
    Returns:
        "up"（连续上涨≥3天）/ "down"（连续下跌≥3天）/ "volatile"（震荡）
    """
    # 简化实现：基于当日平均涨跌幅
    avg_change = sum(s.change_pct for s in market_data) / len(market_data)
    
    if avg_change > 1.0:
        return "up"
    elif avg_change < -1.0:
        return "down"
    return "volatile"

# 在 CompositeStrategy.execute 中调用（策略执行完成后、结果汇总前）
def execute(self, market_data: List[StockData], params: Dict[str, Any]) -> List[ScanResult]:
    # ... 策略执行逻辑 ...
    
    # 应用互斥规则（新模式）
    results = self._apply_mutual_exclusion(results, market_data)
    
    # ... 结果汇总逻辑 ...
    return results
```

### Step 2.3.1 CompositeStrategy._get_weights 方法更新

```python
# composite_strategy.py — _get_weights 根据 legacy_mode 切换权重表
# 真实签名：(self, params, market_state)，params 是 execute() 的入参
def _get_weights(self, params: Dict[str, Any], market_state: str) -> Dict[str, float]:
    composite = params.get("composite_strategy", {}) if params else {}
    use_dynamic = composite.get("dynamic_weights", True)
    manual = composite.get("manual_weights", {}) or {}

    # 根据 legacy_mode 切换权重表
    if self._legacy_mode:
        # 旧模式：10策略权重
        if not use_dynamic:
            return {
                "volume_breakout": composite.get("volume_breakout_weight", 0.14),
                "turnover_rank": composite.get("turnover_rank_weight", 0.14),
                "multi_factor": composite.get("multi_factor_weight", 0.14),
                "ai_technical": composite.get("ai_technical_weight", 0.12),
                "box_breakout": composite.get("box_breakout_weight", 0.10),
                "ma_trend": composite.get("ma_trend_weight", 0.10),
                "bottom_rebound": composite.get("bottom_rebound_weight", 0.10),
                "consecutive_positive": composite.get("consecutive_positive_weight", 0.08),
                "net_inflow": composite.get("net_inflow_weight", 0.08),
                "trend_confirmation": composite.get("trend_confirmation_weight", 0.08),
            }
        # 动态权重：旧 MARKET_STATE_WEIGHTS_OLD（10策略）
        weights = dict(self.MARKET_STATE_WEIGHTS_OLD.get(market_state, self.MARKET_STATE_WEIGHTS_OLD["volatile"]))
    else:
        # 新模式：4聚合策略权重
        if not use_dynamic:
            return {
                "bottom": composite.get("bottom_weight", 0.25),
                "launch": composite.get("launch_weight", 0.25),
                "trend": composite.get("trend_weight", 0.25),
                "money": composite.get("money_weight", 0.25),
            }
        # 动态权重：新 MARKET_STATE_WEIGHTS（4聚合）
        weights = dict(self.MARKET_STATE_WEIGHTS.get(market_state, self.MARKET_STATE_WEIGHTS["volatile"]))

    if manual:
        weights.update(manual)

    # ── API失败的策略降权到0，权重重新分配 ──
    if self._api_failed:
        removed_weight = 0
        for key in list(weights.keys()):
            if key in self._api_failed:
                removed_weight += weights.pop(key, 0)
        if removed_weight > 0 and weights:
            total = sum(weights.values())
            for k in weights:
                weights[k] += removed_weight * weights[k] / total
        self.logger.info(f"API失败策略已降权: {self._api_failed}")

    # 归一化（浮点舍入修正）
    total = sum(weights.values())
    if total > 0 and abs(total - 1.0) > 1e-6:
        weights = {k: v / total for k, v in weights.items()}
    return weights
```

### Step 2.3.2 legacy_mode 配置项（整体切换策略捆绑）

> **需求**：重构后新旧代码并行运行，确保稳定输出。
> 
> **关键修正**：必须整体切换 SUB_STRATEGIES / STRATEGY_NAMES / MARKET_STATE_WEIGHTS / _get_weights 手动模式，缺一不可。

```python
# composite_strategy.py — 新增 legacy_mode 支持（整体切换）

class CompositeStrategy(BaseStrategy):
    """综合策略：纯编排层，所有子策略均为独立模块"""

    # ── 旧模式权重表（10策略）──
    MARKET_STATE_WEIGHTS_OLD = {
        "trend_up": {
            "volume_breakout": 0.15, "turnover_rank": 0.15, "multi_factor": 0.15,
            "ai_technical": 0.12, "box_breakout": 0.10, "ma_trend": 0.10,
            "bottom_rebound": 0.08, "consecutive_positive": 0.07,
            "net_inflow": 0.08, "trend_confirmation": 0.05,
        },
        "trend_down": {
            "bottom_rebound": 0.20, "consecutive_positive": 0.15, "ma_trend": 0.15,
            "volume_breakout": 0.12, "box_breakout": 0.10, "multi_factor": 0.10,
            "ai_technical": 0.08, "turnover_rank": 0.08,
            "net_inflow": 0.05, "trend_confirmation": 0.02,
        },
        "volatile": {
            "volume_breakout": 0.14, "turnover_rank": 0.14, "multi_factor": 0.14,
            "ai_technical": 0.12, "box_breakout": 0.10, "ma_trend": 0.10,
            "bottom_rebound": 0.10, "consecutive_positive": 0.08,
            "net_inflow": 0.08, "trend_confirmation": 0.08,
        },
    }

    # ── 新模式权重表（4聚合策略）──
    MARKET_STATE_WEIGHTS = {
        "trend_up": {
            "bottom": 0.05, "launch": 0.15, "trend": 0.35, "money": 0.30,
        },
        "trend_down": {
            "bottom": 0.45, "launch": 0.10, "trend": 0.20, "money": 0.25,
        },
        "volatile": {
            "bottom": 0.30, "launch": 0.20, "trend": 0.25, "money": 0.25,
        },
    }

    def __init__(self, kline_fetcher: Optional[KlineFetcher] = None):
        super().__init__()
        self.logger = logging.getLogger("AInvest.CompositeStrategy")
        self._last_market_state: str = "volatile"
        self._last_weights: Dict[str, float] = {}
        self._last_sub_results: Dict[str, Dict[str, ScanResult]] = {}
        self._kline_fetcher = kline_fetcher or KlineFetcher(max_workers=8, delay_per_request=0.015)
        self._kline_cache: Dict[str, List[StockData]] = {}
        self._indicator_cache: Dict[str, Dict[str, float]] = {}
        self._money_flow_fetcher = MoneyFlowFetcher(max_workers=4)
        self._api_failed: set = set()
        
        # ── 加载 strategy_config.json（运行时开关）──
        self._skip_money_flow = False
        self._legacy_mode = False
        self._load_strategy_config()
        
        # ── 根据 legacy_mode 整体切换策略捆绑 ──
        if self._legacy_mode:
            # 旧模式：10策略
            self.SUB_STRATEGIES = [
                ("volume_breakout", VolumeBreakoutStrategy),
                ("turnover_rank", TurnoverRankStrategy),
                ("multi_factor", MultiFactorStrategy),
                ("ai_technical", AITechnicalStrategy),
                ("box_breakout", BoxBreakoutStrategy),
                ("ma_trend", MATrendStrategy),
                ("bottom_rebound", BottomReboundStrategy),
                ("consecutive_positive", ConsecutivePositiveStrategy),
                ("net_inflow", NetInflowStrategy),
                ("trend_confirmation", TrendConfirmationStrategy),
            ]
            self.STRATEGY_NAMES = {
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
            }
        else:
            # 新模式：4聚合策略
            self.SUB_STRATEGIES = [
                ("bottom", BottomStrategy),
                ("launch", LaunchStrategy),
                ("trend", TrendStrategy),
                ("money", MoneyStrategy),
            ]
            self.STRATEGY_NAMES = {
                "bottom": "底部策略",
                "launch": "启动策略",
                "trend": "追涨策略",
                "money": "资金策略",
            }
        
        # ── 实例化所有子策略 ──
        self._strategies: Dict[str, BaseStrategy] = {}
        for key, cls in self.SUB_STRATEGIES:
            instance = cls()
            self._strategies[key] = instance

    def _load_strategy_config(self):
        """加载 strategy_config.json 并缓存（运行时开关）"""
        import json as _json
        try:
            with open('strategy_config.json', 'r', encoding='utf-8') as _f:
                _cfg = _json.load(_f)
            if _cfg.get('skip_money_flow', False):
                self._skip_money_flow = True
                self.logger.info('配置跳过资金净流入策略（skip_money_flow=true）')
            # ── legacy_mode 配置（运行时开关，放在 strategy_config.json）──
            if _cfg.get('legacy_mode', False):
                self._legacy_mode = True
                self.logger.info('启用旧模式（legacy_mode=true）')
        except Exception:
            pass

# strategy_config.json 中配置（运行时开关）
# {
#   "tdx_enabled": false,
#   "holdings": [...],
#   "skip_money_flow": true,
#   "legacy_mode": false,  // true=旧10策略模式，false=新4聚合策略模式
#   "launch_fingerprint": {...}
# }
```

**并行验证流程：**
1. 每日 `morning_task.py` 可同时跑两套（通过修改 strategy_config.json 的 legacy_mode 控制）
2. 对比输出结果，确认一致性
3. 验证1-2周后，确认新代码稳定，再移除 `legacy_mode`

### Step 2.4 前置条件：扩展 StrategyType 枚举

在执行前，必须在 `src/core/types.py` 中新增 4 个聚合策略的枚举值：

```python
class StrategyType(Enum):
    # ... 现有枚举值保持不变 ...

    # 新增：4个聚合策略类型
    BOTTOM = "bottom"       # 底部策略（聚合）
    LAUNCH = "launch"       # 启动策略（聚合）
    TREND = "trend"         # 追涨策略（聚合）
    MONEY = "money"         # 资金策略（聚合）
```

### Step 2.5 启动指纹纳入方式（方案A）

**关键决策**：LaunchFingerprintStrategy **不加入** `CompositeStrategy.SUB_STRATEGIES`，仅在 `LaunchStrategy` 内部以 0.35 权重聚合。理由：

- 避免指纹策略被执行两次（SUB_STRATEGIES 跑一次 + LaunchStrategy 内部再跑一次）
- 语义上指纹是"启动信号"的一个子模块，不应独立参与综合评分
- 旧注册表映射保留：`registry.py` 中 `StrategyType.LAUNCH_FINGERPRINT` 指向 `LaunchStrategy` 实例（向后兼容）

```python
# registry.py 中新增：注册4个聚合策略 + 向后兼容映射
# 在现有10大策略注册之后、COMPOSITE注册之前添加：

# ── 新增：4个聚合策略 ──
cls._strategies[StrategyType.BOTTOM] = BottomStrategy()
cls._strategies[StrategyType.LAUNCH] = LaunchStrategy()
cls._strategies[StrategyType.TREND] = TrendStrategy()
cls._strategies[StrategyType.MONEY] = MoneyStrategy()

# ── 向后兼容：旧策略类型映射到聚合策略 ──
cls._strategies[StrategyType.LAUNCH_FINGERPRINT] = cls._strategies[StrategyType.LAUNCH]
# 以下映射保持不变（仍指向原始子策略实例，独立运行时可用）
# cls._strategies[StrategyType.VOLUME_SURGE] = cls._strategies[StrategyType.VOLUME_BREAKOUT]
# ... 其余向后兼容映射不变
```

### Step 2.5.1 聚合策略统一基类 AggregatedStrategy（采纳用户建议）

用户建议所有聚合策略复用同一基类，避免 4 个类各自重复编排循环。该模式**采纳**，作为统一框架。

```python
class AggregatedStrategy(BaseStrategy):
    """聚合策略基类：复用编排循环，子类只声明 _sub_strategies 与 strategy_type"""

    def __init__(self):
        super().__init__()
        self._sub_strategies: List[Tuple[BaseStrategy, float]] = []  # [(实例, 权重), ...]
        self._indicators: Dict[str, Dict] = {}
        self._kline_cache: Dict[str, list] = {}   # 供指纹子策略复用（见 Step 2.7）

    def execute(self, market_data, params):
        # ① 独立运行（非 Composite 注入）时自拉预取，保证 --strategy bottom 等单策略模式可用
        if not self._indicators:
            self._self_prefetch(market_data)

        results = []
        for stock in market_data:
            indicators = self._indicators.get(stock.symbol, {})
            if not indicators:
                continue

            # ② 向子策略传播共享缓存（避免子策略各自重拉 K 线 / 全部跳过）
            for sub, _w in self._sub_strategies:
                sub._indicators = self._indicators
                sub._kline_cache = self._kline_cache

            total_score = 0.0
            sub_details = []
            for strategy, weight in self._sub_strategies:
                sub_result = strategy.execute([stock], params)
                if sub_result:
                    total_score += sub_result[0].score * weight
                    sub_details.append(f"{strategy.name}({sub_result[0].score})")

            if sub_details:
                results.append(ScanResult(
                    symbol=stock.symbol,
                    score=round(min(total_score, 100), 1),
                    signals=[f"{self.name}:{'|'.join(sub_details)}"],
                    strategy=self.strategy_type,
                ))
        return results

    def _self_prefetch(self, market_data):
        from ..data.prefetch import prefetch_kline_indicators
        symbols = [s.symbol for s in market_data if s.amount >= 1_000_000_000]
        ind, kln, _ = prefetch_kline_indicators(symbols=symbols, keep_kline=True)
        self._indicators, self._kline_cache = ind, kln
```

**落地时必须补充的两点（用户原片段未覆盖）**

1. **子策略缓存传播**：`CompositeStrategy._inject_shared_cache` 只向直接的 `_strategies`（4 个聚合策略）注入 `_indicators` / `_kline_cache`，**不会**向下注入到聚合策略内部的子策略（BottomRebound / LaunchFingerprint 等）。若不在基类把 `self._indicators` / `self._kline_cache` 传给每个 `sub`，子策略会因 `if not indicators: continue` 全部跳过（正是旧单策略模式的已知 bug2）。基类 `execute` 中 ② 处完成传播。
2. **独立运行兜底**：单策略模式（`stock_picker.py --strategy bottom/launch/...`）下没有 CompositeStrategy 注入 `_indicators`，原片段会因 `indicators` 为空跳过全部标的。基类 ① 处增加自预取（`_self_prefetch`），复用 `prefetch_kline_indicators`，与 Composite 路径共用同一预取函数，保证单策略模式也可跑。

3. **⚠️ 横截面策略例外（MoneyStrategy 不能用逐股基类，否则静默失效）**
   - 基类 `execute` 对每只股票 `for stock: sub.execute([stock])` 传**单元素列表**。这对逐股型子策略（BottomRebound / LaunchFingerprint / ConsecutivePositive / MATrend 等，只看单只指标）没问题。
   - 但 **MoneyStrategy 的三个子策略是横截面策略**，必须拿到**全市场列表**才能排名/归一化（已核实真实代码 `src/strategies/momentum/`）：
     - `TurnoverRank.execute`：`sorted(market_data, key=lambda x: x.amount)` 按成交额**全市场排名**；传 `[stock]` → 每只都是第 1 名 → 排名分恒满分、无区分度。
     - `MultiFactor.execute`：`max(amount)` / `max(change_pct)` 取**全市场最大值**做归一化；传 `[stock]` → 该股票自身即最大值 → 归一化分恒满分。
     - `NetInflow.execute`：同理依赖全市场做资金排名。
   - **结论**：MoneyStrategy **必须重写 `execute`**，不走基类逐股循环，改为对全市场各跑一次子策略、再按 symbol 聚合：

```python
class MoneyStrategy(AggregatedStrategy):
    @property
    def strategy_type(self): return StrategyType.MONEY

    def __init__(self):
        super().__init__()
        self._sub_strategies = [
            (NetInflowStrategy(), 0.35),
            (TurnoverRankStrategy(), 0.30),
            (MultiFactorStrategy(), 0.35),
        ]

    def execute(self, market_data, params):
        if not self._indicators:
            self._self_prefetch(market_data)          # ① 独立运行兜底（同基类）
        for sub, _w in self._sub_strategies:           # ② 缓存传播（同基类）
            sub._indicators = self._indicators
            sub._kline_cache = self._kline_cache

        # ⚠️ 横截面：每个子策略跑【全市场】一次，而非逐股
        sym_scores: Dict[str, List[float]] = {}
        sym_weights: Dict[str, List[float]] = {}
        for strategy, weight in self._sub_strategies:
            for r in strategy.execute(market_data, params):  # 传全市场
                sym_scores.setdefault(r.symbol, []).append(r.score * weight)
                sym_weights.setdefault(r.symbol, []).append(weight)

        results = []
        for sym, scores in sym_scores.items():
            w = sym_weights[sym]
            total = sum(scores) / sum(w) if sum(w) else 0.0
            results.append(ScanResult(
                symbol=sym, score=round(min(total, 100), 1),
                signals=[f"{self.name}:资金聚合"], strategy=self.strategy_type,
            ))
        return results
```

   - BottomStrategy / LaunchStrategy / TrendStrategy 仍用基类逐股 `execute`（其子策略均为逐股型），**无需重写**。

**与 Step 2.7 的衔接**：指纹子策略 `LaunchFingerprintStrategy` 经传播得到 `self._kline_cache` 后，复用原始 K 线（Step 2.7 的 `__init__` 已声明 `self._kline_cache={}`），无需改动即可被基类编排。

**具体聚合策略只需声明**（`_sub_strategies` 权重见 Step 2.1）：

```python
class BottomStrategy(AggregatedStrategy):
    @property
    def strategy_type(self): return StrategyType.BOTTOM
    def __init__(self):
        super().__init__()
        self._sub_strategies = [
            (BottomReboundStrategy(), 0.6),
            (ConsecutivePositiveStrategy(), 0.4),
        ]
# LaunchStrategy / TrendStrategy / MoneyStrategy 同理，仅换子策略与权重
```

### Step 2.6 4个聚合策略的完整实现代码

> 以下示例**继承自 Step 2.5.1 的 `AggregatedStrategy`**，只展示子策略组合与权重差异；编排循环（指标读取、缓存传播、加权汇总、信号格式）已在基类复用，无需重复。

⚠️ 以下代码中的 `StrategyType.BOTTOM` / `StrategyType.LAUNCH` / etc. 需先完成 Step 2.4 的枚举扩展才能编译通过。

**① BottomStrategy（底部策略）**

```python
from .base import AggregatedStrategy
from ..technical.bottom_rebound import BottomReboundStrategy
from ..momentum.consecutive_positive import ConsecutivePositiveStrategy
from ...core.types import StrategyType


class BottomStrategy(AggregatedStrategy):
    """聚合策略：底部反弹 + 连续小阳吸筹"""
    
    @property
    def name(self) -> str:
        return "底部策略"
    
    @property
    def strategy_type(self):
        return StrategyType.BOTTOM
    
    def __init__(self):
        super().__init__()
        self._sub_strategies = [
            (BottomReboundStrategy(), 0.6),
            (ConsecutivePositiveStrategy(), 0.4),
        ]
```

**② LaunchStrategy（启动策略）**

```python
from .base import AggregatedStrategy
from ..momentum.volume_breakout import VolumeBreakoutStrategy
from ..technical.box_breakout import BoxBreakoutStrategy
from ..technical.launch_fingerprint_strategy import LaunchFingerprintStrategy
from ...core.types import StrategyType


class LaunchStrategy(AggregatedStrategy):
    """聚合策略：放量突破 + 箱体突破 + 启动指纹"""
    
    @property
    def name(self) -> str:
        return "启动策略"
    
    @property
    def strategy_type(self):
        return StrategyType.LAUNCH
    
    def __init__(self):
        super().__init__()
        self._sub_strategies = [
            (VolumeBreakoutStrategy(), 0.35),
            (BoxBreakoutStrategy(), 0.30),
            (LaunchFingerprintStrategy(), 0.35),
        ]
```

**③ TrendStrategy（追涨策略）**

```python
from .base import AggregatedStrategy
from ..momentum.trend_confirmation import TrendConfirmationStrategy
from ..technical.ma_trend import MATrendStrategy
from ..technical.ai_technical import AITechnicalStrategy
from ...core.types import StrategyType


class TrendStrategy(AggregatedStrategy):
    """聚合策略：追涨确认 + 均线趋势 + AI技术面"""
    
    @property
    def name(self) -> str:
        return "追涨策略"
    
    @property
    def strategy_type(self):
        return StrategyType.TREND
    
    def __init__(self):
        super().__init__()
        self._sub_strategies = [
            (TrendConfirmationStrategy(), 0.35),
            (MATrendStrategy(), 0.35),
            (AITechnicalStrategy(), 0.30),
        ]
```

**④ MoneyStrategy（资金策略）**

```python
from .base import AggregatedStrategy
from ..momentum.net_inflow import NetInflowStrategy
from ..momentum.turnover_rank import TurnoverRankStrategy
from ..momentum.multi_factor import MultiFactorStrategy
from ...core.types import StrategyType


class MoneyStrategy(AggregatedStrategy):
    """聚合策略：资金净流入 + 成交额排名 + 多因子"""
    
    @property
    def name(self) -> str:
        return "资金策略"
    
    @property
    def strategy_type(self):
        return StrategyType.MONEY
    
    def __init__(self):
        super().__init__()
        self._sub_strategies = [
            (NetInflowStrategy(), 0.35),
            (TurnoverRankStrategy(), 0.30),
            (MultiFactorStrategy(), 0.35),
        ]
```

### Step 2.7 指纹策略指标兼容性（修正用户建议）

> 用户建议：指纹策略 `execute` 优先用注入的 `_indicators`、否则自拉 K 线。**经核查该写法不可直接照搬**，原因见下。

**为什么不能直接用 `self._indicators`**

| 数据源 | 结构 | 消费方 |
|--------|------|--------|
| 聚合器注入的 `self._indicators`（`calc_all_indicators` 产出） | 标量指标字典：`sma5/sma20/rsi14/macd/ma_bullish_align/consecutive_up/...`（40+ 键） | Bottom / Trend / Money 三策略（Step 2.6 中用 `indicators.get("rsi14")` 等，**正确**） |
| 指纹策略实际所需 | `calculate_vectorized_indicators(klines)` → `{"features":[...], "feature_names":[...]}` + `generate_tags(klines)` 的标签 | **仅 LaunchFingerprint** |

二者键集完全不同。直接 `indicators = self._indicators` 后访问 `indicators["features"]` 会抛 `KeyError`；指纹匹配逻辑全部失效。

**正确做法：注入并复用「原始 K 线」（`_kline_cache`），避免重复网络请求；向量化特征仍本地计算（CPU 开销可忽略，且保证特征口径一致）。**

前提（否则 `_inject_shared_cache` 会因 `hasattr` 为假跳过注入）：

```python
# LaunchFingerprintStrategy.__init__ 中新增
self._kline_cache: Dict[str, list] = {}
```

`execute` 改写：

```python
def execute(self, market_data, params):
    cfg = params.get("launch_fingerprint", {}) if params else {}
    min_score = cfg.get("min_score", 40)
    source = cfg.get("source", "sina")
    max_pullback_prob = cfg.get("max_pullback_prob", 60)

    # 复用聚合层注入的原始K线（避免重复网络请求）；无则自拉（兼容独立运行）
    injected_klines = getattr(self, "_kline_cache", None) or {}

    results = []
    for stock in market_data:
        try:
            klines = injected_klines.get(stock.symbol) \
                     or fetch_kline_from_tencent(stock.symbol, days=120, source=source)
            if not klines or len(klines) < 60:
                continue

            indicators = calculate_vectorized_indicators(klines)
            tags_data = generate_tags(klines)
            # ... 后续指纹匹配逻辑（launch_score / match_fingerprints / 信号生成 保持不变）
```

> **降级说明**：`_kline_cache` 仅含成交额 ≥10 亿的标的（`composite_strategy.py:387` 过滤）。200M–1B 区间的标的指纹策略仍会自拉 K 线，属正常降级，不影响正确性。独立运行（`--strategy launch_fingerprint`）时 `self._kline_cache` 为空，同样回退到自拉，向后兼容。

**当前状态确认（针对"指纹未加入 SUB_STRATEGIES 是否 bug"的核查）**

> 结论：**不是运行时 bug，而是 Phase 2 重构要解决的"接线缺口"；且用户给的一行修复 `("launch_fingerprint", LaunchFingerprintStrategy)` 既不完整、也与方案 A 冲突，不能直接采用。**

- 事实成立：`composite_strategy.py:168-179` 的 `SUB_STRATEGIES` 确有 10 项，`launch_fingerprint` 不在其中 → 综合扫描（每日 `morning_task` 走的 `CompositeStrategy`）**不会执行**该策略。
- 但它并非"坏代码"：`registry.py:51` 已注册 `StrategyType.LAUNCH_FINGERPRINT`，可经单策略模式 `--strategy launch_fingerprint` 独立运行；`strategy_agent.py:157` 也已把 `launch_fingerprint` 配置作为参数传给 Composite，只是 **Composite 内部 `_get_weights` / `_calculate_composite_scores` 从不读取该参数**（传了未消费）。
- 用户一行修复为何不可直接采用：
  1. **缺 import**：`composite_strategy.py` 当前未 `import LaunchFingerprintStrategy`，直接加元组会 `NameError`。
  2. **缺权重**：即使补 import，因 `_get_weights` 的权重表（动态 `MARKET_STATE_WEIGHTS` 与手动回退 dict 343-354 行）均无 `launch_fingerprint` 项，`weights.get("launch_fingerprint", 0.0)` 返回 0 → 策略执行了却对综合分**零贡献**（仅命中时 `+1.5` 多样性分），属"半接线"死状态。
  3. **与方案 A 冲突**：Phase 2 的既定决策是"指纹**不入** `SUB_STRATEGIES`，仅由 `LaunchStrategy` 以 0.35 权重聚合"（见方案 A）。把它平铺进 `SUB_STRATEGIES` 是退回旧架构，与重构方向相悖。
- 正确落点：本缺口由 **Phase 2 / 方案 A** 统一解决——指纹作为 `LaunchStrategy` 的内部子策略被聚合（权重 0.35），而非平铺进 `SUB_STRATEGIES`。当前代码无需为"补这个缺口"做任何改动。

---

## 第三阶段：验证 + 调整（0.5天）

### Step 3.1 导入验证

```bash
python -c "
from src.strategies.aggregated.bottom_strategy import BottomStrategy
from src.strategies.aggregated.launch_strategy import LaunchStrategy
from src.strategies.aggregated.trend_strategy import TrendStrategy
from src.strategies.aggregated.money_strategy import MoneyStrategy
print('全部导入成功 ✅')
from src.strategies.registry import StrategyRegistry
r = StrategyRegistry()
r.initialize()
print('注册成功 ✅')
"
```

### Step 3.2 单策略验证

```bash
python stock_picker.py --strategy bottom --symbols "688362,000725"
python stock_picker.py --strategy launch --symbols "688362,000725"
python stock_picker.py --strategy trend --symbols "688362,000725"
python stock_picker.py --strategy money --symbols "688362,000725"
```

### Step 3.3 综合策略验证

```bash
python morning_task.py --debug --force
```

对比输出：
- ✅ 信号格式变为 `"底部策略:底部反弹(45)|连阳4日吸筹(32)"`
- ✅ 评分分布合理（无满分饱和）
- ✅ 互斥生效（连续下跌≥3天的标的不显示 Trend 信号）

### Step 3.4 评分有效性回测（可选）

对最近 10 个交易日运行评分 → 验证高分标的后 5 日涨幅是否显著高于低分标的。

---

## 第四阶段：清理与归档（0.5天）

| 操作 | 说明 |
|------|------|
| 旧策略文件移入 `src/strategies/archive/`（**仅在 legacy_mode 彻底移除后**） | 保留不删，加 `_DEPRECATED` 后缀注释 |
| 更新 `email_sender.py` 信号渲染 | 适配新格式 `"策略名:子1\|子2"` |
| 更新 `configs/settings.yaml` | 新增 `strategy.bottom/launch/trend/money` 四段（结构见 Step 4.4），旧段保留 |
| 更新 `src/core/config.py` | `StrategyConfig` 新增 4 个字段（dataclass 默认值，与 yaml 对齐） |
| 更新 `strategy_config.json` | **不承载评分参数**，仅保留运行时开关（tdx_enabled / holdings / skip_money_flow / launch_fingerprint） |
| 删除 `strategy_type.py` | 确认无人引用后删除 |

> ⚠️ **归档必须与 `registry.py` 导入原子同步（否则 `ImportError`）**：`src/strategies/registry.py:14-26` 用相对导入 `from .momentum.volume_breakout import VolumeBreakoutStrategy` 直接引用旧策略。Phase 4 移动文件到 `archive/` 后，**必须同步修改 `registry.py` 全部相对路径**（`from .momentum.x` → `from .archive.x`、`from .technical.x` → `from .archive.x`），且**归档与 import 修改放在同一提交内**完成，否则模块加载即断裂。
>
> ⚠️ **过渡期不可归档**：旧 10 策略在 `legacy_mode=true` 期间**仍被实际调用**（每日并行对比、P2 验收门禁都依赖它）。Phase 4 归档步骤必须排在「legacy_mode 彻底移除、新代码稳定」之后，否则 legacy 对比失去标的物、无法验收。

### Step 4.4 配置文件结构变更（明确）

> 用户反馈：原文档"更新 settings.yaml 和 strategy_config.json"未给出结构、且自相矛盾（既说更新又说保持3字段不变）。本节一次性明确两份文件的职责边界与具体写法。

**分工原则（单一数据源）**

- `strategy_config.json` 是「运行时开关文件」，由 `kline_fetcher.py`（读 `tdx_enabled` / `holdings`）和 `composite_strategy.py`（读 `skip_money_flow`）直接 `open()` 读取，**只放开关，不放大任何评分/阈值参数**。
- 所有「策略评分参数」（min_score、RSI 阈值、量比、成交额门槛等）遵循现有 13 个策略的约定：写在 `configs/settings.yaml` 的 `strategy:` 段，并由 `src/core/config.py` 的 `StrategyConfig` 提供 dataclass 默认值。这保证与现有代码完全一致，避免双数据源。

**① configs/settings.yaml —— 新增 4 段（语义对齐用户建议）**

```yaml
strategy:
  # ... 原有 13 段（volume_surge / bottom_rebound / trend_confirmation ...）保持不变 ...

  # ── 新增：4 个聚合策略（重构后生效）──
  bottom:                     # 对应 StrategyType.BOTTOM
    min_score: 50             # 综合评分门槛（低于此分不入选）
    rsi_threshold: 35         # 底部反弹触发 RSI 上限（<35 视为超卖）
    min_consecutive_days: 3   # 连续小阳最少天数
    max_consecutive_days: 7   # 连续小阳最多天数（过热过滤）

  launch:                     # 对应 StrategyType.LAUNCH
    min_score: 55             # 综合评分门槛
    min_volume_ratio: 2.0     # 放量倍数门槛（用户建议的 volume_ratio）
    min_box_range: 3.0        # 箱体最小振幅%
    min_breakout_pct: 0.5     # 突破幅度%
    fingerprint_min_score: 40 # 指纹子策略门槛

  trend:                      # 对应 StrategyType.TREND
    min_score: 60
    min_rsi: 55               # 强势 RSI 阈值（用户建议的 rsi_min）
    min_consecutive_up: 3     # 最少连续上涨天数

  money:                      # 对应 StrategyType.MONEY
    min_score: 50
    top_n: 500                # 成交额排名门槛（用户建议的 amount_rank）
    min_amount: 100000000     # 最小成交额
```

**② src/core/config.py —— StrategyConfig 新增 4 字段（默认值须与 yaml 一致）**

```python
# 聚合策略：底部反弹
bottom: Dict[str, Any] = field(default_factory=lambda: {
    "min_score": 50, "rsi_threshold": 35,
    "min_consecutive_days": 3, "max_consecutive_days": 7,
})
# 聚合策略：启动突破
launch: Dict[str, Any] = field(default_factory=lambda: {
    "min_score": 55, "min_volume_ratio": 2.0,
    "min_box_range": 3.0, "min_breakout_pct": 0.5,
    "fingerprint_min_score": 40,
})
# 聚合策略：追涨确认
trend: Dict[str, Any] = field(default_factory=lambda: {
    "min_score": 60, "min_rsi": 55, "min_consecutive_up": 3,
})
# 聚合策略：资金流向
money: Dict[str, Any] = field(default_factory=lambda: {
    "min_score": 50, "top_n": 500, "min_amount": 100_000_000,
})
```

**③ strategy_config.json —— 仅运行时开关（新增 legacy_mode）**

```json
{
  "tdx_data_source": false,
  "tdx_enabled": false,
  "holdings": [ ... ],
  "skip_money_flow": true,
  "legacy_mode": false,
  "launch_fingerprint": { "min_score": 40, "source": "sina", "max_pullback_prob": 60 }
}
```

> **字段说明（TDX 双开关设计）**：
> - `tdx_data_source`：**开关①（数据源层）**——true 时 K 线抓取优先走 TDX（`tdx_fetcher.get_kline`），false 走默认源（东财/新浪/腾讯）。由 `kline_fetcher` 读取。
> - `tdx_enabled`：**开关②（分析层）**——true 时启用「TDX 持仓分析模式」，独立运行 `strategy_analysis_tdx.py` 仅对 `holdings` 给持仓建议；false 为正式全市场扫描。由分析入口读取。
> - `holdings`：持仓标的列表（开关②为 true 时使用）
> - `skip_money_flow`：跳过资金净流入策略开关
> - `legacy_mode`：新旧模式切换（true=旧10策略模式，false=新4聚合策略模式）
> - `launch_fingerprint`：启动指纹配置
>
> **说明**：两个开关解耦——可「只用 TDX 当数据源、仍跑全市场正式扫描」（①开②关），也可「正式数据源 + 单独跑 TDX 持仓分析」（①关②开），互不影响。

> **关于用户建议的 JSON 结构**：用户建议的 `strategies:{bottom/launch/trend/money}` 语义正确，但落地位置应改为 `settings.yaml` 的 `strategy:` 段（而非 `strategy_config.json`）。理由：保持与现有 13 个策略「同一文件、同一 dataclass」的单一数据源约定。若硬塞进 `strategy_config.json`，需在 `composite_strategy.py` 额外写一套 JSON 读取逻辑，与现有 `Config` 体系重复，不推荐。

**④ 聚合策略代码读取方式（呼应 Step 2.6）**

Step 2.6 示例代码中的硬编码值（`rsi14 < 35`、`3 <= cu <= 10`、`min_score` 等）在执行时应改为从 `self.config.strategy.bottom / launch / trend / money` 读取，例如：

```python
cfg = self.config.strategy.bottom
if rsi14 < cfg.get("rsi_threshold", 35):
    ...
total_score = min(total_score, cfg.get("min_score", 50))
```

---

## 第五阶段：新增功能（0.5天）

### Step 5.1 回测模块独立执行 + 写入缓存

> **需求**：回测模块独立运行，结果写入缓存。

> **v1 初版（2026-07-14 补写）**：原 stub 仅 prefetch + dump 计数，**缺失 N 日前向收益等核心指标**。现改为「策略选标 → 测算」闭环，与用户「回测主要依赖运行策略后选取标的」一致。

**① 复用现有基础，不重写**
- `backtest/enhanced/` 已具备 `EnhancedBacktester` + `TradeRecord`/`BacktestResult`（含 `total_return/max_drawdown/win_rate/profit_factor/sharpe_ratio/equity_curve`），`run()` 已能装载 `cache/kline/{date}/` 缓存。**v1 在其上扩展 walk-forward，不再另起炉灶**。
- `test/tdx` 的 `backtest/runner.py` 已有 `analyze_day`/`detect_signals`/`generate_report` 的逐日信号+报告雏形，其「N 日收益测算」逻辑并入 v1；`runner.py` 本身作为 stub 不再单独保留（见 5.2 ③）。

> ⚠️ **前置依赖：必须给 `engine.scan` 增加 `as_of` 参数（防未来函数）—— 否则回测结果无效**
> Step 5.1 ② 的 `engine.scan(universe, as_of=T, legacy_mode=...)` 当前**不存在**：`src/core/engine.py:59` 的 `scan(strategy, limit, **kwargs)` 无 `as_of`，回测若用实时/未来数据会引入前视偏差。实现方式（落地前置任务）：

    # src/core/engine.py
    def scan(self, strategy, limit=20, as_of=None, **kwargs):
        market_data = self.data_agent.fetch_market_data(as_of=as_of)  # 取 ≤as_of 历史快照
        # CompositeStrategy 内部 prefetch_kline_indicators(..., as_of=as_of) 切片 K 线 ≤as_of

> `as_of` 需一路透传至 `kline_fetcher` / `prefetch_kline_indicators`，确保回测窗口只用 T 及之前数据。这是 P2 验收（legacy vs stage 对比）**有效性的前提**——不先实现 `as_of`，回测指标不可信。

**② v1 核心算法（walk-forward：策略选标 → 测算）**

```python
# backtest/enhanced/walk_forward.py  (v1 草稿)
from src.data.prefetch import prefetch_kline_indicators
from .backtester import EnhancedBacktester, BacktestResult
from .config import BacktestConfig
from .report import write_backtest_report

def run_walk_forward(cfg: BacktestConfig) -> BacktestResult:
    # 1) 复用每日扫描缓存 cache/kline/{date}/（与 morning_task 同源），避免重复网络请求
    #    若缺失则 prefetch_kline_indicators(keep_kline=True) 补齐历史
    # 2) 遍历每个 rebalance 日 T（按 cfg.cadence: daily / weekly）
    #      window = kline[ <= T ]                  # 只用 T 及之前数据，防未来函数
    #      ranked = engine.scan(universe, as_of=T,
    #                           legacy_mode=cfg.legacy_mode)   # ⚠️ 需给 scan 新增 as_of 参数（当前用实时数据）
    #      top_n  = ranked[: cfg.top_n]             # 取策略选出的前 N 只
    # 3) 对 top_n 每只标的，算持有期 H ∈ cfg.horizons([5,10,20]) 的前向指标：
    #      fwd_ret[H] = (close[T+H] - close[T]) / close[T]     # ★ N 日收益（此前缺失的核心）
    #      mdd[H]     = min_{t∈[T,T+H]} (close[t]-close[T]) / close[T]   # 区间内最大回撤
    #      hit[H]     = fwd_ret[H] > 0                            # 是否盈利
    # 4) 跨所有 T 聚合：
    #      avg_ret[H]   = mean(fwd_ret[H])
    #      win_rate[H]  = mean(hit[H])                            # 胜率
    #      sharpe[H]    = mean(fwd_ret[H]) / std(fwd_ret[H]) * sqrt(252/cadence)
    #      max_dd[H]    = mean(mdd[H])                            # 平均最大回撤
    #      excess[H]    = avg_ret[H] - bench_ret[H]               # 相对沪深300同期超额
    #      overlap      = 相邻 T 选股 Top-N 重叠率（稳定性）
    # 5) legacy vs stage 对比（呼应 legacy_mode）：
    #      同法各跑一遍，对比 avg_ret/win_rate/max_dd，验证新策略不回退
    # 6) 落盘：cache/backtest/{date}/report.json + reports/backtest_{date}.md
    ...
    return result
```

**③ 关键参数清单（v1 必须覆盖，此前缺失）**

| 参数 | 含义 | 来源 |
|------|------|------|
| `horizons` | 持有期 H = [5,10,20] 日 | BacktestConfig |
| `top_n` | 每期选股数（默认 15） | BacktestConfig |
| `cadence` | 调仓频率 daily/weekly | BacktestConfig |
| `fwd_ret` | **N 日前向收益（核心）** | close[T+H]/close[T] |
| `win_rate` | 胜率 | hit 均值 |
| `max_dd` | 持有期最大回撤 | 区间内最小值 |
| `sharpe` | 风险调整收益 | mean/std × √年化 |
| `excess` | 基准超额 | 沪深300 同期 |
| `overlap` | 选股稳定性 | 相邻期 Top-N 交集 / N |

**④ 独立执行命令（写缓存）**

```bash
# v1：walk-forward 回测（新4策略），写入 cache/backtest/
python -m backtest.enhanced.walk_forward \
    --universe all --top-n 15 --horizons 5,10,20 \
    --cadence daily --start 2026-01-01 --end 2026-07-14

# 旧模式对照（legacy_mode=true），用于 P2 验收门禁对比
python -m backtest.enhanced.walk_forward \
    --universe all --legacy-mode --start 2026-01-01 --end 2026-07-14
```

> 缓存落点：`cache/backtest/{end}/report.json`（与每日 `cache/kline/{date}/` 同源复用）。

### Step 5.1.1 实盘推荐跟踪与收益归因（v1 方案 · 2026-07-15）

> **新增需求**：当前历史回测尚未完全落地，先增加一套“实盘推荐跟踪账本”。每次执行新/旧策略并发送邮件时，记录当次推荐的 15-25 只标的、邮件发送时价格、策略模式、排名、评分、命中信号，并在后续交易日自动补算 T+1/T+3/T+5/T+10 收益、涨跌停可交易状态、模拟买卖收益、100w 资金仓位收益，用连续 5-10 天真实观察来判断新旧策略可信度。

#### 5.1.1.1 设计目标

| 目标 | 说明 |
|------|------|
| 推荐留痕 | 每次策略执行都 append 记录，不覆盖历史；同一标的同一天被新旧策略同时推荐也分别记录 |
| 价格留痕 | 记录邮件发送时价格，作为“推荐价”；同时记录次日开盘、最高、最低、收盘，区分“推荐收益”和“可成交收益” |
| 新旧对比 | `strategy_mode` 区分 `new_4_aggregated` 与 `legacy_10_atomic`，输出重合率、胜率、平均收益、最大回撤 |
| 交易约束 | 涨停不可买、跌停不可卖；ST / 北交所 / 主板 / 创业板 / 科创板涨跌停比例不同，必须按市场规则判断 |
| 仓位模拟 | 以 100w 资金为基准，支持等权、分数加权、风险平价、快进快出、持有 5-10 天等模型 |
| 展示友好 | 输出 CSV/JSON 作为底账，同时生成 Markdown/HTML 收益榜，便于邮件或页面展示 |

#### 5.1.1.2 数据落点

建议新增独立目录，不混入普通报告：

```text
data/
└── tracking/
    ├── recommendations.csv          # 推荐明细总表，append-only
    ├── observations.csv             # 每日行情观察表，append-only
    ├── trades_simulated.csv         # 模拟交易流水
    ├── portfolio_daily.csv          # 组合每日净值
    └── snapshots/
        ├── 2026-07-15_new.json
        └── 2026-07-15_legacy.json

reports/
└── tracking/
    ├── strategy_tracking_2026-07-15.md
    └── strategy_tracking_2026-07-15.html
```

> `recommendations.csv` 必须是 append-only。即使同一天重复执行策略，也新增一批 `run_id`，不直接覆盖，后续通过 `run_id` 追踪每次邮件推荐的真实效果。

#### 5.1.1.3 推荐明细表结构

`recommendations.csv`

| 字段 | 含义 |
|------|------|
| `run_id` | 单次策略执行 ID，例如 `20260715_162812_new` |
| `run_time` | 策略执行完成/邮件发送时间 |
| `trade_date` | 推荐所属交易日 |
| `strategy_mode` | `new_4_aggregated` / `legacy_10_atomic` |
| `strategy_name` | `composite` 等 |
| `rank` | 推荐排名，1-25 |
| `symbol` | 股票代码 |
| `name` | 股票名称 |
| `score` | 策略评分 |
| `signals` | 命中信号摘要 |
| `hit_strategy_keys` | 命中的策略 key，便于结构化统计 |
| `recommend_price` | 邮件发送时价格，即推荐价 |
| `recommend_change_pct` | 推荐时涨跌幅 |
| `recommend_amount` | 推荐时成交额 |
| `limit_status_at_recommend` | 推荐时状态：`normal` / `limit_up` / `limit_down` / `suspended` |
| `can_buy_at_recommend` | 推荐时是否理论可买 |
| `email_subject` | 邮件标题，便于追溯 |
| `report_path` | 当次报告路径 |

#### 5.1.1.4 每日观察表结构

`observations.csv`

| 字段 | 含义 |
|------|------|
| `run_id` | 对应推荐批次 |
| `symbol` | 股票代码 |
| `observe_date` | 观察交易日 |
| `holding_day` | T+N，推荐日为 T+0 |
| `open` / `high` / `low` / `close` | 当日 OHLC |
| `change_pct` | 当日涨跌幅 |
| `limit_status` | `normal` / `limit_up` / `limit_down` / `suspended` |
| `can_buy` | 当日是否可买，涨停/停牌为 false |
| `can_sell` | 当日是否可卖，跌停/停牌为 false |
| `ret_from_recommend_close` | 相对推荐价的收盘收益 |
| `max_ret_from_recommend` | 相对推荐价的区间最高收益 |
| `min_ret_from_recommend` | 相对推荐价的区间最低收益 |
| `drawdown_from_entry` | 从买入价计算的持有期最大回撤 |

#### 5.1.1.5 价格与收益口径

必须同时保留两套口径，避免“看起来赚了但实际买不到”的偏差：

| 口径 | 买入价 | 卖出价 | 用途 |
|------|--------|--------|------|
| 推荐价收益 | 邮件发送时 `recommend_price` | 后续收盘价 / 最高价 | 衡量策略信号质量 |
| 可成交收益 | 次一交易日开盘价或推荐后下一可成交价 | 策略规则触发价 / 收盘价 | 衡量实盘可复制收益 |

默认 v1 规则：

```text
推荐收益 = close[T+n] / recommend_price - 1
可成交买入价 = 若推荐时未涨停且未停牌，则 recommend_price；否则取下一交易日第一个可买价格
T+1收益 = close[T+1] / buy_price - 1
T+5收益 = close[T+5] / buy_price - 1
T+10收益 = close[T+10] / buy_price - 1
最大浮盈 = max(high[T+1:T+n]) / buy_price - 1
最大回撤 = min(low[T+1:T+n]) / buy_price - 1
```

#### 5.1.1.6 涨跌停与不可交易规则

必须在模拟交易前判断交易状态：

| 场景 | 规则 |
|------|------|
| 推荐时涨停 | 记录命中，但模拟买入延后到下一可买交易日 |
| 推荐时跌停 | 可买但风险标记为 `limit_down_at_recommend`，默认降权或剔除 |
| 买入日涨停 | 不成交，继续等待下一交易日 |
| 卖出日跌停 | 不成交，继续持有到下一可卖交易日 |
| 停牌 | 不买不卖，收益按最近可得收盘价标记，交易模拟等待复牌 |
| 一字板 | 若开盘价=最高价=最低价=涨停价，默认不可买；若跌停同理默认不可卖 |

涨跌停比例需按标的类型判断：

```text
ST: 5%
沪深主板: 10%
创业板/科创板: 20%
北交所: 30%
新股上市早期: 单独标记，不纳入默认统计或单独统计
```

#### 5.1.1.7 100w 资金仓位模拟

以 100w 为基准，先实现三种仓位模型，再用连续 5-10 天结果比较：

| 模型 | 分配方式 | 适用场景 |
|------|----------|----------|
| 等权模型 | Top N 等权，单票资金 = 100w / N | 基准模型，最公平 |
| 分数加权 | 权重 ∝ `score * confidence`，单票上限 10%-12% | 强化高分标的 |
| 交集增强 | 新旧共同命中票双倍权重，单票上限 15% | 优先验证共识票 |

v1 默认资金约束：

```text
总资金: 1,000,000
单票最大仓位: 100,000，若新旧共同命中可放宽到 150,000
单票最小仓位: 20,000
最多持仓: 15-25 只
现金保留: 5%-10%，用于涨停无法买入后的递补
买入手续费/滑点: 默认 0.05%-0.10%
卖出手续费/滑点: 默认 0.10%-0.15%，含印花税估算
```

#### 5.1.1.8 快进快出与持有策略

需要同时测两类策略，不预设哪一种最好：

| 策略 | 买入 | 卖出 | 评价指标 |
|------|------|------|----------|
| 快进快出 T+1 | 推荐日可买则买，否则下一可买日 | T+1 收盘或次日冲高回落触发 | 胜率、平均收益、资金周转 |
| 短持 T+3 | 推荐价/次日开盘买入 | T+3 收盘；期间盈利 >5% 可止盈 | 收益/回撤平衡 |
| 标准 T+5 | 推荐价/次日开盘买入 | T+5 收盘；跌破 -5% 止损 | 主观察口径 |
| 趋势 T+10 | 推荐价/次日开盘买入 | T+10 收盘；跌破 5日线止盈/止损 | 检验趋势延续 |
| 移动止盈 | 推荐价/次日开盘买入 | 最高浮盈回撤 3%-5% 卖出 | 尽量吃主升段 |

默认止损止盈：

```text
止损: -5%
第一止盈: +5%，可卖出 50%
第二止盈: +8% 或 +10%，清仓或保留 20% 底仓
移动止盈: 最高浮盈回撤 3%-5%
```

#### 5.1.1.9 新旧策略可信度指标

连续观察 5-10 个交易日后，生成如下对比表：

| 指标 | 新策略 | 旧策略 | 共同命中 | 说明 |
|------|--------|--------|----------|------|
| Top15 平均 T+1 收益 | - | - | - | 快进快出效果 |
| Top15 平均 T+5 收益 | - | - | - | 主观察指标 |
| Top15 平均 T+10 收益 | - | - | - | 趋势延续 |
| T+5 胜率 | - | - | - | 收益 > 0 的比例 |
| 平均最大浮盈 | - | - | - | 是否有冲高机会 |
| 平均最大回撤 | - | - | - | 风险暴露 |
| 涨停不可买比例 | - | - | - | 信号是否追高 |
| 跌停不可卖比例 | - | - | - | 风险事件 |
| 新旧 TopN 重合率 | - | - | - | 策略一致性 |
| 100w 组合收益 | - | - | - | 资金层面结果 |

可信度初判规则：

```text
若某策略连续 5-10 天 T+5 胜率 >= 55%，且平均 T+5 收益 > 沪深300同期 +1%，可判定有效。
若共同命中票胜率显著高于单边命中票，则后续仓位模型应提高共同命中权重。
若新策略候选更多但 Top15 收益弱，应调高 min_score / 降低单一启动指纹权重。
若旧策略收益高但回撤大，应引入涨幅过滤、涨停不可买过滤、行业集中度限制。
```

#### 5.1.1.10 实现入口建议

新增三个独立命令，先不侵入主策略逻辑：

```bash
# 1) 正常扫描并发送邮件，同时落推荐账本
python main.py scan --report --email -s composite -l 25
python main.py scan --report --email -s composite -l 25 --legacy-mode

# 2) 每日收盘后补全观察数据，计算 T+1/T+3/T+5/T+10
python main.py tracking update --date 2026-07-16

# 3) 生成新旧策略收益对比报告
python main.py tracking report --start 2026-07-15 --end 2026-07-25 --capital 1000000
```

模块建议：

```text
src/tracking/
├── __init__.py
├── recorder.py          # 扫描完成后 append recommendations.csv
├── observer.py          # 每日补行情 observations.csv
├── simulator.py         # 交易约束、涨跌停、手续费、仓位模拟
├── analyzer.py          # 新旧策略对比、胜率、收益、回撤、重合率
└── report.py            # 输出 md/html
```

#### 5.1.1.11 与邮件链路的接入点

在 `engine.scan()` 返回 Top15-25 后、`ReportAgent.send_email()` 发送前后都要记录：

```text
1. scan 完成后：记录 run_id、策略模式、TopN、评分、信号、推荐时价格
2. email 发送成功后：回写 email_subject、report_path、md_attachment_path、sent=true
3. email 发送失败时：仍保留推荐记录，sent=false，避免策略信号丢失
```

推荐价优先使用 `ScanResult.data.close`；如果数据源有实时价格字段则使用实时价，否则用当前快照 close，并在字段 `price_source` 标记 `snapshot_close`。

#### 5.1.1.12 展示格式

每日收益报告至少包含：

```text
一、新旧策略今日推荐对比
- 新策略 Top25
- 旧策略 Top25
- 共同命中标的

二、历史批次收益追踪
- T+1 / T+3 / T+5 / T+10 收益榜
- 最大浮盈榜
- 最大回撤榜
- 涨停不可买 / 跌停不可卖记录

三、100w 组合模拟
- 等权收益
- 分数加权收益
- 共同命中增强收益
- 快进快出 vs 持有 5/10 天

四、策略可信度结论
- 新策略是否有效
- 旧策略是否仍优于新策略
- 新策略需要调哪些权重/阈值
```

#### 5.1.1.13 v1 验收标准

| 验收项 | 标准 |
|--------|------|
| 推荐记录 | 连续多次执行 scan 不覆盖，`recommendations.csv` 正确 append |
| 邮件价格 | 每条推荐都有 `recommend_price` 和 `run_time` |
| 新旧区分 | `strategy_mode` 可区分新旧策略，报告标题也区分 |
| 观察更新 | 至少能补算 T+1/T+3/T+5/T+10 收益 |
| 涨跌停 | 涨停不可买、跌停不可卖在模拟交易中生效 |
| 资金模拟 | 100w 等权模型可输出组合收益、持仓、现金、手续费 |
| 展示报告 | 可生成 Markdown/HTML 收益追踪表 |
| 连续观察 | 支持按 5-10 天窗口输出新旧策略可信度结论 |

#### 5.1.1.14 `sample_demo_report.html` 可复用点与正式化修正

> 参考文件：`data/tracking/sample_demo_report.html`  
> 结论：该 demo **可以作为收益跟踪报告 v1 的页面骨架**，尤其是“三段式结构”已经符合当前需求；但里面的数据口径、去重、交易约束和字段完整性还不够，不能直接作为正式回测结论使用。

**可直接复用的展示结构**

| 模块 | demo 已有内容 | 正式版保留方式 |
|------|---------------|----------------|
| 新旧策略可信度对比 | 新/旧模式、样本数、可交易数、胜率、平均交易收益、D+1~D+10累计收益 | 保留为报告第一屏核心表，用于连续 5-10 天判断新旧策略 |
| 100w 组合模拟 | 方法=`score`、风格=`fast`、组合预期收益、剩余现金、持仓数、持仓明细 | 保留，但补充真实成交约束、手续费、仓位上限、去重 |
| 近期推荐明细 | 日期、模式、排名、代码、名称、发送价、交易收益、D+1、D+5、备注 | 保留为底账视图，增加 `run_id`、评分、信号、涨跌停状态、是否可买卖 |
| HTML 样式 | 轻量 CSS、卡片分区、红涨绿跌、表格布局 | 保留轻量模板，后续同时输出 Markdown 和 HTML |

**demo 中值得纳入正式版的字段**

```text
模式: new / old
样本: 推荐样本数
可交易: 排除涨停不可买、跌停不可卖、停牌后的有效样本
胜率: 收益 > 0 的标的占比
平均交易收益%: 真实可成交买卖价计算的平均收益
D+1 ~ D+10累计%: 连续观察窗口收益曲线
组合预期收益: 100w 模拟组合收益
剩余现金: 因一手股数、涨停不可买、仓位上限剩余的现金
持仓数: 实际成交标的数
发送价: 邮件发送时记录的推荐价
交易收益%: 按买卖约束后的实际模拟收益
备注: 涨停不可买、跌停不可卖、停牌、重复命中、共同命中等说明
```

**必须修正的问题**

| 问题 | demo 表现 | 正式修正 |
|------|-----------|----------|
| 样本过小 | 示例只有 7 条记录 | 正式报告必须标注样本数，样本低于 30 时只给“观察中”，不下强结论 |
| 持仓重复 | 组合模拟里 `600519`、`000858` 重复出现 | 同一 `run_id + symbol` 必须去重；新旧共同命中用 `overlap=true` 标记，不重复买入 |
| 排名异常 | 推荐明细里排名全部为 1 | 正式记录必须保存真实 `rank`，并支持 Top15/Top25 分层统计 |
| `None` 展示 | D+8~D+10 显示 `None` | 前端显示为 `-` 或 `待观察`，并记录 `observation_status=pending` |
| 收益口径不清 | D+N累计% 与平均交易收益关系未说明 | 明确区分“单票平均收益”“组合累计收益”“推荐价收益”“可成交收益” |
| 缺少交易约束 | 未展示涨停不可买、跌停不可卖 | 增加 `limit_status`、`can_buy`、`can_sell`、`trade_status` |
| 缺少风险指标 | 没有最大回撤、最大浮盈、止损触发 | 增加 `max_ret`、`max_drawdown`、`stop_loss_hit`、`take_profit_hit` |
| 缺少策略解释 | 没有评分、命中信号、策略 key | 增加 `score`、`signals`、`hit_strategy_keys`，便于反向优化 |
| 缺少基准对比 | 没有沪深300/中证全指同期收益 | 增加 `benchmark_ret`、`excess_ret`，避免牛市里误判策略有效 |
| 缺少手续费滑点 | 组合预期收益未扣成本 | 正式组合收益统一扣滑点、佣金、印花税 |

**正式版报告建议结构**

```text
一、策略可信度总览
- 新策略 / 旧策略 / 共同命中 三列对比
- 样本数、可交易数、胜率、平均收益、超额收益、最大回撤
- D+1 ~ D+10 收益曲线表

二、100w 组合模拟
- 等权 / 分数加权 / 共同命中增强 三种模型并列
- 组合收益、剩余现金、持仓数、手续费、最大回撤
- 实际成交持仓表：代码、名称、买入价、卖出价、收益、权重、金额、股数、交易状态

三、近期推荐明细
- 默认末 30 条，可按 run_id / 日期 / 策略模式过滤
- 展示发送价、可成交买入价、D+1/D+3/D+5/D+10、最大浮盈、最大回撤、备注

四、结构优化建议
- 哪个策略模式胜率更高
- 哪些子策略贡献正收益
- 哪些信号容易追高或不可买
- 新策略权重/阈值下一轮如何调
```

**正式版 HTML 模板要求**

```text
1. 保持 demo 的轻量卡片 + 表格结构，便于邮件阅读。
2. 数字展示统一保留 2 位小数；缺失值显示为 “待观察”。
3. 红色表示上涨/盈利，绿色表示下跌/亏损，灰色表示待观察或不可交易。
4. 表格字段较多时支持横向滚动，避免手机端挤压变形。
5. 报告顶部必须显示生成时间、统计窗口、记录总数、有效样本数。
6. 每个结论旁边必须显示样本数，避免小样本误判。
```

**v1 落地优先级**

```text
P0: 复用 demo 三段式报告结构，先生成 HTML/Markdown。
P0: 修复去重、rank、None 展示、样本数提示。
P0: 推荐明细接入真实 recommendations.csv。
P1: 组合模拟接入涨停不可买、跌停不可卖、手续费滑点。
P1: 增加 D+1/D+3/D+5/D+10、最大浮盈、最大回撤。
P2: 增加基准收益、超额收益、子策略贡献分析。
```

#### 5.1.1.15 `backtest_review_and_plan.md` 审查结论采纳（落地版修正）

> 参考文件：`docs/backtest_review_and_plan.md`  
> 结论：该审查方案**可优化并应合并进回测路线**。它对原 Step 5.1 / 5.1.1 做了更贴近当前代码的落地校正：历史 walk-forward 不应再依赖不存在的 `backtest/enhanced/`，实盘跟踪也不应新建 `src/tracking/`，而应复用当前已存在的 `src/backtest/` 模块。
>
> **权威修正**：若本节与前文 `backtest/enhanced/`、`src/tracking/`、CSV-only 等草稿描述冲突，以本节为准。

**可采纳点总览**

| 审查结论 | 是否采纳 | 写入路线 |
|----------|----------|----------|
| `as_of` 防前视链路已满足，是回测成立前提 | 采纳 | 所有 replay/evaluate/update 必须传 `as_of` |
| `backtest/enhanced/` 不存在，Step 5.1 照抄不可执行 | 采纳 | Step 5.1 改为复用 `src/backtest/` + replay |
| 实盘推荐跟踪比离线历史回测更能判断新旧策略可信度 | 采纳 | 优先级调整：先 5.1.1，后 5.1 |
| 文档写 `src/tracking/`，现状是 `src/backtest/` | 采纳 | 命名统一为 `src/backtest/` |
| JSONL 已是当前落盘主格式，CSV 作为补充 | 采纳 | JSONL 主、CSV 并存 |
| limiter / allocator / report 已有 v1，但缺 P1/P2 能力 | 采纳 | 按 P0/P1/P2 补齐 |

**Step 5.1 历史回测修正**

原草稿中的：

```text
backtest/enhanced/walk_forward.py
EnhancedBacktester / BacktestResult / TradeRecord / BacktestConfig
```

当前项目中不存在，不能作为落地对象。修正为：

```text
src/backtest/
├── tracker.py      # 推荐记录 JSONL 追加
├── returns.py      # 后续收益计算
├── allocator.py    # 100w 仓位分配
├── limiter.py      # 涨跌停/停牌交易约束
├── report.py       # HTML 收益跟踪报告
└── models.py       # 结构化记录模型
```

历史回测不新建 `backtest/enhanced/`，而是扩展为 replay 模式：

```text
1. 遍历历史交易日 T
2. 调用 engine.scan(strategy=composite, as_of=T, legacy_mode=false/true)
3. 保存当日新/旧策略推荐记录到 recommendations.jsonl
4. 用 KlineFetcher 获取 T 之后行情，计算持仓第 N 日收益
5. 用 allocator 做 100w 模拟组合
6. 用 report 输出新旧策略对比
```

> 注意：当前 CLI 若尚未暴露 `backtest --action replay/evaluate`，需在 CLI 层补入口；底层逻辑优先复用 `src/backtest`，不要另建一套 parallel backtester。

**P0 修正：不做会导致不可执行或结论不可信**

| 项目 | 修正要求 |
|------|----------|
| 历史 walk-forward | 删除/废弃 `backtest/enhanced/` 方案，改为 `src/backtest` replay |
| 防前视 | replay、evaluate、update 全部使用 `as_of=观察日/推荐日`；收益计算只允许读取推荐日后的行情 |
| universe 范围 | 不做无约束全 A 重扫；优先复用现有成交额过滤口径，避免数小时 API 重抓 |
| 命名统一 | 文档和代码统一叫 `src/backtest`，不要再新增 `src/tracking` |
| 存储格式 | `recommendations.jsonl` 作为程序主账本，CSV 作为人工审阅导出 |
| Sharpe / 波动率 | `std == 0` 时 Sharpe 记 0，避免除零 |
| CLI 入口 | 在现有 `backtest` 命令基础上扩展 `--action replay/evaluate/report`，而不是新增散落脚本 |

**P1 修正：补齐实盘跟踪核心字段和规则**

`tracker.py` 推荐记录需补字段：

```text
run_id
run_time
signals
limit_status_at_recommend
can_buy_at_recommend
email_subject
report_path
overlap              # 新旧共同命中
```

`limiter.py` 交易约束需补齐：

```text
ST: ±5%
沪深主板: ±10%
创业板/科创板: ±20%
北交所: ±30%
一字板: 开=高=低=涨停/跌停时按不可买/不可卖处理
停牌: 不买不卖，交易顺延
涨停不可买: 不建仓，等待下一可买日
跌停不可卖: 顺延卖出，最多等待 5 个交易日后标记风险
```

`allocator.py` 仓位模型需补齐：

```text
equal: 等权
score: 分数加权
kelly: 凯利/胜率权重
overlap_boost: 新旧共同命中双倍权重，单票上限可放宽
fast: 次日/短线快进快出
long: D+5 持有
t3/t5/t10: 持仓第 3/5/10 交易日
stop_loss_take_profit: -5% 止损，+5%/+8% 分批止盈
trailing_stop: 最高浮盈回撤 3%-5% 移动止盈
```

`report.py` 收益报告需补齐：

```text
共同命中列
等权 / 分数加权 / 共同命中增强 三模型并列
样本量护栏：样本 < 30 只显示“观察中”，不下强结论
可交易样本数 / 不可交易样本数
最大浮盈 / 最大回撤 / 止损触发 / 止盈触发
```

**P2 修正：提升可信度和可审阅性**

| 项目 | 要求 |
|------|------|
| 基准对比 | 增加沪深300或中证全指同期收益，输出 `benchmark_ret` / `excess_ret` |
| CSV 导出 | JSONL 主账本不变，额外导出 `recommendations.csv`、`portfolio_daily.csv` |
| 收益标签 | 将 `D+1/D+5` 明确为“持仓第 N 交易日”，避免买入被涨停顺延后口径混乱 |
| 子策略归因 | 按 `hit_strategy_keys` 汇总子策略胜率、平均收益、不可交易比例 |
| 无网络回归 | 使用合成数据验证记录、收益、分配、报告全链路 |

**推荐落地顺序（修正版）**

```text
1. 先让每日新/旧策略 scan + email 自动写入 recommendations.jsonl，积累真实样本。
2. 补齐 tracker P1 字段，确保每条推荐能追溯 run_id、邮件标题、报告路径、推荐时价格和可买状态。
3. 补齐 limiter 的 ST/北交所/一字板/停牌规则，避免收益模拟失真。
4. 扩展 allocator：先做 overlap_boost，再做止损止盈/移动止盈。
5. 扩展 report：共同命中列、三模型并列、样本量护栏。
6. 再做 replay 历史回测，用 as_of 逐日复盘新旧策略。
7. 最后补基准超额收益、CSV 导出、子策略归因。
```

**调整后的验证清单**

```text
[ ] scan 发送邮件后 recommendations.jsonl 自动 append，且不覆盖旧记录
[ ] 每条记录包含 run_id/run_time/signals/email_subject/report_path
[ ] 新旧共同命中标的 overlap=true，组合模拟不重复买入
[ ] 涨停不可买、跌停不可卖、ST、北交所、一字板、停牌规则可用合成数据验证
[ ] evaluate/report 能输出新旧策略胜率、D+1~D+10、100w组合收益
[ ] 样本 < 30 时报告只显示“观察中”
[ ] replay 使用 engine.scan(as_of=T)，不读取未来行情做选股
[ ] JSONL 与 CSV 数据一致
```

#### 5.1.1.16 交易时间门禁（非交易时间信号不入样本）

> **新增硬规则**：交易时间之外执行的策略结果，只能作为人工查看/调试输出，**不得写入收益跟踪账本、不得进入收益统计、不得进入回测样本、不得影响新旧策略可信度结论**。

**规则原因**

非交易时间的价格快照可能来自收盘价、缓存价、延迟行情或不完整盘前/盘后数据，无法代表真实可成交价格。若写入 `recommendations.jsonl` 并参与 T+N 收益，会污染策略可信度。

**交易时间定义（A股普通交易日）**

```text
上午连续竞价: 09:30 - 11:30
下午连续竞价: 13:00 - 15:00
集合竞价、午间、收盘后、周末、节假日: 默认不计入收益样本
```

> v1 只采纳连续竞价时间段。集合竞价阶段如需纳入，必须单独增加 `session=call_auction` 并独立统计，不与普通盘中推荐混算。

**落地规则**

| 场景 | 是否写入推荐账本 | 是否计算收益 | 是否进入回测/可信度统计 | 说明 |
|------|------------------|--------------|--------------------------|------|
| 交易日 09:30-11:30 | 是 | 是 | 是 | 正常盘中信号 |
| 交易日 13:00-15:00 | 是 | 是 | 是 | 正常盘中信号 |
| 交易日 09:30 前 | 否 | 否 | 否 | 盘前数据不可作为推荐价 |
| 交易日 11:30-13:00 | 否 | 否 | 否 | 午间休市，不可成交 |
| 交易日 15:00 后 | 否 | 否 | 否 | 收盘后不可成交 |
| 周末/节假日 | 否 | 否 | 否 | 非交易日 |
| 手工调试/历史 replay | 仅写入 replay 专用输出，不写入实盘推荐账本 | 按 replay 规则独立计算 | 不混入实盘样本 | 与真实推荐分离 |

**实现要求**

```text
1. scan 完成后，tracker.record() 前先判断当前时间是否处于有效交易时间。
2. 非交易时间执行 scan 时，允许生成普通 scan_report，但不 append recommendations.jsonl。
3. 非交易时间发送邮件时，邮件可发送，但标题/摘要需标记“非交易时间观察”，且不进入收益跟踪。
4. evaluate/report 默认只读取 trading_session=regular 的记录。
5. replay 历史回测必须使用独立 run_type=replay，不得写入 run_type=live 的真实推荐账本。
6. 所有收益报表顶部显示有效样本过滤条件：仅统计交易时间内 live 推荐。
```

**新增字段**

`RecommendationRecord` 增加：

```text
run_type: live / replay / debug
trading_session: regular / pre_market / lunch_break / after_close / non_trading_day / call_auction
is_countable: true / false
exclude_reason: 非交易时间 / 非交易日 / 调试模式 / replay隔离
```

**统计口径**

```text
收益统计样本 = run_type == live
           and trading_session == regular
           and is_countable == true

非交易时间样本只允许出现在“调试记录/观察记录”里，不进入：
- 新旧策略胜率
- T+1/T+3/T+5/T+10 收益
- 100w 组合模拟
- 子策略归因
- replay 历史回测基线
```

**验证清单补充**

```text
[ ] 09:29 执行 scan 不写入 recommendations.jsonl
[ ] 11:45 执行 scan 不写入 recommendations.jsonl
[ ] 15:01 执行 scan 不写入 recommendations.jsonl
[ ] 周末/节假日执行 scan 不写入 recommendations.jsonl
[ ] 非交易时间邮件标题标记“非交易时间观察”
[ ] evaluate/report 只统计 trading_session=regular 的 live 样本
[ ] replay 输出与 live 推荐账本隔离
```

### Step 5.2 TDX 模式配置驱动（双开关 · 不单独开分支 · 可废弃 test/tdx 分支）

> **需求**：TDX 为配置驱动，dev/pro 两分支都可用；**执行标的分析时单独运行即可，无需保留 test/tdx 分支**。

**① 双开关设计（呼应 4.③ 配置示例）**
- 开关① `tdx_data_source`：数据源层，true 时 K 线优先走 TDX（`tdx_fetcher.get_kline`）。
- 开关② `tdx_enabled`：分析层，true 时启用 TDX 持仓分析模式（独立运行 `strategy_analysis_tdx.py`）。

**② TDX 分析 = 独立运行，不并入主 composite 管线**
- 真实实现已在 `test/tdx` 分支验证：`strategy_analysis_tdx.py`（537 行，读 `holdings`、调 `get_tdx_fetcher()`、算 MA/RSI/KDJ/MACD 给持仓建议）+ `src/data/tdx_fetcher.py`（`TdxFetcher` 单例）。
- **落地动作**：把这两个文件恢复/合并进 `dev`（配置门控，dev/pro 都可用），作为独立分析入口：
  ```bash
  # 单独运行 TDX 持仓分析（开关②触发），不接入 morning_task 主扫描
  python strategy_analysis_tdx.py --config strategy_config.json
  ```
- 仅在用户「执行标的分析」时按需单独跑；与主全市场扫描互不影响。

**③ 废弃 test/tdx 分支（确认可删除）**
- 理由：TDX 已成配置项（双开关），不再需要独立分支隔离；`strategy_analysis_tdx.py`/`tdx_fetcher.py` 合并进 dev 后，test/tdx 的唯一价值消失。
- 步骤：
  1. 将 `test/tdx` 的 `strategy_analysis_tdx.py`、`src/data/tdx_fetcher.py` 合并进 dev（TDX 文件与 dev 无冲突，直接并入）；
  2. 验证 `python strategy_analysis_tdx.py` 可独立运行、读 `holdings` 输出持仓建议报告；
  3. `git branch -D test/tdx` 删除特性分支；
  4. dev 合入 pro 时，TDX 文件随主线一并进入 pro，开关默认 false（不影响正式扫描）。
- ⚠️ `test/tdx` 的 `backtest/runner.py` **不并入**（其 N 日收益逻辑已被 5.1 v1 walk_forward 吸收），删除分支时一并丢弃。

**④ 配置驱动示例（两个分支通用）**

```json
{
  "tdx_data_source": false,
  "tdx_enabled": false,
  "holdings": [
    {"symbol": "688362", "cost": 25.30},
    {"symbol": "000725", "cost": 4.15}
  ]
}
```

> `tdx_enabled=true` → 单独跑 TDX 持仓分析；`tdx_data_source=true` → 抓取 K 线优先 TDX。两者独立，可任意组合。

---

## 时间线汇总

```
阶段                   时间       产出
──────────────────────────────────────────────
零、建立回测基线         ~2小时    backtest.runner 运行旧10策略模式，记录基准数据
一、提交基线+剩余Bug     ~3小时    git commit + 6项修复
二、创建聚合策略层       ~8小时    4个 aggregated/*.py + legacy_mode + 互斥逻辑
三、验证+调整            ~4小时    导入+单策略+composite + 对比基线
四、清理与归档           ~4小时    archive/ + config 更新
五、新增功能             ~4小时    backtest/enhanced walk_forward(v1) + TDX双开关配置驱动
──────────────────────────────────────────────
总计                   ~2.5-3天   25个文件改动，净减 ~400行
```

## 附录：两方案关键不同点

| 项目 | 用户方案 (strategy_refactor_plan.md) | 我的方案 (OPTIMIZE_PLAN.md) | 折中方案 |
|------|--------------------------------------|----------------------------|---------|
| 旧策略文件处理 | 未明确 | 删除 | 移入 archive/ 备查 |
| 聚合目录名 | `aggregated/` | `stage/` | **`aggregated/`** |
| strategy_type.py | 删除 | 未提 | **保留（确认无依赖后再删）** |
| 互斥范围 | 4级优先级 | 仅 bottom↔trend | **仅 bottom↔trend** |
| 策略内子策略权重 | 固定比例 | 无 | **固定比例（方案2.1所示）** |
| 验证回测 | 单元测试+集成+回测 | walk-forward | **walk-forward(v1 初版)：策略选标→N日收益/胜率/回撤/基准超额** |
| 启动指纹纳入方式 | 加入 SUB_STRATEGIES | 加入 LaunchStrategy | **方案A：仅聚合在 LaunchStrategy 内部（0.35权重），SUB_STRATEGIES 不移除旧策略** |
