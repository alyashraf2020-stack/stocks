"""Only official Bot API methods for pairing and outgoing notifications."""

import logging
import re

import httpx


class _RedactTelegram(logging.Filter):
    def filter(self, record):
        return "api.telegram.org/bot" not in record.getMessage()


logging.getLogger("httpx").addFilter(_RedactTelegram())
logging.getLogger("httpcore").setLevel(logging.WARNING)

TOKEN = re.compile(r"^[0-9]{5,20}:[A-Za-z0-9_-]{20,128}$")


class TransportError(Exception):
    def __init__(self, code, *, retry=None, permanent=False, revoke=False):
        super().__init__(code)
        self.code, self.retry, self.permanent, self.revoke = (
            code,
            retry,
            permanent,
            revoke,
        )


class Telegram:
    def __init__(self, token, client=None):
        if not TOKEN.fullmatch(token):
            raise TransportError("TELEGRAM_CREDENTIALS_INVALID", permanent=True)
        self.token = token
        self.client = client

    def call(self, name, payload=None):
        url = "https://api.telegram.org/bot" + self.token + "/" + name
        try:
            if self.client:
                response = self.client.post(
                    url, json=payload or {}, follow_redirects=False
                )
            else:
                with httpx.Client(
                    timeout=8, follow_redirects=False, trust_env=False
                ) as client:
                    response = client.post(url, json=payload or {})
            data = response.json()
        except (httpx.HTTPError, ValueError):
            raise TransportError("TELEGRAM_UNAVAILABLE", retry=30) from None
        if not isinstance(data, dict):
            raise TransportError("TELEGRAM_UNAVAILABLE", retry=30)
        code = response.status_code
        if code == 429:
            seconds = (data.get("parameters") or {}).get("retry_after", 60)
            raise TransportError(
                "TELEGRAM_RATE_LIMITED",
                retry=max(1, min(86400, seconds if isinstance(seconds, int) else 60)),
            )
        if code == 401:
            raise TransportError("TELEGRAM_CREDENTIALS_INVALID", permanent=True)
        if name == "sendMessage" and code == 403:
            raise TransportError(
                "TELEGRAM_DESTINATION_REVOKED", permanent=True, revoke=True
            )
        if code == 409:
            raise TransportError("TELEGRAM_POLL_CONFLICT", permanent=True)
        if code >= 500:
            raise TransportError("TELEGRAM_UNAVAILABLE", retry=30)
        if (
            not response.is_success
            or not isinstance(data, dict)
            or data.get("ok") is not True
        ):
            raise TransportError("TELEGRAM_REQUEST_REJECTED", permanent=True)
        return data.get("result")

    def bot(self):
        result = self.call("getMe")
        name = result.get("username", "") if isinstance(result, dict) else ""
        if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", name):
            raise TransportError("TELEGRAM_BOT_UNVERIFIED", permanent=True)
        return name

    def updates(self):
        data = self.call(
            "getUpdates",
            {
                "timeout": 0,
                "limit": 100,
                "offset": -100,
                "allowed_updates": ["message"],
            },
        )
        return data if isinstance(data, list) else []

    def deliver(self, chat_id, text):
        self.call(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "link_preview_options": {"is_disabled": True},
                "protect_content": True,
            },
        )
