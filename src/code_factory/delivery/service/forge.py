"""What the git and checks modules ask of delivery: the forge, the push screen, commit statuses."""

import re

from code_factory.delivery.service.shipping import ShippingMixin
from code_factory.git.models import PullRef
from code_factory.platform.errors import ConflictError, UnavailableError

_NUMBER = re.compile(r"/pull/(\d+)$")
# A full commit id: it goes into the statuses path, so nothing else may.
_COMMIT = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


class DeliveryForge(ShippingMixin):
    """`ForgePort` and `ScreenPort` of the git module, over gh and the push screen."""

    async def open_pull(
        self, repository: str, *, branch: str, head: str, base: str, title: str
    ) -> PullRef:
        """The open pull request of `branch` into `base` at `head`, created when there is none."""
        found = await self._gh_json(
            repository, ["pr", "view", branch, "--json", "url,number,headRefOid,baseRefName,state"]
        )
        if isinstance(found, dict) and found.get("state") == "OPEN":
            if found.get("headRefOid") != head:
                msg = f"the open pull request {found.get('url')} holds another head"
                raise ConflictError(msg)
            if found.get("baseRefName") != base:
                msg = f"the open pull request does not target {base}"
                raise ConflictError(msg)
            url = str(found["url"])
            return PullRef(number=int(found["number"]), url=url)
        answer = await self._gh_in(
            repository,
            ["pr", "create", "--head", branch, "--base", base, "--title", title, "--body", title],
        )
        if not answer.ok:
            msg = f"GitHub did not open the pull request: {answer.reason}"
            raise UnavailableError(msg)
        url = answer.stdout.strip().splitlines()[-1]
        found_number = _NUMBER.search(url)
        return PullRef(number=int(found_number.group(1)) if found_number else 0, url=url)

    async def held(self, repository: str, branch: str, base: str, new: str) -> str | None:
        """Why a push of `new` onto `base` is held by the screen, or `None`."""
        return await self._screen(repository, branch, base, new)

    async def post_status(
        self, repository: str, commit: str, state: str, context: str, description: str
    ) -> bool:
        """Post a commit status of `commit`; whether GitHub took it."""
        if _COMMIT.fullmatch(commit) is None:
            return False
        answer = await self._gh_in(
            repository,
            [
                "api", "--method", "POST", f"repos/{{owner}}/{{repo}}/statuses/{commit}",
                "-f", f"state={state}", "-f", f"context={context}",
                "-f", f"description={description}",
            ],
        )  # fmt: skip
        return answer.ok
