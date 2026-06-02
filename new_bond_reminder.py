#!/usr/bin/env python3
"""
新债打新提醒 — 内置模块（复用 check_trading + email_sender 基础设施）

功能：
  1. 判断当天是否为交易日 → 复用 check_trading.is_trading_day()
  2. 获取当天可申购的新债数据 → 三大模块
  3. 有可打新债 → 生成邮件（复用 email_sender 模板 + SMTP）
  4. 无新债 → 静默退出

调试模式（--debug）：只发送主收件人，不发送抄送
测试模式（--test）：使用模拟数据发送测试邮件查看UI效果

导出函数：
  get_new_bonds_today()     → 今日可申购新债
  get_future_bonds()        → 未来可申购可转债
  get_approved_bond_news()  → 已获批可转债动态
  generate_bond_content()   → 生成文本内容（复用 email_sender 模板）
  send_bond_email()         → 发送新债邮件
  has_bonds_today()         → 快速判断今日是否有新债
"""

import sys
import os
import argparse
import logging
import time
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from check_trading import is_trading_day
from src.reports.email_sender import EmailSender, format_email_html_responsive
from src.core.config import Config, EmailConfig
from src.data.fetcher import DataFetcher

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("BondReminder")


# ── 模拟测试数据 ──
MOCK_BONDS_TODAY = [
    {'bond_code': '113686.SH', 'bond_name': '测试转债',
     'apply_code': '754686', 'apply_date': datetime.now().strftime('%m-%d'),
     'price': '100.00', 'rating': 'AA+', 'max_shares': '10000'},
    {'bond_code': '123250.SZ', 'bond_name': '演示转债',
     'apply_code': '370750', 'apply_date': datetime.now().strftime('%m-%d'),
     'price': '100.00', 'rating': 'AA', 'max_shares': '10000'},
    {'bond_code': '113687.SH', 'bond_name': 'UI预览EB',
     'apply_code': '754687', 'apply_date': datetime.now().strftime('%m-%d'),
     'price': '100.00', 'rating': 'AAA', 'max_shares': '5000'},
]

MOCK_BONDS_FUTURE = [
    {'bond_name': '迪威转债', 'apply_date': '20260604', 'stock_name': '迪威尔', 'price': '32.49', 'rating': 'AA'},
    {'bond_name': '肇民转债', 'apply_date': '20260615', 'stock_name': '肇民科技', 'price': '28.50', 'rating': 'AA-'},
    {'bond_name': '中科转债', 'apply_date': '20260620', 'stock_name': '中科曙光', 'price': '45.00', 'rating': 'AAA'},
]

MOCK_APPROVED = [
    {'bond_name': '南芯转债', 'stock_code': '南芯科技', 'status': '已获核准批文',
     'notice_date': '2026-05', 'conv_price': '待公告'},
    {'bond_name': '春风转债', 'stock_code': '春风动力', 'status': '已获核准(已完成分红)',
     'notice_date': '2026-05', 'conv_price': '待公告'},
    {'bond_name': '华翔转债', 'stock_code': '华翔股份', 'status': '已获核准(已完成分红)',
     'notice_date': '2026-05', 'conv_price': '待公告'},
    {'bond_name': '中科转债', 'stock_code': '中科曙光', 'status': '已提交注册(80亿)',
     'notice_date': '2026-05', 'conv_price': '待公告'},
    {'bond_name': '赛恩斯转债', 'stock_code': '赛恩斯', 'status': '即将上会审核',
     'notice_date': '2026-06', 'conv_price': '待公告'},
]

MOCK_PIPELINE = {
    'stats': {'approved_waiting': 18, 'passed_committee': 11,
              'upcoming_review': 6, 'inquiry_done': 6},
    'source_url': 'https://caifuhao.eastmoney.com/news/20260530151213071344710',
    'source_name': '东方财富财富号·待发可转债统计表(截至2026-05-30)',
}


# ═══════════════════════════════════════════════════════
# 数据获取（核心，不动）
# ═══════════════════════════════════════════════════════

def has_bonds_today() -> bool:
    """快速判断今日是否有可申购新债"""
    bonds = get_new_bonds_today()
    return len(bonds) > 0


