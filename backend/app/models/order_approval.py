from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ReviewChallenge(Base):
    __tablename__ = "order_review_challenges"
    proposal_id: Mapped[str] = mapped_column(
        ForeignKey("order_proposals.id"), primary_key=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    binding: Mapped[str] = mapped_column(String(64))
    expires: Mapped[float] = mapped_column(Float)
    created: Mapped[float] = mapped_column(Float)


class OrderApproval(Base):
    __tablename__ = "order_approvals"
    proposal_id: Mapped[str] = mapped_column(
        ForeignKey("order_proposals.id"), primary_key=True
    )
    fingerprint: Mapped[str] = mapped_column(String(64))
    challenge_hash: Mapped[str] = mapped_column(String(64), unique=True)
    owner: Mapped[str] = mapped_column(String(64))
    purpose: Mapped[str] = mapped_column(String(30))
    policy: Mapped[str] = mapped_column(String(64))
    created: Mapped[float] = mapped_column(Float)
