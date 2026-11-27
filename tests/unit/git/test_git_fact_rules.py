"""Facts, merges, merge-tree and clash rules over hand-worked histories."""

from code_factory.git.models import GitFacts
from code_factory.git.rules.facts import (
    base_branch,
    build_facts,
    default_branch,
    holds_own_commit,
    is_merged,
    parse_branch_refs,
    stack_base,
    untraced,
)
from code_factory.git.rules.merges import (
    clash,
    merged_from,
    pair_key,
    parse_merges,
    read_merge_tree,
)

# a (root) <- m (merge of feat tip f into main); feat2 is cut at a and holds nothing.
REFS = (
    "refs/heads/main m\nrefs/heads/feat f\nrefs/heads/feat2 a\n"
    "refs/remotes/origin/HEAD m\nrefs/remotes/origin/main m\n"
)
MERGES = "m\ta f\tMerge pull request #1 from owner/feat\n"
LINE = "m a f\nf a\na\n"
LOG = "m\ta f\tMerge pull request #1 from owner/feat\nf\ta\tFeature work\na\t\tStart\n"


def _facts(refs: str = REFS, *, ok: bool = True) -> GitFacts:
    return build_facts(parse_branch_refs(refs), None, MERGES, LINE, LOG, ok=ok)


def test_refs_skip_origin_head_and_key_remotes_by_origin_name() -> None:
    tips = parse_branch_refs(REFS)
    assert tips.local == {"main", "feat", "feat2"}
    assert tips.remote == {"main"}
    assert tips.tips["origin/main"] == "m"
    assert "origin/HEAD" not in tips.tips


def test_default_branch_prefers_origin_head_then_main_then_master_then_main() -> None:
    assert default_branch("origin/trunk", frozenset({"main"})) == "trunk"
    assert default_branch(None, frozenset({"master"})) == "master"
    assert default_branch(None, frozenset({"main", "master"})) == "main"
    assert default_branch(None, frozenset({"trunk"})) == "main"


def test_a_branch_merged_by_its_later_parent_is_merged_and_one_cut_from_main_is_not() -> None:
    facts = _facts()
    assert facts.merged_in == {"f"}
    assert facts.log == "Merge pull request #1 from owner/feat\nFeature work\nStart"
    assert facts.main_subjects == {"m": "Merge pull request #1 from owner/feat", "a": "Start"}
    assert is_merged("CF-1", "feat", facts)
    assert not is_merged("CF-2", "feat2", facts)
    assert not holds_own_commit("feat2", facts)
    assert (
        holds_own_commit(
            "feat",
            build_facts(parse_branch_refs(REFS + "refs/heads/x z\n"), None, "", LINE, LOG, ok=True),
        )
        is False
    )


def test_a_branch_with_no_tip_is_merged_by_a_merge_subject_or_an_id_prefix() -> None:
    refs = "refs/heads/main m\n"
    log = "m\ta f\tMerge pull request #1 from owner/gone\nx\ta\tCF-9: Add thing\n"
    facts = build_facts(
        parse_branch_refs(refs),
        None,
        "m\ta f\tMerge pull request #1 from owner/gone\n",
        LINE,
        log,
        ok=True,
    )
    assert is_merged("CF-1", "gone", facts)
    assert is_merged("CF-9", "other", facts)
    assert not is_merged("CF-3", "other", facts)


def test_nothing_is_merged_while_facts_are_unknown() -> None:
    assert not is_merged("CF-1", "feat", _facts(ok=False))


def test_untraced_names_the_branch_and_the_log_window() -> None:
    facts = build_facts(
        parse_branch_refs("refs/heads/main m\n"), None, "", LINE, "m\ta\tStart\n", ok=True
    )
    assert untraced("CF-5", "ghost", facts) == (
        "ghost has no local or remote branch here, and main holds no pull request merge of it "
        "nor, in its last 1000 commits, a commit starting with CF-5 that landed work"
    )
    assert untraced("CF-5", "", facts) is None


def test_base_branch_and_stack_base() -> None:
    facts = _facts()
    assert base_branch(facts) == "origin/main"
    assert stack_base("feat", facts).cut == "feat"
    assert not stack_base("feat", facts).on_origin
    gone = stack_base("away", facts)
    assert (gone.cut, gone.on_origin) == ("origin/away", False)


LOG_MERGES = """m3\tm2 b3\t1800\tMerge pull request #9 from o/process/clean-slate
b3\tb2\t1700\tMore
b2\tb1 m2\t1650\tMerge main into the branch
m2\tm1 t1\t1600\tMerge pull request #8 from o/tickets/cf-13
t1\tm1\t1550\tFile CF-13
m1\tc0 a2\t1500\tMerge pull request #7 from o/ticket/cf-12
b1\tc0\t1300\tStart the slate
a2\ta1\t1200\tCF-12: finish
a1\tc0\t1100\tCF-12: start
c0\t\t1000\tStart
"""


def test_merges_name_their_ticket_and_when_the_work_started() -> None:
    got = [
        (m.commit, m.head, m.pull, m.branch, m.ticket, m.at, m.started)
        for m in parse_merges(LOG_MERGES, 0)
    ]
    assert got == [
        ("m3", "b3", 9, "process/clean-slate", None, 1800.0, 1300.0),
        ("m1", "a2", 7, "ticket/cf-12", "CF-12", 1500.0, 1100.0),
    ]


def test_the_since_boundary_is_inclusive_and_empty_logs_ship_nothing() -> None:
    assert [m.commit for m in parse_merges(LOG_MERGES, 1800)] == ["m3"]
    assert [m.commit for m in parse_merges(LOG_MERGES, 1801)] == []
    assert parse_merges("c0\t\t1000\tStart\n", 0) == []
    assert parse_merges("", 0) == []


def test_read_merge_tree_cases() -> None:
    assert read_merge_tree(0, "tree\n") == []
    assert read_merge_tree(1, "tree\na.txt\nb.txt\n") == ["a.txt", "b.txt"]
    assert read_merge_tree(1, "") is None
    assert read_merge_tree(129, "tree\n") is None
    assert pair_key("b", "a") == pair_key("a", "b") == "a..b"


GLOBS = ["Cargo.lock", "web/src/generated/**", "tests/golden/**"]


def test_clash_names_the_first_glob_both_sides_touch() -> None:
    assert clash(["Cargo.lock", "a.rs"], ["Cargo.lock"], GLOBS) == (
        "Cargo.lock on the branch and Cargo.lock on main match Cargo.lock"
    )
    assert clash(["web/src/generated/a.ts"], ["web/src/generated/deep/b.ts"], GLOBS) == (
        "web/src/generated/a.ts on the branch and web/src/generated/deep/b.ts on main "
        "match web/src/generated/**"
    )
    assert clash(["Cargo.lock"], ["src/a.rs"], GLOBS) is None


def test_a_merge_subject_names_its_pull_request_and_branch() -> None:
    assert merged_from("Merge pull request #7 from owner/ticket/cf-12") == (7, "ticket/cf-12")
    assert merged_from("Merge pull request #x from owner/feat") == (None, "feat")
    assert merged_from("Merge pull request #8 from solo") == (8, "solo")
    assert merged_from("Merge pull request #1 from a from b/c") == (1, "c")


def test_other_subjects_and_multi_line_ones_name_no_pull_request() -> None:
    assert merged_from("Merge pull request #7") is None
    assert merged_from("Merge pull request #7 fromage") is None
    assert merged_from("Revert Merge pull request #7 from o/b") is None
    assert merged_from("Merge pull request #7 from o/b\nmore") is None
