"""The ticket routes: talk and review, and files (writes are the ticket-writes module's)."""

from fastapi import APIRouter

from code_factory.tickets.routes import files, talk

router = APIRouter()
for part in (talk.router, files.router):
    router.include_router(part)
