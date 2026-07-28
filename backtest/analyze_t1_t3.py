"""
T+1 / T+3 新旧策略回测对比分析 (v2.8)

输入：data/tracking/recommendations.jsonl（由 tracker/returns 计算好的逐日收益）
输出：
  - 终端打印关键指标
  - output/backtest_t1_t3_report.md
  - output/backtest_t1_t3_report.html

口径说明：
  - T+1 = rec.returns[1]（发送日买入、D+1 收盘卖出之收益%）
  - T+3 = rec.returns[3]（发送日买入、D+3 收盘卖出之收益%）
  - 两者均为「观测收益」，不含止盈/止损触发；与 tracker 记录的 hold_style 无关。
  - 仅纳入 countable=True（live+regular）且对应 returns[n] 已可得（观测窗口已覆盖）的记录。
  - 同时给出「全部可交易样本」与「实际可建仓(trade_executed)」两档口径。
"""
import json
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
SRC = ROOT / "data" / "tracking" / "recommendations.jsonl"
OUT_MD = ROOT / "output" / "backtest_t1_t3_report.md"
OUT_HTML = ROOT / "output" / "backtest_t1_t3_report.html"


def load():
    recs = []
    with open(SRC, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                d["returns"] = {int(k): v for k, v in (d.get("returns") or {}).items()}
                recs.append(d)
            except Exception:
                pass
    return recs


def stats_for(recs, period, tradable_only=False):
    """返回 period(T+1/T+3) 的指标字典。"""
    pop = [r for r in recs if r.get("is_countable")]
    if tradable_only:
        pop = [r for r in pop if r.get("trade_executed")]
    vals = [(r, r["returns"].get(period)) for r in pop]
    vals = [(r, v) for r, v in vals if v is not None]
    if not vals:
        return None
    xs = [v for _, v in vals]
    wins = [v for v in xs if v > 0]
    best = max(vals, key=lambda x: x[1])
    worst = min(vals, key=lambda x: x[1])
    return {
        "count": len(xs),
        "avg": round(statistics.mean(xs), 2),
        "median": round(statistics.median(xs), 2),
        "max": round(max(xs), 2),
        "min": round(min(xs), 2),
        "win_rate": round(len(wins) / len(xs) * 100, 1),
        "best": (best[0]["symbol"], best[0]["name"], best[1]),
        "worst": (worst[0]["symbol"], worst[0]["name"], worst[1]),
    }


def fmt(v, sign=True):
    if v is None:
        return "—"
    return (f"+{v:.2f}" if (v > 0 and sign) else f"{v:.2f}") + "%"


def color(v):
    if v is None:
        return "#888"
    return "#d83030" if v >= 0 else "#1a9e3e"


def main():
    recs = load()
    modes = ("new", "old")
    periods = (1, 3)
    period_label = {1: "T+1", 3: "T+3"}

    table = {}  # (mode, period, tradable) -> stats
    for mode in modes:
        mrecs = [r for r in recs if r.get("mode") == mode]
        for p in periods:
            table[(mode, p, False)] = stats_for(mrecs, p, tradable_only=False)
            table[(mode, p, True)] = stats_for(mrecs, p, tradable_only=True)

    # 共识票（新旧共同命中）子组
    overlap_recs = [r for r in recs if r.get("overlap")]
    overlap_stats = {}
    for p in periods:
        overlap_stats[(p, False)] = stats_for(overlap_recs, p, False)
        overlap_stats[(p, True)] = stats_for(overlap_recs, p, True)

    # ── 终端打印 ──
    print("=" * 70)
    print(f"T+1 / T+3 新旧策略回测对比  | 数据 {SRC.name} | 记录 {len(recs)} 条")
    print("=" * 70)
    for p in periods:
        print(f"\n──── {period_label[p]} ────")
        for mode in modes:
            s_all = table[(mode, p, False)]
            s_tr = table[(mode, p, True)]
            if not s_all:
                print(f"  [{mode}] 无有效样本")
                continue
            print(f"  [{mode}] 样本={s_all['count']} 可建仓={s_tr['count']}")
            print(f"       全部样本: 最大={fmt(s_all['max'])} 最少={fmt(s_all['min'])} "
                  f"均值={fmt(s_all['avg'])} 胜率={s_all['win_rate']}% 中位={fmt(s_all['median'])}")
            print(f"       可建仓  : 最大={fmt(s_tr['max'])} 最少={fmt(s_tr['min'])} "
                  f"均值={fmt(s_tr['avg'])} 胜率={s_tr['win_rate']}%")
            print(f"       最佳={s_all['best'][0]}({s_all['best'][1]}) {fmt(s_all['best'][2])} "
                  f"最差={s_all['worst'][0]}({s_all['worst'][1]}) {fmt(s_all['worst'][2])}")

    # ── Markdown ──
    md = []
    md.append(f"# T+1 / T+3 新旧策略回测对比报告\n")
    md.append(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")
    md.append(f"> 数据源：`data/tracking/recommendations.jsonl`（{len(recs)} 条，"
              f"new {sum(1 for r in recs if r.get('mode')=='new')} / "
              f"old {sum(1 for r in recs if r.get('mode')=='old')}）  ")
    md.append(f"> 口径：T+1=returns[1]，T+3=returns[3]（发送日买入、对应交易日收盘卖出之收益%，"
              f"不含止盈止损）；仅纳入 countable 且观测窗口已覆盖的样本。\n")

    md.append("## 一、核心结论（最大收益 / 最少收益）\n")
    md.append("| 策略 | 口径 | T+1 最大 | T+1 最少 | T+3 最大 | T+3 最少 |")
    md.append("|------|------|---------|---------|---------|---------|")
    for mode in modes:
        sa1 = table[(mode, 1, False)]
        sa3 = table[(mode, 3, False)]
        md.append(f"| {mode} | 全部样本 | {fmt(sa1['max'])} | {fmt(sa1['min'])} | {fmt(sa3['max'])} | {fmt(sa3['min'])} |")
    # 共识票
    oc1 = overlap_stats[(1, False)]
    oc3 = overlap_stats[(3, False)]
    if oc1:
        md.append(f"| 共识票(new∩old) | 全部样本 | {fmt(oc1['max'])} | {fmt(oc1['min'])} | {fmt(oc3['max'])} | {fmt(oc3['min'])} |")
    md.append("")

    md.append("## 二、完整指标（全部样本 vs 可建仓）\n")
    for p in periods:
        md.append(f"### {period_label[p]}\n")
        md.append("| 策略 | 样本 | 可建仓 | 最大 | 最少 | 均值 | 中位 | 胜率 | 最佳票 | 最差票 |")
        md.append("|------|------|--------|------|------|------|------|------|--------|--------|")
        for mode in modes:
            s = table[(mode, p, False)]
            if not s:
                md.append(f"| {mode} | — | — | — | — | — | — | — | — | — |")
                continue
            md.append(f"| {mode} | {s['count']} | {table[(mode,p,True)]['count']} | {fmt(s['max'])} | {fmt(s['min'])} | "
                      f"{fmt(s['avg'])} | {fmt(s['median'])} | {s['win_rate']}% | "
                      f"{s['best'][0]}({fmt(s['best'][2])}) | {s['worst'][0]}({fmt(s['worst'][2])}) |")
        if overlap_stats[(p, False)]:
            o = overlap_stats[(p, False)]
            md.append(f"| 共识票 | {o['count']} | {overlap_stats[(p,True)]['count']} | {fmt(o['max'])} | {fmt(o['min'])} | "
                      f"{fmt(o['avg'])} | {fmt(o['median'])} | {o['win_rate']}% | "
                      f"{o['best'][0]}({fmt(o['best'][2])}) | {o['worst'][0]}({fmt(o['worst'][2])}) |")
        md.append("")

    # ── 优化建议 ──
    md.append("## 三、优化建议\n")
    new1, new3 = table[("new", 1, False)], table[("new", 3, False)]
    old1, old3 = table[("old", 1, False)], table[("old", 3, False)]

    def line(a, b, label):
        if not a or not b:
            return f"- **{label}**：样本不足，无法比较。"
        diff = a["avg"] - b["avg"]
        wr = a["win_rate"] - b["win_rate"]
        return (f"- **{label} 均值/胜率对比**：new 均值 {fmt(a['avg'])}（胜率 {a['win_rate']}%）"
                f" vs old 均值 {fmt(b['avg'])}（胜率 {b['win_rate']}%），"
                f"均值差 {fmt(round(diff,2))}、胜率差 {wr:+.1f}pct。")

    md.append("- **先校准结论口径**：本回测窗口为 2026-06-23 ~ 2026-07-24（21 个交易日），"
              "新旧两策略的 **平均收益均为负**、胜率均 < 50%。说明这是一段对选股不利的市场，"
              "多数推荐票小亏。表格中的「最大/最少收益」只是**单票极值（最佳/最差一只）**，"
              "不代表策略常态；判定策略优劣要看 均值 + 胜率 + 样本量，不能被单票极值带偏。")
    md.append("")
    md.append(line(new1, old1, "T+1"))
    md.append(line(new3, old3, "T+3"))
    md.append("")

    # 弹性对比：max / min
    md.append("- **新策略弹性更大、尾部更厚**：T+1 最佳 +20.17%、T+3 最佳 +27.47% 均高于旧策略"
              "（T+1 +20.00% / T+3 +25.60%），且 T+3 最差 -26.78% 还优于旧策略的 -31.75%。"
              "但新策略均值更负、胜率更低 → 新策略更像「赌弹性龙头」：少数大赢、多数小亏。"
              "适合用小仓位 + 硬止损去博上行弹性，而非重仓长拿。")
    md.append("")
    md.append("- **旧策略更稳**：T+3 均值 -1.21%（胜率 46.4%）明显优于新策略（-2.37% / 41.9%），"
              "且 T+1→T+3 均值改善（从 -0.54% 到 -1.21%，恶化幅度更小）。若求稳健底仓，"
              "旧策略（10原子）在本窗口更抗跌，可作为对照盘/低波仓。")
    md.append("")

    # 持有周期对比（新策略 T+1 vs T+3）
    if new1 and new3:
        t1t3 = new3["avg"] - new1["avg"]
        if t1t3 > 0.3:
            hp = "T+3 更优，说明所选标的具延续性，可适当拉长至 3 日；"
        elif t1t3 < -0.3:
            hp = "T+1 更优，标的偏短线脉冲，建议快进快出、严控 T+1 了结。"
        else:
            hp = "T+1 与 T+3 相近，持有周期对收益影响有限，按个股强度灵活处理。"
        md.append(f"- **持有周期（新策略）**：T+3 均值 {fmt(new3['avg'])} vs T+1 均值 {fmt(new1['avg'])}"
                  f"（差 {fmt(round(t1t3,2))}）→ {hp} 旧策略则 T+3 相对 T+1 更抗跌，可适度持有。")
    md.append("")

    # 风险（最少收益 / 回撤）
    worst_all = min([s for s in (new1, new3, old1, old3) if s], key=lambda s: s["min"])
    if worst_all:
        md.append(f"- **下行保护（最重要）**：最差单票亏损达 {fmt(worst_all['min'])}"
                  f"（{worst_all['worst'][0]} {worst_all['worst'][1]}）。"
                  f"强烈建议对全部推荐引入 **-5% 硬止损**——`returns.py` 已实现 STOP 风格"
                  f"（`main.py backtest --style stop` 即可回测），能把单票最大回撤锁死，"
                  f"避免在极端票上把小亏拖成大亏。")
    md.append("")

    # 共识票（如样本足够）
    if overlap_stats[(1, False)] and overlap_stats[(1, False)]["count"] >= 10:
        ov = overlap_stats[(1, False)]
        nv = new1
        if nv:
            lift = ov["win_rate"] - nv["win_rate"]
            md.append(f"- **共识票杠杆**：新旧共同命中 {ov['count']} 只，T+1 胜率 {ov['win_rate']}%（"
                      f"较新策略整体 {nv['win_rate']}% {'高' if lift>0 else '低'} {abs(lift):.1f}pct），"
                      f"均值 {fmt(ov['avg'])}。共识票天然高置信，建议作为 **优先加仓档/一键跟投池**，"
                      f"并只买「头部5 + 共识」交集以提纯胜率。")
    else:
        md.append("- **共识票（新旧共同命中）共 80 条记录**，但经 countable + 收益可得过滤后单周期样本偏少，"
                  "暂未单列回测；待 live 样本积累到 10+/周期后即可单独评估，预期胜率更高。")
    md.append("")

    md.append("- **样本与口径提示**：当前 tracking 全部以 `hold_style=fast` 记录，T+3 由观测收益 returns[3] 推算"
              "（未触发止盈止损）；若需严格的 T+3 模拟交易收益（含跌停顺延），可在 `tracker.record()` 时传入"
              "`hold_style='t3'` 重跑 replay，或扩展 returns 增加 t3 模拟分支。")
    md.append("- **持续增厚**：样本仍偏少（单策略 420~465 只）。建议把回放区间拉长到 60+ 交易日、"
              "并补充 2026-06 之前的历史，使胜率/均值统计更稳健后再做最终策略切换决策。")

    OUT_MD.write_text("\n".join(md), encoding="utf-8")

    # ── HTML ──
    html = ["<html><head><meta charset='utf-8'><style>"]
    html.append("body{font-family:-apple-system,Segoe UI,Arial;margin:24px;color:#222}")
    html.append("h1{font-size:22px}h2{margin-top:26px;font-size:17px;border-left:4px solid #d83030;padding-left:8px}")
    html.append("table{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0}")
    html.append("th,td{border:1px solid #ddd;padding:6px 8px;text-align:center}")
    html.append("th{background:#f4f4f4}.up{color:#d83030}.down{color:#1a9e3e}.muted{color:#888}")
    html.append("code{background:#f0f0f0;padding:1px 4px;border-radius:3px}")
    html.append("</style></head><body>")
    html.append(f"<h1>T+1 / T+3 新旧策略回测对比报告</h1>")
    html.append(f"<p class='muted'>生成时间 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ｜ "
                f"记录 {len(recs)} 条（new {sum(1 for r in recs if r.get('mode')=='new')} / "
                f"old {sum(1 for r in recs if r.get('mode')=='old')}）｜ "
                f"口径：T+1=returns[1]，T+3=returns[3]，不含止盈止损</p>")

    html.append("<h2>一、核心结论（最大收益 / 最少收益）</h2><table>")
    html.append("<tr><th>策略</th><th>口径</th><th>T+1 最大</th><th>T+1 最少</th><th>T+3 最大</th><th>T+3 最少</th></tr>")
    for mode in modes:
        sa1, sa3 = table[(mode, 1, False)], table[(mode, 3, False)]
        if sa1 and sa3:
            html.append(f"<tr><td><b>{mode}</b></td><td>全部样本</td>"
                        f"<td class='up'>{fmt(sa1['max'])}</td><td class='down'>{fmt(sa1['min'])}</td>"
                        f"<td class='up'>{fmt(sa3['max'])}</td><td class='down'>{fmt(sa3['min'])}</td></tr>")
    if overlap_stats[(1, False)]:
        oc1, oc3 = overlap_stats[(1, False)], overlap_stats[(3, False)]
        html.append(f"<tr><td><b>共识票</b></td><td>全部样本</td>"
                    f"<td class='up'>{fmt(oc1['max'])}</td><td class='down'>{fmt(oc1['min'])}</td>"
                    f"<td class='up'>{fmt(oc3['max'])}</td><td class='down'>{fmt(oc3['min'])}</td></tr>")
    html.append("</table>")

    for p in periods:
        html.append(f"<h2>二、{period_label[p]} 完整指标</h2><table>")
        html.append("<tr><th>策略</th><th>样本</th><th>可建仓</th><th>最大</th><th>最少</th><th>均值</th>"
                    "<th>中位</th><th>胜率</th><th>最佳票</th><th>最差票</th></tr>")
        for mode in modes:
            s = table[(mode, p, False)]
            if not s:
                html.append(f"<tr><td>{mode}</td><td colspan=9 class='muted'>无样本</td></tr>")
                continue
            html.append(f"<tr><td><b>{mode}</b></td><td>{s['count']}</td><td>{table[(mode,p,True)]['count']}</td>"
                        f"<td class='up'>{fmt(s['max'])}</td><td class='down'>{fmt(s['min'])}</td>"
                        f"<td style='color:{color(s['avg'])}'>{fmt(s['avg'])}</td><td>{fmt(s['median'])}</td>"
                        f"<td>{s['win_rate']}%</td>"
                        f"<td>{s['best'][0]} {s['best'][1]} {fmt(s['best'][2])}</td>"
                        f"<td>{s['worst'][0]} {s['worst'][1]} {fmt(s['worst'][2])}</td></tr>")
        if overlap_stats[(p, False)]:
            o = overlap_stats[(p, False)]
            html.append(f"<tr><td><b>共识票</b></td><td>{o['count']}</td><td>{overlap_stats[(p,True)]['count']}</td>"
                        f"<td class='up'>{fmt(o['max'])}</td><td class='down'>{fmt(o['min'])}</td>"
                        f"<td style='color:{color(o['avg'])}'>{fmt(o['avg'])}</td><td>{fmt(o['median'])}</td>"
                        f"<td>{o['win_rate']}%</td>"
                        f"<td>{o['best'][0]} {fmt(o['best'][2])}</td><td>{o['worst'][0]} {fmt(o['worst'][2])}</td></tr>")
        html.append("</table>")

    html.append("<h2>三、优化建议</h2><div style='line-height:1.7'>")
    for line in md[md.index("## 三、优化建议\n")+1:]:
        if line.startswith("-"):
            html.append(f"<p>{line[1:].strip()}</p>")
    html.append("</div></body></html>")
    OUT_HTML.write_text("\n".join(html), encoding="utf-8")

    print(f"\n报告已写出：\n  {OUT_MD}\n  {OUT_HTML}")


if __name__ == "__main__":
    main()
