"""
Marcus策略小助手 命令行工具 · 公共模块重构
"""
import sys
import argparse
import logging
from pathlib import Path
from typing import Optional

from ..core.engine import AInvestEngine
from ..core.config import Config
from ..core.types import StrategyType


def setup_logging(level: str = "INFO"):
    """配置日志"""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def create_engine(config_path: Optional[str] = None) -> AInvestEngine:
    """创建引擎实例"""
    if config_path:
        config = Config.from_yaml(config_path)
    else:
        # 默认使用项目配置
        default_config = Path(__file__).parent.parent.parent / "configs" / "settings.yaml"
        if default_config.exists():
            config = Config.from_yaml(str(default_config))
        else:
            config = Config()

    return AInvestEngine(config)


def cmd_scan(args):
    """执行扫描命令"""
    engine = create_engine(args.config)

    strategy = StrategyType(args.strategy)
    legacy_mode = bool(getattr(args, "legacy_mode", False)) and strategy == StrategyType.COMPOSITE
    mode_label = None
    scan_kwargs = {}
    if strategy == StrategyType.COMPOSITE:
        scan_kwargs["legacy_mode"] = legacy_mode
        mode_label = "旧策略-10原子策略" if legacy_mode else "新策略-4聚合策略"

    # debug 模式: 标的池取持仓(strategy_config.holdings), 不走全市场扫描
    if getattr(args, "debug", False):
        scan_kwargs["universe"] = "holdings"

    # 执行扫描
    results = engine.scan(
        strategy=strategy,
        limit=args.limit,
        **scan_kwargs
    )
    if mode_label:
        context = dict(engine._last_strategy_context or {})
        context["mode_label"] = mode_label
        context["legacy_mode"] = legacy_mode
        engine._last_strategy_context = context

    # 打印结果
    print(f"\n{'='*60}")
    print(f"扫描完成: {strategy.value}" + (f" / {mode_label}" if mode_label else ""))
    print(f"{'='*60}\n")

    for i, result in enumerate(results, 1):
        signals = ", ".join(result.signals[:3])
        print(f"{i:2d}. {result.name}({result.symbol}) - 评分: {result.score:.1f}")
        print(f"    信号: {signals}")
        if result.data:
            print(f"    涨幅: {result.data.change_pct:+.2f}%  成交额: {result.data.amount/1e8:.2f}亿")
        print()

    # 生成报告
    if args.report:
        output_path = engine.generate_report(
            results=results,
            format=args.format
        )
        print(f"报告已生成: {output_path}")

    # 发送邮件（进程内直发，与新债通道同构）
    if args.email:
        success = engine.report_agent.send_email(
            results=results,
            strategy_name=f"{mode_label}（{strategy.value}）" if mode_label else strategy.value,
            strategy_context=engine._last_strategy_context,
        )
        print("邮件发送成功" if success else "邮件发送失败")


def cmd_email(args):
    """邮件测试命令"""
    engine = create_engine(args.config)

    print("\n测试SMTP连接...")
    success = engine.report_agent.test_email()

    if success:
        print("✅ 邮件配置正常")
    else:
        print("❌ 邮件配置异常,请检查SMTP设置")


def cmd_market(args):
    """执行市场分析命令"""
    engine = create_engine(args.config)
    analysis = engine.analyze_market()

    print(f"\n{'='*60}")
    print("市场分析报告")
    print(f"{'='*60}\n")
    print(f"日期: {analysis.date}")
    print(f"市场情绪: {analysis.market_sentiment}")
    print(f"风险等级: {analysis.risk_level}")
    print(f"\n{analysis.summary}")

    if analysis.sector_heat:
        print("\n板块热度:")
        for sector, heat in sorted(analysis.sector_heat.items(), key=lambda x: x[1], reverse=True):
            bar = "█" * int(heat * 10)
            print(f"  {sector}: {bar} {heat:.0%}")


