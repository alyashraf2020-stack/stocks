"""Public browser push services only. No owner-supplied arbitrary outbound host."""

import base64
import hmac
import re
from urllib.parse import urlsplit

import requests
from cryptography.hazmat.primitives.asymmetric.ec import (
    SECP256R1,
    EllipticCurvePublicKey,
    derive_private_key,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from pywebpush import WebPushException, webpush

from app.integrations.telegram_client import TransportError

HOSTS = {
    "fcm.googleapis.com",
    "updates.push.services.mozilla.com",
    "web.push.apple.com",
}


def endpoint_allowed(value):
    try:
        if (
            not isinstance(value, str)
            or not value.isascii()
            or any(ord(c) <= 32 for c in value)
        ):
            return False
        url = urlsplit(value)
        host = url.hostname or ""
        allowed = (
            host in HOSTS
            or bool(re.fullmatch(r"[a-z0-9-]{1,50}\.notify\.windows\.com", host))
            or bool(re.fullmatch(r"[a-z0-9-]{1,50}\.push\.apple\.com", host))
        )
        return (
            url.scheme == "https"
            and allowed
            and url.netloc == host
            and url.port is None
            and not url.fragment
            and not url.query
            and bool(re.fullmatch(r"/[A-Za-z0-9._~:/!$&'()*+,;=@%-]{4,1900}", url.path))
            and not re.search(r"%|\.\.|//", url.path)
        )
    except (ValueError, TypeError):
        return False


def decode(value):
    return base64.urlsafe_b64decode(
        value.rstrip("=") + "=" * (-len(value.rstrip("=")) % 4)
    )


def configured_pair(private, public, subject):
    if not (
        re.fullmatch(r"[A-Za-z0-9_-]{43}", private)
        and re.fullmatch(r"[A-Za-z0-9_-]{87}", public)
        and re.fullmatch(r"(?:mailto:[^@\s]+@[^@\s]+|https://[^\s?#]+)", subject)
    ):
        return False
    try:
        secret = derive_private_key(int.from_bytes(decode(private), "big"), SECP256R1())
        expected = secret.public_key().public_bytes(
            Encoding.X962, PublicFormat.UncompressedPoint
        )
        return hmac.compare_digest(expected, decode(public))
    except ValueError:
        return False


def validate_device(device):
    if not endpoint_allowed(device.endpoint):
        raise ValueError("PUSH_ENDPOINT_UNSUPPORTED")
    try:
        EllipticCurvePublicKey.from_encoded_point(
            SECP256R1(), decode(device.keys.p256dh)
        )
        if len(decode(device.keys.auth)) != 16:
            raise ValueError("length")
    except ValueError:
        raise ValueError("PUSH_SUBSCRIPTION_KEYS_INVALID") from None


class DirectSession(requests.Session):
    def __init__(self):
        super().__init__()
        self.trust_env = False

    def request(self, method, url, **kwargs):
        if not endpoint_allowed(url):
            raise TransportError("PUSH_ENDPOINT_UNSUPPORTED", permanent=True)
        kwargs["allow_redirects"] = False
        return super().request(method, url, **kwargs)


def deliver(subscription, data, environment, ttl):
    if not endpoint_allowed(subscription.get("endpoint")):
        raise TransportError("PUSH_ENDPOINT_UNSUPPORTED", permanent=True)
    try:
        with DirectSession() as session:
            response = webpush(
                subscription_info=subscription,
                data=data,
                vapid_private_key=environment.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": environment.VAPID_SUBJECT},
                timeout=8,
                ttl=max(1, min(3600, ttl)),
                requests_session=session,
            )
        if not 200 <= response.status_code < 300:
            raise TransportError("PUSH_REDIRECT_REJECTED", permanent=True)
    except WebPushException as exc:
        code = exc.response.status_code if exc.response is not None else 503
        if code in {404, 410}:
            raise TransportError(
                "DEVICE_EXPIRED", permanent=True, revoke=True
            ) from None
        if code == 429:
            value = exc.response.headers.get("Retry-After", "")
            raise TransportError(
                "PUSH_RATE_LIMITED",
                retry=min(86400, max(1, int(value)))
                if value.isdecimal() and len(value) < 8
                else 60,
            ) from None
        if code >= 500:
            raise TransportError("PUSH_UNAVAILABLE", retry=30) from None
        raise TransportError("PUSH_REJECTED", permanent=True) from None
    except (requests.RequestException, ValueError):
        raise TransportError("PUSH_UNAVAILABLE", retry=30) from None
