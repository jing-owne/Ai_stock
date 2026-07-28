#!/usr/bin/env python3
"""
早盘任务：策略扫描 + 新债检查（独立并行）

执行逻辑：
  1. 交易日检查 → 非交易日跳过
  2. 始终执行策略扫描 → 发策略邮件
  3. 策略完成后 → 独立检查可转债 → 有新债则发债邮件
  4. 两个邮件独立发送，互不影响

调用方式：
  python morning_task.py            # 正常执行
  python morning_task.py --debug    # 调试模式（只发收件人，不抄送）
  python morning_task.py --force    # 强制跳过交易日检查
  python morning_task.py --intraday  # 跳过可转债检查（不发债邮件）
"""

import sys
import os
import subprocess

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

force = "--force" in sys.argv
debug = "--debug" in sys.argv
intraday = "--intraday" in sys.argv


def run_strategy_scan(env, legacy: bool = False):
    """执行一次策略扫描并发送邮件（新策略 或 旧策略）。

    新旧策略各自独立运行、独立发邮件、独立记录到跟踪库(mode=new/old)，
    任一失败仅告警，不阻塞另一策略及后续可转债检查。
    """
    label = "旧策略(10原子)" if legacy else "新策略(4聚合)"
    print(f"[策略] 执行策略扫描（{label}）...")
    cmd = [
        sys.executable, "main.py", "scan",
        "--email", "--report",
        "-s", "composite", "-l", "15",
    ]
    if legacy:
        cmd.append("--legacy-mode")
    try:
        result = subprocess.run(
            cmd, cwd=PROJECT_DIR, env=env,
            stdout=sys.stdout, stderr=sys.stderr,
        )
        rc = result.returncode
    except Exception as e:
        rc = -1
        print(f"[错误] {label}扫描异常: {e}")
    if rc != 0:
        print(f"[警告] {label}扫描退出码={rc}，但邮件可能已发送/已部分记录")
    print(f"[策略] {label}扫描完成")


def main():
    from check_trading import is_trading_day

    # ── 交易日检查 ──
    if not force:
        is_td, reason = is_trading_day()
        if not is_td:
            print(f"[跳过] 非交易日 ({reason})")
            return 0

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    # ═══════════════════════════════════════════════
    # 第一步：先跑新策略，再跑旧策略（各自独立发邮件 + 记录，互不阻塞）
    # ═══════════════════════════════════════════════
    run_strategy_scan(env, legacy=False)
    run_strategy_scan(env, legacy=True)

    # ═══════════════════════════════════════════════
    # 第二步：策略完成后，独立检查可转债
    # ═══════════════════════════════════════════════
    if intraday:
        print("[新债] --intraday 模式：跳过可转债检查，不发债邮件")
    else:
        print("[新债] 检查可转债...")
        from new_bond_reminder import (
            has_bonds_today, get_new_bonds_today,
            get_future_bonds, get_approved_bond_news,
            send_bond_email,
        )

        if has_bonds_today():
            print("[新债] 今日有新债可申购，发送新债邮件")
            bonds_today = get_new_bonds_today()
            bonds_future, future_src = get_future_bonds()
            _, pipeline, _ = get_approved_bond_news()

            pipeline_bonds = len(pipeline.get('lists', {}).get('approved_waiting', [])) if pipeline else 0
            print(f"[新债] 今日:{len(bonds_today)}只 | 未来:{len(bonds_future)}只 | 已获批待发:{pipeline_bonds}家")

            success = send_bond_email(
                bonds_today, bonds_future, future_src, pipeline,
                debug=debug,
            )
            if success:
                print("[新债] 新债邮件发送成功")
            else:
                print("[新债] 新债邮件发送失败")
        else:
            print("[新债] 今日无新债，不发送新债邮件")

    return 0


if __name__ == "__main__":
    sys.exit(main())
