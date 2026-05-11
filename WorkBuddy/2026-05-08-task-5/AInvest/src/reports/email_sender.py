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
    将文本内容格式化为精美的HTML邮件
    
    Args:
        content: 原始文本内容（多行字符串）
        title: 邮件标题
        
    Returns:
        HTML格式的邮件内容
    """
    # 获取当前时间
    now = datetime.now()
    date_str = now.strftime('%Y年%m月%d日 %H:%M')
    
    # 将文本内容转为HTML（保留换行和基本格式）
    lines = content.split('\n')
    html_lines = []
    
    for line in lines:
        line = line.strip()
        if not line:
            html_lines.append('<br>')
            continue
        
        # 处理分隔线
        if line.startswith('==') or line.startswith('━━'):
            html_lines.append('<hr style="border: none; border-top: 2px solid #3498db; margin: 15px 0;">')
            continue
        
        # 处理标题
        if line.startswith('【') and line.endswith('】'):
            html_lines.append(f'<h3 style="color: #2c3e50; margin: 15px 0 10px 0; padding-bottom: 5px; border-bottom: 2px solid #3498db;">{line}</h3>')
            continue
        
        # 处理子标题
        if line.startswith('## '):
            html_lines.append(f'<h4 style="color: #34495e; margin: 12px 0 8px 0;">{line[3:]}</h4>')
            continue
        
        # 处理列表项
        if line.startswith('• ') or line.startswith('- '):
            html_lines.append(f'<li style="margin: 5px 0;">{line[2:]}</li>')
            continue
        
        # 处理序号项（如 "1. xxx"）
        if re.match(r'^\d+\.\s', line):
            html_lines.append(f'<li style="margin: 5px 0;">{re.sub(r"^\d+\.\s", "", line)}</li>')
            continue
        
        # 处理引用/重点项
        if line.startswith('▶'):
            line = line[1:].strip()
            html_lines.append(f'<div style="margin: 10px 0; padding: 10px; background: #f8f9fa; border-left: 4px solid #3498db; border-radius: 4px;"><b>{line}</b></div>')
            continue
        
        # 处理表格行（如包含 | 的内容）
        if '|' in line and line.count('|') >= 2:
            cells = [c.strip() for c in line.split('|') if c.strip()]
            if cells and cells[0] not in ['---', '----']:
                # 判断是否为表头
                is_header = all(c in cells[0] or cells[0] in c for c in ['股票', '代码', '名称', '评分'])
                if is_header or len(cells) >= 4:
                    html_lines.append('<tr>' + ''.join(f'<th style="border: 1px solid #ddd; padding: 8px; background: #3498db; color: white;">{c}</th>' for c in cells) + '</tr>')
                else:
                    html_lines.append('<tr>' + ''.join(f'<td style="border: 1px solid #ddd; padding: 8px;">{c}</td>' for c in cells) + '</tr>')
            continue
        
        # 处理普通文本
        # 高亮数字和百分比
        line = re.sub(r'([+-]?\d+\.?\d*%)', r'<span style="color: #e74c3c; font-weight: bold;">\1</span>', line)
        line = re.sub(r'(评分[:：]\d+\.?\d*)', r'<span style="color: #27ae60; font-weight: bold;">\1</span>', line)
        
        html_lines.append(f'<p style="margin: 5px 0; line-height: 1.6;">{line}</p>')
    
    content_html = '\n'.join(html_lines)
    
    # 生成完整的HTML邮件
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background-color: white;
            border-radius: 10px;
            padding: 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .header {{
            text-align: center;
            border-bottom: 2px solid #3498db;
            padding-bottom: 20px;
            margin-bottom: 20px;
        }}
        .header h1 {{
            color: #2c3e50;
            margin: 0 0 10px 0;
            font-size: 24px;
        }}
        .header .date {{
            color: #7f8c8d;
            font-size: 14px;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #ecf0f1;
            text-align: center;
            color: #95a5a6;
            font-size: 12px;
        }}
        .warning {{
            background-color: #fff3cd;
            border: 1px solid #ffc107;
            border-radius: 5px;
            padding: 15px;
            margin: 15px 0;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 10px 0;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 10px;
            text-align: left;
        }}
        th {{
            background-color: #3498db;
            color: white;
        }}
        tr:nth-child(even) {{
            background-color: #f8f9fa;
        }}
        ul {{
            margin: 5px 0;
            padding-left: 20px;
        }}
        .emoji {{
            font-size: 16px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
            <div class="date">{date_str}</div>
        </div>
        
        <div class="content">
            {content_html}
        </div>
        
        <div class="footer">
            <p>本报告由 <strong>Marcus量化选股小助手</strong> 自动生成</p>
            <p>仅供参考，不构成投资建议 | 股市有风险，投资需谨慎</p>
        </div>
    </div>
</body>
</html>
"""
    return html


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
        # 构建邮件主题
        today = datetime.now().strftime('%Y-%m-%d')
        subject = f"{self.config.subject_prefix} {today} {strategy_name}选股报告"
        
        # 使用配置中的收件人
        to_emails = self.config.to_emails if self.config.to_emails else []
        cc_emails = self.config.cc_emails if self.config.cc_emails else []
        
        self.logger.info(f"准备发送邮件:")
        self.logger.info(f"  主题: {subject}")
        self.logger.info(f"  收件人: {to_emails}")
        self.logger.info(f"  附件: {attachments}")
        
        # 使用格式化的HTML模板
        formatted_html = format_email_html(results_summary, f"Marcus量化选股 - {strategy_name}策略")
        
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