def get_new_bonds_today() -> List[Dict]:
    """获取今日可申购新债 — 数据来源: 同花顺IPO日历(stock_ipo_ths)"""
    try:
        import akshare as ak
        df = ak.stock_ipo_ths()
        if df is None or df.empty:
            return []

        today = datetime.now().date()
        bonds = []

        for _, row in df.iterrows():
            apply_date_str = str(row.get('申购日期', ''))
            if not apply_date_str or apply_date_str in ('-', 'nan'):
                continue
            try:
                if '-' in apply_date_str and '周' in apply_date_str:
                    date_part = apply_date_str.split(' ')[0]
                    parsed_date = datetime.strptime(
                        f"{today.year}-{date_part}", "%Y-%m-%d").date()
                else:
                    parsed_date = datetime.strptime(
                        apply_date_str[:10], "%Y-%m-%d").date()
            except (ValueError, IndexError):
                continue

            if parsed_date != today:
                continue

            stock_name = str(row.get('股票简称', ''))
            is_bond = any(kw in stock_name for kw in
                          ['转债', 'EB', '可转债', '可交债', '交换债'])
            if not is_bond:
                continue

            bonds.append({
                'bond_code': str(row.get('股票代码', '')),
                'bond_name': stock_name,
                'apply_code': str(row.get('申购代码', '')),
                'apply_date': today.strftime('%m-%d'),
                'price': str(row.get('发行价格', '100.00')),
                'rating': str(row.get('债券评级', '待查')),
                'max_shares': str(row.get('申购上限（万股）', '-')),
            })

        logger.info(f"今日可申购新债: {len(bonds)} 只")
        return bonds

    except ImportError:
        logger.warning("akshare 未安装")
        return []
    except Exception as e:
        logger.error(f"获取新债日历失败: {e}")
        return []


def get_future_bonds() -> Tuple[List[Dict], str]:
    """获取未来可申购可转债 — 数据来源: 东方财富 bond_cov_comparison"""
    import pandas as pd
    today = datetime.now().date()
    source = "东方财富 bond_cov_comparison"

    try:
        import akshare as ak
        for attempt in range(3):
            try:
                if attempt > 0:
                    time.sleep(2)
                df = ak.bond_cov_comparison()
                break
            except Exception:
                if attempt == 2:
                    raise
                continue

        if df is None or df.empty or '申购日期' not in df.columns:
            return [], source

        valid = df[df['申购日期'].notna()].copy()
        valid['申购日期_dt'] = pd.to_datetime(
            valid['申购日期'], format='%Y%m%d', errors='coerce')
        future = valid[valid['申购日期_dt'] >= pd.Timestamp(today)]

        bonds = []
        for _, row in future.iterrows():
            bonds.append({
                'bond_name': str(row.get('转债名称', '')),
                'bond_code': str(row.get('转债代码', '')),
                'apply_date': str(row.get('申购日期', '')),
                'stock_name': str(row.get('正股名称', '')),
                'stock_code': str(row.get('正股代码', '')),
                'price': str(row.get('转股价', '-')),
                'rating': '待查',
            })

        logger.info(f"未来可申购可转债: {len(bonds)} 只")
        return bonds, source

    except ImportError:
        return [], source
    except Exception as e:
        logger.warning(f"获取未来新债失败: {e}")
        return [], source


def get_approved_bond_news() -> Tuple[List[Dict], Dict, str]:
    """
    获取已获批可转债动态
    来源: 巨潮资讯(bond_cov_stock_issue_cninfo) + 东方财富财富号
    """
    import pandas as pd
    today = datetime.now().date()
    cutoff = today - timedelta(days=90)

    approved_list = []
    source = "巨潮资讯网(bond_cov_stock_issue_cninfo)"

    try:
        import akshare as ak
        df = ak.bond_cov_stock_issue_cninfo()
        if df is not None and not df.empty:
            df['公告日期_dt'] = pd.to_datetime(df['公告日期'], errors='coerce')
            recent = df[df['公告日期_dt'] >= pd.Timestamp(cutoff)]

            for _, row in recent.iterrows():
                bond_name = str(row.get('债券简称', ''))
                stock_code = str(row.get('标的股票', ''))
                notice_date = str(row.get('公告日期', ''))[:10] \
                    if pd.notna(row.get('公告日期')) else ''
                conv_price = str(row.get('转股价格', ''))
                if conv_price in ('nan', 'None', ''):
                    conv_price = '待公告'

                approved_list.append({
                    'bond_name': bond_name,
                    'stock_code': stock_code,
                    'notice_date': notice_date,
                    'status': '已发行',
                    'conv_price': conv_price,
                })

        logger.info(f"近期已发行可转债: {len(approved_list)} 只")
    except Exception as e:
        logger.warning(f"获取已发行可转债失败: {e}")

    pipeline = _fetch_pipeline()
    if pipeline:
        source += " + 东方财富财富号"

    return approved_list, pipeline, source