def cmd_list(args):
    """列出所有策略"""
    print("\n可用策略:")
    print("-" * 40)
    for st in StrategyType:
        print(f"  {st.value:20s} - {st.name}")
    print()


def cmd_health(args):
    """健康检查"""
    engine = create_engine(args.config)

    health = engine.health_check()

    print("\n策略小助手健康状态:")
    print("-" * 40)
    for key, value in health.items():
        if isinstance(value, dict):
            print(f"{key}:")
            for k, v in value.items():
                print(f"  {k}: {v}")
        else:
            print(f"{key}: {value}")


def cmd_backtest(args):
    """回测 / 跟踪 / 组合模拟 命令 (v2.8 真实实现)"""
    from datetime import datetime
    from ..backtest.tracker import RecommendationTracker
    from ..backtest.report import PerformanceReporter
    from ..backtest.models import StrategyMode
    from ..data.kline_fetcher import KlineFetcher

    action = getattr(args, "action", "evaluate")
    capital = getattr(args, "capital", 1_000_000)
    method = getattr(args, "method", "score")
    style = getattr(args, "style", "fast")

    tracker = RecommendationTracker()

    if action == "replay":
        # ── 历史回放：对 start~end 每个交易日，分别跑 新/旧 策略(as_of 防前视)，记录 + 算收益 ──
        from datetime import timedelta
        if not args.start or not args.end:
            print("replay 需要提供 --start 和 --end，格式 YYYY-MM-DD")
            return
        try:
            d1 = datetime.strptime(args.start, "%Y-%m-%d")
            d2 = datetime.strptime(args.end, "%Y-%m-%d")
        except ValueError:
            print("日期格式错误，应为 YYYY-MM-DD")
            return
        engine = create_engine(args.config)
        fetcher = KlineFetcher()
        cur = d1
        replayed = 0
        while cur <= d2:
            ds = cur.strftime("%Y-%m-%d")
            # 跳过明显非交易日（周末）—粗略
            if cur.weekday() >= 5:
                cur += timedelta(days=1)
                continue
            for mode, legacy in (("new", False), ("old", True)):
                try:
                    results = engine.scan(
                        StrategyType.COMPOSITE, limit=args.limit,
                        as_of=ds, legacy_mode=legacy,
                    )
                    if results:
                        tracker.record(
                            results,
                            mode=mode,
                            send_date=ds,
                            hold_style=style,
                            run_type="replay",
                            strategy_name="composite",
                            force=True,
                        )
                        replayed += 1
                        print(f"  [{ds}] {mode}: 记录 {len(results)} 只")
                except Exception as e:
                    print(f"  [{ds}] {mode} 回放失败: {e}")
            cur += timedelta(days=1)
        print(f"\n历史回放完成：新增 {replayed} 条记录 ({args.start}~{args.end})")

    # ── 评估：计算全部记录收益 + 生成报告 ──
    reporter = PerformanceReporter(KlineFetcher(), tracker)
    result = reporter.generate(capital=capital, method=method, style=style)

    print(f"\n{'='*60}")
    print(f"跟踪报告（生成于 {result['generated_at']}，记录总数 {result['total_records']}）")
    print(f"{'='*60}")
    for mode in (StrategyMode.NEW.value, StrategyMode.OLD.value):
        s = result["summary"].get(mode, {})
        if s.get("count", 0) == 0:
            print(f"\n[{mode}] 无记录")
            continue
        wr = s.get("win_rate")
        atr = s.get("avg_trade_return")
        print(f"\n[{mode}] 样本={s['count']} 可交易={s.get('traded')} "
              f"胜率={wr}% 平均交易收益={atr}%")
        cum = s.get("cum_day_return", {})
        print("  逐日累计收益%: " + "  ".join(
            f"D+{n}:{cum.get(n)}" for n in range(1, 11)))
    pf = result.get("portfolio")
    if pf:
        print(f"\n[组合模拟] 方法={method} 风格={style} 预期收益={pf['expected_return']}% "
              f"持仓={len(pf['positions'])} 现金={pf['cash_left']:.0f}")
    else:
        print("\n[组合模拟] 暂无可用候选（需先有可交易记录的当日推荐）")
    print(f"\nHTML 报告已生成至 data/tracking/report_{datetime.now().strftime('%Y-%m-%d')}.html")


