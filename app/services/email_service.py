
import os
import smtplib
from email.message import EmailMessage

from dotenv import load_dotenv

load_dotenv()


def send_email(to_email: str, subject: str, body: str) -> bool:
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    sender_email = os.getenv("SMTP_FROM_EMAIL")

    if not all([smtp_server, smtp_username, smtp_password, sender_email]):
        raise RuntimeError(
            "SMTP configuration is incomplete. Check your .env file."
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender_email
    message["To"] = to_email
    message.set_content(body)

    try:
        with smtplib.SMTP(
            smtp_server,
            smtp_port,
            timeout=20,
        ) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_username, smtp_password)
            server.send_message(message)

        return True

    except (smtplib.SMTPException, OSError) as error:
        raise RuntimeError(
            "Unable to send email. Check your SMTP settings and connection."
        ) from error
