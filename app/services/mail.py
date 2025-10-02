"""Module for easy sending emails"""
# Import smtplib for the actual sending function.
from redmail import EmailSender

# Here are the email package modules we'll need.
from email.message import EmailMessage

from app.schemas.settings import settings


def get_default_sender():
    return settings.smtp_from

def get_default_message():
    msg = EmailMessage()
    msg['From'] = get_default_sender()
    return msg



def get_mail_client():
    """Return predefined client"""
    return EmailSender(
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_password,
    )


if __name__ == "__main__":
    client = get_mail_client()
    client.send(
        subject="Vaše vstupenka",
        sender=get_default_sender(),
        receivers=["test@lukasmatuska.cz"],
        text="Hello world!",
        html="<h1>Hi, </h1><p>this is an email.</p>"
    )