def create_parser() -> argparse.ArgumentParser:
    """创建命令行解析器"""
    parser = argparse.ArgumentParser(
        description="Marcus策略小助手 - AI驱动的量化策略分析平台 · 可转债打新提醒",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "-c", "--config",
        help="配置文件路径"
    )

    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别"
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # scan命令
    scan_parser = subparsers.add_parser("scan", help="执行标的扫描")
    scan_parser.add_argument(
        "-s", "--strategy",
        default="composite",
        choices=[st.value for st in StrategyType],
        help="策略类型"
    )
    scan_parser.add_argument("-l", "--limit", type=int, default=15, help="返回结果数量")
    scan_parser.add_argument("--report", action="store_true", help="生成报告")
    scan_parser.add_argument(
        "-f", "--format",
        default="html",
        choices=["html", "markdown", "json"],
        help="报告格式"
    )
    scan_parser.add_argument("--email", action="store_true", help="发送邮件报告")
    scan_parser.add_argument("--debug", action="store_true", help="调试模式:正常发邮件但跳过抄送")
    scan_parser.add_argument("--legacy-mode", action="store_true", help="composite策略使用旧10原子策略模式")
    scan_parser.set_defaults(func=cmd_scan)

    # email命令
    email_parser = subparsers.add_parser("email", help="测试邮件配置")
    email_parser.set_defaults(func=cmd_email)

    # market命令
    market_parser = subparsers.add_parser("market", help="分析市场状态")
    market_parser.set_defaults(func=cmd_market)

    # list命令
    list_parser = subparsers.add_parser("list", help="列出所有策略")
    list_parser.set_defaults(func=cmd_list)

    # health命令
    health_parser = subparsers.add_parser("health", help="策略小助手健康检查")
    health_parser.set_defaults(func=cmd_health)

    # backtest命令（跟踪 / 回放 / 组合模拟）
    backtest_parser = subparsers.add_parser("backtest", help="回测/跟踪/组合模拟")
    backtest_parser.add_argument(
        "--action", default="evaluate",
        choices=["evaluate", "replay"],
        help="evaluate=对已有跟踪记录算收益+报告；replay=历史回放新/旧策略"
    )
    backtest_parser.add_argument("-s", "--strategy", default="composite", help="回放用的策略(默认composite)")
    backtest_parser.add_argument("--start", help="回放开始日期 YYYY-MM-DD")
    backtest_parser.add_argument("--end", help="回放结束日期 YYYY-MM-DD")
    backtest_parser.add_argument("--limit", type=int, default=15, help="回放每条记录数量")
    backtest_parser.add_argument("--capital", type=float, default=1_000_000, help="组合资金(默认100w)")
    backtest_parser.add_argument("--method", default="score", choices=["equal", "score", "kelly", "overlap_boost"], help="分配方式")
    backtest_parser.add_argument("--style", default="fast", choices=["fast", "long", "t3", "t5", "t10", "stop", "trailing"], help="持有风格")
    backtest_parser.set_defaults(func=cmd_backtest)

    return parser


def cli():
    """CLI入口"""
    parser = create_parser()
    args = parser.parse_args()

    setup_logging(args.log_level)

    if not args.command:
        parser.print_help()
        return

    args.func(args)


def main():
    """主入口"""
    try:
        cli()
    except KeyboardInterrupt:
        print("\n\n已退出")
        sys.exit(0)
    except Exception as e:
        print(f"\n错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
