"""audit_log is append-only: a trigger rejects UPDATE, DELETE, and TRUNCATE."""

import pytest
from sqlalchemy import delete, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models import AuditLog
from tests.db.factories import audit_log

pytestmark = pytest.mark.db

INSUFFICIENT_PRIVILEGE = "42501"


def _insert(session: Session) -> AuditLog:
    row = audit_log()
    session.add(row)
    session.flush()
    return row


def _assert_append_only_error(exc: pytest.ExceptionInfo[DBAPIError], op: str) -> None:
    assert exc.value.orig is not None
    assert exc.value.orig.sqlstate == INSUFFICIENT_PRIVILEGE  # type: ignore[attr-defined]
    assert f"audit_log is append-only: {op} rejected" in str(exc.value.orig)


def test_audit_log_insert_allowed(db_session: Session) -> None:
    row = _insert(db_session)
    db_session.refresh(row)
    assert row.id > 0
    assert row.created_at is not None


def test_audit_log_update_rejected(db_session: Session) -> None:
    row = _insert(db_session)
    with pytest.raises(DBAPIError) as exc:
        db_session.execute(update(AuditLog).where(AuditLog.id == row.id).values(action="edited"))
    _assert_append_only_error(exc, "UPDATE")


def test_audit_log_orm_update_rejected(db_session: Session) -> None:
    row = _insert(db_session)
    row.detail = {"tampered": True}
    with pytest.raises(DBAPIError) as exc:
        db_session.flush()
    _assert_append_only_error(exc, "UPDATE")


def test_audit_log_delete_rejected(db_session: Session) -> None:
    row = _insert(db_session)
    with pytest.raises(DBAPIError) as exc:
        db_session.execute(delete(AuditLog).where(AuditLog.id == row.id))
    _assert_append_only_error(exc, "DELETE")


def test_audit_log_truncate_rejected(db_session: Session) -> None:
    _insert(db_session)
    with pytest.raises(DBAPIError) as exc:
        db_session.execute(text("TRUNCATE audit_log"))
    _assert_append_only_error(exc, "TRUNCATE")


def test_audit_log_actor_check(db_session: Session) -> None:
    db_session.add(audit_log(actor="admin"))
    with pytest.raises(DBAPIError) as exc:
        db_session.flush()
    assert exc.value.orig.diag.constraint_name == "ck_audit_log_actor_valid"  # type: ignore[union-attr]
