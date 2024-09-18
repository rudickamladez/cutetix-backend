"""Module for easy sending emails"""
# Import smtplib for the actual sending function.
import smtplib

# Here are the email package modules we'll need.
from email.message import EmailMessage

# Import os for getting values of ENV vars
import os


def get_default_message():
    msg = EmailMessage()
    msg['From'] = os.getenv('SMTP_FROM')
    return msg


def get_smtp_client():
    print('creating smtp client')
    client = smtplib.SMTP_SSL(
        host=os.getenv('SMTP_HOST'),
        port=os.getenv('SMTP_PORT'),
        timeout=2
    )
    # client.starttls()
    print('smtp login', os.getenv('SMTP_USER'), os.getenv('SMTP_PASSWORD'))
    client.login(
        user=os.getenv('SMTP_USER'),
        password=os.getenv('SMTP_PASSWORD')
    )
    return client


if __name__ == "__main__":
    with get_smtp_client() as client:
        msg = get_default_message()
        msg['To'] = 'matuska.lukas@lukasmatuska.cz'
        msg['Subject'] = 'New ticket'
        msg.add_header('Content-Type', 'text')
        msg.set_payload('Hello world!')
        client.send_message(msg=msg)
    # with smtplib.SMTP_SSL(
    #     host=os.getenv('SMTP_HOST'),
    #     port=os.getenv('SMTP_PORT'),
    #     timeout=2
    # ) as server:
    #     server.login(
    #         user=os.getenv('SMTP_USER'),
    #         password=os.getenv('SMTP_PASSWORD')
    #     )
    #     server.sendmail(
    #         os.getenv('SMTP_FROM'),
    #         'test@lukasmatuska.cz', 
    #         'Hello world!'
    #     )

