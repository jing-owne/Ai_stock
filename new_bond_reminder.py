#!/usr/bin/env python3
"""
新债打新提醒 — 独立模块（增强版）

功能：
  1. 判断当天是否为A股交易日
  2. 获取当天可申购的新债（转债/可交换债）数据
  3. 有可打新债 → 发送独立邮件（主题：新债打新提醒），含三大模块：
     - 今日可申购新债
     - 未来可申购可转债
     - 近期已获批可转债动态
  4. 无新债 → 静默退出，不发送邮件

调试模式（--debug）：只发送主收件人，不发送抄送
测试模式（--test）：使用模拟数据发送测试邮件查看UI效果

数据来源：
  - 今日新债: akshare stock_ipo_ths (同花顺IPO日历)
  - 未来新债: akshare bond_cov_comparison (东方财富可转债对比)
  - 已获批: akshare bond_cov_stock_issue_cninfo (巨潮可转债发行公告)
  - 审批管线: 东方财富财富号"待发可转债统计表"

邮件池：
  - 策略邮件池（email）: 看 settings.yaml email 段
  - 新债邮件池（bond_email）: 看 settings.yaml bond_email 段
"""

import sys
import os
import argparse
import smtplib
import logging
import time
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formatdate
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("BondReminder")


# ── 2026年A股法定节假日 ──
HOLIDAYS_2026 = {
    "2026-01-01", "2026-01-02", "2026-01-03",
    "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20",
    "2026-02-21", "2026-02-22", "2026-02-23", "2026-02-24",
    "2026-04-04", "2026-04-05", "2026-04-06",
    "2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04", "2026-05-05",
    "2026-06-19", "2026-06-20", "2026-06-21",
    "2026-09-26", "2026-09-27",
    "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04",
    "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08",
}


def is_trading_day() -> bool:
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    weekday = now.weekday()
    if weekday >= 5:
        logger.info(f"{today_str} 周末，非交易日")
        return False
    if today_str in HOLIDAYS_2026:
        logger.info(f"{today_str} 法定节假日，非交易日")
        return False
    return True


# ── 模拟测试数据 ──
MOCK_BONDS_TODAY = [
    {
        'bond_code': '113686.SH', 'bond_name': '测试转债',
        'apply_code': '754686', 'apply_date': datetime.now().strftime('%m-%d'),
        'price': '100.00', 'rating': 'AA+', 'max_shares': '10000',
    },
    {
        'bond_code': '123250.SZ', 'bond_name': '演示转债',
        'apply_code': '370750', 'apply_date': datetime.now().strftime('%m-%d'),
        'price': '100.00', 'rating': 'AA', 'max_shares': '10000',
    },
    {
        'bond_code': '113687.SH', 'bond_name': 'UI预览EB',
        'apply_code': '754687', 'apply_date': datetime.now().strftime('%m-%d'),
        'price': '100.00', 'rating': 'AAA', 'max_shares': '5000',
    },
]

MOCK_BONDS_FUTURE = [
    {'bond_name': '迪威转债', 'apply_date': '20260604', 'stock_name': '迪威尔', 'price': '32.49', 'rating': 'AA'},
    {'bond_name': '肇民转债', 'apply_date': '20260615', 'stock_name': '肇民科技', 'price': '28.50', 'rating': 'AA-'},
    {'bond_name': '中科转债', 'apply_date': '20260620', 'stock_name': '中科曙光', 'price': '45.00', 'rating': 'AAA'},
]

MOCK_APPROVED = [
    {'bond_name': '南芯转债', 'stock_name': '南芯科技', 'status': '已获核准批文', 'approve_date': '2026-05'},
    {'bond_name': '春风转债', 'stock_name': '春风动力', 'status': '已获核准批文(已完成分红)', 'approve_date': '2026-05'},
    {'bond_name': '华翔转债', 'stock_name': '华翔股份', 'status': '已获核准批文(已完成分红)', 'approve_date': '2026-05'},
    {'bond_name': '中科转债', 'stock_name': '中科曙光', 'status': '已提交注册(80亿)', 'approve_date': '2026-05'},
    {'bond_name': '赛恩斯转债', 'stock_name': '赛恩斯', 'status': '即将上会审核', 'approve_date': '2026-06'},
    {'bond_name': '振华转债', 'stock_name': '振华股份', 'status': '即将上会审核', 'approve_date': '2026-06'},
]

