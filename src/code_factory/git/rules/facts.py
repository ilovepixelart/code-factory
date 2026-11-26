"""What git knows of a repository: tips, merged branches, the log of the default branch."""

from code_factory.git.models import MERGE_LOG_LIMIT, GitFacts, RefTips, StackBase

_LOCAL = "refs/heads/"
_REMOTE = "refs/remotes/origin/"


def parse_branch_refs(text: str) -> RefTips:
    """Read `%(refname) %(objectname)` lines of the local branches and origin's."""
    tips: dict[str, str] = {}
    local: set[str] = set()
    remote: set[str] = set()
    for line in text.splitlines():
        name, _, sha = line.partition(" ")
        if name.startswith(_LOCAL):
            local.add(name.removeprefix(_LOCAL))
            tips[name.removeprefix(_LOCAL)] = sha
        elif name.startswith(_REMOTE) and name != f"{_REMOTE}HEAD":
            remote.add(name.removeprefix(_REMOTE))
            tips[f"origin/{name.removeprefix(_REMOTE)}"] = sha
    return RefTips(local=frozenset(local), remote=frozenset(remote), tips=tips)


def default_branch(symbolic_ref: str | None, local: frozenset[str]) -> str:
    """The default branch: origin's `HEAD` target, else a local `main` or `master`, else `main`."""
    head = (symbolic_ref or "").strip()
    if head:
        return head.removeprefix("origin/")
    return next((name for name in ("main", "master") if name in local), "main")


def _merge_rows(text: str) -> list[tuple[str, str, str]]:
    rows = []
    for line in text.splitlines():
        fields = line.split("\t", 2)
        if len(fields) >= 2:  # noqa: PLR2004  # hash and parents are required, the subject is not
            rows.append((fields[0], fields[1], fields[2] if len(fields) > 2 else ""))  # noqa: PLR2004
    return rows


def _first_parents(listing: str) -> dict[str, str | None]:
    history: dict[str, str | None] = {}
    for line in listing.splitlines():
        words = line.split()
        if words:
            history[words[0]] = words[1] if len(words) > 1 else None
    return history


def _first_parent_line(history: dict[str, str | None], tip: str) -> list[str]:
    line: list[str] = []
    seen: set[str] = set()
    at: str | None = tip if tip in history else None
    while at is not None and at not in seen:
        seen.add(at)
        line.append(at)
        at = history.get(at)
    return line


def _merged_into(rest: str) -> str | None:
    quoted = rest.removeprefix("branch '") if rest.startswith("branch '") else None
    if quoted is not None and "' into " in quoted:
        return quoted.partition("' into ")[0]
    return rest.partition(" into ")[0] if " into " in rest else None


def merged_heads(log: str) -> frozenset[str]:
    """The branches the subjects of `log` name as merged.

    Git's title for merging one into another (`Merge <branch> into ...`, `Merge branch '<branch>'
    into ...`) and a pull request's head (`Merge pull request #<n> from <owner>/<branch>`).
    """
    heads: set[str] = set()
    for subject in log.splitlines():
        if not subject.startswith("Merge "):
            continue
        rest = subject.removeprefix("Merge ")
        if (merged := _merged_into(rest)) is not None:
            heads.add(merged)
        if rest.startswith("pull request #") and " from " in rest:
            head = rest.partition(" from ")[2]
            heads.add(head)
            if "/" in head:
                heads.add(head.partition("/")[2])
    return frozenset(heads)


def merged_branch(subject: str) -> str | None:
    """The branch a merge subject says it merged, without its owner."""
    if subject.startswith("Merge pull request #") and " from " in subject:
        head = subject.partition(" from ")[2]
        if "/" in head:
            return head.partition("/")[2]
    if subject.startswith("Merge branch '") and "'" in subject[len("Merge branch '") :]:
        return subject[len("Merge branch '") :].partition("'")[0]
    return None


def _landed_subjects(rows: list[tuple[str, str, str]], merges: list[tuple[str, str, str]]) -> str:
    """Subjects of the newest commits, followed by the older merges."""
    read = {commit for commit, _, _ in rows}
    subjects = [subject for _, _, subject in rows]
    subjects.extend(subject for commit, _, subject in merges if commit not in read)
    return "\n".join(subjects)


