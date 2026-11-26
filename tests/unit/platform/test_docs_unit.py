import json

import pytest

from repo_files import ROOT

VENDORED = ROOT / "src/code_factory/platform/web/static/docs-assets/swagger-ui"
# Swagger UI release the vendored files come from (https://www.npmjs.com/package/swagger-ui-dist).
VENDORED_VERSION = "5.35.1"


def test_the_vendored_swagger_ui_is_the_pinned_release_with_its_licence() -> None:
    package = json.loads((VENDORED / "package.json").read_text(encoding="utf-8"))
    assert (package["name"], package["version"]) == ("swagger-ui-dist", VENDORED_VERSION)
    assert package["license"] == "Apache-2.0"
    assert "Apache License" in (VENDORED / "LICENSE").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["swagger-ui-bundle.js", "swagger-ui.css"])
def test_the_vendored_files_are_present(name: str) -> None:
    assert (VENDORED / name).stat().st_size > 100_000
