"""Database models for TestPulse Omni."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TestHistory(Base):
    """One persisted execution of any of the six test engines."""

    __tablename__ = "test_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    test_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    target: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, index=True
    )

    __table_args__ = (
        Index("ix_test_history_type_created", "test_type", "created_at"),
    )

    def to_dict(self, include_details: bool = True) -> dict:
        payload = {
            "id": self.id,
            "test_type": self.test_type,
            "target": self.target,
            "status": self.status,
            "summary": self.summary,
            "score": self.score,
            "duration_ms": self.duration_ms,
            "created_at": (
                self.created_at.isoformat()
                if self.created_at is not None
                else None
            ),
        }
        if include_details:
            payload["details"] = self.details or {}
        return payload
