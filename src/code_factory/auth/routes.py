"""The owner's sign-in link: a one-time value becomes the session cookie."""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse, Response

from code_factory.auth.service import AuthService
from code_factory.platform.web.dependencies import service_of
from code_factory.platform.web.errors import error_response
from code_factory.platform.web.guard import OWNER_COOKIE

# Not under `/api`: the link is opened by hand, and the page behind it is the board.
router = APIRouter(include_in_schema=False)

SESSION_LIFETIME = timedelta(days=365)
SPENT = "this sign-in link is spent or unknown: run `code-factory sign-in` for a new one"
_NOT_BOARD_PAGES = ("/api/", "/owner/", "/mcp")

AuthDep = Annotated[AuthService, Depends(service_of(AuthService))]


def landing(asked: str) -> str:
    """Where the sign-in lands: `asked` when it is a path of the board, else `/`."""
    local = asked.startswith("/") and not asked.startswith("//") and "\\" not in asked
    if not local or asked.startswith(_NOT_BOARD_PAGES) or not asked.isprintable():
        return "/"
    return asked


@router.get("/owner/{nonce}")
async def sign_in(nonce: str, auth: AuthDep, to: str = "") -> Response:
    """Spend the link, set the owner's cookie and open the board."""
    session = await auth.redeem_sign_in_nonce(nonce, lifetime=SESSION_LIFETIME)
    if session is None:
        return error_response(403, SPENT)
    response = RedirectResponse(landing(to), status_code=303)
    response.set_cookie(
        OWNER_COOKIE,
        session.token.get_secret_value(),
        max_age=int(SESSION_LIFETIME.total_seconds()),
        httponly=True,
        samesite="strict",
        path="/",
    )
    return response
