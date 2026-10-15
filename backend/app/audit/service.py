"""Append-only audit log (04 section 4.7). The DB trigger rejects UPDATE/DELETE."""

from typing import Any

from sqlalchemy.orm import Session

from app.models import Actor, AuditLog


def record(
    session: Session,
    *,
    actor: Actor,
    action: str,
    user_id: str | None,
    ref_type: str,
    ref_id: str,
    detail: dict[str, Any],
) -> None:
    """Add one entry to the caller's transaction; it commits or rolls back with it."""
    session.add(
        AuditLog(
            actor=actor,
            action=action,
            user_id=user_id,
            ref_type=ref_type,
            ref_id=ref_id,
            detail=detail,
        )
    )
    session.flush()
