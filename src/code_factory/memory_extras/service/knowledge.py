"""The knowledge search: memory entries, ticket documents and the repository's documents."""

from code_factory.memory_extras.models import Doc, Found
from code_factory.memory_extras.rules import (
    address,
    entry_text,
    plain_snippet,
    rank,
    snippet,
    words_of,
)
from code_factory.memory_extras.service.recall import RecallMixin

# Ticket documents holding every word that are ranked: the count of results is exact below it.
TICKET_DOCUMENTS = 500


class KnowledgeMixin(RecallMixin):
    """Search over what a repository knows."""

    async def knowledge(self, repository: str, query: str, limit: int) -> tuple[list[Found], int]:
        """Up to `limit` ranked results, and how many documents held every word of the query.

        The ranking is BM25 over whole words; a ticket document counts as held only among the
        first 500 that do. An empty query answers `([], 0)`.
        """
        words = words_of(query)
        if not words:
            return [], 0
        root = await self._root(repository)
        entries = await self._memory.list_entries(repository)
        corpus = [Doc(path=f"memory/{e.id}", text=entry_text(e)) for e in entries]
        corpus += await self._files.knowledge_files(repository, root)
        found = await self._tickets.search_documents(repository, words, TICKET_DOCUMENTS)
        corpus += [Doc(path=f"tickets/{d.ticket_id}/{d.name}.md", text=d.text) for d in found]
        ranked = rank(corpus, words)
        web = await self._origin.web(repository) if ranked else ""
        return [
            Found(
                repository=repository,
                path=doc.path,
                snippet=plain_snippet(snippet(doc.text, words)),
                open=address(repository, doc.path, web),
            )
            for doc in ranked[: max(limit, 0)]
        ], len(ranked)
