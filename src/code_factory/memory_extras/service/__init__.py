"""The memory-extras module's public API.

Reads (`page`, `knowledge`, `rules_for`, `applicable`, `pairs`, `proposals`, `review_queue`),
delivery (`deliver`), the owner's writes (`add`, `edit`, `retire`, `merge`, `approve`, `dismiss`,
`restore`) and the checks an entry meets on its way in (`admit`, `paired`).
"""

from code_factory.memory_extras.service.writes import WritesMixin


class MemoryExtrasService(WritesMixin):
    """Everything about a memory entry beyond storing it."""


__all__ = ["MemoryExtrasService"]
