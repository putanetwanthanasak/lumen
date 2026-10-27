"""Errors that carry a machine-readable code (Session 13 on): the body is
{"detail": {"code": ..., "message": ...}}. Older errors keep a plain string detail,
so no existing client sees a new shape."""

from fastapi import HTTPException


def coded(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})
