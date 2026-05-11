"""
邮件发送模块
使用SMTP发送分析报告
支持丰富的邮件内容格式
"""
import smtplib
import re
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.header import Header
from email.utils import formatdate
from typing import List, Optional
from pathlib import Path
from datetime import datetime

from ..core.config import EmailConfig


def format_email_html(content: str, title: str = "Marcus量化选股报告") -> str:
    """
    将文本内容格式化为适合 iPhone 阅读的 HTML 邮件。

    设计原则：
    - 紧凑间距（段落 margin 仅 3-4px），避免大量空白
    - 一级标题（【】）深蓝底白字，视觉分区明显
    - ▶ 开头的股票/操作条目用浅灰卡片，左侧彩条
    - 正文字号 14px，手机可读；最大宽度 600px
    - 涨幅红色，跌幅绿色，评分橙色
    """
    now = datetime.now()
    date_str = now.strftime('%Y年%m月%d日 %H:%M')

    lines = content.split('\n')
    html_lines = []

    for line in lines:
        line_stripped = line.strip()

        # 空行 → 小间隔，不输出 <br>（由 CSS margin 控制）
        if not line_stripped:
            continue

        # ── 分隔线（== 或 ━━ 开头）→ 忽略，改用标题自带边框
        if line_stripped.startswith('==') or line_stripped.startswith('━━'):
            continue

        # ── 一级标题 【xxx】
        if line_stripped.startswith('【') and line_stripped.endswith('】'):
            label = line_stripped[1:-1]
            html_lines.append(
                f'<div class="sec-title">{label}</div>'
            )
            continue

        # ── 子标题 ## xxx
        if line_stripped.startswith('## '):
            html_lines.append(
                f'<div class="sub-title">{line_stripped[3:]}</div>'
            )
            continue

        # ── 要点列表 • 或 -
        if line_stripped.startswith('• ') or line_stripped.startswith('- '):
            text = line_stripped[2:]
            text = _highlight(text)
            html_lines.append(f'<div class="bullet">• {text}</div>')
            continue

        # ── ▶ 股票/操作卡片
        if line_stripped.startswith('▶'):
            text = line_stripped[1:].strip()
            text = _highlight(text)
            # 缩进行（前有空格）视为卡片内子行
            if line.startswith('   '):
                html_lines.append(f'<div class="card-row">{text}</div>')
            else:
                html_lines.append(f'<div class="card-head">{text}</div>')
            continue

        # ── 普通文本
        text = _highlight(line_stripped)
        html_lines.append(f'<div class="row">{text}</div>')

    content_html = '\n'.join(html_lines)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{
  font-family:-apple-system,"PingFang SC","Microsoft YaHei",Arial,sans-serif;
  font-size:14px;line-height:1.55;color:#222;
  background:#eef1f5;
}}
.wrap{{
  max-width:600px;margin:0 auto;
  background:#fff;border-radius:10px;
  overflow:hidden;
  box-shadow:0 1px 6px rgba(0,0,0,.12);
}}
/* 顶部标题栏 */
.hdr{{
  background:linear-gradient(135deg,#1a5fad 0%,#2980b9 100%);
  padding:16px 16px 12px;
  text-align:center;color:#fff;
}}
.hdr h1{{font-size:17px;font-weight:700;letter-spacing:.5px}}
.hdr .dt{{font-size:12px;opacity:.85;margin-top:3px}}
/* 内容区 */
.body{{padding:12px 14px 16px}}
/* 一级标题：深蓝底白字 */
.sec-title{{
  background:#1a5fad;color:#fff;
  font-size:13px;font-weight:700;
  padding:5px 10px;border-radius:4px;
  margin:10px 0 4px;
}}
/* 二级标题：橙色文字 */
.sub-title{{
  color:#e67e22;font-size:13px;font-weight:700;
  margin:7px 0 2px;
}}
/* 普通列表行 */
.bullet{{
  font-size:13px;color:#333;
  padding:2px 0 2px 4px;
  border-left:3px solid #2980b9;
  margin:2px 0;
}}
/* ▶ 卡片头部（股票名行） */
.card-head{{
  background:#f0f4f8;
  border-left:4px solid #2980b9;
  border-radius:0 4px 4px 0;
  padding:5px 8px;
  font-size:13px;font-weight:700;
  margin:5px 0 1px;
}}
/* 卡片内子行（价格/策略等） */
.card-row{{
  font-size:12px;color:#444;
  padding:1px 8px 1px 12px;
  margin:1px 0;
}}
/* 普通文本行 */
.row{{
  font-size:13px;color:#333;
  padding:2px 0;
  margin:1px 0;
}}
/* 数字高亮 */
.up{{color:#e74c3c;font-weight:600}}
.dn{{color:#27ae60;font-weight:600}}
.score{{color:#e67e22;font-weight:600}}
.amt{{color:#2980b9;font-weight:600}}
/* 底部 */
.ftr{{
  background:#f0f2f5;
  border-top:1px solid #d0d7de;
  padding:10px 14px 12px;
  text-align:center;
}}
.ftr-risk{{
  font-size:11px;color:#888;
  line-height:1.6;margin-bottom:5px;
  border:1px solid #dde3ea;border-radius:4px;
  background:#f8f9fb;padding:6px 10px;
  text-align:left;
}}
.ftr-copy{{
  font-size:11px;color:#bbb;
}}
</style>
</head>
<body>
<div class="wrap">
  <div class="hdr">
    <h1>{title}</h1>
    <div class="dt">{date_str}</div>
  </div>
  <div class="body">
{content_html}
  </div>
  <div class="ftr">
    <div class="ftr-risk">风险提示：以上内容仅供参考，不构成投资建议。股市有风险，投资需谨慎，请独立判断。建议分散持仓，严格执行止损（-5%），量化模型不能替代基本面分析与个人判断。</div>
    <div class="ftr-copy">本报告由 Marcus量化选股小助手 自动生成 · 请勿转发</div>
  </div>
</div>
</body>
</html>"""
    return html


def _highlight(text: str) -> str:
    """对文本中的数字、百分比、评分做颜色高亮"""
    # 正涨幅（+开头或纯正数%）→ 红
    text = re.sub(
        r'(\+\d+\.?\d*%)',
        r'<span class="up">\1</span>', text
    )
    # 负涨幅 → 绿
    text = re.sub(
        r'(-\d+\.?\d*%)',
        r'<span class="dn">\1</span>', text
    )
    # 无符号百分比（涨幅/换手等）→ 红
    text = re.sub(
        r'(?<![+-])(\b\d+\.?\d*%)(?!</span>)',
        r'<span class="up">\1</span>', text
    )
    # 评分 → 橙
    text = re.sub(
        r'(评分[:：]\s*\d+\.?\d*)',
        r'<span class="score">\1</span>', text
    )
    # 成交额（含"亿"或"万"）→ 蓝
    text = re.sub(
        r'(\d+\.?\d*[亿万])',
        r'<span class="amt">\1</span>', text
    )
    return text


class EmailSender:
    """
    邮件发送器
    
    支持QQ邮箱SMTP发送，包含丰富的邮件格式
    """
    
    def __init__(self, config: EmailConfig):
        self.config = config
        self.logger = logging.getLogger("AInvest.EmailSender")
    
    def send(
        self,
        subject: str,
        html_content: str,
        to_emails: Optional[List[str]] = None,
        cc_emails: Optional[List[str]] = None,
        attachments: Optional[List[str]] = None
    ) -> bool:
        """
        发送邮件
        
        Args:
            subject: 邮件主题
            html_content: HTML邮件内容
            to_emails: 收件人列表（覆盖配置）
            cc_emails: 抄送列表（覆盖配置）
            attachments: 附件路径列表
            
        Returns:
            发送是否成功
        """
        if not self.config.enabled:
            self.logger.info("邮件发送已禁用")
            return False
        
        # 确定收件人
        recipients = to_emails or self.config.to_emails
        cc_list = cc_emails or self.config.cc_emails
        
        if not recipients:
            self.logger.error("没有配置收件人")
            return False
        
        # 调试模式跳过抄送
        if self.config.debug_mode:
            cc_list = []
            self.logger.info("调试模式：跳过抄送")
        
        try:
            # 创建邮件（使用mixed以支持附件）
            msg = MIMEMultipart('mixed')
            msg['Subject'] = Header(subject, 'utf-8')
            msg['From'] = self.config.smtp_user
            msg['To'] = ', '.join(recipients)
            msg['Date'] = formatdate(localtime=True)
            
            if cc_list:
                msg['Cc'] = ', '.join(cc_list)
            
            # 添加HTML内容（同时保留纯文本版本）
            plain_content = self._html_to_plain(html_content)
            msg.attach(MIMEText(plain_content, 'plain', 'utf-8'))
            msg.attach(MIMEText(html_content, 'html', 'utf-8'))
            
            # 添加附件
            if attachments:
                for filepath in attachments:
                    self._add_attachment(msg, filepath)
            
            # 发送邮件
            all_recipients = recipients + cc_list
            
            # 根据端口选择连接方式
            if self.config.smtp_port == 465:
                server = smtplib.SMTP_SSL(self.config.smtp_server, self.config.smtp_port)
            else:
                server = smtplib.SMTP(self.config.smtp_server, self.config.smtp_port)
                server.starttls()
            
            with server as smtp_server:
                smtp_server.login(self.config.smtp_user, self.config.smtp_password)
                smtp_server.sendmail(self.config.smtp_user, all_recipients, msg.as_string())
            
            self.logger.info(f"邮件发送成功: {recipients}")
            return True
            
        except smtplib.SMTPAuthenticationError:
            self.logger.error("SMTP认证失败，请检查用户名和授权码")
            return False
        except smtplib.SMTPException as e:
            self.logger.error(f"SMTP发送失败: {e}")
            return False
        except Exception as e:
            self.logger.error(f"邮件发送异常: {e}")
            return False
    
    def _html_to_plain(self, html: str) -> str:
        """将HTML转换为纯文本"""
        # 简单处理：移除HTML标签，保留文本
        text = re.sub(r'<br\s*/?>', '\n', html)
        text = re.sub(r'<p[^>]*>', '\n', text)
        text = re.sub(r'</p>', '', text)
        text = re.sub(r'<h[1-6][^>]*>', '\n', text)
        text = re.sub(r'</h[1-6]>', '\n', text)
        text = re.sub(r'<div[^>]*>', '\n', text)
        text = re.sub(r'</div>', '', text)
        text = re.sub(r'<li[^>]*>', '• ', text)
        text = re.sub(r'</li>', '\n', text)
        text = re.sub(r'<ul[^>]*>', '', text)
        text = re.sub(r'</ul>', '', text)
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'&nbsp;', ' ', text)
        text = re.sub(r'&lt;', '<', text)
        text = re.sub(r'&gt;', '>', text)
        text = re.sub(r'&amp;', '&', text)
        text = re.sub(r'\n\s*\n', '\n\n', text)
        return text.strip()
    
    def _add_attachment(self, msg: MIMEMultipart, filepath: str):
        """添加附件"""
        try:
            path = Path(filepath)
            if not path.exists():
                self.logger.warning(f"附件不存在: {filepath}")
                return
            
            with open(path, 'rb') as f:
                part = MIMEApplication(f.read(), Name=path.name)
                part['Content-Disposition'] = f'attachment; filename="{path.name}"'
                msg.attach(part)
            
            self.logger.debug(f"已添加附件: {path.name}")
            
        except Exception as e:
            self.logger.warning(f"添加附件失败: {e}")
    
    def send_report(
        self,
        results_summary: str,
        html_content: str,
        strategy_name: str,
        attachments: Optional[List[str]] = None
    ) -> bool:
        """
        发送选股报告
        
        Args:
            results_summary: 结果摘要（纯文本）
            html_content: HTML报告内容
            strategy_name: 策略名称
            attachments: 附件路径列表
            
        Returns:
            发送是否成功
        """
        # 构建邮件主题：固定格式
        today = datetime.now().strftime('%Y-%m-%d')
        subject = f"[Marcus量化选股小助手] {today} 动态策略报告"
        
        # 使用配置中的收件人
        to_emails = self.config.to_emails if self.config.to_emails else []
        cc_emails = self.config.cc_emails if self.config.cc_emails else []
        
        self.logger.info(f"准备发送邮件:")
        self.logger.info(f"  主题: {subject}")
        self.logger.info(f"  收件人: {to_emails}")
        self.logger.info(f"  附件: {attachments}")
        
        # 使用格式化的HTML模板（标题固定为"Marcus量化选股小助手"）
        formatted_html = format_email_html(results_summary, "Marcus量化选股小助手")
        
        return self.send(
            subject=subject,
            html_content=formatted_html,
            to_emails=to_emails,
            cc_emails=cc_emails,
            attachments=attachments
        )
    
    def test_connection(self) -> bool:
        """
        测试SMTP连接
        
        Returns:
            连接是否成功
        """
        try:
            with smtplib.SMTP_SSL(
                self.config.smtp_server,
                self.config.smtp_port
            ) as server:
                server.login(self.config.smtp_user, self.config.smtp_password)
            
            self.logger.info("SMTP连接测试成功")
            return True
            
        except Exception as e:
            self.logger.error(f"SMTP连接测试失败: {e}")
            return False