def build_facts(  # noqa: PLR0913  # the five reads of one snapshot and whether all succeeded
    refs: RefTips,
    symbolic: str | None,
    merges: str,
    line: str,
    log: str,
    *,
    ok: bool,
) -> GitFacts:
    """Facts from the five reads: refs, origin's `HEAD`, the merges, the parents and the log.

    `merged_in` holds the later parents of merge commits that are not on the default line, and the
    tips that reached the default branch inside a later branch (a stacked ticket).
    """
    default = default_branch(symbolic, refs.local)
    branches = [default] + ([f"origin/{default}"] if default in refs.remote else [])
    merge_rows = _merge_rows(merges)
    history = _first_parents(line)
    own_line = {
        commit
        for branch in branches
        if (tip := refs.tips.get(branch)) is not None
        for commit in _first_parent_line(history, tip)
    }
    reached = {tip for tip in refs.tips.values() if tip in history and tip not in own_line}
    merged_in = {
        parent
        for _, parents, _ in merge_rows
        for parent in parents.split()[1:]
        if parent not in own_line
    } | reached
    recent = _merge_rows(log)
    landed = _landed_subjects(recent, merge_rows)
    return GitFacts(
        default_branch=default,
        local=refs.local,
        remote=refs.remote,
        tips=refs.tips,
        merged_in=frozenset(merged_in),
        log=landed,
        merged_heads=merged_heads(landed),
        main_line=frozenset(own_line),
        main_subjects={commit: subject for commit, _, subject in recent if commit in own_line},
        known=ok,
    )


def _own_tips(branch: str, facts: GitFacts) -> list[str]:
    tips = (facts.tips.get(branch), facts.tips.get(f"origin/{branch}"))
    return [tip for tip in tips if tip is not None and tip != ""]


def branch_merged(branch: str, facts: GitFacts) -> bool | None:
    """Whether a local or remote tip of `branch` is merged; `None` with no tip or unknown facts."""
    if not facts.known:
        return None
    tips = _own_tips(branch, facts)
    return any(tip in facts.merged_in for tip in tips) if tips else None


def is_merged(ticket_id: str, branch: str, facts: GitFacts) -> bool:
    """Whether a ticket's work reached the default branch.

    With a local or remote tip only that tip counts. A branch with no tip falls back to the log: a
    merge subject naming the branch, or a line starting with the ticket id. No branch, or unknown
    facts, is never merged.
    """
    if not branch or not facts.known:
        return False
    by_tip = branch_merged(branch, facts)
    if by_tip is not None:
        return by_tip
    return branch in facts.merged_heads or any(
        line.startswith(ticket_id) for line in facts.log.splitlines()
    )


def untraced(ticket_id: str, branch: str, facts: GitFacts) -> str | None:
    """Why a branch does not read as merged when no fact can say: no tip, nothing in the log."""
    traced = not facts.known or branch_merged(branch, facts) is not None
    if not branch or traced or is_merged(ticket_id, branch, facts):
        return None
    return (
        f"{branch} has no local or remote branch here, and {facts.default_branch} holds no pull "
        f"request merge of it nor, in its last {MERGE_LOG_LIMIT} commits, a commit starting with "
        f"{ticket_id} that landed work"
    )


def holds_own_commit(branch: str, facts: GitFacts) -> bool:
    """Whether `branch`, here or on origin, holds a commit the default branch does not."""
    return any(
        tip not in facts.main_line and tip not in facts.merged_in
        for tip in _own_tips(branch, facts)
    )


def base_branch(facts: GitFacts) -> str:
    """Where work forks from: origin's default branch when tracked, else the local one."""
    if facts.default_branch in facts.remote:
        return f"origin/{facts.default_branch}"
    return facts.default_branch


def base_tip(facts: GitFacts) -> str | None:
    """The commit `base_branch` names in the repository these facts were read from."""
    return facts.tips.get(base_branch(facts)) or None


def stack_base(parent_branch: str, facts: GitFacts) -> StackBase:
    """Where a branch stacked on `parent_branch` is cut from: the local branch, else origin's."""
    cut = parent_branch if parent_branch in facts.local else f"origin/{parent_branch}"
    return StackBase(cut=cut, on_origin=parent_branch in facts.remote)
