"""
AInvest - AI驱动的股票量化分析平台

入口文件
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.cli.main import main

if __name__ == "__main__":
    main()
