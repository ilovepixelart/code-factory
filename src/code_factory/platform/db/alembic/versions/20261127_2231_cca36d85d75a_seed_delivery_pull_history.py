"""Copy known pull timestamps and recover older merges proven by delivery events."""

from collections.abc import Sequence

from alembic import op

revision: str = "cca36d85d75a"
down_revision: str | Sequence[str] | None = "3b368180bf21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        WITH events AS (
            SELECT ticket_number, url,
                   min(at) FILTER (WHERE kind = 'pull_request') AS opened_at,
                   min(at) FILTER (WHERE kind = 'merged_pull_request') AS merged_at
              FROM delivery_events
             WHERE kind IN ('pull_request', 'merged_pull_request') AND url <> ''
             GROUP BY ticket_number, url
        )
        INSERT INTO delivery_pull_history
            (url, ticket_number, repository, state, opened_at, merged_at, closed_at,
             first_review_at, changed_lines)
        SELECT p.url, p.ticket_number, p.repository,
               CASE WHEN e.merged_at IS NOT NULL OR p.merged_on_host IS NOT NULL
                    THEN 'merged' ELSE p.state END,
               COALESCE(p.created_on_host, e.opened_at, p.since),
               COALESCE(p.merged_on_host, e.merged_at,
                        CASE WHEN p.state = 'merged' THEN p.since END),
               CASE WHEN p.state = 'closed' THEN p.since END,
               p.first_review_at, p.additions + p.deletions
          FROM delivery_pulls p
          LEFT JOIN events e USING (ticket_number, url)
         WHERE p.url <> ''
        ON CONFLICT (url) DO NOTHING
    """)
    op.execute("""
        WITH events AS (
            SELECT ticket_number, url,
                   min(at) FILTER (WHERE kind = 'pull_request') AS opened_at,
                   min(at) FILTER (WHERE kind = 'merged_pull_request') AS merged_at
              FROM delivery_events
             WHERE kind IN ('pull_request', 'merged_pull_request') AND url <> ''
             GROUP BY ticket_number, url
        )
        INSERT INTO delivery_pull_history
            (url, ticket_number, repository, state, opened_at, merged_at)
        SELECT DISTINCT ON (e.url) e.url, e.ticket_number, t.repository, 'merged',
               e.opened_at, e.merged_at
          FROM events e JOIN tickets t ON t.number = e.ticket_number
         WHERE e.merged_at IS NOT NULL AND e.opened_at IS NOT NULL
         ORDER BY e.url, e.merged_at, e.ticket_number
        ON CONFLICT (url) DO NOTHING
    """)


def downgrade() -> None:
    """Leave history intact when reverting only the backfill revision."""
