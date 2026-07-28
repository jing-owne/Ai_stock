"""
业绩报告生成器

功能：
  1. 对全部跟踪记录计算收益（调用 ReturnCalculator）
  2. 按 模式(new/old) 分组，统计 连续 1~10 日 的平均收益、累计收益、胜率
  3. 对比 新策略 / 旧策略 可信度（逐日收益曲线 + 胜率）
  4. 用最新一天的记录模拟 100w 组合分配（快进快出 / 长期持有）
输出：HTML（便于展示）+ JSON 摘要
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from .models import RecommendationRecord, StrategyMode
from .tracker import RecommendationTracker, TRACKING_DIR
from .returns import ReturnCalculator
from .allocator import PositionAllocator, PortfolioPlan

logger = logging.getLogger("AInvest.Report")

MAX_WINDOW = 10


class PerformanceReporter:
    def __init__(self, kline_fetcher, tracker: Optional[RecommendationTracker] = None):
        self.f = kline_fetcher
        self.tracker = tracker or RecommendationTracker()
        self.calc = ReturnCalculator(kline_fetcher)

    # ───────────────────────────────────────────────
    # 1. 计算全部记录收益（回填并持久化）
    # ───────────────────────────────────────────────
    def refresh(self) -> List[RecommendationRecord]:
        recs = self.tracker.load_all()
        for r in recs:
            if r.is_countable and r.observed_days < MAX_WINDOW:
                try:
                    self.calc.compute(r, MAX_WINDOW)
                except Exception as e:
                    r.notes = f"计算失败:{e}"
                    r.observed_days = MAX_WINDOW
        self.tracker.save(recs)
        return recs

    # ───────────────────────────────────────────────
    # 2. 分组统计（新旧策略可信度）
    # ───────────────────────────────────────────────
    def summarize(self, recs: List[RecommendationRecord]) -> Dict[str, Any]:
        out = {}
        countable_recs = [r for r in recs if r.is_countable]
        for mode in (StrategyMode.NEW.value, StrategyMode.OLD.value):
            grp = [r for r in countable_recs if r.mode == mode]
            if not grp:
                out[mode] = {"count": 0}
                continue
            # 逐日平均收益
            day_avg = {}
            day_cum = {}
            base = 1.0
            for n in range(1, MAX_WINDOW + 1):
                vals = [r.returns.get(n) for r in grp if r.returns.get(n) is not None]
                day_avg[n] = round(sum(vals) / len(vals), 2) if vals else None
                if day_avg[n] is not None:
                    base *= (1 + day_avg[n] / 100)
                day_cum[n] = round((base - 1) * 100, 2) if day_avg[n] is not None else None
            # 交易胜率（仅统计可建仓且已算出交易收益的）
            traded = [r for r in grp if r.trade_executed and r.trade_return is not None]
            wins = [r for r in traded if r.trade_return > 0]
            out[mode] = {
                "count": len(grp),
                "status": "观察中" if len(grp) < 30 else "可评估",
                "traded": len(traded),
                "wins": len(wins),
                "win_rate": round(len(wins) / len(traded) * 100, 1) if traded else None,
                "avg_trade_return": round(sum(r.trade_return for r in traded) / len(traded), 2) if traded else None,
                "avg_day_return": day_avg,
                "cum_day_return": day_cum,
            }
        return out

    # ───────────────────────────────────────────────
    # 3. 组合模拟（100w）
    # ───────────────────────────────────────────────
    def simulate_portfolio(
        self, recs: List[RecommendationRecord],
        capital: float = 1_000_000, method: str = "score", style: str = "fast"
    ) -> Optional[PortfolioPlan]:
        candidates = self._latest_candidates(recs)
        if not candidates:
            return None
        return PositionAllocator(capital=capital, method=method).allocate(candidates, style=style)

    def simulate_portfolios(
        self, recs: List[RecommendationRecord], capital: float = 1_000_000, style: str = "fast"
    ) -> Dict[str, Dict[str, Any]]:
        out = {}
        for method in ("equal", "score", "overlap_boost"):
            plan = self.simulate_portfolio(recs, capital=capital, method=method, style=style)
            if plan:
                out[method] = plan.to_dict()
        return out

    def _latest_candidates(self, recs: List[RecommendationRecord]) -> List[Dict[str, Any]]:
        if not recs:
            return []
        countable_recs = [r for r in recs if r.is_countable]
        if not countable_recs:
            return []
        latest = max(r.date for r in countable_recs)
        todays = [r for r in countable_recs if r.date == latest]
        by_symbol: Dict[str, Dict[str, Any]] = {}
        for r in todays:
            if not r.trade_executed or r.trade_return is None:
                continue
            item = {
                "symbol": r.symbol,
                "name": r.name,
                "buy_price": r.send_price,
                "expected_return": r.trade_return,
                "score": r.score,
                "executable": True,
                "overlap": r.overlap,
                "modes": {r.mode},
            }
            prev = by_symbol.get(r.symbol)
            if not prev:
                by_symbol[r.symbol] = item
                continue
            prev["modes"].add(r.mode)
            prev["overlap"] = prev.get("overlap") or r.overlap or len(prev["modes"]) > 1
            prev["score"] = max(prev.get("score", 0), r.score)
            if r.trade_return > prev.get("expected_return", -999):
                prev.update({
                    "name": r.name,
                    "buy_price": r.send_price,
                    "expected_return": r.trade_return,
                })
        return sorted(
            by_symbol.values(),
            key=lambda x: (not x.get("overlap", False), -x.get("score", 0), -x.get("expected_return", 0)),
        )

    # ───────────────────────────────────────────────
    # 4. 生成报告
    # ───────────────────────────────────────────────
    def generate(self, capital=1_000_000, method="score", style="fast",
                 out_html: bool = True) -> Dict[str, Any]:
        recs = self.refresh()
        summary = self.summarize(recs)
        portfolio = self.simulate_portfolio(recs, capital, method, style)
        portfolios = self.simulate_portfolios(recs, capital, style)

        result = {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_records": len(recs),
            "countable_records": len([r for r in recs if r.is_countable]),
            "summary": summary,
            "portfolio": portfolio.to_dict() if portfolio else None,
            "portfolios": portfolios,
            "recent": [r.to_dict() for r in recs if r.is_countable][-30:],
        }
        if out_html:
            self._render_html(result, capital, method, style)
        return result

    # ── HTML 渲染 ──
    def _render_html(self, result: Dict[str, Any], capital, method, style) -> None:
        def color(v):
            if v is None:
                return "#888"
            return "#d83030" if v >= 0 else "#1a9e3e"   # 红涨绿跌

        lines = ['<html><head><meta charset="utf-8"><style>']
        lines.append("body{font-family:-apple-system,Segoe UI,Arial;margin:24px;color:#222}")
        lines.append("h2{margin-top:28px}.card{background:#fafafa;border:1px solid #eee;border-radius:8px;padding:14px;margin:10px 0}")
        lines.append("table{border-collapse:collapse;width:100%;font-size:13px}th,td{border:1px solid #ddd;padding:6px 8px;text-align:center}")
        lines.append("th{background:#f0f0f0}.up{color:#d83030}.down{color:#1a9e3e}.muted{color:#888}")
        lines.append("</style></head><body>")
        lines.append(
            f"<h1>策略收益跟踪报告</h1><p class='muted'>生成时间：{result['generated_at']} "
            f"｜ 记录总数：{result['total_records']} ｜ 有效样本：{result.get('countable_records', 0)} "
            f"｜ 过滤条件：live + regular + is_countable</p>"
        )

        # 新旧策略逐日累计收益对比
        lines.append("<h2>一、新旧策略可信度对比（连续1~10日累计收益%）</h2>")
        lines.append("<div class='card'><table>")
        lines.append("<tr><th>模式</th><th>样本</th><th>可交易</th><th>胜率</th><th>平均交易收益%</th>")
        for n in range(1, MAX_WINDOW + 1):
            lines.append(f"<th>D+{n}累计%</th>")
        lines.append("</tr>")
        for mode in (StrategyMode.NEW.value, StrategyMode.OLD.value):
            s = result["summary"].get(mode, {})
            if s.get("count", 0) == 0:
                lines.append(f"<tr><td>{mode}</td><td colspan='{5+MAX_WINDOW}' class='muted'>无记录</td></tr>")
                continue
            lines.append("<tr>")
            lines.append(f"<td><b>{mode}</b><br><span class='muted'>{s.get('status','')}</span></td><td>{s['count']}</td><td>{s.get('traded')}</td>")
            lines.append(f"<td>{s.get('win_rate')}</td><td style='color:{color(s.get('avg_trade_return'))}'>{s.get('avg_trade_return')}</td>")
            for n in range(1, MAX_WINDOW + 1):
                v = s.get("cum_day_return", {}).get(n)
                lines.append(f"<td style='color:{color(v)}'>{v}</td>")
            lines.append("</tr>")
        lines.append("</table></div>")

        # 组合模拟
        portfolios = result.get("portfolios") or {}
        if portfolios:
            lines.append(f"<h2>二、100w 组合模拟（三模型并列，风格={style}）</h2>")
            lines.append("<div class='card'><table><tr><th>模型</th><th>组合预期收益%</th><th>剩余现金</th><th>持仓数</th></tr>")
            for method_name, pf in portfolios.items():
                lines.append(f"<tr><td>{method_name}</td><td style='color:{color(pf['expected_return'])}'>{pf['expected_return']}</td>"
                             f"<td>{pf['cash_left']:.0f}</td><td>{len(pf['positions'])}</td></tr>")
            lines.append("</table></div>")

            pf = result.get("portfolio") or next(iter(portfolios.values()))
            lines.append(f"<div class='card'><p>当前明细模型：<b>{method}</b> ｜ 组合预期收益：<b style='color:{color(pf['expected_return'])}'>{pf['expected_return']}%</b> ｜ 剩余现金：{pf['cash_left']:.0f}元 ｜ 持仓数：{len(pf['positions'])}</p>")
            lines.append("<table><tr><th>代码</th><th>名称</th><th>买入价</th><th>预期收益%</th><th>权重</th><th>金额</th><th>股数</th><th>备注</th></tr>")
            for a in pf["positions"]:
                lines.append(f"<tr><td>{a['symbol']}</td><td>{a['name']}</td><td>{a['buy_price']:.2f}</td>"
                             f"<td style='color:{color(a['expected_return'])}'>{a['expected_return']}</td>"
                             f"<td>{a['weight']*100:.1f}%</td><td>{a['amount']:.0f}</td><td>{a['shares']}</td>"
                             f"<td class='muted'>{a.get('note','')}</td></tr>")
            lines.append("</table></div>")
        else:
            lines.append("<h2>二、100w 组合模拟</h2><p class='muted'>暂无可用候选（需先有可交易记录的当日推荐）</p>")

        # 近期明细
        lines.append("<h2>三、近期推荐明细（末30条）</h2>")
        lines.append("<div class='card'><table><tr><th>日期</th><th>模式</th><th>共同</th><th>排名</th><th>代码</th><th>名称</th><th>标签</th><th>发送价</th><th>自买入价涨跌幅%</th><th>交易收益%</th><th>最大浮盈%</th><th>最大回撤%</th><th>D+1%</th><th>D+5%</th><th>退出</th><th>备注</th></tr>")
        for r in result["recent"]:
            tr = r.get("trade_return")
            rsb = r.get("return_since_buy")
            lines.append(f"<tr><td>{r['date']}</td><td>{r['mode']}</td><td>{'是' if r.get('overlap') else ''}</td><td>{r['rank']}</td><td>{r['symbol']}</td>"
                         f"<td>{r['name']}</td><td class='muted'>{', '.join(r.get('tags', []))}</td><td>{r['send_price']:.2f}</td>"
                         f"<td style='color:{color(rsb)}'>{rsb}</td>"
                         f"<td style='color:{color(tr)}'>{tr}</td>"
                         f"<td style='color:{color(r.get('max_return'))}'>{r.get('max_return')}</td>"
                         f"<td style='color:{color(r.get('max_drawdown'))}'>{r.get('max_drawdown')}</td>"
                         f"<td style='color:{color(r.get('returns',{}).get(1))}'>{r.get('returns',{}).get(1)}</td>"
                         f"<td style='color:{color(r.get('returns',{}).get(5))}'>{r.get('returns',{}).get(5)}</td>"
                         f"<td class='muted'>{r.get('exit_reason','')}</td>"
                         f"<td class='muted'>{r.get('notes','')}</td></tr>")
        lines.append("</table></div>")

        # 当日推荐标的 · 自买入价涨跌幅收益率（最新一天）
        lines.append("<h2>四、当日推荐标的 · 自买入价涨跌幅收益率</h2>")
        recent_list = result.get("recent", [])
        if recent_list:
            latest_date = max(r["date"] for r in recent_list)
            todays = [r for r in recent_list if r["date"] == latest_date]
            todays.sort(key=lambda x: -(x.get("return_since_buy") or 0))
            lines.append(f"<p class='muted'>统计日：{latest_date} ｜ 共 {len(todays)} 只（按自买入价涨跌幅降序）</p>")
            lines.append("<div class='card'><table><tr><th>模式</th><th>共同</th><th>代码</th><th>名称</th><th>买入价</th><th>自买入价涨跌幅%</th><th>标签</th></tr>")
            for r in todays:
                rsb = r.get("return_since_buy")
                lines.append(f"<tr><td>{r['mode']}</td><td>{'是' if r.get('overlap') else ''}</td>"
                             f"<td>{r['symbol']}</td><td>{r['name']}</td><td>{r['send_price']:.2f}</td>"
                             f"<td style='color:{color(rsb)}'>{rsb}</td>"
                             f"<td class='muted'>{', '.join(r.get('tags', []))}</td></tr>")
            lines.append("</table></div>")
        else:
            lines.append("<p class='muted'>暂无记录</p>")
        lines.append("</body></html>")

        out_path = TRACKING_DIR / f"report_{datetime.now().strftime('%Y-%m-%d')}.html"
        out_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"报告已生成: {out_path}")
