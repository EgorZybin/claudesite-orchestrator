from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from app.adapters.errors import AdapterConfigurationError, SmtpEmailError
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class SmtpEmailAdapter:
    def __init__(self, settings: Settings | None = None) -> None:
        self._s = settings or get_settings()

    def is_configured(self) -> bool:
        """True если в env есть host + from_default. user/password опциональны (бывают релеи без auth)."""
        return bool(self._s.smtp_host and self._s.smtp_from_default)

    def send(
        self,
        *,
        to: str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
        reply_to: str | None = None,
        cc: list[str] | None = None,
        from_name: str | None = None,
    ) -> None:
        if not self.is_configured():
            raise AdapterConfigurationError(
                "SMTP not configured: set SMTP_HOST and SMTP_FROM_DEFAULT env vars"
            )
        if not to or "@" not in to:
            raise SmtpEmailError(f"invalid recipient: {to!r}")

        from_addr = self._s.smtp_from_default or ""
        from_header = formataddr((from_name or "", from_addr)) if from_name else from_addr

        msg = EmailMessage()
        msg["From"] = from_header
        msg["To"] = to
        msg["Subject"] = subject
        if reply_to:
            msg["Reply-To"] = reply_to
        if cc:
            msg["Cc"] = ", ".join(cc)
        msg.set_content(body_text or "")
        if body_html:
            msg.add_alternative(body_html, subtype="html")

        all_recipients = [to] + list(cc or [])

        try:
            with smtplib.SMTP(
                host=self._s.smtp_host,
                port=self._s.smtp_port,
                timeout=self._s.smtp_timeout_seconds,
            ) as smtp:
                if self._s.smtp_use_tls:
                    smtp.starttls()
                if self._s.smtp_user and self._s.smtp_password:
                    smtp.login(self._s.smtp_user, self._s.smtp_password)
                refused = smtp.send_message(msg, from_addr=from_addr, to_addrs=all_recipients)
                if refused:
                    raise SmtpEmailError(f"SMTP refused recipients: {refused}")
        except (smtplib.SMTPException, OSError, TimeoutError) as e:
            raise SmtpEmailError(f"SMTP send failed ({type(e).__name__}): {e}") from e
