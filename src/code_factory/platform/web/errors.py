"""Error answers: always an RFC 9457 problem, with the status the error calls for.

`type` is `about:blank` (the status says what kind of failure it is) and `title` is the status's
standard phrase; `detail` is the sentence naming what is wrong and how to repair it. Clients branch
on `type` and `status`, never on the wording of `detail`.
"""

import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from code_factory.platform.errors import (
    BadRequestError,
    CodeFactoryError,
    ConflictError,
    ForbiddenError,
    GoneError,
    NotFoundError,
    PreconditionFailedError,
    UnavailableError,
)

logger = logging.getLogger(__name__)

_STATUS: dict[type[CodeFactoryError], int] = {
    BadRequestError: 400,
    ForbiddenError: 403,
    NotFoundError: 404,
    ConflictError: 409,
    GoneError: 410,
    PreconditionFailedError: 412,
    UnavailableError: 503,
}
INTERNAL_ERROR_SENTENCE = "internal error"


def status_for(error: CodeFactoryError) -> int:
    """Status of the nearest mapped class in the error's ancestry; 500 when none is mapped."""
    for cls in type(error).__mro__:
        if cls in _STATUS:
            return _STATUS[cls]  # ty: ignore[invalid-argument-type]
    return 500


PROBLEM_TYPE = "application/problem+json"


class Problem(BaseModel):
    """Every error answer (RFC 9457): what kind, its status, and the sentence that says why."""

    type: str
    title: str
    status: int
    detail: str


def problem_doc(description: str) -> dict[str, Any]:
    """An error response as a route documents it: the problem schema under its media type."""
    schema = {"$ref": "#/components/schemas/Problem"}
    return {
        "model": Problem,
        "description": description,
        "content": {PROBLEM_TYPE: {"schema": schema}},
    }


def problem(status: int, sentence: str, errors: Sequence[Mapping[str, str]] = ()) -> dict[str, Any]:
    """The problem body: `about:blank`, the status phrase, the status, the sentence, `errors`."""
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": HTTPStatus(status).phrase,
        "status": status,
        "detail": sentence,
    }
    if errors:
        body["errors"] = [dict(e) for e in errors]
    return body


def error_response(
    status: int,
    sentence: str,
    headers: Mapping[str, str] | None = None,
    errors: Sequence[Mapping[str, str]] = (),
) -> JSONResponse:
    """The one error answer; `headers` are the ones the status requires (`Allow`, ...)."""
    return JSONResponse(
        problem(status, sentence, errors),
        status_code=status,
        headers=headers,
        media_type=PROBLEM_TYPE,
    )


def internal_error_response() -> JSONResponse:
    """The answer to a failure nobody expected: nothing about the cause."""
    return error_response(500, INTERNAL_ERROR_SENTENCE)


Handler = Callable[[Request, Exception], Awaitable[JSONResponse]]
# Coroutines: Starlette awaits a coroutine handler on the loop and sends a plain one to a thread.
_HANDLERS: dict[type[Exception], Handler] = {}


def _handles(error: type[Exception]) -> Callable[[Handler], Handler]:
    """Register the decorated handler as the answer to `error` and its subclasses."""

    def register(handler: Handler) -> Handler:
        _HANDLERS[error] = handler
        return handler

    return register


@_handles(CodeFactoryError)
async def _domain_handler(_request: Request, error: Exception) -> JSONResponse:
    if not isinstance(
        error, CodeFactoryError
    ):  # pragma: no cover  # registered for this class only
        raise error
    return error_response(status_for(error), str(error))


@_handles(StarletteHTTPException)
async def _http_handler(_request: Request, error: Exception) -> JSONResponse:
    if not isinstance(error, StarletteHTTPException):  # pragma: no cover
        raise error
    sentence = "not found" if error.status_code == 404 else str(error.detail).lower()  # noqa: PLR2004
    return error_response(error.status_code, sentence, error.headers)


@_handles(RequestValidationError)
async def _validation_handler(_request: Request, error: Exception) -> JSONResponse:
    if not isinstance(error, RequestValidationError):  # pragma: no cover
        raise error
    found = error.errors()
    sentences = [f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in found]
    pointers = [
        {"pointer": "/" + "/".join(str(part) for part in item["loc"]), "detail": item["msg"]}
        for item in found
    ]
    return error_response(400, "invalid request: " + "; ".join(sentences), errors=pointers)


def install_error_handlers(app: FastAPI) -> None:
    """Map the error classes to answers. Unexpected exceptions are caught by `ErrorBoundary`."""
    for cls, handler in _HANDLERS.items():
        app.add_exception_handler(cls, handler)
