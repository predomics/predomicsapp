"""Optional email sending service using aiosmtplib."""

import logging

from ..core.config import settings

_log = logging.getLogger(__name__)


def is_email_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_from)


async def send_email(to: str, subject: str, html_body: str) -> bool:
    """Send an email. Returns True on success, False if SMTP not configured or error."""
    if not is_email_configured():
        _log.warning("SMTP not configured, email not sent to %s", to)
        return False

    try:
        import aiosmtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.smtp_from
        msg["To"] = to
        msg.attach(MIMEText(html_body, "html"))

        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user or None,
            password=settings.smtp_password or None,
            # Port 465 speaks TLS from the first byte; 587/25 start in clear text and
            # upgrade with STARTTLS. Using implicit TLS on 587 fails the handshake.
            use_tls=settings.smtp_tls and settings.smtp_port == 465,
            start_tls=settings.smtp_tls and settings.smtp_port != 465,
            timeout=20,
        )
        return True
    except ImportError:
        _log.warning("aiosmtplib not installed, email not sent")
        return False
    except Exception as e:
        _log.error("Email send failed: %s", e)
        return False


async def send_password_reset(to: str, token: str) -> bool:
    reset_url = f"{settings.frontend_url.rstrip('/')}/reset-password?token={token}"
    html = f"""\
<h2>Password Reset — PredomicsApp</h2>
<p>Click the link below to reset your password. This link expires in 1 hour.</p>
<p><a href="{reset_url}">{reset_url}</a></p>
<p>If you did not request this, you can safely ignore this email.</p>
"""
    return await send_email(to, "PredomicsApp Password Reset", html)


async def send_email_verification(to: str, token: str) -> bool:
    verify_url = f"{settings.frontend_url.rstrip('/')}/verify-email?token={token}"
    html = f"""\
<h2>Confirm your email — PredomicsApp</h2>
<p>Click the link below to activate your account. This link expires in 24 hours.</p>
<p><a href="{verify_url}">{verify_url}</a></p>
<p>If you did not create an account, you can safely ignore this email.</p>
"""
    return await send_email(to, "Confirm your PredomicsApp account", html)


async def send_already_registered(to: str) -> bool:
    """Tell the owner of an address that someone tried to register with it again."""
    login_url = f"{settings.frontend_url.rstrip('/')}/login"
    html = f"""\
<h2>You already have a PredomicsApp account</h2>
<p>Someone (probably you) tried to create an account with this email address,
but one already exists. You can <a href="{login_url}">sign in</a>, or use
"Forgot password" on that page if you no longer remember your password.</p>
<p>If this was not you, no action is needed: nothing was changed.</p>
"""
    return await send_email(to, "PredomicsApp: you already have an account", html)
