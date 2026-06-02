#!/usr/bin/env python3
"""
新债打新提醒 — 独立模块

功能：
  1. 判断当天是否为A股交易日（复用 check_trading 逻辑）
  2. 获取当天可申购的新债（转债/可交换债）数据
  3. 有可打新债 → 发送独立邮件（主题：新债打新提醒），使用新债专用邮件池
  4. 无新债 → 静默退出，不发送邮件
  5. 完全不影响原有的打新新股新债提醒（策略报告中仍包含完整IPO日历）

邮件池：
  - 策略邮件池（email）: 看 settings.yaml email 段，发策略报告
  - 新债邮件池（bond_email）: 看 settings.yaml bond_email 段，仅发新债提醒
    收件人: 2210265283@qq.com，抄送: 1971615727@qq.com
"""

import sys
import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formatdate
from datetime import datetime, timedelta
from typing import List, Dict

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("BondReminder")


# ─────────────────────────────────────────────
# 交易日判断（复用 check_trading 逻辑，但更精简）
# ─────────────────────────────────────────────

# 2026年A股法定节假日休市安排
HOLIDAYS_2026 = {
    # 元旦: 1月1日-1月3日
    "2026-01-01", "2026-01-02", "2026-01-03",
    # 春节: 2月16日-2月24日（除夕2/16）
    "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20",
    "2026-02-21", "2026-02-22", "2026-02-23", "2026-02-24",
    # 补班日（2/14周六、2/28周六上班，但非A股交易日，跳过）
    # 清明: 4月4日-4月6日
    "2026-04-04", "2026-04-05", "2026-04-06",
    # 劳动: 5月1日-5月5日
    "2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04", "2026-05-05",
    # 端午: 6月19日-6月21日
    "2026-06-19", "2026-06-20", "2026-06-21",
    # 中秋: 9月26日-9月27日
    "2026-09-26", "2026-09-27",
    # 国庆: 10月1日-10月8日
    "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04",
    "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08",
}


def is_trading_day() -> bool:
    """判断今天是否为A股交易日"""
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    weekday = now.weekday()  # 0=Mon, 6=Sun

    # 周六日
    if weekday >= 5:
        logger.info(f"{today_str} 是周末，非交易日")
        return False

    # 法定节假日
    if today_str in HOLIDAYS_2026:
        logger.info(f"{today_str} 是法定节假日，非交易日")
        return False

    # 交易时段检查（9:15-15:30，放宽到全天查询可打新债）
    # 打新债提醒可以在交易日任意时间运行，不受盘中时段限制
    # 但如果要在非交易时段也不发送，可取消下面注释
    # current_time = now.hour * 60 + now.minute
    # if current_time < 9 * 60 + 15 or current_time > 15 * 60 + 30:
    #     logger.info(f"非交易时段，跳过")
    #     return False

    return True


# ─────────────────────────────────────────────
# 新债日历获取
# ─────────────────────────────────────────────

def get_new_bonds_today() -> List[Dict]:
    """
    获取今天可申购的新债（转债/可交换债）

    Returns:
        新债列表，每项包含: bond_code, bond_name, apply_code, price, rating, max_shares
    """
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

            # 解析申购日期
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

            # 只取今天的
            if parsed_date != today:
                continue

            stock_name = str(row.get('股票简称', ''))
            stock_code = str(row.get('股票代码', ''))

            # 判断是否为新债：名称含"转债" 或 代码前3位匹配债券特征
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
            pe = str(row.get('发行市盈率', '-'))
            max_shares = str(row.get('申购上限（万股）', '-'))
            rating = str(row.get('债券评级', '-'))

            bonds.append({
                'bond_code': stock_code,
                'bond_name': stock_name,
                'apply_code': apply_code,
                'apply_date': today.strftime('%m-%d'),
                'price': price if price not in ('-', 'nan') else '100.00',
                'pe': pe if pe not in ('-', 'nan') else '-',
                'rating': rating if rating not in ('-', 'nan') else '待查',
                'max_shares': max_shares if max_shares not in ('-', 'nan') else '-',
            })

        logger.info(f"今日可申购新债: {len(bonds)} 只")
        return bonds

    except ImportError:
        logger.warning("akshare 未安装，无法获取新债数据")
        return []
    except Exception as e:
        logger.error(f"获取新债日历失败: {e}")
        return []


# ─────────────────────────────────────────────
# 新债邮件发送
# ─────────────────────────────────────────────

