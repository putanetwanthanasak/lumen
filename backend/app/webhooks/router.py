"""POST /webhooks/bnpl (04 sections 5 and 6).

Order matters: size limit, then signature over the raw bytes, then schema, then one
transaction. Nothing is written unless all three checks pass.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import SecretStr, ValidationError
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import parse_event
from app.webhooks.processor import Outcome, process_event
from app.webhooks.signature import SignatureError, get_now, get_vendor_secrets, verify

MAX_BODY_BYTES = 64 * 1024

# 04 section 5.4. Each outcome maps to one fixed response.
RESPONSES: dict[Outcome, tuple[int, dict[str, Any]]] = {
    Outcome.PROCESSED: (200, {"status": "processed"}),
    Outcome.DUPLICATE: (200, {"status": "duplicate"}),  # 200 so the sender stops retrying
    Outcome.PENDING_PARENT: (202, {"status": "pending_parent"}),
    Outcome.CONFLICT: (409, {"detail": "event_id reused with different payload"}),
    Outcome.CONTRACT_CONFLICT: (409, {"detail": "contract_id reused with different contract"}),
    # Stored and audited but not applied (OR-05, INV-6, user mismatch). A resend gets
    # this same answer again (L59 1).
    Outcome.REJECTED: (409, {"detail": "event conflicts with the installment"}),
}

router = APIRouter()


@dataclass(frozen=True)
class VerifiedRequest:
    vendor: str
    body: bytes


async def _read_body(request: Request) -> bytes:
    # Stream with a cap instead of trusting Content-Length, which a sender can omit.
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="payload too large")
    return bytes(body)


async def verified_request(
    request: Request,
    secrets: Annotated[Mapping[str, SecretStr | None], Depends(get_vendor_secrets)],
    now: Annotated[int, Depends(get_now)],
) -> VerifiedRequest:
    body = await _read_body(request)
    try:
        vendor = verify(
            secrets=secrets,
            vendor=request.headers.get("X-Vendor-Id"),
            timestamp=request.headers.get("X-Timestamp"),
            signature=request.headers.get("X-Signature"),
            body=body,
            now=now,
        )
    except SignatureError:
        # One message for every failure: the client learns nothing about which check failed.
        raise HTTPException(status_code=401, detail="unauthorized") from None
    return VerifiedRequest(vendor=vendor, body=body)


@router.post("/webhooks/bnpl")
def receive_webhook(
    verified: Annotated[VerifiedRequest, Depends(verified_request)],
    session: Annotated[Session, Depends(get_session)],
) -> JSONResponse:
    try:
        event = parse_event(verified.body)
    except ValidationError as exc:
        # Review R5: type and loc only. msg can quote the caller's input back.
        errors = [{"type": e["type"], "loc": e["loc"]} for e in exc.errors(include_url=False)]
        return JSONResponse(status_code=422, content={"detail": errors})

    outcome = process_event(
        session, vendor=verified.vendor, event=event, payload=json.loads(verified.body)
    )
    session.commit()  # on any exception the session closes and rolls back
    status_code, content = RESPONSES[outcome]
    return JSONResponse(status_code=status_code, content=content)
