"""code-factory: a board that takes tickets from spec to merged with coding agents."""

from importlib.metadata import version

PACKAGE_NAME = "code-factory"
# The single version source is pyproject.toml; installed metadata carries it here.
__version__ = version(PACKAGE_NAME)

__all__ = ["PACKAGE_NAME", "__version__"]
