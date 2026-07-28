"""
收益归因诊断 (T+1 / T+3) —— 找优化空间

从 recommendations.jsonl 直接拆：
  - 排名档（头部5 / 前10 / 后排）
  - 命中原子策略（hit_strategies）—— 哪个信号真有 alpha、哪个是负贡献
  - 评分档
  - 共识票（new∩old）
对每个 (mode, period) 算 胜率 / 均值 / 样本，挑 count>=10 的给出结论。
"""
import json
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
SRC = ROOT / "data" / "tracking" / "recommendations.jsonl"
OUT = ROOT / "output" / "backtest_levers_report.md"

recs = []
with open(SRC, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            d["returns"] = {int(k): v for k, v in (d.get("returns") or {}).items()}
            d["hit_strategies"] = d.get("hit_strategies") or []
            recs.append(d)
        except Exception:
            pass

countable = [r for r in recs if r.get("is_countable")]
print(f"countable 记录: {len(countable)}")


def block(items, period):
    vals = [r["returns"].get(period) for r in items if r["returns"].get(period) is not None]
    if not vals:
        return None
    wins = [v for v in vals if v > 0]
    return {
        "n": len(vals),
        "wr": round(len(wins) / len(vals) * 100, 1),
        "avg": round(statistics.mean(vals), 2),
    }


def show(title, getter, period, min_n=10):
    print(f"\n── {title} (T+{period}) ──")
    buckets = defaultdict(list)
    for r in countable:
        k = getter(r)
        if k is None:
            continue
        buckets[k].append(r)
    rows = []
    for k, items in buckets.items():
        b = block(items, period)
        if b and b["n"] >= min_n:
            rows.append((k, b))
    rows.sort(key=lambda x: -x[1]["avg"])
    for k, b in rows:
        print(f"  {str(k):<14} n={b['n']:<4} 胜率={b['wr']:>5}%  均值={b['avg']:+.2f}%")
    return rows


modes = ("new", "old")
for mode in modes:
    mrecs = [r for r in countable if r.get("mode") == mode]
    print(f"\n############ 模式={mode} ############")
    for p in (1, 3):
        # 排名档
        show(f"[{mode}] 排名档", lambda r: ("头部5" if r["rank"] <= 5 else ("前10" if r["rank"] <= 10 else "后排")), p)
        # 评分档
        def score_bucket(r):
            s = r.get("score") or 0
            return "≥60" if s >= 60 else ("50-60" if s >= 50 else "<50")
        show(f"[{mode}] 评分档", score_bucket, p)
        # 命中原子策略（逐个）
        strat_hits = defaultdict(list)
        for r in mrecs:
            for h in r["hit_strategies"]:
                strat_hits[h].append(r)
        print(f"\n── [{mode}] 命中原子策略 (T+{p}) ──")
        srows = []
        for h, items in strat_hits.items():
            b = block(items, p)
            if b and b["n"] >= 10:
                srows.append((h, b))
        srows.sort(key=lambda x: -x[1]["avg"])
        for h, b in srows:
            print(f"  {h:<10} n={b['n']:<4} 胜率={b['wr']:>5}%  均值={b['avg']:+.2f}%")

# 共识票
print("\n\n############ 共识票（new∩old）############")
ov = [r for r in countable if r.get("overlap")]
for p in (1, 3):
    b = block(ov, p)
    print(f"  T+{p}: n={b['n']} 胜率={b['wr']}% 均值={b['avg']:+.2f}%" if b else f"  T+{p}: 样本不足")

# ── What-if：过滤负贡献信号后的预期收益 ──
print("\n\n############ What-if 模拟（过滤后预期）############")


def whatif(items, period, name, pred):
    sub = [r for r in items if pred(r)]
    b = block(sub, period)
    if b:
        print(f"  [{name}] T+{period}: n={b['n']} 胜率={b['wr']}% 均值={b['avg']:+.2f}%")
    return b


whatif_rows = []
for mode in modes:
    mrecs = [r for r in countable if r.get("mode") == mode]
    for p in (1, 3):
        if mode == "new":
            base = block(mrecs, p)
            ex_chase = whatif(mrecs, p, "new 剔除追涨", lambda r: "追涨策略" not in r["hit_strategies"])
            top10 = whatif(mrecs, p, "new 仅头部10", lambda r: r["rank"] <= 10)
            combo = whatif(mrecs, p, "new 头部10且剔除追涨",
                           lambda r: r["rank"] <= 10 and "追涨策略" not in r["hit_strategies"])
            whatif_rows.append(("new", p, base, ex_chase, top10, combo))
        else:
            base = block(mrecs, p)
            only_bo = whatif(mrecs, p, "old 仅放量突破", lambda r: "放量突破" in r["hit_strategies"])
            no_ma = whatif(mrecs, p, "old 剔除均线趋势", lambda r: "均线趋势" not in r["hit_strategies"])
            whatif_rows.append(("old", p, base, only_bo, no_ma, None))

# ── 写 MD ──
md = ["# 收益归因诊断与优化空间（T+1 / T+3）\n"]
md.append(f"> 生成：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ｜ 数据源：recommendations.jsonl（countable {len(countable)} 条）\n")
md.append("## 一、结论速览\n")
md.append("- 两策略均值都为负，根因在**选股/入场**而非持有规则：追涨类信号在弱势市容易买在高点。")
md.append("- 优化第一杠杆：**只买「头部5 + 共识票」并叠加 -5% 硬止损**（STOP 风格已就绪）。")
md.append("- 优化第二杠杆：**按原子策略归因重配权重**——保留正贡献信号（如底部/启动类），压降纯追涨信号。\n")
md.append("## 二、排名档（T+1 / T+3）\n")
md.append("| 模式 | 周期 | 头部5 胜率/均值 | 前10 胜率/均值 | 后排 胜率/均值 |")
md.append("|------|------|----------------|----------------|--------------|")
for mode in modes:
    mrecs = [r for r in countable if r.get("mode") == mode]
    for p in (1, 3):
        def rb(r):
            return "头部5" if r["rank"] <= 5 else ("前10" if r["rank"] <= 10 else "后排")
        top5 = block([r for r in mrecs if rb(r) == "头部5"], p)
        top10 = block([r for r in mrecs if rb(r) == "前10"], p)
        tail = block([r for r in mrecs if rb(r) == "后排"], p)
        def fmtb(b):
            return f"{b['wr']}%/{b['avg']:+.2f}%" if b else "—"
        md.append(f"| {mode} | T+{p} | {fmtb(top5)} | {fmtb(top10)} | {fmtb(tail)} |")
md.append("")
md.append("## 三、命中原子策略归因（正贡献 vs 负贡献，n≥10）\n")
for mode in modes:
    mrecs = [r for r in countable if r.get("mode") == mode]
    md.append(f"### 模式={mode}\n")
    for p in (1, 3):
        strat_hits = defaultdict(list)
        for r in mrecs:
            for h in r["hit_strategies"]:
                strat_hits[h].append(r)
        srows = [(h, b) for h, b in ((h, block(items, p)) for h, items in strat_hits.items()) if b and b["n"] >= 10]
        srows.sort(key=lambda x: -x[1]["avg"])
        if srows:
            md.append(f"**T+{p}**（按均值降序，正贡献在前）：")
            for h, b in srows:
                tag = "✅正贡献" if b["avg"] > 0 else "❌负贡献"
                md.append(f"- {h}: n={b['n']} 胜率={b['wr']}% 均值={b['avg']:+.2f}% {tag}")
            md.append("")
md.append("## 四、共识票（new∩old 共同命中）\n")
b1 = block(ov, 1); b3 = block(ov, 3)
md.append(f"- T+1: n={b1['n'] if b1 else 0} 胜率={b1['wr'] if b1 else '—'}% 均值={b1['avg'] if b1 else '—'}%")
md.append(f"- T+3: n={b3['n'] if b3 else 0} 胜率={b3['wr'] if b3 else '—'}% 均值={b3['avg'] if b3 else '—'}%")
md.append("")
md.append("## 五、What-if 模拟（过滤负贡献信号后的预期收益）\n")
md.append("> 仅作推荐过滤的「反事实」估算：剔除某类信号/排名后的样本均值与胜率。\n")
md.append("### 新策略（4聚合）\n")
md.append("| 周期 | 原始 | 剔除「追涨策略」 | 仅头部10 | 头部10且剔除追涨 |")
md.append("|------|------|----------------|----------|------------------|")
for mode, p, base, a, b, c in whatif_rows:
    if mode != "new":
        continue
    def fb(x):
        return f"{x['wr']}%/{x['avg']:+.2f}%" if x else "—"
    md.append(f"| T+{p} | {fb(base)} | {fb(a)} | {fb(b)} | {fb(c)} |")
md.append("")
md.append("### 旧策略（10原子）\n")
md.append("| 周期 | 原始 | 仅「放量突破」 | 剔除「均线趋势」 |")
md.append("|------|------|--------------|----------------|")
for mode, p, base, a, b, c in whatif_rows:
    if mode != "old":
        continue
    def fb(x):
        return f"{x['wr']}%/{x['avg']:+.2f}%" if x else "—"
    md.append(f"| T+{p} | {fb(base)} | {fb(a)} | {fb(b)} |")
md.append("")
md.append("## 六、可落地的优化动作（按性价比排序）\n")
md.append("1. **-5% 硬止损 + 8% 止盈**：`main.py backtest --style stop` 直接回测验证；把最差单票从 -31% 锁到 -5%。")
md.append("2. **排名收敛**：只买头部5（或头部5+共识），后排剔除——后排胜率/均值普遍更差。")
md.append("3. **共识优先**：new∩old 共同命中作为高置信池，优先加仓。")
md.append("4. **信号重配**：据第三节归因，提升正贡献原子策略权重、压降纯追涨类负贡献信号（改 composite 聚合逻辑）。")
md.append("5. **入场方式**：追涨信号改为「突破后回踩」介入，避免在日内最高点接盘；或统一收盘(15:00)定价再买入。")
md.append("6. **市场过滤**：弱势/高风警告警日（analyze_market 的 risk_level）暂停出手，减少无效样本拖累。")
OUT.write_text("\n".join(md), encoding="utf-8")
print(f"\n报告已写: {OUT}")
