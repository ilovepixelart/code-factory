"""The owner's codex login: a ChatGPT login file, never shown in an answer, a log or a repr."""

import json

from pydantic import BaseModel, SecretStr

from code_factory.agents.models.connections import ConnectionDefinition, Model, Status
from code_factory.platform.errors import BadRequestError

NOT_CHATGPT = "the codex login is not a ChatGPT login"


class CodexLogin(BaseModel):
    """What a request to the codex backend is sent with, held for one request."""

    access_token: SecretStr
    account_id: str


def _token(tokens: object, name: str) -> str | None:
    value = tokens.get(name) if isinstance(tokens, dict) else None
    return value if isinstance(value, str) and value else None


def codex_login(text: str) -> CodexLogin:
    """The ChatGPT login in the text of codex's `auth.json`.

    Its `auth_mode` is `chatgpt` when it names one, and its `tokens` hold an access token and an
    account id. The refusal never names a token.
    """
    try:
        file = json.loads(text)
    except ValueError:
        msg = "the codex login file does not read as JSON"
        raise BadRequestError(msg) from None
    if not isinstance(file, dict):
        msg = "the codex login file does not read as JSON"
        raise BadRequestError(msg)
    mode = file.get("auth_mode")
    if isinstance(mode, str) and mode != "chatgpt":
        raise BadRequestError(NOT_CHATGPT)
    access, account = (
        _token(file.get("tokens"), "access_token"),
        _token(file.get("tokens"), "account_id"),
    )
    if access is None or account is None:
        raise BadRequestError(NOT_CHATGPT)
    return CodexLogin(access_token=SecretStr(access), account_id=account)


def login_problem(file: str, text: str | None) -> str | None:
    """Why the login in `text`, the content of the file at `file`, is not one a run can use."""
    if text is None:
        return f"no codex login at {file}: run `codex` once on this machine"
    try:
        codex_login(text)
    except BadRequestError as why:
        return str(why)
    return None


def login_status(connection: ConnectionDefinition, file: str, text: str | None) -> Status:
    """The status of a codex-login connection: it answers when the file is a ChatGPT login.

    Its address is never asked: only the key broker sends the login there, one request per run.
    """
    problem = login_problem(file, text)
    return Status(name=connection.name, answers=problem is None, problem=problem or "")


def login_reach(checked: Status | None) -> str:
    """What a check says when only the login's status is known."""
    return "answers" if checked is not None and checked.answers else "no usable codex login"


def catalog_models(body: str) -> list[Model] | None:
    """The picker-visible models from the authenticated Codex catalog."""
    try:
        payload = json.loads(body)
    except ValueError:
        return None
    rows = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return None
    return [
        Model(id=model["slug"])
        for model in rows
        if isinstance(model, dict)
        and model.get("visibility") == "list"
        and isinstance(model.get("slug"), str)
        and model["slug"]
    ]
