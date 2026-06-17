from __future__ import annotations

import logging
import smtplib
import asyncio
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)

def _send_email_sync(to_email: str, subject: str, html_content: str):
    """Synchronous function to send an email via SMTP."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from_email
    msg["To"] = to_email
    msg.set_content(html_content, subtype="html")
    try:
        print(f"--- EMAIL DEBUGGER ---")
        print(f"Attempting to send email to: {to_email}")
        print(f"SMTP Server: {settings.smtp_server}")
        print(f"SMTP Port: {settings.smtp_port}")
        print(f"SMTP Username: {settings.smtp_username}")
        print(f"SMTP From: {settings.smtp_from_email}")
        print(f"----------------------")
        
        # Determine if SSL/TLS is needed based on port
        if settings.smtp_port in [465]:
            # Implicit TLS
            with smtplib.SMTP_SSL(settings.smtp_server, settings.smtp_port) as server:
                if settings.smtp_username and settings.smtp_password:
                    server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(msg, from_addr=settings.smtp_from_email, to_addrs=[to_email])
        else:
            # Explicit TLS (STARTTLS)
            with smtplib.SMTP(settings.smtp_server, settings.smtp_port) as server:
                server.ehlo()
                server.starttls()
                if settings.smtp_username and settings.smtp_password:
                    server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(msg, from_addr=settings.smtp_from_email, to_addrs=[to_email])
        
        print(f"Verification email sent to {to_email}")
    except Exception as e:
        import traceback
        print(f"Failed to send email to {to_email}. Error: {e}")
        traceback.print_exc()
        # Not raising the error because we don't want to break the background task

async def send_verification_email(to_email: str, token: str):
    """
    Sends an email verification link to the given email address.
    If SMTP_SERVER is not configured, logs the verification token instead.
    """
    verification_link = f"{settings.frontend_url}/verify-email?token={token}"
    
    if not settings.smtp_server:
        print(f"SMTP is disabled. Verification link for {to_email}: {verification_link}")
        return

    subject = "Verify your account"
    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #2563eb;">Welcome to DevOps AI Agent!</h2>
        <p>Thank you for registering. To complete your account setup and access the platform, please verify your email address by clicking the button below:</p>
        <div style="text-align: center; margin: 30px 0;">
          <a href="{verification_link}" style="background-color: #2563eb; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">Verify Email Address</a>
        </div>
        <p>If the button doesn't work, you can copy and paste the following link into your browser:</p>
        <p style="word-break: break-all; color: #6b7280; font-size: 0.9em;">
          <a href="{verification_link}">{verification_link}</a>
        </p>
        <p style="margin-top: 40px; font-size: 0.8em; color: #9ca3af;">
          If you did not create an account, no further action is required.
        </p>
      </body>
    </html>
    """

    # Run the synchronous SMTP call in a background thread
    await asyncio.to_thread(_send_email_sync, to_email, subject, html_content)


async def send_invite_email(to_email: str, invite_code: str, invited_by: str):
    """
    Sends a team invitation email with an accept link.
    Falls back to logging if SMTP is not configured.
    """
    accept_link = f"{settings.frontend_url}/accept-invite?code={invite_code}"

    if not settings.smtp_server:
        logger.info(f"SMTP is disabled. Invite link for {to_email}: {accept_link}")
        return

    subject = "You've been invited to join DevOps AI Hub"
    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #0d9488;">You're Invited!</h2>
        <p><strong>{invited_by}</strong> has invited you to join their team on <strong>DevOps AI Hub</strong>.</p>
        <p>Click the button below to accept the invitation and create your account:</p>
        <div style="text-align: center; margin: 30px 0;">
          <a href="{accept_link}" style="background-color: #0d9488; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">Accept Invitation</a>
        </div>
        <p>If the button doesn't work, you can copy and paste the following link into your browser:</p>
        <p style="word-break: break-all; color: #6b7280; font-size: 0.9em;">
          <a href="{accept_link}">{accept_link}</a>
        </p>
        <p style="margin-top: 40px; font-size: 0.8em; color: #9ca3af;">
          This invite link expires in 7 days. If you were not expecting this invitation, you can safely ignore this email.
        </p>
      </body>
    </html>
    """

    await asyncio.to_thread(_send_email_sync, to_email, subject, html_content)
