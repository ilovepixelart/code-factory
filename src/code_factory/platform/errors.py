"""Errors the application raises on purpose.

Each message is the sentence shown to the person, so it names what is wrong and, where there is
one, the command that repairs it. The HTTP status of each class is decided in `platform.web.errors`.
"""


class CodeFactoryError(Exception):
    """Base of every error raised on purpose; `str(error)` is a complete sentence."""


class BadRequestError(CodeFactoryError):
    """The request is well formed but asks for something that cannot be done."""


class NotFoundError(CodeFactoryError):
    """A named thing does not exist."""


class ConflictError(CodeFactoryError):
    """The request conflicts with the current state."""


class PreconditionFailedError(CodeFactoryError):
    """The thing changed since the caller read it (a stale `If-Match`)."""


class GoneError(CodeFactoryError):
    """The thing existed and is no longer there (an expired or used undo)."""


class ForbiddenError(CodeFactoryError):
    """The caller is not allowed to do this; the sentence says what it may do instead."""


class UnavailableError(CodeFactoryError):
    """A dependency the request needs is not available right now."""


class SettingsError(CodeFactoryError):
    """A setting is missing or invalid."""


class DatabaseUnavailableError(UnavailableError):
    """The database cannot be reached."""


class DatabaseBusyError(UnavailableError):
    """The database answers, but a lock or load keeps it from finishing the work in time."""


class SchemaMismatchError(CodeFactoryError):
    """The database schema or data format is not the one this build reads."""


class MigrationsNotFoundError(CodeFactoryError):
    """The Alembic configuration is not next to this checkout."""