def _fetch_pipeline() -> Optional[Dict]:
    """审批管线统计（东方财富财富号，缓存，约每周更新）"""
    return {
        'stats': {
            'approved_waiting': 18, 'passed_committee': 11,
            'upcoming_review': 6, 'inquiry_done': 6,
        },
        'source_url': 'https://caifuhao.eastmoney.com/news/20260530151213071344710',
        'source_name': '东方财富财富号 · 待发可转债统计表(截至2026-05-30)',
        'article_date': '2026-05-30',
    }


# ═══════════════════════════════════════════════════════
# 内容生成 → 复用 email_sender 模板
# ═══════════════════════════════════════════════════════

def generate_bond_content(
    bonds_today: List[Dict],
    bonds_future: List[Dict],
    future_source: str,
    approved_list: List[Dict],
    pipeline: Dict,
    approved_source: str,
) -> str:
    """
    生成新债邮件文本内容（复用 email_sender 的 format_email_html_responsive 模板）
    格式与 generate_summary() 一致，使用 【】 标题 + | 表格
    """
    lines = []
    fetcher = DataFetcher()

    # ── 每日一言 ──
    lines.append("【每日一言】")
    lines.append("")
    lines.append(f"💡 {fetcher.get_daily_quote()}")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")

    # ── 财经动态 ──
    lines.append("【财经动态】")
    lines.append("")
    news_list = fetcher.fetch_all_news()
    if news_list:
        for i, news in enumerate(news_list[:8], 1):
            title = news.get('title', '')
            lines.append(f"{i}. {title}")
    else:
        lines.append("暂无财经动态更新")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")

    # ── 今日可申购新债 ──
    lines.append("【今日可申购新债】")
    lines.append("")
    if bonds_today:
        # 表格头
        lines.append(f"债券名称 | 申购代码 | 发行价 | 评级 | 申购上限")
        lines.append(f"--- | --- | --- | --- | ---")
        for b in bonds_today:
            lines.append(
                f"{b['bond_name']}（{b['bond_code']}） | "
                f"{b['apply_code']} | "
                f"¥{b['price']} | "
                f"{b.get('rating', '待查')} | "
                f"{b['max_shares']}张"
            )
        lines.append("")
        lines.append(f"📊 共 {len(bonds_today)} 只可申购新债")
        lines.append("💡 新债申购无市值要求，中签后缴款，建议顶格申购")
    else:
        lines.append("今日无新债可申购")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")

    # ── 未来可申购可转债 ──
    if bonds_future:
        lines.append("【未来可申购可转债】")
        lines.append("")
        lines.append(f"债券名称 | 正股 | 申购日期 | 转股价")
        lines.append(f"--- | --- | --- | ---")
        for b in bonds_future:
            apply_str = b.get('apply_date', '')
            if len(apply_str) == 8:
                try:
                    apply_str = datetime.strptime(apply_str, '%Y%m%d').strftime('%m-%d')
                except ValueError:
                    pass
            lines.append(
                f"{b['bond_name']} | "
                f"{b.get('stock_name', '-')} | "
                f"{apply_str} | "
                f"¥{b.get('price', '-')}"
            )
        lines.append("")
        lines.append(f"📊 共 {len(bonds_future)} 只 | 数据来源: {future_source}")
        lines.append("⚠️ 申购日期为预估，实际以公司公告为准")
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")

    # ── 已获批可转债动态 ──
    if approved_list or (pipeline and pipeline.get('stats')):
        lines.append("【已获批可转债动态】")
        lines.append("")

        # 管线概览
        if pipeline and pipeline.get('stats'):
            stats = pipeline.get('stats', {})
            labels = {
                'approved_waiting': '📌 已获核准/同意注册',
                'passed_committee': '✅ 通过上市委审核',
                'upcoming_review': '🔜 即将上会审核',
                'inquiry_done': '📝 完成问询待上会',
            }
            stat_parts = []
            for key, label in labels.items():
                val = stats.get(key, 0)
                if val > 0:
                    stat_parts.append(f"{label}: {val}家")
            lines.append(f"📊 审批管线: {' | '.join(stat_parts)}")
            lines.append(f"   来源: {pipeline.get('source_name', '东方财富财富号')}")
            lines.append("")

        # 已发行表格
        if approved_list:
            lines.append(f"债券名称 | 正股 | 状态 | 公告日期 | 转股价")
            lines.append(f"--- | --- | --- | --- | ---")
            for b in approved_list[:12]:
                lines.append(
                    f"{b['bond_name']} | "
                    f"{b.get('stock_code', '-')} | "
                    f"{b.get('status', '已发行')} | "
                    f"{b.get('notice_date', '-')} | "
                    f"{b.get('conv_price', '-')}"
                )
            lines.append("")
            lines.append(f"📊 近90天共 {len(approved_list)} 只 | 数据来源: {approved_source}")
        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")

    # ── 打新债小贴士 ──
    lines.append("【打新债小贴士】")
    lines.append("")
    lines.append("• 无需持有股票市值，空账户也可参与申购")
    lines.append("• 建议顶格申购（10000张起），提高中签率")
    lines.append("• 中签后T+2日16:00前确保账户有足额资金")
    lines.append("• 上市首日可择机卖出锁定收益")
    lines.append("• 申购当日无需缴款，中签后再存入资金即可")
    lines.append("")

    return '\n'.join(lines)


