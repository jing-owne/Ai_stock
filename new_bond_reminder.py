#!/usr/bin/env python3
"""
新债打新提醒 — 内置模块（复用 check_trading + email_sender 基础设施）

功能：
  1. 判断当天是否为交易日 → 复用 check_trading.is_trading_day()
  2. 获取当天可申购的新债数据 → 三大模块
  3. 有可打新债 → 生成邮件（复用 email_sender 模板 + SMTP）
  4. 无新债 → 静默退出

调试模式（--debug）：只发送主收件人，不发送抄送

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
from src.reports.email_sender import format_email_html_responsive
from src.common.smtp_sender import SMTPSender
from src.core.config import Config, EmailConfig
from src.data.fetcher import DataFetcher

from src.common.logger import get_logger, setup_root_logger

setup_root_logger()
logger = get_logger("BondReminder")




# ═══════════════════════════════════════════════════════
# 数据获取（核心，不动）
# ═══════════════════════════════════════════════════════

def has_bonds_today() -> bool:
    """快速判断今日是否有可申购新债"""
    bonds = get_new_bonds_today()
    return len(bonds) > 0


def _enrich_bond_detail(bond: Dict) -> Dict:
    """用 bond_zh_cov_info 补充单只可转债的评级和申购上限"""
    import akshare as ak
    import pandas as pd
    bond_code = bond.get('bond_code', '')
    if not bond_code:
        bond['rating'] = '待查'
        bond['max_shares'] = '1000手(10000张)'
        return bond
    try:
        df = ak.bond_zh_cov_info(symbol=bond_code)
        if df is not None and not df.empty:
            rating = str(df.iloc[0].get('RATING', ''))
            online_aau = df.iloc[0].get('ONLINE_GENERAL_AAU', None)
            if rating and rating not in ('nan', 'None', ''):
                bond['rating'] = rating
            else:
                bond['rating'] = '待查'
            if online_aau and not pd.isna(online_aau):
                lots = int(online_aau)
                bond['max_shares'] = f'{lots}手({lots*10}张)'
            else:
                bond['max_shares'] = '1000手(10000张)'
        else:
            bond['rating'] = '待查'
            bond['max_shares'] = '1000手(10000张)'
    except Exception as e:
        logger.debug(f"获取{bond_code}评级失败: {e}")
        bond['rating'] = '待查'
        bond['max_shares'] = '1000手(10000张)'
    return bond


def _enrich_bonds(bonds: List[Dict]) -> List[Dict]:
    """批量补充可转债评级和申购上限"""
    for bond in bonds:
        _enrich_bond_detail(bond)
    return bonds


def get_new_bonds_today() -> List[Dict]:
    """获取今日可申购新债 — 数据来源: 同花顺 bond_zh_cov_info_ths → stock_ipo_ths 兜底"""
    import akshare as ak
    import pandas as pd
    today = datetime.now().date()

    def _try_ths():
        """第1源: bond_zh_cov_info_ths（直接返回可转债，含转股价）"""
        df = ak.bond_zh_cov_info_ths()
        if df is None or df.empty or '申购日期' not in df.columns:
            return []
        bonds = []
        for _, row in df.iterrows():
            apply_date_str = str(row.get('申购日期', ''))
            if not apply_date_str or apply_date_str in ('nan', 'NaT', '', 'None'):
                continue
            try:
                parsed_date = pd.to_datetime(apply_date_str).date()
            except Exception:
                continue
            if pd.isna(parsed_date) or parsed_date != today:
                continue
            bonds.append({
                'bond_code': str(row.get('债券代码', '')),
                'bond_name': str(row.get('债券简称', '')),
                'apply_code': str(row.get('申购代码', '')),
                'apply_date': today.strftime('%m-%d'),
                'price': str(row.get('转股价格', '100.00')),
                'rating': '',
                'max_shares': '',
            })
        return bonds

    def _try_ipo():
        """第2源: stock_ipo_ths（兜底，按名称过滤可转债）"""
        df = ak.stock_ipo_ths()
        if df is None or df.empty:
            return []
        bonds = []
        for _, row in df.iterrows():
            apply_date_str = str(row.get('申购日期', ''))
            if not apply_date_str or apply_date_str in ('-', 'nan'):
                continue
            try:
                if '-' in apply_date_str and '周' in apply_date_str:
                    date_part = apply_date_str.split(' ')[0]
                    parsed_date = datetime.strptime(f"{today.year}-{date_part}", "%Y-%m-%d").date()
                else:
                    parsed_date = datetime.strptime(apply_date_str[:10], "%Y-%m-%d").date()
            except (ValueError, IndexError):
                continue
            if parsed_date != today:
                continue
            stock_name = str(row.get('股票简称', row.get('标的简称', '')))
            if not any(kw in stock_name for kw in ['转债', 'EB', '可转债', '可交债', '交换债']):
                continue
            bonds.append({
                'bond_code': str(row.get('股票代码', row.get('代码', ''))),
                'bond_name': stock_name,
                'apply_code': str(row.get('申购代码', '')),
                'apply_date': today.strftime('%m-%d'),
                'price': str(row.get('发行价格', '100.00')),
                'rating': '',
                'max_shares': '',
            })
        return bonds

    try:
        bonds = _try_ths()
        if not bonds:
            bonds = _try_ipo()
        bonds = _enrich_bonds(bonds)
        logger.info(f"今日可申购新债: {len(bonds)} 只")
        return bonds
    except ImportError:
        logger.warning("akshare 未安装")
        return []
    except Exception as e:
        logger.error(f"获取新债日历失败: {e}")
        return []


def get_future_bonds() -> Tuple[List[Dict], str]:
    """获取未来可申购可转债 — 数据来源: 同花顺 bond_zh_cov_info_ths → bond_cov_comparison 兜底"""
    import akshare as ak
    import pandas as pd
    today = datetime.now().date()
    source = "同花顺 bond_zh_cov_info_ths"

    def _try_ths():
        df = ak.bond_zh_cov_info_ths()
        if df is None or df.empty or '申购日期' not in df.columns:
            return []
        df['申购日期_dt'] = pd.to_datetime(df['申购日期'], errors='coerce')
        future = df[df['申购日期_dt'] >= pd.Timestamp(today)]
        bonds = []
        for _, row in future.iterrows():
            bonds.append({
                'bond_name': str(row.get('债券简称', '')),
                'bond_code': str(row.get('债券代码', '')),
                'apply_date': str(row.get('申购日期', ''))[:10],
                'stock_name': str(row.get('正股简称', '')),
                'stock_code': str(row.get('正股代码', '')),
                'price': str(row.get('转股价格', '-')),
                'rating': '待查',
            })
        return bonds

    def _try_cov():
        for attempt in range(2):
            try:
                if attempt > 0:
                    time.sleep(2)
                df = ak.bond_cov_comparison()
                if df is None or df.empty or '申购日期' not in df.columns:
                    return []
                valid = df[df['申购日期'].notna()].copy()
                valid['申购日期_dt'] = pd.to_datetime(valid['申购日期'], format='%Y%m%d', errors='coerce')
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
                return bonds
            except Exception:
                continue
        return []

    try:
        bonds = _try_ths()
        if bonds:
            bonds = _enrich_bonds(bonds)
            # 归一化日期格式后升序排序（与新股一致）
            def _parse_date(d):
                ds = d.get('apply_date', '')
                if len(ds) == 8 and ds.isdigit():
                    return ds  # YYYYMMDD
                if len(ds) == 10 and ds[4] == '-':
                    return ds.replace('-', '')  # YYYY-MM-DD → YYYYMMDD
                return ds
            bonds.sort(key=_parse_date)
            logger.info(f"未来可申购可转债: {len(bonds)} 只 (同花顺)")
            return bonds, source

        bonds = _try_cov()
        if bonds:
            bonds = _enrich_bonds(bonds)
            # 归一化日期格式后升序排序
            def _parse_date2(d):
                ds = d.get('apply_date', '')
                if len(ds) == 8 and ds.isdigit():
                    return ds
                if len(ds) == 10 and ds[4] == '-':
                    return ds.replace('-', '')
                return ds
            bonds.sort(key=_parse_date2)
            source = "东方财富 bond_cov_comparison"
            logger.info(f"未来可申购可转债: {len(bonds)} 只 (东财)")
            return bonds, source

        logger.info("未来可申购可转债: 0 只")
        return [], source
    except ImportError:
        return [], source
    except Exception as e:
        logger.warning(f"获取未来新债失败: {e}")
        return [], source


def get_approved_bond_news() -> Tuple[List[Dict], Dict, str]:
    """
    获取已获批可转债动态
    只保留进行中/已获批待发的可转债，过滤掉已发行的历史数据
    来源: 东方财富财富号（每周更新）
    """
    pipeline = _fetch_pipeline()
    source = "东方财富财富号"
    # 不再返回已发行债券列表，用审批管线列表替代
    approved_list = []  # 保留兼容，实际用 pipeline.lists
    return approved_list, pipeline, source


def _fetch_pipeline() -> Optional[Dict]:
    """审批管线统计（东方财富财富号，约每周更新）"""
    return {
        'stats': {
            'approved_waiting': 18, 'passed_committee': 11,
            'upcoming_review': 6, 'inquiry_done': 6,
        },
        # 详细列表（从2026-05-30文章提取）
        'lists': {
            'approved_waiting': [
                '南芯科技', '金帝股份', '豪能股份', '科博达',
                '维科精密', '中汽股份', '四方科技', '圣泉集团',
            ],
            'passed_committee': [
                '肇民科技', '奥普特',
                '中科曙光(已提交注册)', '炬申股份(已提交注册)', '特宝生物(已提交注册)',
            ],
            'upcoming_review': [
                '赛恩斯', '振华股份', '先锋精科',
                '久吾高科', '中仑新材', '千红制药',
            ],
            'completed_dividend': [
                '春风动力', '爱科科技', '金三江', '迪威尔',
                '华翔股份', '科博达', '中汽股份',
            ],
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
    pipeline: Dict,
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

    # ── 大盘指数（暂时禁用，保留获取模块） ──
    # date_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    # lines.append("【大盘指数】")
    # lines.append("")
    # lines.append(f"📅 {date_str}")
    # try:
    #     overview = fetcher.get_market_overview()
    #     if overview.get('sh_index'):
    #         sh = overview['sh_index']
    #         arrow = "↑" if sh['change_pct'] >= 0 else "↓"
    #         lines.append(f"上证指数 {sh['price']:.1f} {sh['change_pct']:+.2f}% {arrow}")
    #     if overview.get('sz_index'):
    #         sz = overview['sz_index']
    #         arrow = "↑" if sz['change_pct'] >= 0 else "↓"
    #         lines.append(f"深证成指 {sz['price']:.1f} {sz['change_pct']:+.2f}% {arrow}")
    #     if overview.get('cyb_index'):
    #         cyb = overview['cyb_index']
    #         arrow = "↑" if cyb['change_pct'] >= 0 else "↓"
    #         lines.append(f"创业板指 {cyb['price']:.1f} {cyb['change_pct']:+.2f}% {arrow}")
    # except Exception:
    #     lines.append("大盘指数获取失败")
    # lines.append("")
    # lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    # lines.append("")

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
        # 表格头（手机端精简：去申购代码、发行价）
        lines.append(f"债券名称 | 评级 | 申购上限")
        lines.append(f"--- | --- | ---")
        for b in bonds_today:
            lines.append(
                f"{b['bond_name']}（{b['bond_code']}） | "
                f"{b.get('rating', '待查')} | "
                f"{b['max_shares']}"
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
    if pipeline and pipeline.get('stats'):
        lines.append("【已获批可转债动态】")
        lines.append("")

        # 管线概览
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
        lines.append(f"📊 审批管线: {' · '.join(stat_parts)}")
        lines.append(f"   来源: {pipeline.get('source_name', '东方财富财富号')}")
        lines.append("")

        # 详细列表
        bond_lists = pipeline.get('lists', {})
        if bond_lists:
            # 已获核准批文（待发行）
            approved = bond_lists.get('approved_waiting', [])
            if approved:
                lines.append(f"📌 已获核准/同意注册（等待发行）: {', '.join(approved)}等")
                lines.append("")
            # 通过上市委审核
            passed = bond_lists.get('passed_committee', [])
            if passed:
                lines.append(f"✅ 通过上市委审核: {', '.join(passed)}")
                lines.append("")
            # 即将上会
            upcoming = bond_lists.get('upcoming_review', [])
            if upcoming:
                lines.append(f"🔜 即将上会审核: {', '.join(upcoming)}")
                lines.append("")
            # 已完成分红可随时发行
            dividend = bond_lists.get('completed_dividend', [])
            if dividend:
                lines.append(f"📋 已完成分红（可随时发行）: {', '.join(dividend)}")
                lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")

    # ── 打新债小贴士 ──
    lines.append("【打新债小贴士】")
    lines.append("")
    lines.append("• 无需持有标的市值，空账户也可参与申购")
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
    pipeline: Dict,
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
        bonds_today, bonds_future, future_source, pipeline
    )

    # 复用电邮模板 → HTML
    date_str = datetime.now().strftime('%Y-%m-%d')
    subject = f"【Marcus策略小助手】{date_str} 新债上新申购提醒"
    html_content = format_email_html_responsive(text_content, subject)

    # 保存预览
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(output_dir, exist_ok=True)
    preview_path = os.path.join(output_dir, "bond_email_preview.html")
    with open(preview_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    logger.info(f"HTML预览: {preview_path}")

    # 使用公共SMTP发送器
    sender = SMTPSender(
        smtp_server=bond_cfg.smtp_server,
        smtp_port=bond_cfg.smtp_port,
        smtp_user=bond_cfg.smtp_user,
        smtp_password=bond_cfg.smtp_password,
        sender_name=bond_cfg.sender_name,
    )

    return sender.send(
        subject=subject,
        html_content=html_content,
        to_emails=bond_cfg.to_emails,
        cc_emails=bond_cfg.cc_emails,  # 新债专用抄送池（来自 configs/settings.yaml）
        debug=debug,
    )


# ═══════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='新债打新提醒（内置模块版）')
    parser.add_argument('--debug', action='store_true',
                        help='调试模式：只发收件人，不发送抄送')
    args = parser.parse_args()

    mode_label = "调试" if args.debug else "正式"
    logger.info("=" * 50)
    logger.info(f"新债打新提醒 [{mode_label}] — 开始检查")

    # ── 交易日判断（复用 check_trading）──
    is_td, reason = is_trading_day()
    if not is_td:
        logger.info(f"今日非交易日({reason})，跳过")
        return 0

    # ── 获取数据 ──
    bonds_today = get_new_bonds_today()
    if not bonds_today:
        logger.info("今日无新债可申购，不发送邮件")
        return 0
    bonds_future, future_source = get_future_bonds()
    _, pipeline, _ = get_approved_bond_news()

    # ── 发送 ──
    pipeline_bonds = len(pipeline.get('lists', {}).get('approved_waiting', [])) if pipeline else 0
    logger.info(f"今日: {len(bonds_today)}只 | 未来: {len(bonds_future)}只 | 已获批待发: {pipeline_bonds}家")

    success = send_bond_email(
        bonds_today, bonds_future, future_source, pipeline,
        debug=args.debug
    )

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
