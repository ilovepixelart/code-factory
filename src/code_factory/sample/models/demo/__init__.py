"""The `demo` sample: a board in use, so every page has something to show.

Plain data. Each record goes through its module's own model and service when it is loaded, so a
value a model or a rule refuses fails the load rather than reaching a page.
"""

from code_factory.sample.models.demo.records import (
    DEMO_AGENTS,
    DEMO_ANSWERS,
    DEMO_CHECKS,
    DEMO_COMMENTS,
    DEMO_CONNECTIONS,
    DEMO_DOCUMENTS,
    DEMO_MEMORY,
    DEMO_PRICES,
    DEMO_PROPOSALS,
    DEMO_PULL_SIZES,
    DEMO_QUESTIONS,
    DEMO_RELEASES,
    DEMO_REVIEWS,
    DEMO_SCORER,
    DEMO_SESSIONS,
)
from code_factory.sample.models.demo.tickets import (
    DEMO_REPOSITORIES,
    DEMO_TICKETS,
    DemoSession,
    DemoTicket,
    Stage,
)

__all__ = [
    "DEMO_AGENTS",
    "DEMO_ANSWERS",
    "DEMO_CHECKS",
    "DEMO_COMMENTS",
    "DEMO_CONNECTIONS",
    "DEMO_DOCUMENTS",
    "DEMO_MEMORY",
    "DEMO_PRICES",
    "DEMO_PROPOSALS",
    "DEMO_PULL_SIZES",
    "DEMO_QUESTIONS",
    "DEMO_RELEASES",
    "DEMO_REPOSITORIES",
    "DEMO_REVIEWS",
    "DEMO_SCORER",
    "DEMO_SESSIONS",
    "DEMO_TICKETS",
    "DemoSession",
    "DemoTicket",
    "Stage",
]
