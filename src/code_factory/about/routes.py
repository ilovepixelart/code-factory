"""What is running."""

from typing import Annotated

from fastapi import APIRouter, Depends

from code_factory.about.models import About
from code_factory.about.service import AboutService
from code_factory.platform.web.dependencies import service_of

router = APIRouter(prefix="/api", tags=["about"])

AboutServiceDep = Annotated[AboutService, Depends(service_of(AboutService))]


@router.get("/about", summary="Name and version")
async def about(service: AboutServiceDep) -> About:
    """The name and version of this build."""
    return service.about()
