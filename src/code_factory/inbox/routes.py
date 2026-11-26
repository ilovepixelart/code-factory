"""The Inbox page's reads: everything that waits on the owner, and the badge count."""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from code_factory.inbox.models import InboxCount, InboxPage
from code_factory.inbox.service import InboxService
from code_factory.platform.web.conditional import conditional_json
from code_factory.platform.web.dependencies import service_of

router = APIRouter(prefix="/api", tags=["inbox"])

InboxDep = Annotated[InboxService, Depends(service_of(InboxService))]


@router.get(
    "/inbox",
    summary="Everything that waits on the owner, by section, each oldest first",
    response_model=InboxPage,
    responses={304: {"description": "Unchanged since the tag in If-None-Match."}},
)
async def inbox(request: Request, service: InboxDep) -> Response:
    """ETag'd: the page polls it, and an unchanged inbox answers 304 to its own tag."""
    page = InboxPage.model_validate(await service.page())
    return conditional_json(request, json.dumps(page.model_dump(mode="json")))


@router.get("/inbox/count", summary="How many items wait on a reply, and the newest sentence")
async def inbox_count(service: InboxDep) -> InboxCount:
    """The badge of the navigation: zero is an answer."""
    return InboxCount.model_validate(await service.count())
