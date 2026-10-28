"""JSON request bodies and query strings for the app API, parsed the way the webhook
body is.

The body is read with a size cap and validated by a strict pydantic model. A 422
carries each error's type and loc only: msg and input can quote the caller's
input back (review R5).
"""

import re
from collections import Counter
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import HTTPException, Request
from pydantic import BaseModel, BeforeValidator, ValidationError

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
            raise _unprocessable(exc) from None

    return parse


def _unprocessable(exc: ValidationError) -> HTTPException:
    errors = [{"type": e["type"], "loc": e["loc"]} for e in exc.errors(include_url=False)]
    return HTTPException(status_code=422, detail=errors)


def query_params[M: BaseModel](model: type[M]) -> Callable[[Request], M]:
    """As json_body, for the query string: every value is a string, a key may appear
    once, and the strict model decides the rest (unknown keys are rejected)."""

    def parse(request: Request) -> M:
        items = request.query_params.multi_items()
        repeated = sorted(k for k, n in Counter(k for k, _ in items).items() if n > 1)
        if repeated:
            raise HTTPException(
                status_code=422,
                detail=[{"type": "repeated_query_param", "loc": ["query", k]} for k in repeated],
            )
        try:
            return model.model_validate(dict(items))
        except ValidationError as exc:
            raise _unprocessable(exc) from None

    return parse


# [0-9], not \d, as for money: plain ASCII digits only, so "+6", "6.0" and "๖" fail.
COUNT_PATTERN = re.compile(r"[0-9]{1,4}")


def _query_int(value: object) -> int:
    if not isinstance(value, str) or COUNT_PATTERN.fullmatch(value) is None:
        raise ValueError("must be a whole number such as 6")
    return int(value)


QueryInt = Annotated[int, BeforeValidator(_query_int)]
