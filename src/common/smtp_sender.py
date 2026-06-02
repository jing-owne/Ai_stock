"""
通用SMTP邮件发送器（纯发送，无业务逻辑）

职责：发送HTML/纯文本邮件，支持附件
不依赖任何业务类型，可被策略邮件、新债邮件等任意场景复用

用法：
    from src.common.smtp_sender import SMTPSender

    sender = SMTPSender(
        smtp_server="smtp.qq.com",
        smtp_port=465,
        smtp_user="xxx@qq.com",
        smtp_password="auth_code",
        sender_name="发件人名称"
    )
    ok = sender.send(
        subject="邮件主题",
        html_content="<html>...</html>",
        to_emails=["a@qq.com"],
        cc_emails=["b@qq.com"],
        attachments=["/path/to/file.pdf"],
        debug=False
    )
"""

import smtplib
import logging
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.header import Header
from email.utils import formatdate
from typing import List, Optional
from pathlib import Path


class SMTPSender:
    """通用SMTP邮件发送器"""

    def __init__(
        self,
        smtp_server: str,
        smtp_port: int = 465,
        smtp_user: str = "",
        smtp_password: str = "",
        sender_name: str = "",
    ):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.sender_name = sender_name
        self.logger = logging.getLogger("AInvest.SMTPSender")

    def send(
        self,
        subject: str,
        html_content: str,
        plain_content: str = None,
        to_emails: Optional[List[str]] = None,
        cc_emails: Optional[List[str]] = None,
        attachments: Optional[List[str]] = None,
        debug: bool = False,
    ) -> bool:
        """
        发送邮件

        Args:
            subject: 邮件主题
            html_content: HTML正文
            plain_content: 纯文本正文（不传则自动从HTML提取）
            to_emails: 收件人列表
            cc_emails: 抄送列表
            attachments: 附件路径列表
            debug: True=跳过抄送

        Returns:
            发送是否成功
        """
        if not to_emails:
            self.logger.error("没有收件人")
            return False

        recipients = to_emails
        cc_list = [] if debug else (cc_emails or [])

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = Header(subject, "utf-8")
            if self.sender_name:
                msg["From"] = Header(self.sender_name, "utf-8").encode() + f" <{self.smtp_user}>"
            else:
                msg["From"] = self.smtp_user
            msg["To"] = ", ".join(recipients)
            msg["Date"] = formatdate(localtime=True)

            if cc_list:
                msg["Cc"] = ", ".join(cc_list)

            # 附带纯文本版本
            text = plain_content or self._html_to_plain(html_content)
            msg.attach(MIMEText(text, "plain", "utf-8"))
            msg.attach(MIMEText(html_content, "html", "utf-8"))

            # 附件
            if attachments:
                mixed = MIMEMultipart("mixed")
                mixed["Subject"] = msg["Subject"]
                mixed["From"] = msg["From"]
                mixed["To"] = msg["To"]
                mixed["Date"] = msg["Date"]
                if cc_list:
                    mixed["Cc"] = msg["Cc"]
                mixed.attach(msg)
                for fp in attachments:
                    self._add_attachment(mixed, fp)
                msg = mixed

            all_recipients = recipients + cc_list

            if self.smtp_port == 465:
                server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, timeout=30)
            else:
                server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30)
                server.starttls()

            with server as smtp:
                smtp.login(self.smtp_user, self.smtp_password)
                smtp.sendmail(self.smtp_user, all_recipients, msg.as_string())

            self.logger.info(
                f"邮件发送成功 -> {recipients}"
                + (f" cc:{cc_list}" if cc_list else "")
            )
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

    def test_connection(self) -> bool:
        """测试SMTP连接"""
        try:
            with smtplib.SMTP_SSL(
                self.smtp_server, self.smtp_port, timeout=30
            ) as server:
                server.login(self.smtp_user, self.smtp_password)
            self.logger.info("SMTP连接测试成功")
            return True
        except Exception as e:
            self.logger.error(f"SMTP连接测试失败: {e}")
            return False

    @staticmethod
    def _html_to_plain(html_text: str) -> str:
        """HTML转纯文本"""
        text = re.sub(r"<br\s*/?>", "\n", html_text)
        text = re.sub(r"<p[^>]*>", "\n", text)
        text = re.sub(r"</p>", "", text)
        text = re.sub(r"<h[1-6][^>]*>", "\n", text)
        text = re.sub(r"</h[1-6]>", "\n", text)
        text = re.sub(r"<div[^>]*>", "\n", text)
        text = re.sub(r"</div>", "", text)
        text = re.sub(r"<li[^>]*>", "• ", text)
        text = re.sub(r"</li>", "\n", text)
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("&nbsp;", " ").replace("&lt;", "<")
        text = text.replace("&gt;", ">").replace("&amp;", "&")
        return text.strip()

    @staticmethod
    def _add_attachment(msg: MIMEMultipart, filepath: str):
        """添加附件"""
        try:
            p = Path(filepath)
            if not p.exists():
                logging.warning(f"附件不存在: {filepath}")
                return
            with open(p, "rb") as f:
                part = MIMEApplication(f.read(), Name=p.name)
                part["Content-Disposition"] = f'attachment; filename="{p.name}"'
                msg.attach(part)
        except Exception as e:
            logging.warning(f"添加附件失败: {e}")
