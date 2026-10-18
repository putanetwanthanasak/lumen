"""End-user identification for the app API (04 section 9).

The prototype has no end-user auth: the caller names the user in the X-Demo-User
header, which 04 marks as demo-only. Anyone who can reach the API can act as any
user. A deployment needs real auth here before anything else.
"""

from typing import Annotated

from fastapi import Header, HTTPException
from pydantic import TypeAdapter, ValidationError

from app.schemas import Id

_ID: TypeAdapter[str] = TypeAdapter(Id)


def demo_user(x_demo_user: Annotated[str | None, Header()] = None) -> str:
    """The user_ref the platform uses for this user. 401 if missing or malformed."""
    try:
        return _ID.validate_python(x_demo_user, strict=True)
    except ValidationError:
        raise HTTPException(status_code=401, detail="unauthorized") from None
