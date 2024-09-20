"""Module for easy sending emails"""
# Import smtplib for the actual sending function.
from redmail import EmailSender

# Here are the email package modules we'll need.
from email.message import EmailMessage

# Import os for getting values of ENV vars
import os


def get_default_message():
    msg = EmailMessage()
    msg['From'] = os.getenv('SMTP_FROM')
    return msg


def get_default_sender():
    return os.getenv('SMTP_FROM')


def get_mail_client():
    """Return predefined client"""
    return EmailSender(
        host=os.getenv('SMTP_HOST'),
        port=os.getenv('SMTP_PORT'),
        username=os.getenv('SMTP_USER'),
        password=os.getenv('SMTP_PASSWORD'),
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
