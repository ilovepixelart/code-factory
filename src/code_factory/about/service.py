"""Name and version of the running build."""

from code_factory import PACKAGE_NAME, __version__
from code_factory.about.models import About


class AboutService:
    """Answers "what is this", for the API and the MCP server alike."""

    def about(self) -> About:
        """Name and version, read from the package metadata (the one version source)."""
        return About(name=PACKAGE_NAME, version=__version__)
