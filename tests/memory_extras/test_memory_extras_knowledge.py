"""The knowledge search over memory entries, ticket documents and the repository's documents."""

from code_factory.platform.text import Paging
from memory_extras_bench import Bench


async def knowledge_bench(bench: Bench) -> None:
    await bench.seed(
        "2026-10-02-the-gate-ran-twice",
        "The gate ran twice on one tree",
        kind="lesson",
        source="CF-2",
    )
    bench.tickets.documents["sample"] = [
        ("CF-7", "spec", "The gate refuses a push whose checks did not pass")
    ]
    bench.git.files = {"README.md": "gate", "docs/other.md": "nothing relevant here"}
    bench.git.remote = "git@github.com:owner/name.git"


async def test_results_are_ranked_and_each_opens_its_own_kind_of_address(bench: Bench) -> None:
    await knowledge_bench(bench)
    found, matched = await bench.service.knowledge("sample", "gate", 10)
    assert matched == 3
    # Every document holds `gate` once, so the shortest ranks first: 1, 10 and 16 words.
    assert [(f.path, f.open) for f in found] == [
        ("README.md", "https://github.com/owner/name/blob/HEAD/README.md"),
        ("tickets/CF-7/spec.md", "/tickets/sample/CF-7"),
        ("memory/2026-10-02-the-gate-ran-twice", "#2026-10-02-the-gate-ran-twice"),
    ]
    assert {f.repository for f in found} == {"sample"}


async def test_a_snippet_is_plain_text_around_the_words(bench: Bench) -> None:
    await knowledge_bench(bench)
    found, _ = await bench.service.knowledge("sample", "gate", 10)
    assert found[1].snippet == "The gate refuses a push whose checks did not pass"
    # The window is twelve words from the start of the 17 the entry has.
    assert found[2].snippet == "kind: lesson date: 2026-10-02 source: CF-2 The gate ran..."


async def test_the_limit_cuts_the_results_and_the_count_still_says_how_many_matched(
    bench: Bench,
) -> None:
    await knowledge_bench(bench)
    found, matched = await bench.service.knowledge("sample", "gate", 2)
    assert (len(found), matched) == (2, 3)


async def test_a_word_matches_whole_words_in_any_case_and_every_word_must_be_held(
    bench: Bench,
) -> None:
    await knowledge_bench(bench)
    assert (await bench.service.knowledge("sample", "GATE twice", 10))[1] == 1
    assert (await bench.service.knowledge("sample", "gat", 10)) == ([], 0)
    assert (await bench.service.knowledge("sample", "gate nothing matches this", 10)) == ([], 0)


async def test_an_empty_query_has_no_results(bench: Bench) -> None:
    await knowledge_bench(bench)
    assert await bench.service.knowledge("sample", "  ?! ", 10) == ([], 0)


async def test_a_retired_entry_is_not_searched(bench: Bench) -> None:
    await bench.seed("2026-10-02-old", "The gate ran twice", retired="no longer true")
    assert await bench.service.knowledge("sample", "gate", 10) == ([], 0)


async def test_a_repository_without_a_github_origin_has_no_address_for_its_files(
    bench: Bench,
) -> None:
    bench.git.files = {"README.md": "gate"}
    found, _ = await bench.service.knowledge("sample", "gate", 10)
    assert [(f.path, f.open) for f in found] == [("README.md", "")]


async def test_the_page_pages_the_results_of_every_repository(bench: Bench) -> None:
    await bench.seed("2026-10-01-a", "Keep small things", source="chat")
    await bench.seed("2026-10-02-b", "Keep small plans", source="chat", repository="second")
    first = await bench.service.page("keep small", Paging(1, 1))
    second = await bench.service.page("keep small", Paging(2, 1))
    beyond = await bench.service.page("keep small", Paging(9, 1))
    assert (first.matched, first.page, first.size, [r.repository for r in first.results]) == (
        2, 1, 1, ["sample"],
    )  # fmt: skip
    assert [r.repository for r in second.results] == ["second"]
    assert (beyond.page, [r.repository for r in beyond.results]) == (2, ["second"])


async def test_a_page_without_a_query_has_no_results(bench: Bench) -> None:
    await knowledge_bench(bench)
    page = await bench.service.page("   ")
    assert (page.results, page.matched) == ([], 0)
