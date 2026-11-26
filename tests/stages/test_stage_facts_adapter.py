"""The facts source over the git module's service: one read of the repository answers every ticket,
and the board's trees say which branches a run works on."""

from code_factory.git.models import GitFacts, TreeInfo, TreeKind
from code_factory.stages.adapters import GitServiceFacts


class FakeGit:
    """What `GitService` answers: facts of a repository and the trees of its runs."""

    def __init__(self, facts: GitFacts, trees: list[TreeInfo] | None = None) -> None:
        self.facts_read = [facts]
        self.trees = trees or []
        self.failing_trees = False
        self.asked: list[str] = []

    async def facts(self, repository: str) -> GitFacts:
        self.asked.append(repository)
        return self.facts_read[0]

    async def list_trees(self, repository: str) -> list[TreeInfo]:
        del repository
        if self.failing_trees:
            msg = "git is gone"
            raise RuntimeError(msg)
        return self.trees


def tree(branch: str, *, valid: bool = True) -> TreeInfo:
    return TreeInfo(
        name=f"t-{branch}",
        kind=TreeKind.CLONE,
        ticket_id="CF-2",
        branch=branch,
        path="/x",
        valid=valid,
    )


FACTS = GitFacts(
    default_branch="main",
    local=frozenset({"main", "feat/CF-1"}),
    remote=frozenset({"main"}),
    tips={"main": "M", "feat/CF-1": "A", "origin/main": "M"},
    merged_in=frozenset(),
    log="",
)


async def test_each_ticket_is_answered_from_one_read_of_its_repository() -> None:
    git = FakeGit(FACTS)

    found = await GitServiceFacts(git).read("sample", {"CF-1": "feat/CF-1", "CF-3": ""})

    assert git.asked == ["sample"]
    assert (found["CF-1"].local, found["CF-1"].has_commits, found["CF-1"].head) == (True, True, "A")
    assert (found["CF-3"].local, found["CF-3"].known) == (False, True)


async def test_a_branch_a_valid_board_tree_works_on_is_in_a_worktree() -> None:
    git = FakeGit(FACTS, [tree("feat/CF-2"), tree("feat/CF-5", valid=False), tree("")])

    found = await GitServiceFacts(git).read(
        "sample", {"CF-2": "feat/CF-2", "CF-5": "feat/CF-5", "CF-1": "feat/CF-1"}
    )

    assert [found[t].in_worktree for t in ("CF-2", "CF-5", "CF-1")] == [True, False, False]


async def test_trees_that_cannot_be_listed_leave_the_facts_without_worktrees() -> None:
    git = FakeGit(FACTS, [tree("feat/CF-2")])
    git.failing_trees = True

    found = await GitServiceFacts(git).read("sample", {"CF-2": "feat/CF-2"})

    assert not found["CF-2"].in_worktree
    assert found["CF-2"].known


async def test_facts_git_could_not_read_make_every_ticket_unknown() -> None:
    unknown = FACTS.model_copy(update={"known": False})

    found = await GitServiceFacts(FakeGit(unknown)).read("sample", {"CF-1": "feat/CF-1"})

    assert not found["CF-1"].known
