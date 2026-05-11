"""
Marcus 策略小助手 (AInvest) 命令行工具
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
    
    # 执行扫描
    results = engine.scan(
        strategy=strategy,
        limit=args.limit
    )
    
    # 打印结果
    print(f"\n{'='*60}")
    print(f"扫描完成: {strategy.value}")
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
    
    # 发送邮件
    if args.email:
        success = engine.report_agent.send_email(
            results=results,
            strategy_name=strategy.name,
            strategy_context=engine._last_strategy_context
        )
        if success:
            print("✅ 邮件发送成功")
        else:
            print("❌ 邮件发送失败")


def cmd_email(args):
    """邮件测试命令"""
    engine = create_engine(args.config)
    
    print("\n测试SMTP连接...")
    success = engine.report_agent.test_email()
    
    if success:
        print("✅ 邮件配置正常")
    else:
        print("❌ 邮件配置异常，请检查SMTP设置")


def cmd_market(args):
    """执行市场分析命令"""
    
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
    
    print("\n系统健康状态:")
    print("-" * 40)
    for key, value in health.items():
        if isinstance(value, dict):
            print(f"{key}:")
            for k, v in value.items():
                print(f"  {k}: {v}")
        else:
            print(f"{key}: {value}")


def cmd_backtest(args):
    """回测命令"""
    engine = create_engine(args.config)
    
    strategy = StrategyType(args.strategy)
    
    result = engine.strategy_agent.backtest(
        strategy_type=strategy,
        start_date=args.start,
        end_date=args.end
    )
    
    print(f"\n回测结果: {strategy.value}")
    print("-" * 40)
    print(f"收益率: {result['total_return']:.2f}%")
    print(f"胜率: {result['win_rate']:.2f}%")
    print(f"最大回撤: {result['max_drawdown']:.2f}%")
    print(f"夏普比率: {result['sharpe_ratio']:.2f}")
    print(f"总交易次数: {result['total_trades']}")


def create_parser() -> argparse.ArgumentParser:
    """创建命令行解析器"""
    parser = argparse.ArgumentParser(
        description="Marcus策略小助手(AInvest) - AI驱动的量化策略选股平台",
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
    scan_parser = subparsers.add_parser("scan", help="执行股票扫描")
    scan_parser.add_argument(
        "-s", "--strategy",
        default="volume_surge",
        choices=["volume_surge", "turnover_rank", "multi_factor", "ai_technical", "institution", "composite"],
        help="选股策略"
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
    health_parser = subparsers.add_parser("health", help="系统健康检查")
    health_parser.set_defaults(func=cmd_health)
    
    # backtest命令
    backtest_parser = subparsers.add_parser("backtest", help="回测策略")
    backtest_parser.add_argument("-s", "--strategy", required=True, help="策略类型")
    backtest_parser.add_argument("--start", required=True, help="开始日期 YYYY-MM-DD")
    backtest_parser.add_argument("--end", required=True, help="结束日期 YYYY-MM-DD")
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