# ═══════════════════════════════════════════════════════
# 邮件发送 → 复用 EmailSender
# ═══════════════════════════════════════════════════════

def send_bond_email(
    bonds_today: List[Dict],
    bonds_future: List[Dict],
    future_source: str,
    approved_list: List[Dict],
    pipeline: Dict,
    approved_source: str,
    debug: bool = False,
) -> bool:
    """
    发送新债邮件（复用 EmailSender + format_email_html_responsive）

    Args:
        debug: True=只发主收件人跳过抄送
    """
    config_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "configs", "settings.yaml"
    )
    config = Config.from_yaml(config_path)
    bond_cfg = config.bond_email

    if not bond_cfg.enabled:
        logger.info("新债邮件未启用")
        return False
    if not bond_cfg.to_emails:
        logger.error("未配置收件人")
        return False

    # 生成文本内容
    text_content = generate_bond_content(
        bonds_today, bonds_future, future_source,
        approved_list, pipeline, approved_source
    )

    # 复用电邮模板 → HTML
    subject = "新债打新提醒"
    html_content = format_email_html_responsive(text_content, subject)

    # 保存预览
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(output_dir, exist_ok=True)
    preview_path = os.path.join(output_dir, "bond_email_preview.html")
    with open(preview_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    logger.info(f"HTML预览: {preview_path}")

    # 创建 EmailSender 发邮件
    sender = EmailSender(bond_cfg)

    return sender.send(
        subject=subject,
        html_content=text_content,  # send() 内部会调 format_email_html_responsive
        to_emails=bond_cfg.to_emails,
        cc_emails=[] if debug else bond_cfg.cc_emails,
        use_responsive=True,
    )


# ═══════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='新债打新提醒（内置模块版）')
    parser.add_argument('--debug', action='store_true',
                        help='调试模式：只发收件人，不发送抄送')
    parser.add_argument('--test', action='store_true',
                        help='测试模式：使用模拟数据发送邮件预览UI效果')
    args = parser.parse_args()

    mode_label = "测试" if args.test else ("调试" if args.debug else "正式")
    logger.info("=" * 50)
    logger.info(f"新债打新提醒 [{mode_label}] — 开始检查")

    # ── 交易日判断（复用 check_trading）──
    if not args.test:
        is_td, reason = is_trading_day()
        if not is_td:
            logger.info(f"今日非交易日({reason})，跳过")
            return 0

    # ── 获取数据 ──
    if args.test:
        bonds_today = MOCK_BONDS_TODAY
        bonds_future = MOCK_BONDS_FUTURE
        future_source = "模拟数据"
        approved_list = MOCK_APPROVED
        pipeline = MOCK_PIPELINE
        approved_source = "模拟数据"
    else:
        bonds_today = get_new_bonds_today()
        if not bonds_today:
            logger.info("今日无新债可申购，不发送邮件")
            return 0
        bonds_future, future_source = get_future_bonds()
        approved_list, pipeline, approved_source = get_approved_bond_news()

    # ── 发送 ──
    logger.info(f"今日: {len(bonds_today)}只 | 未来: {len(bonds_future)}只 | 已获批: {len(approved_list)}条")

    success = send_bond_email(
        bonds_today, bonds_future, future_source,
        approved_list, pipeline, approved_source,
        debug=args.debug or args.test
    )

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