MOCK_PIPELINE_NEWS = {
    'stats': {
        'approved_waiting': 18, 'passed_committee': 11,
        'upcoming_review': 6, 'inquiry_done': 6,
    },
    'source_url': 'https://caifuhao.eastmoney.com/news/20260530151213071344710',
    'source_name': '东方财富财富号·待发可转债统计表(截至2026-05-30)',
}


# ═══════════════════════════════════════════════════════
# 数据获取
# ═══════════════════════════════════════════════════════

def get_new_bonds_today() -> List[Dict]:
    """获取今日可申购新债 — 数据来源: 同花顺IPO日历"""
    try:
        import akshare as ak
        df = ak.stock_ipo_ths()
        if df is None or df.empty:
            logger.warning("stock_ipo_ths 返回空数据")
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
                        f"{today.year}-{date_part}", "%Y-%m-%d"
                    ).date()
                else:
                    parsed_date = datetime.strptime(
                        apply_date_str[:10], "%Y-%m-%d"
                    ).date()
            except (ValueError, IndexError):
                continue

            if parsed_date != today:
                continue

            stock_name = str(row.get('股票简称', ''))
            stock_code = str(row.get('股票代码', ''))

            is_bond = (
                '转债' in stock_name
                or 'EB' in stock_name
                or '可转债' in stock_name
                or '可交债' in stock_name
                or '交换债' in stock_name
            )
            if not is_bond:
                continue

            apply_code = str(row.get('申购代码', ''))
            price = str(row.get('发行价格', '-'))
            max_shares = str(row.get('申购上限（万股）', '-'))
            rating = str(row.get('债券评级', '-'))

            bonds.append({
                'bond_code': stock_code,
                'bond_name': stock_name,
                'apply_code': apply_code,
                'apply_date': today.strftime('%m-%d'),
                'price': price if price not in ('-', 'nan') else '100.00',
                'rating': rating if rating not in ('-', 'nan') else '待查',
                'max_shares': max_shares if max_shares not in ('-', 'nan') else '-',
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
    """获取未来可申购可转债 — 数据来源: 东方财富可转债对比"""
    import pandas as pd
    today = datetime.now().date()
    source = "东方财富 bond_cov_comparison"

    try:
        import akshare as ak
        # 重试机制
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

        if df is None or df.empty:
            return [], source

        if '申购日期' not in df.columns:
            return [], source

        valid = df[df['申购日期'].notna()].copy()
        valid['申购日期_dt'] = pd.to_datetime(
            valid['申购日期'], format='%Y%m%d', errors='coerce'
        )
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
        logger.warning("akshare 未安装，无法获取未来新债")
        return [], source
    except Exception as e:
        logger.warning(f"获取未来新债失败: {e}")
        return [], source


def get_approved_bond_news() -> Tuple[List[Dict], Dict, str]:
    """
    获取已获批可转债动态
    数据来源:
      1. akshare bond_cov_stock_issue_cninfo (巨潮资讯网 - 已发行可转债公告)
      2. 东方财富财富号"待发可转债统计表" (审批管线)
    """
    import pandas as pd
    today = datetime.now().date()
    cutoff = today - timedelta(days=90)

    approved_list = []
    pipeline_stats = {}
    source = "巨潮资讯网(bond_cov_stock_issue_cninfo)"

    # ── 来源1: 近期已发行可转债(已获批并发行) ──
    try:
        import akshare as ak
        df = ak.bond_cov_stock_issue_cninfo()
        if df is not None and not df.empty:
            df['公告日期_dt'] = pd.to_datetime(df['公告日期'], errors='coerce')
            recent = df[df['公告日期_dt'] >= pd.Timestamp(cutoff)]

            for _, row in recent.iterrows():
                bond_name = str(row.get('债券简称', ''))
                stock_code = str(row.get('标的股票', ''))
                notice_date = str(row.get('公告日期', ''))[:10] if pd.notna(row.get('公告日期')) else ''
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

    # ── 来源2: 东方财富审批管线 ──
    try:
        pipeline_data = _fetch_eastmoney_pipeline()
        if pipeline_data:
            pipeline_stats = pipeline_data
            if source:
                source += " + 东方财富财富号"
            else:
                source = "东方财富财富号"
    except Exception as e:
        logger.warning(f"获取东方财富管线数据失败: {e}")

    return approved_list, pipeline_stats, source


def _fetch_eastmoney_pipeline() -> Optional[Dict]:
    """
    获取可转债审批管线统计
    数据来源: 东方财富财富号"待发可转债统计表"（手动维护，约每周更新）
    最新文章: https://caifuhao.eastmoney.com/news/20260530151213071344710
    """
    # 管线数据由WebFetch手动提取后缓存于此（至下次更新）
    stats = {
        'approved_waiting': 18,   # 已获核准批文/同意注册
        'passed_committee': 11,   # 通过上市委审核
        'upcoming_review': 6,     # 即将上会审核
        'inquiry_done': 6,        # 完成问询待上会
    }

    return {
        'stats': stats,
        'source_url': 'https://caifuhao.eastmoney.com/news/20260530151213071344710',
        'source_name': '东方财富财富号 · 待发可转债统计表(截至2026-05-30)',
        'article_date': '2026-05-30',
    }


# ═══════════════════════════════════════════════════════
# HTML邮件构建
# ═══════════════════════════════════════════════════════

def _rating_color(rating: str) -> str:
    return {
        'AAA': '#2E7D32', 'AA+': '#388E3C', 'AA': '#43A047',
        'AA-': '#66BB6A', 'A+': '#FFA726', 'A': '#FF9800',
    }.get(rating, '#666')


def _build_today_section(bonds: List[Dict]) -> str:
    """构建'今日可申购新债'模块"""
    if not bonds:
        return ""

    rows = ""
    for i, b in enumerate(bonds):
        bg = '#fafafa' if i % 2 == 0 else '#fff'
        rc = _rating_color(b.get('rating', ''))

        rows += f"""
        <tr style="background:{bg};">
            <td style="padding:12px;border-bottom:1px solid #eee;">
                <div style="font-weight:600;color:#333;font-size:15px;">{b['bond_name']}</div>
                <div style="font-size:12px;color:#999;margin-top:2px;">{b['bond_code']}</div>
            </td>
            <td style="padding:12px;border-bottom:1px solid #eee;text-align:center;">
                <span style="background:#FFF3E0;color:#E65100;font-weight:bold;font-size:14px;
                padding:4px 10px;border-radius:4px;">{b['apply_code']}</span>
            </td>
            <td style="padding:12px;border-bottom:1px solid #eee;text-align:center;color:#333;font-size:14px;">
                ¥{b['price']}
            </td>
            <td style="padding:12px;border-bottom:1px solid #eee;text-align:center;">
                <span style="font-weight:bold;font-size:14px;color:{rc};">{b.get('rating', '待查')}</span>
            </td>
            <td style="padding:12px;border-bottom:1px solid #eee;text-align:center;color:#666;font-size:13px;">
                {b['max_shares']}张
            </td>
        </tr>"""

    return f"""
    <!-- 今日可申购 -->
    <div style="margin-bottom:28px;">
      <div style="font-size:16px;color:#333;font-weight:bold;margin-bottom:6px;">
        📋 今日可申购新债
      </div>
      <div style="display:inline-block;background:#FFF3E0;color:#E65100;font-size:13px;
        padding:2px 10px;border-radius:12px;margin-bottom:4px;">
        共 {len(bonds)} 只
      </div>
      <div style="display:inline-block;background:#F5F5F5;color:#999;font-size:11px;
        padding:2px 8px;border-radius:10px;margin-left:6px;vertical-align:middle;">
        数据来源: 同花顺IPO日历
      </div>
      <div style="font-size:13px;color:#999;margin-top:10px;margin-bottom:16px;line-height:1.6;">
        新债申购无市值要求，中签后缴款，建议顶格申购
      </div>
      <table width="100%" cellpadding="0" cellspacing="0"
        style="border-collapse:collapse;border-radius:8px;overflow:hidden;border:1px solid #eee;">
        <thead>
          <tr style="background:linear-gradient(90deg,#FFF3E0,#FFE0B2);">
            <td style="padding:12px;font-size:13px;color:#BF360C;font-weight:bold;text-align:left;">债券名称</td>
            <td style="padding:12px;font-size:13px;color:#BF360C;font-weight:bold;text-align:center;">申购代码</td>
            <td style="padding:12px;font-size:13px;color:#BF360C;font-weight:bold;text-align:center;">发行价</td>
            <td style="padding:12px;font-size:13px;color:#BF360C;font-weight:bold;text-align:center;">评级</td>
            <td style="padding:12px;font-size:13px;color:#BF360C;font-weight:bold;text-align:center;">上限</td>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </div>"""


def _build_future_section(bonds: List[Dict], source: str) -> str:
    """构建'未来可申购可转债'模块"""
    if not bonds:
        return ""

    rows = ""
    for i, b in enumerate(bonds):
        bg = '#fafafa' if i % 2 == 0 else '#fff'
        # 格式化申购日期
        apply_str = b.get('apply_date', '')
        if len(apply_str) == 8:
            try:
                dt = datetime.strptime(apply_str, '%Y%m%d')
                apply_str = dt.strftime('%m-%d')
            except ValueError:
                pass

        rows += f"""
        <tr style="background:{bg};">
            <td style="padding:10px;border-bottom:1px solid #eee;">
                <span style="font-weight:600;color:#333;font-size:14px;">{b['bond_name']}</span>
            </td>
            <td style="padding:10px;border-bottom:1px solid #eee;color:#555;font-size:13px;text-align:center;">
                {b.get('stock_name', '-')}
            </td>
            <td style="padding:10px;border-bottom:1px solid #eee;text-align:center;">
                <span style="background:#E3F2FD;color:#1565C0;font-weight:bold;font-size:13px;
                padding:3px 8px;border-radius:4px;">{apply_str}</span>
            </td>
            <td style="padding:10px;border-bottom:1px solid #eee;color:#333;font-size:13px;text-align:center;">
                ¥{b.get('price', '-')}
            </td>
        </tr>"""

    return f"""
    <!-- 未来可申购 -->
    <div style="margin-bottom:28px;">
      <div style="font-size:16px;color:#333;font-weight:bold;margin-bottom:6px;">
        📅 未来可申购可转债
      </div>
      <div style="display:inline-block;background:#E3F2FD;color:#1565C0;font-size:13px;
        padding:2px 10px;border-radius:12px;margin-bottom:4px;">
        共 {len(bonds)} 只
      </div>
      <div style="display:inline-block;background:#F5F5F5;color:#999;font-size:11px;
        padding:2px 8px;border-radius:10px;margin-left:6px;vertical-align:middle;">
        数据来源: {source}
      </div>
      <div style="font-size:12px;color:#999;margin-top:10px;margin-bottom:16px;line-height:1.6;">
        ⚠️ 申购日期为预估，实际发行日期以公司公告为准
      </div>
      <table width="100%" cellpadding="0" cellspacing="0"
        style="border-collapse:collapse;border-radius:8px;overflow:hidden;border:1px solid #eee;">
        <thead>
          <tr style="background:linear-gradient(90deg,#E3F2FD,#BBDEFB);">
            <td style="padding:10px;font-size:13px;color:#0D47A1;font-weight:bold;text-align:left;">债券名称</td>
            <td style="padding:10px;font-size:13px;color:#0D47A1;font-weight:bold;text-align:center;">正股</td>
            <td style="padding:10px;font-size:13px;color:#0D47A1;font-weight:bold;text-align:center;">申购日期</td>
            <td style="padding:10px;font-size:13px;color:#0D47A1;font-weight:bold;text-align:center;">转股价</td>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </div>"""


def _build_approved_section(approved_list: List[Dict], pipeline: Dict, source: str) -> str:
    """构建'已获批可转债动态'模块"""
    has_approved = bool(approved_list)
    has_pipeline = bool(pipeline and pipeline.get('stats'))

    if not has_approved and not has_pipeline:
        return ""

    parts = []

    # ── 审批管线概览 ──
    if has_pipeline:
        stats = pipeline.get('stats', {})
        stats_items = []
        labels = {
            'approved_waiting': ('📌 已获核准/同意注册', '#2E7D32', '#E8F5E9'),
            'passed_committee': ('✅ 通过上市委审核', '#1565C0', '#E3F2FD'),
            'upcoming_review': ('🔜 即将上会审核', '#E65100', '#FFF3E0'),
            'inquiry_done': ('📝 完成问询待上会', '#6A1B9A', '#F3E5F5'),
        }
        for key, (label, color, bg) in labels.items():
            val = stats.get(key, 0)
            if val > 0:
                stats_items.append(
                    f'<span style="display:inline-block;background:{bg};color:{color};'
                    f'font-size:12px;padding:3px 10px;border-radius:12px;margin:2px 4px;">'
                    f'{label}: {val}家</span>'
                )

        pipeline_source_url = pipeline.get('source_url', '')
        pipeline_source_name = pipeline.get('source_name', '东方财富财富号')

        parts.append(f"""
      <div style="margin-bottom:16px;padding:16px;background:#FAFAFA;border-radius:8px;
        border:1px solid #E0E0E0;">
        <div style="font-size:14px;color:#333;font-weight:bold;margin-bottom:8px;">
          📊 可转债审批管线概览
        </div>
        <div style="line-height:2.2;">
          {''.join(stats_items)}
        </div>
        <div style="font-size:11px;color:#999;margin-top:8px;">
          数据来源: <a href="{pipeline_source_url}" style="color:#1565C0;text-decoration:none;"
            target="_blank">{pipeline_source_name}</a>
        </div>
      </div>""")

    # ── 近期已发行可转债 ──
    if approved_list:
        rows = ""
        for i, b in enumerate(approved_list[:15]):
            bg = '#fafafa' if i % 2 == 0 else '#fff'
            rows += f"""
          <tr style="background:{bg};">
            <td style="padding:8px 10px;border-bottom:1px solid #eee;font-weight:600;color:#333;font-size:13px;">
              {b['bond_name']}
            </td>
            <td style="padding:8px 10px;border-bottom:1px solid #eee;color:#555;font-size:12px;text-align:center;">
              {b.get('stock_code', '-')}
            </td>
            <td style="padding:8px 10px;border-bottom:1px solid #eee;text-align:center;">
              <span style="background:#E8F5E9;color:#2E7D32;font-size:11px;
              padding:2px 6px;border-radius:8px;">{b.get('status', '已发行')}</span>
            </td>
            <td style="padding:8px 10px;border-bottom:1px solid #eee;color:#666;font-size:12px;text-align:center;">
              {b.get('notice_date', '-')}
            </td>
            <td style="padding:8px 10px;border-bottom:1px solid #eee;color:#333;font-size:12px;text-align:center;">
              {b.get('conv_price', '-')}
            </td>
          </tr>"""

        parts.append(f"""
      <div style="margin-bottom:4px;">
        <div style="font-size:14px;color:#333;font-weight:bold;margin-bottom:6px;">
          📰 近期已获批并发行可转债
        </div>
        <div style="display:inline-block;background:#E8F5E9;color:#2E7D32;font-size:12px;
          padding:2px 10px;border-radius:12px;margin-bottom:12px;">
          近90天共 {len(approved_list)} 只
        </div>
        <table width="100%" cellpadding="0" cellspacing="0"
          style="border-collapse:collapse;border-radius:8px;overflow:hidden;border:1px solid #eee;font-size:12px;">
          <thead>
            <tr style="background:linear-gradient(90deg,#E8F5E9,#C8E6C9);">
              <td style="padding:8px 10px;font-size:12px;color:#1B5E20;font-weight:bold;text-align:left;">债券名称</td>
              <td style="padding:8px 10px;font-size:12px;color:#1B5E20;font-weight:bold;text-align:center;">正股代码</td>
              <td style="padding:8px 10px;font-size:12px;color:#1B5E20;font-weight:bold;text-align:center;">状态</td>
              <td style="padding:8px 10px;font-size:12px;color:#1B5E20;font-weight:bold;text-align:center;">公告日期</td>
              <td style="padding:8px 10px;font-size:12px;color:#1B5E20;font-weight:bold;text-align:center;">转股价</td>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </div>""")

    return f"""
    <!-- 已获批动态 -->
    <div style="margin-bottom:28px;">
      <div style="font-size:16px;color:#333;font-weight:bold;margin-bottom:6px;">
        📰 已获批可转债动态
      </div>
      <div style="display:inline-block;background:#F5F5F5;color:#999;font-size:11px;
        padding:2px 8px;border-radius:10px;margin-bottom:16px;">
        数据来源: {source}
      </div>
      {''.join(parts)}
    </div>"""


def build_bond_email_html(
    bonds_today: List[Dict],
    bonds_future: List[Dict],
    future_source: str,
    approved_list: List[Dict],
    pipeline: Dict,
    approved_source: str,
    debug: bool = False,
) -> str:
    """构建完整HTML邮件"""
    now = datetime.now()
    date_str = now.strftime('%Y年%m月%d日 %H:%M')
    debug_badge = (
        '<span style="background:#FF5722;color:#fff;font-size:11px;padding:2px 8px;'
        'border-radius:10px;margin-left:8px;vertical-align:middle;">调试模式(无抄送)</span>'
        if debug else ''
    )

    today_section = _build_today_section(bonds_today)
    future_section = _build_future_section(bonds_future, future_source)
    approved_section = _build_approved_section(approved_list, pipeline, approved_source)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>新债打新提醒</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;min-height:100vh;">
<tr><td align="center" style="padding:20px 12px;">

<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:#fff;border-radius:12px;box-shadow:0 4px 16px rgba(0,0,0,0.1);overflow:hidden;">

  <!-- 头部 -->
  <tr>
    <td style="background:linear-gradient(135deg,#F57C00,#E65100);padding:28px 20px;text-align:center;">
      <div style="font-size:36px;margin-bottom:4px;">💰</div>
      <div style="font-size:22px;font-weight:bold;color:#fff;letter-spacing:2px;">
        新债打新提醒{debug_badge}
      </div>
      <div style="font-size:13px;color:rgba(255,255,255,0.8);margin-top:8px;">
        {date_str} · Marcus策略师
      </div>
    </td>
  </tr>

  <!-- 内容 -->
  <tr>
    <td style="padding:28px 24px;">

      {today_section}
      {future_section}
      {approved_section}

      <!-- 贴士 -->
      <div style="margin-top:24px;padding:18px 16px;background:linear-gradient(135deg,#FFF8E1,#FFF3E0);
        border-radius:8px;border-left:4px solid #FF9800;">
        <div style="font-size:14px;color:#E65100;font-weight:bold;margin-bottom:8px;">
          💡 打新债小贴士
        </div>
        <div style="font-size:13px;color:#795548;line-height:2;">
          • 无需持有股票市值，空账户也可参与申购<br>
          • 建议顶格申购（10000张起），提高中签率<br>
          • 中签后T+2日16:00前确保账户有足额资金<br>
          • 上市首日可择机卖出锁定收益
        </div>
      </div>

      <div style="margin-top:12px;padding:12px 16px;background:#E8F5E9;border-radius:8px;border-left:4px solid #4CAF50;">
        <div style="font-size:13px;color:#2E7D32;">
          📌 申购当日无需缴款，中签后再存入资金即可
        </div>
      </div>

    </td>
  </tr>

  <!-- 底部 -->
  <tr>
    <td style="padding:16px 24px;background:#fafafa;text-align:center;border-top:1px solid #eee;">
      <div style="font-size:12px;color:#999;line-height:1.8;">
        以上信息仅供参考，不构成投资建议<br>
        数据来源于公开接口，可能存在延迟或遗漏<br>
        <span style="color:#ccc;">自动发送 · Marcus策略小助手</span>
      </div>
    </td>
  </tr>

</table>

</td></tr>
</table>
</body>
</html>"""


# ═══════════════════════════════════════════════════════
# 邮件发送
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
    from src.core.config import Config

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

    subject = "新债打新提醒"
    html_content = build_bond_email_html(
        bonds_today, bonds_future, future_source,
        approved_list, pipeline, approved_source,
        debug=debug
    )

    # 纯文本版本
    plain_lines = [f"【新债打新提醒】{datetime.now().strftime('%Y-%m-%d')}", ""]
    plain_lines.append("── 今日可申购新债 ──")
    for b in bonds_today:
        plain_lines.append(f"  ▶ {b['bond_name']}（{b['bond_code']}）")
        plain_lines.append(f"    申购代码: {b['apply_code']} | 发行价: ¥{b['price']} | 评级: {b.get('rating', '待查')}")
        plain_lines.append("")
    if bonds_future:
        plain_lines.append("── 未来可申购可转债 ──")
        for b in bonds_future:
            plain_lines.append(f"  ▶ {b['bond_name']} | {b.get('stock_name', '')} | {b.get('apply_date', '')}")
        plain_lines.append("")
    if approved_list:
        plain_lines.append(f"── 近期已获批可转债（近90天: {len(approved_list)}只）──")
        for b in approved_list[:10]:
            plain_lines.append(f"  ▶ {b['bond_name']} | {b.get('stock_code', '')} | {b.get('status', '')} | {b.get('notice_date', '')}")
        plain_lines.append("")
    plain_lines.append("新债申购无市值要求，中签后缴款，建议顶格申购。")
    plain_content = '\n'.join(plain_lines)

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = Header(subject, 'utf-8')
        msg['From'] = bond_cfg.smtp_user
        msg['To'] = ', '.join(bond_cfg.to_emails)
        msg['Date'] = formatdate(localtime=True)

        cc_list = [] if debug else bond_cfg.cc_emails
        if cc_list:
            msg['Cc'] = ', '.join(cc_list)

        msg.attach(MIMEText(plain_content, 'plain', 'utf-8'))
        msg.attach(MIMEText(html_content, 'html', 'utf-8'))

        all_recipients = bond_cfg.to_emails + cc_list

        with smtplib.SMTP_SSL(bond_cfg.smtp_server, bond_cfg.smtp_port, timeout=30) as server:
            server.login(bond_cfg.smtp_user, bond_cfg.smtp_password)
            server.sendmail(bond_cfg.smtp_user, all_recipients, msg.as_string())

        logger.info(f"✅ 新债提醒邮件已发送")
        logger.info(f"   收件人: {bond_cfg.to_emails}")
        if cc_list:
            logger.info(f"   抄送: {cc_list}")
        else:
            logger.info(f"   抄送: (调试模式，已跳过)")
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP 认证失败")
        return False
    except Exception as e:
        logger.error(f"邮件发送失败: {e}")
        return False


# ═══════════════════════════════════════════════════════
# HTML预览输出（调试用）
# ═══════════════════════════════════════════════════════

def save_preview(html_content: str):
    """保存HTML预览到output目录"""
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(output_dir, exist_ok=True)
    preview_path = os.path.join(output_dir, "bond_email_preview.html")
    with open(preview_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    logger.info(f"HTML预览已保存: {preview_path}")
    return preview_path


# ═══════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='新债打新提醒（增强版）')
    parser.add_argument('--debug', action='store_true',
                        help='调试模式：只发收件人，不发送抄送')
    parser.add_argument('--test', action='store_true',
                        help='测试模式：使用模拟数据发送邮件预览UI效果')
    args = parser.parse_args()

    if args.debug:
        logger.info("⚠️ 调试模式：仅发送主收件人，跳过抄送")
    if args.test:
        logger.info("🧪 测试模式：使用模拟新债数据")

    mode_label = "测试" if args.test else ("调试" if args.debug else "正式")

    logger.info("=" * 50)
    logger.info(f"新债打新提醒 [{mode_label}] — 开始检查")

    # 交易日判断（测试模式跳过）
    if not args.test and not is_trading_day():
        logger.info("今日非交易日，跳过")
        return 0

    # ── 获取数据 ──
    if args.test:
        bonds_today = MOCK_BONDS_TODAY
        bonds_future = MOCK_BONDS_FUTURE
        future_source = "模拟数据"
        approved_list = MOCK_APPROVED
        pipeline = MOCK_PIPELINE_NEWS
        approved_source = "模拟数据"
        logger.info(f"模拟今日新债: {len(bonds_today)} 只")
    else:
        # 1) 今日新债
        bonds_today = get_new_bonds_today()

        if not bonds_today:
            logger.info("今日无新债可申购，不发送邮件")
            return 0

        # 2) 未来新债
        bonds_future, future_source = get_future_bonds()

        # 3) 已获批动态
        approved_list, pipeline, approved_source = get_approved_bond_news()

    # ── 输出摘要 ──
    logger.info(f"今日可申购: {len(bonds_today)} 只")
    logger.info(f"未来可申购: {len(bonds_future)} 只")
    logger.info(f"已获批记录: {len(approved_list)} 条")
    if pipeline and pipeline.get('stats'):
        logger.info(f"审批管线: {pipeline['stats']}")

    # ── 生成HTML预览 ──
    html = build_bond_email_html(
        bonds_today, bonds_future, future_source,
        approved_list, pipeline, approved_source,
        debug=args.debug or args.test
    )
    save_preview(html)

    # ── 发送邮件 ──
    success = send_bond_email(
        bonds_today, bonds_future, future_source,
        approved_list, pipeline, approved_source,
        debug=args.debug or args.test
    )

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
