"""A ticket's id as the team module names it, `CF-<n>`, and the number its tables hold."""

from code_factory.platform.errors import BadRequestError

PREFIX = "CF-"


def claim_ticket(number: int) -> str:
    """The id a person reads, `CF-<n>`."""
    return f"{PREFIX}{number}"


def claim_number(ticket_id: str) -> int:
    """The number of an id `CF-<n>` written as `claim_ticket` writes it; anything else is refused.

    `CF-0001` is refused, not read as 1: claims are keyed by the written id, so a second spelling
    would miss a held claim.
    """
    digits = ticket_id.removeprefix(PREFIX)
    if (
        digits == ticket_id
        or not (digits.isascii() and digits.isdigit())
        or digits != str(int(digits))
        or int(digits) == 0
    ):
        msg = f"{ticket_id!r} is not a ticket id CF-<n>: write CF and a number from 1, as in CF-12"
        raise BadRequestError(msg)
    return int(digits)
