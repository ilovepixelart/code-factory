"""Whether the process can do its work: today, whether the database answers."""

from code_factory.platform.db import DATABASE_ERRORS, AsyncEngine, ping
from code_factory.platform.errors import UnavailableError


class ReadinessService:
    """Pings the database within a deadline."""

    def __init__(self, engine: AsyncEngine, timeout_s: float) -> None:
        self._engine = engine
        self._timeout_s = timeout_s

    async def check(self) -> None:
        """Return when the database answers; raise `UnavailableError` with the reason if not."""
        try:
            await ping(self._engine, self._timeout_s)
        except TimeoutError:
            msg = f"the database did not answer within {self._timeout_s:g} s"
            raise UnavailableError(msg) from None
        except DATABASE_ERRORS as error:
            msg = f"the database is not reachable ({type(error).__name__})"
            raise UnavailableError(msg) from error
