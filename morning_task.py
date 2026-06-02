#!/usr/bin/env python3
"""
早盘任务：新债检查 + 策略选股（内置模块）

执行逻辑：
  1. 交易日检查 → 非交易日跳过
  2. 今日有新债 → 发送新债邮件（独立邮件池）
  3. 今日无新债 → 执行策略选股 + 发送策略邮件

调用方式：
  python morning_task.py            # 正常执行
  python morning_task.py --debug    # 调试模式（新债邮件不收抄送）
  python morning_task.py --force    # 强制跳过交易日检查
"""

import sys
import os
import subprocess

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

force = "--force" in sys.argv
debug = "--debug" in sys.argv


def main():
    from check_trading import is_trading_day

    # ── 交易日检查 ──
    if not force:
        is_td, reason = is_trading_day()
        if not is_td:
            print(f"[跳过] 非交易日 ({reason})")
            return 0

    # ── 新债检查 ──
    from new_bond_reminder import (
        has_bonds_today, get_new_bonds_today,
        get_future_bonds, get_approved_bond_news,
        send_bond_email,
    )

    if has_bonds_today():
        print("[新债] 今日有新债可申购，发送新债邮件")
        bonds_today = get_new_bonds_today()
        bonds_future, future_src = get_future_bonds()
        approved, pipeline, appr_src = get_approved_bond_news()

        success = send_bond_email(
            bonds_today, bonds_future, future_src,
            approved, pipeline, appr_src,
            debug=debug
        )
        return 0 if success else 1

    # ── 无新债 → 策略选股 ──
    print("[策略] 今日无新债，执行策略选股")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [
        sys.executable, "main.py", "scan",
        "--email", "--report",
        "-s", "composite", "-l", "15"
    ]
    result = subprocess.run(
        cmd, cwd=PROJECT_DIR, env=env,
        stdout=sys.stdout, stderr=sys.stderr,
    )
    # 策略邮件已发送即为成功，忽略控制台输出编码报错
    if result.returncode != 0:
        print(f"[警告] 策略扫描退出码={result.returncode}，但邮件可能已发送")
    return 0


if __name__ == "__main__":
    sys.exit(main())
