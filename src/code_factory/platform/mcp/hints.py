"""The four annotation hints every tool states (the specification's defaults are pessimistic)."""

from mcp.types import ToolAnnotations

READ_ONLY = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
# Adds something and changes nothing that exists: calling twice adds twice.
APPENDS = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False
)
# Overwrites what exists; the same call twice leaves the same state.
SETS = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False
)
# Overwrites what exists; a second call differs (a version moves, text is added).
REPLACES = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False
)
