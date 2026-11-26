"""What the git and checks modules ask of delivery: the forge, the push screen, commit statuses."""

import json
import re
from pathlib import Path

from code_factory.delivery.adapters.gh import GhResult
from code_factory.delivery.service.shipping import ShippingMixin
from code_factory.git.models import PullRef
from code_factory.platform.errors import ConflictError, UnavailableError

_NUMBER = re.compile(r"/pull/(\d+)$")
# A full commit id: it goes into the statuses path, so nothing else may.
_COMMIT = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


class DeliveryForge(ShippingMixin):
    """`ForgePort` and `ScreenPort` of the git module, over gh and the push screen."""

    _where: dict[str, str] | None = None

    def _repository_of(self, url: str) -> str | None:
        return (self._where or {}).get(url)

    async def _gh_for(self, url: str, argv: list[str]) -> GhResult:
        repository = self._repository_of(url)
        if repository is not None:
            return await self._gh_in(repository, argv)
        return await self._gh.run(Path.home(), argv)

    async def open_pull(
        self, repository: str, *, branch: str, head: str, base: str, title: str
    ) -> PullRef:
        """The open pull request of `branch` into `base` at `head`, created when there is none."""
        found = await self._gh_json(
            repository, ["pr", "view", branch, "--json", "url,number,headRefOid,state"]
        )
        if isinstance(found, dict) and found.get("state") == "OPEN":
            if found.get("headRefOid") != head:
                msg = f"the open pull request {found.get('url')} holds another head"
                raise ConflictError(msg)
            return self._remember(repository, str(found["url"]))
        answer = await self._gh_in(
            repository,
            ["pr", "create", "--head", branch, "--base", base, "--title", title, "--body", title],
        )
        if not answer.ok:
            msg = f"GitHub did not open the pull request: {answer.reason}"
            raise UnavailableError(msg)
        return self._remember(repository, answer.stdout.strip().splitlines()[-1])

    def _remember(self, repository: str, url: str) -> PullRef:
        self._where = {**(self._where or {}), url: repository}
        found = _NUMBER.search(url)
        return PullRef(number=int(found.group(1)) if found else 0, url=url)

    async def pull_state(self, ref: PullRef) -> str:
        """GitHub's `mergeStateStatus` of the pull request, '' when unread."""
        answer = await self._gh_for(ref.url, ["pr", "view", ref.url, "--json", "mergeStateStatus"])
        if not answer.ok:
            return ""
        try:
            return str(json.loads(answer.stdout).get("mergeStateStatus") or "")
        except json.JSONDecodeError, AttributeError:
            return ""

    def is_clean(self, state: str) -> bool:
        """Only `CLEAN` merges."""
        return state == "CLEAN"

    async def merge(self, ref: PullRef, head: str) -> None:
        """Merge at exactly `head`; `ConflictError` with GitHub's words when it refuses."""
        argv = ["pr", "merge", ref.url, "--merge", "--match-head-commit", head]
        answer = await self._gh_for(ref.url, argv)
        if not answer.ok:
            msg = f"GitHub refused the merge: {answer.reason}"
            raise ConflictError(msg)

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
