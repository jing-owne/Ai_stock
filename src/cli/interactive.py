"""
交互式命令行界面
"""
import sys
import readline
from typing import Optional

from ..core.engine import AInvestEngine
from ..core.config import Config
from ..core.types import StrategyType


class InteractiveCLI:
    """
    交互式命令行界面
    """
    
    COMMANDS = {
        "help": "显示帮助信息",
        "scan": "执行股票扫描",
        "market": "分析市场",
        "list": "列出策略",
        "report": "生成报告",
        "health": "健康检查",
        "quit": "退出",
    }
    
    def __init__(self, engine: Optional[AInvestEngine] = None):
        self.engine = engine or AInvestEngine()
        self.running = True
    
    def run(self):
        """运行交互式界面"""
        self.print_welcome()
        
        while self.running:
            try:
                command = input("\nAInvest> ").strip()
                
                if not command:
                    continue
                
                self.process_command(command)
                
            except KeyboardInterrupt:
                print("\n使用 'quit' 退出")
            except EOFError:
                break
        
        print("\n再见!")
    
    def print_welcome(self):
        """打印欢迎信息"""
        print("=" * 50)
        print("  AInvest - AI量化分析平台")
        print("  输入 'help' 查看可用命令")
        print("=" * 50)
    
    def process_command(self, command: str):
        """处理命令"""
        parts = command.split()
        cmd = parts[0].lower()
        args = parts[1:]
        
        if cmd == "help":
            self.cmd_help()
        elif cmd == "quit" or cmd == "exit":
            self.running = False
        elif cmd == "scan":
            self.cmd_scan(args)
        elif cmd == "market":
            self.cmd_market()
        elif cmd == "list":
            self.cmd_list()
        elif cmd == "health":
            self.cmd_health()
        elif cmd == "report":
            self.cmd_report(args)
        else:
            print(f"未知命令: {cmd}")
            print("输入 'help' 查看可用命令")
    
    def cmd_help(self):
        """显示帮助"""
        print("\n可用命令:")
        for cmd, desc in self.COMMANDS.items():
            print(f"  {cmd:12s} - {desc}")
        print()
    
    def cmd_scan(self, args):
        """执行扫描"""
        strategy = "volume_surge"
        limit = 10
        
        if args:
            strategy = args[0]
        if len(args) > 1:
            try:
                limit = int(args[1])
            except ValueError:
                print("limit必须是数字")
                return
        
        try:
            strategy_type = StrategyType(strategy)
        except ValueError:
            print(f"无效的策略: {strategy}")
            return
        
        print(f"\n正在执行 {strategy_type.value} 策略扫描...")
        results = self.engine.scan(strategy_type, limit=limit)
        
        print(f"\n找到 {len(results)} 只符合条件的股票:")
        for i, r in enumerate(results, 1):
            print(f"  {i}. {r.name}({r.symbol}) - 评分: {r.score:.1f}")
    
    def cmd_market(self):
        """市场分析"""
        print("\n正在分析市场...")
        analysis = self.engine.analyze_market()
        
        print(f"\n市场情绪: {analysis.market_sentiment}")
        print(f"风险等级: {analysis.risk_level}")
        print(f"\n{analysis.summary}")
    
    def cmd_list(self):
        """列出策略"""
        print("\n可用策略:")
        for st in StrategyType:
            print(f"  {st.value:20s} - {st.name}")
    
    def cmd_health(self):
        """健康检查"""
        health = self.engine.health_check()
        print(f"\n系统状态: {health['status']}")
        print(f"版本: {health['version']}")
    
    def cmd_report(self, args):
        """生成报告"""
        strategy = "volume_surge"
        limit = 10
        fmt = "html"
        
        if args:
            strategy = args[0]
        if len(args) > 1:
            fmt = args[1]
        
        try:
            strategy_type = StrategyType(strategy)
        except ValueError:
            print(f"无效的策略: {strategy}")
            return
        
        print(f"\n生成 {strategy_type.value} 报告...")
        results = self.engine.scan(strategy_type, limit=limit)
        path = self.engine.generate_report(results, format=fmt)
        
        print(f"报告已生成: {path}")


def interactive():
    """启动交互式界面"""
    cli = InteractiveCLI()
    cli.run()


if __name__ == "__main__":
    interactive()
