# -*- coding: utf-8 -*-
"""
邮件发送模块
支持DEBUG模式（不发送邮件）
"""

import smtplib
import base64
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.header import Header
from datetime import datetime
from config import EMAIL_CONFIG


class MailSender:
    """邮件发送器"""

    def __init__(self):
        self.config = EMAIL_CONFIG
        self.enabled = EMAIL_CONFIG.get('enabled', True)
        self.debug_mode = EMAIL_CONFIG.get('debug_mode', True)

    def send_selection_report(self, content, subject=None, attachment_path=None):
        """
        发送选股报告邮件
        attachment_path: 附件文件路径（如选股数据txt文件）
        """
        if not self.enabled:
            print("⚠️ 邮件发送未启用")
            return False

        if self.debug_mode:
            print("\n" + "=" * 60)
            print("🔧 DEBUG模式 - 邮件内容预览")
            print("=" * 60)
            print(content)
            if attachment_path:
                print(f"\n📎 附件: {attachment_path}")
            print("=" * 60)
            print("✅ DEBUG模式：邮件未实际发送")
            return True

        # 生成邮件主题
        if not subject:
            today = datetime.now().strftime('%Y-%m-%d')
            subject = f"{self.config.get('subject_prefix', '[AI选股]')} {today} 选股报告"

        # 发送邮件
        try:
            return self._send_email(subject, content, attachment_path)
        except Exception as e:
            print(f"❌ 发送邮件失败: {e}")
            return False

    def _send_email(self, subject, content, attachment_path=None):
        """实际发送邮件"""
        msg = MIMEMultipart('mixed')  # 使用mixed以支持附件
        msg['Subject'] = Header(subject, 'utf-8')
        sender_name = self.config.get('sender_name', 'AI选股系统')
        sender_email = self.config['smtp_user']

        # QQ邮箱严格要求：使用正确的RFC 2047编码
        # 格式: =?utf-8?B?<base64>?= <email@domain.com>
        import base64
        encoded_name = base64.b64encode(sender_name.encode('utf-8')).decode('utf-8')
        from_header = f"=?utf-8?B?{encoded_name}?= <{sender_email}>"
        msg['From'] = from_header

        # 使用标准方式添加头部
        msg['From'] = Header(from_header, 'utf-8')

        # 多个收件人
        to_addresses = ','.join(self.config['to_emails'])
        msg['To'] = to_addresses

        # 添加抄送（调试模式时不抄送）
        cc_addresses = self.config.get('cc_emails', [])
        if cc_addresses and not self.debug_mode:
            cc_str = ','.join(cc_addresses)
            msg['Cc'] = cc_str

        # 添加Date头
        from email.utils import formatdate
        msg['Date'] = formatdate(localtime=True)

        # 纯文本内容
        plain_content = self._html_to_plain(content)
        msg.attach(MIMEText(plain_content, 'plain', 'utf-8'))

        # HTML内容（可选）
        html_content = self._format_html(content)
        msg.attach(MIMEText(html_content, 'html', 'utf-8'))

        # 添加附件
        if attachment_path:
            try:
                with open(attachment_path, 'rb') as f:
                    attachment = MIMEApplication(f.read(), Name=os.path.basename(attachment_path))
                    attachment['Content-Disposition'] = f'attachment; filename="{os.path.basename(attachment_path)}"'
                    msg.attach(attachment)
                print(f"✅ 已添加附件: {os.path.basename(attachment_path)}")
            except Exception as e:
                print(f"⚠️ 添加附件失败: {e}")

        # 发送邮件
        try:
            if self.config.get('smtp_port') == 465:
                # SSL连接
                server = smtplib.SMTP_SSL(self.config['smtp_server'], self.config['smtp_port'])
                server.login(self.config['smtp_user'], self.config['smtp_password'])
            else:
                # 普通连接
                server = smtplib.SMTP(self.config['smtp_server'], self.config['smtp_port'])
                server.starttls()
                server.login(self.config['smtp_user'], self.config['smtp_password'])

            # 所有收件人（包括抄送，调试模式时不发抄送）
            if self.debug_mode:
                all_recipients = self.config['to_emails']
                print("📧 [调试模式] 不发送抄送")
            else:
                all_recipients = self.config['to_emails'] + self.config.get('cc_emails', [])
            server.sendmail(self.config['smtp_user'], all_recipients, msg.as_string())
            server.quit()

            # 显示所有收件人
            all_str = ', '.join(all_recipients)
            print(f"✅ 邮件已发送至: {all_str}")
            return True

        except smtplib.SMTPException as e:
            print(f"❌ SMTP错误: {e}")
            return False
        except Exception as e:
            print(f"❌ 发送失败: {e}")
            return False

    def _html_to_plain(self, html):
        """将HTML转换为纯文本（避免格式问题）"""
        # 简单处理：移除HTML标签，保留文本
        import re
        text = re.sub(r'<br\s*/?>', '\n', html)
        text = re.sub(r'<p[^>]*>', '\n', text)
        text = re.sub(r'</p>', '', text)
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'&nbsp;', ' ', text)
        text = re.sub(r'&lt;', '<', text)
        text = re.sub(r'&gt;', '>', text)
        text = re.sub(r'\n\s*\n', '\n\n', text)
        return text.strip()

    def _format_html(self, content):
        """将内容格式化为HTML邮件"""
        # 简单处理，直接包裹在pre标签中避免换行问题
        return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{ font-family: "Microsoft YaHei", Arial, sans-serif; line-height: 1.6; padding: 20px; }}
.stock-item {{ margin: 15px 0; padding: 10px; background: #f5f5f5; border-radius: 5px; }}
.stock-name {{ font-weight: bold; color: #333; }}
.stock-score {{ color: #e74c3c; }}
.advice {{ color: #27ae60; font-weight: bold; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background-color: #3498db; color: white; }}
</style>
</head>
<body>
<pre style="font-family: 'Microsoft YaHei', monospace; white-space: pre-wrap; word-wrap: break-word;">
{content}
</pre>
</body>
</html>
"""


def test_email():
    """测试邮件发送"""
    print("=" * 60)
    print("邮件发送测试")
    print("=" * 60)

    sender = MailSender()

    test_content = """
【AI智能选股系统 - 测试邮件】
时间: {time}

这是一封测试邮件，用于验证邮件发送功能是否正常。

DEBUG模式: {debug}
邮件配置:
- SMTP服务器: {smtp}
- 发送邮箱: {from_addr}
- 接收邮箱: {to_addr}
""".format(
        time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        debug="开启" if sender.debug_mode else "关闭",
        smtp=sender.config.get('smtp_server', 'N/A'),
        from_addr=sender.config.get('smtp_user', 'N/A'),
        to_addr=', '.join(sender.config.get('to_emails', []))
    )

    result = sender.send_selection_report(test_content)
    return result


if __name__ == "__main__":
    test_email()
