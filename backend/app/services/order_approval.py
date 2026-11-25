"""Single-use local review bound to the HTTPS owner and a browser session."""

import hashlib
import hmac
import os
import secrets

from app.models.order_approval import OrderApproval, ReviewChallenge
from app.services.order_proposal_service import (
    ProposalError,
    event,
    invalidate_if_needed,
    transition,
)
from app.services.scanner_repository import digest

TTL = 120
PURPOSE = "LOCAL_REVIEW_ONLY"


def owner_binding():
    # Single owner is enforced by Caddy. Derive a separate stable identifier.
    secret = os.getenv("INTEGRATIONS_GATEWAY_SECRET", "").encode()
    if len(secret) < 32:
        raise ProposalError("OWNER_GATEWAY_REQUIRED")
    return hmac.new(secret, b"egx-order-owner-v1", hashlib.sha256).hexdigest()


def browser_binding(session, row):
    return digest(
        [
            owner_binding(),
            session,
            row.id,
            row.version,
            row.fingerprint,
            row.data["context"]["policy"],
        ]
    )


def issue(db, row, fingerprint, now, session):
    invalidate_if_needed(db, row, now)
    if row.state not in {"BLOCKED", "APPROVAL_REQUIRED"}:
        return None
    if not hmac.compare_digest(row.fingerprint, fingerprint):
        raise ProposalError("DRAFT_FINGERPRINT_CHANGED")
    clock = now.timestamp()
    previous = db.get(ReviewChallenge, row.id)
    if previous and previous.created + 2 > clock:
        raise ProposalError("REVIEW_RATE_LIMIT")
    token = secrets.token_urlsafe(32)
    until = min(clock + TTL, row.expires)
    db.merge(
        ReviewChallenge(
            proposal_id=row.id,
            token_hash=digest(token),
            binding=browser_binding(session, row),
            created=clock,
            expires=until,
        )
    )
    if row.state == "BLOCKED":
        transition(db, row, "APPROVAL_REQUIRED", clock, PURPOSE)
    else:
        event(db, row, clock, "REVIEW_CHALLENGE_REPLACED")
    return {"challenge": token, "expires": until, "purpose": PURPOSE}


def confirm(db, row, request, now, session):
    invalidate_if_needed(db, row, now)
    if row.state != "APPROVAL_REQUIRED":
        return "REVIEW_NO_LONGER_AVAILABLE"
    clock = now.timestamp()
    active = db.get(ReviewChallenge, row.id)
    if not active or active.expires <= clock:
        return "REVIEW_CHALLENGE_EXPIRED"
    if (
        not session
        or not hmac.compare_digest(request.fingerprint, row.fingerprint)
        or not hmac.compare_digest(active.binding, browser_binding(session, row))
        or not hmac.compare_digest(active.token_hash, digest(request.challenge))
    ):
        raise ProposalError("REVIEW_BINDING_MISMATCH")
    db.add(
        OrderApproval(
            proposal_id=row.id,
            fingerprint=row.fingerprint,
            challenge_hash=active.token_hash,
            purpose=PURPOSE,
            owner=owner_binding(),
            policy=row.data["context"]["policy"],
            created=clock,
        )
    )
    db.delete(active)
    transition(db, row, "LOCAL_REVIEWED", clock, PURPOSE)
    return None