def build_bond_email_html(bonds: List[Dict]) -> str:
    """构建新债打新提醒 HTML 邮件内容"""
    now = datetime.now()
    date_str = now.strftime('%Y年%m月%d日 %H:%M')

    rows_html = ""
    for b in bonds:
        rows_html += f"""
        <tr>
            <td style="padding:10px 12px;border-bottom:1px solid #eee;font-weight:bold;color:#333;">
                {b['bond_name']}<br>
                <span style="font-size:12px;color:#999;">{b['bond_code']}</span>
            </td>
            <td style="padding:10px 12px;border-bottom:1px solid #eee;color:#E67E22;font-weight:bold;">
                {b['apply_code']}
            </td>
            <td style="padding:10px 12px;border-bottom:1px solid #eee;color:#333;">
                {b['price']}
            </td>
            <td style="padding:10px 12px;border-bottom:1px solid #eee;color:#666;">
                {b.get('rating', '待查')}
            </td>
            <td style="padding:10px 12px;border-bottom:1px solid #eee;color:#666;">
                {b['max_shares']}
            </td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>新债打新提醒</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;min-height:100vh;">
<tr><td align="center" style="padding:20px 12px;">

  <!-- 主卡片 -->
  <table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:#fff;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,0.08);overflow:hidden;">

    <!-- 头部 -->
    <tr>
      <td style="background:linear-gradient(135deg,#E67E22,#D35400);padding:24px 20px;text-align:center;">
        <div style="font-size:28px;margin-bottom:6px;">💰</div>
        <div style="font-size:20px;font-weight:bold;color:#fff;letter-spacing:1px;">新债打新提醒</div>
        <div style="font-size:13px;color:rgba(255,255,255,0.85);margin-top:6px;">{date_str} · Marcus策略师</div>
      </td>
    </tr>

    <!-- 内容区 -->
    <tr>
      <td style="padding:24px 20px;">

        <div style="font-size:16px;color:#333;margin-bottom:8px;font-weight:bold;">
          📋 今日可申购新债（{len(bonds)}只）
        </div>
        <div style="font-size:13px;color:#999;margin-bottom:16px;">
          新债申购无市值要求，中签后缴款，建议积极参与
        </div>

        <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
          <thead>
            <tr style="background:#FFF3E0;">
              <td style="padding:10px 12px;font-size:13px;color:#E65100;font-weight:bold;text-align:left;">债券名称/代码</td>
              <td style="padding:10px 12px;font-size:13px;color:#E65100;font-weight:bold;text-align:center;">申购代码</td>
              <td style="padding:10px 12px;font-size:13px;color:#E65100;font-weight:bold;text-align:center;">发行价</td>
              <td style="padding:10px 12px;font-size:13px;color:#E65100;font-weight:bold;text-align:center;">评级</td>
              <td style="padding:10px 12px;font-size:13px;color:#E65100;font-weight:bold;text-align:center;">上限</td>
            </tr>
          </thead>
          <tbody>
            {rows_html}
          </tbody>
        </table>

        <div style="margin-top:20px;padding:16px;background:#FFF8E1;border-radius:8px;border-left:4px solid #FF9800;">
          <div style="font-size:14px;color:#E65100;font-weight:bold;margin-bottom:6px;">💡 打新债小贴士</div>
          <div style="font-size:13px;color:#795548;line-height:1.8;">
            • 无需持有股票市值，空账户也可参与<br>
            • 申购时输入申购代码 + 顶格申购（10000张起）<br>
            • 中签后T+2日16:00前确保账户有足额资金<br>
            • 上市首日建议择机卖出锁定收益
          </div>
        </div>

      </td>
    </tr>

    <!-- 底部 -->
    <tr>
      <td style="padding:16px 20px;background:#fafafa;text-align:center;border-top:1px solid #eee;">
        <div style="font-size:12px;color:#999;">以上仅供参考，不构成投资建议</div>
        <div style="font-size:12px;color:#ccc;margin-top:4px;">自动发送 · Marcus策略小助手</div>
      </td>
    </tr>

  </table>

</td></tr>
</table>
</body>
</html>"""
    return html


def send_bond_email(bonds: List[Dict]) -> bool:
    """使用新债专用邮件池发送打新提醒"""
    from src.core.config import Config

    # 加载配置
    config_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "configs", "settings.yaml"
    )
    config = Config.from_yaml(config_path)
    bond_cfg = config.bond_email

    if not bond_cfg.enabled:
        logger.info("新债邮件未启用，跳过发送")
        return False

    if not bond_cfg.to_emails:
        logger.error("新债邮件池未配置收件人")
        return False

    # 构建邮件
    subject = "新债打新提醒"
    html_content = build_bond_email_html(bonds)

    # 纯文本版本
    lines = [f"【新债打新提醒】{datetime.now().strftime('%Y-%m-%d')}", ""]
    for b in bonds:
        lines.append(f"  {b['bond_name']}（{b['bond_code']}）")
        lines.append(f"  申购代码: {b['apply_code']} | 发行价: {b['price']} | 评级: {b.get('rating', '待查')}")
        lines.append("")
    lines.append("新债申购无市值要求，中签后缴款，建议积极参与。")
    plain_content = '\n'.join(lines)

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = Header(subject, 'utf-8')
        msg['From'] = bond_cfg.smtp_user
        msg['To'] = ', '.join(bond_cfg.to_emails)
        msg['Date'] = formatdate(localtime=True)

        if bond_cfg.cc_emails:
            msg['Cc'] = ', '.join(bond_cfg.cc_emails)

        msg.attach(MIMEText(plain_content, 'plain', 'utf-8'))
        msg.attach(MIMEText(html_content, 'html', 'utf-8'))

        all_recipients = bond_cfg.to_emails + bond_cfg.cc_emails

        with smtplib.SMTP_SSL(
            bond_cfg.smtp_server, bond_cfg.smtp_port, timeout=30
        ) as server:
            server.login(bond_cfg.smtp_user, bond_cfg.smtp_password)
            server.sendmail(bond_cfg.smtp_user, all_recipients, msg.as_string())

        logger.info(f"✅ 新债提醒邮件已发送")
        logger.info(f"   收件人: {bond_cfg.to_emails}")
        logger.info(f"   抄送: {bond_cfg.cc_emails}")
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error("新债邮件发送失败: SMTP 认证失败，请检查授权码")
        return False
    except Exception as e:
        logger.error(f"新债邮件发送失败: {e}")
        return False


# ─────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────

def main():
    """主流程"""
    logger.info("=" * 50)
    logger.info("新债打新提醒 — 开始检查")

    # 1. 交易日判断
    if not is_trading_day():
        logger.info("今日非交易日，无需检查新债")
        return 0

    # 2. 获取今日可申购新债
    bonds = get_new_bonds_today()

    # 3. 判断是否发送邮件
    if not bonds:
        logger.info("今日无新债可申购，不发送邮件")
        return 0

    # 4. 发送新债提醒邮件
    logger.info(f"发现 {len(bonds)} 只可申购新债，准备发送邮件...")
    success = send_bond_email(bonds)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
