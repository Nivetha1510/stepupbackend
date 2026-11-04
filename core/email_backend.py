"""Email backend that sends through Brevo's HTTPS API.

Hosts such as Render's free tier block outbound SMTP ports, so SMTP cannot be used there. Set
EMAIL_MODE=brevo and BREVO_API_KEY; DEFAULT_FROM_EMAIL must be a sender verified in your Brevo account.
"""
import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from email.utils import parseaddr

BREVO_URL = "https://api.brevo.com/v3/smtp/email"


class BrevoEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        sent = 0
        for message in email_messages:
            name, address = parseaddr(message.from_email or settings.DEFAULT_FROM_EMAIL)
            sender = {"email": address}
            if name:
                sender["name"] = name
            try:
                response = requests.post(
                    BREVO_URL,
                    headers={"api-key": settings.BREVO_API_KEY, "accept": "application/json"},
                    json={
                        "sender": sender,
                        "to": [{"email": recipient} for recipient in message.to],
                        "subject": message.subject,
                        "textContent": message.body,
                    },
                    timeout=10,
                )
                response.raise_for_status()
            except requests.RequestException:
                if not self.fail_silently:
                    raise
                continue
            sent += 1
        return sent
