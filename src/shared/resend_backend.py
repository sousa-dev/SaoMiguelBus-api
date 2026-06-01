"""Custom email backend that sends via the Resend API.

Used in production when ``USE_SMTP`` is ``False`` (the default).
Requires the ``RESEND_API_KEY`` environment variable.
"""

from __future__ import annotations

import logging
from typing import Any

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)


class ResendEmailBackend(BaseEmailBackend):
    """Send emails through the `Resend <https://resend.com>`_ HTTP API."""

    API_URL = "https://api.resend.com/emails"

    def send_messages(self, email_messages: list[Any]) -> int:
        """Post each message to the Resend API.

        Returns:
            The number of messages successfully sent.
        """
        sent = 0
        for message in email_messages:
            payload = {
                "from": message.from_email,
                "to": message.to,
                "subject": message.subject,
                "text": message.body,
            }
            if hasattr(message, "alternatives") and message.alternatives:
                payload["html"] = message.alternatives[0][0]

            response = requests.post(
                self.API_URL,
                headers={
                    "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if response.status_code != 200:
                logger.error("Failed to send email: %s", response.json())
            else:
                logger.info("Successfully sent email to %s", message.to)
                sent += 1
        return sent
