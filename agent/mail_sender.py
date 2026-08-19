"""邮件发送器：SMTP over SSL/TLS。"""
import mimetypes
import os
import smtplib
import ssl
from email import encoders
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from logger import logger


def _content_disposition(filename: str) -> str:
    encoded = Header(filename, "utf-8").encode()
    return f'attachment; filename="{encoded}"'


class MailSender:
    def __init__(self, email_config: dict, secrets: dict):
        self._cfg = email_config
        self._secrets = secrets

    def send(self, to: str, subject: str, body: str,
             html: bool = False, attachment_path: Optional[str] = None) -> bool:
        msg = MIMEMultipart()
        msg["From"] = self._cfg.get("email_account", "")
        msg["To"] = to
        msg["Subject"] = subject
        content_type = "html" if html else "plain"
        msg.attach(MIMEText(body, content_type, "utf-8"))

        if attachment_path and os.path.exists(attachment_path):
            filename = os.path.basename(attachment_path)
            ctype, _ = mimetypes.guess_type(attachment_path)
            if not ctype:
                ctype = "application/octet-stream"
            maintype, subtype = ctype.split("/", 1)
            with open(attachment_path, "rb") as f:
                data = f.read()
            part = MIMEBase(maintype, subtype)
            part.set_payload(data)
            encoders.encode_base64(part)
            part["Content-Disposition"] = _content_disposition(filename)
            msg.attach(part)

        server = self._cfg.get("smtp_server", "")
        port = int(self._cfg.get("smtp_port", 587))
        use_tls = self._cfg.get("smtp_tls", True)
        account = self._cfg.get("email_account", "")
        password = self._secrets.get("smtp_password") or self._secrets.get("email_password", "")

        try:
            if port == 465 or not use_tls:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(server, port, context=context, timeout=30) as smtp:
                    smtp.login(account, password)
                    smtp.send_message(msg)
            else:
                context = ssl.create_default_context()
                with smtplib.SMTP(server, port, timeout=30) as smtp:
                    smtp.starttls(context=context)
                    smtp.login(account, password)
                    smtp.send_message(msg)
            logger.info(f"邮件已发送到 {to}，主题: {subject}")
            return True
        except Exception as e:
            logger.error(f"邮件发送失败: {e}")
            return False