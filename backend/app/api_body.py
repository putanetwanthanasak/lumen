"""JSON request bodies for the app API, parsed the way the webhook body is.

The body is read with a size cap and validated by a strict pydantic model. A 422
carries each error's type and loc only: msg and input can quote the caller's
input back (review R5).
"""

from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request
from pydantic import BaseModel, ValidationError

MAX_BODY_BYTES = 64 * 1024


async def _read_body(request: Request) -> bytes:
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="payload too large")
    return bytes(body)


def json_body[M: BaseModel](model: type[M]) -> Callable[[Request], Awaitable[M]]:
    """A FastAPI dependency that parses the request body into `model`."""

    async def parse(request: Request) -> M:
        body = await _read_body(request)
        try:
            return model.model_validate_json(body)
        except ValidationError as exc:
            errors = [{"type": e["type"], "loc": e["loc"]} for e in exc.errors(include_url=False)]
            raise HTTPException(status_code=422, detail=errors) from None

    return parse
