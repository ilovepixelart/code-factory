"""Error answers for tools: a domain error is its sentence, anything else is masked.

FastMCP raises `ToolError` for every tool failure, masking the text of an unexpected exception
(`mask_error_details=True`) and chaining the original as the cause. A `CodeFactoryError` is
written to be read by the person (or model) that caused it, so it is unmasked here and carries
the same sentence the HTTP API gives. Arguments outside a tool's input schema are refused before
it runs, and the refusal names each argument and why instead of pydantic's report.
"""

from typing import override

from fastmcp.exceptions import ToolError
from fastmcp.exceptions import ValidationError as ArgumentsError
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools import ToolResult
from mcp import types
from pydantic import ValidationError

from code_factory.platform.errors import CodeFactoryError


def _where(location: tuple[int | str, ...]) -> str:
    return ".".join(str(part) for part in location) or "arguments"


def arguments_sentence(error: ValidationError) -> str:
    """Each refused argument and why, then what to do: one sentence the model can act on."""
    problems = "; ".join(
        f"{_where(e['loc'])} {e['msg'][:1].lower()}{e['msg'][1:]}" for e in error.errors()
    )
    return f"bad arguments: {problems}. Call again within the tool's input schema."


class DomainErrors(Middleware):
    """Turns a masked `CodeFactoryError` back into a `ToolError` with its own sentence."""

    @override
    async def on_call_tool(
        self,
        context: MiddlewareContext[types.CallToolRequestParams],
        call_next: CallNext[types.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        """Call the tool; a domain error that FastMCP masked is raised with its sentence."""
        try:
            return await call_next(context)
        except ArgumentsError as error:
            cause = error.__cause__
            if isinstance(cause, ValidationError):
                raise ToolError(arguments_sentence(cause)) from cause
            raise
        except ToolError as error:
            cause = error.__cause__
            if isinstance(cause, CodeFactoryError):
                raise ToolError(str(cause)) from cause
            raise
