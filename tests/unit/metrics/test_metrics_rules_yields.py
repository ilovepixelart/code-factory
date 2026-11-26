"""The yield of each agent and model over merged work, from hand-worked rows."""

from code_factory.metrics.rules.factory import BoardRun, FactoryRow, yields


def factory_row(ticket_id: str, escaped: tuple[str, ...] = (), intake: float = 100.0) -> FactoryRow:
    return FactoryRow(
        repository="sample", ticket=ticket_id, intake_to_merge=intake, escaped=escaped
    )


def board_run(  # noqa: PLR0913  # a fixture builder
    ticket_id: str,
    agent: str,
    model: str,
    stage: str = "build",
    cost: float | None = None,
    *,
    unfinished: bool = False,
) -> BoardRun:
    return BoardRun(
        repository="sample",
        ticket=ticket_id,
        agent=agent,
        model=model,
        stage=stage,
        cost=cost,
        unfinished=unfinished,
    )


def test_each_setups_merges_and_those_that_held_count_a_ticket_once_per_setup() -> None:
    rows = [factory_row("CF-1"), factory_row("CF-2", escaped=("CF-9",))]
    worked = [
        board_run("CF-1", "coder", "opus"),
        board_run("CF-1", "coder", "opus"),
        board_run("CF-2", "coder", "opus"),
        board_run("CF-2", "", "sonnet"),
        board_run("CF-3", "coder", "opus"),
    ]
    found = [(y.agent, y.model, y.merged, y.held) for y in yields(rows, worked)]
    assert found == [("", "sonnet", 1, 0), ("coder", "opus", 2, 1)]


def test_an_entry_exists_for_a_setup_with_no_merged_ticket() -> None:
    [only] = yields(
        [],
        [board_run("CF-3", "coder", "opus", unfinished=True), board_run("CF-4", "coder", "opus")],
    )
    assert (only.runs, only.unfinished, only.merged, only.held, only.median_intake_to_merge) == (
        2,
        1,
        0,
        0,
        None,
    )


def test_end_to_end_needs_a_spec_run_and_a_build_run_and_cost_counts_only_its_own_runs() -> None:
    rows = [factory_row("CF-1", intake=100.0), factory_row("CF-2", intake=300.0)]
    worked = [
        board_run("CF-1", "a", "opus", "spec", 1.0),
        board_run("CF-1", "a", "opus", "build", 2.0),
        board_run("CF-1", "b", "opus", "build", 4.0),
        board_run("CF-2", "a", "opus", "build"),
    ]
    by_agent = {y.agent: y for y in yields(rows, worked)}
    assert (by_agent["a"].end_to_end, by_agent["a"].cost, by_agent["a"].median_intake_to_merge) == (
        1,
        3.0,
        200.0,
    )
    assert (by_agent["b"].end_to_end, by_agent["b"].cost) == (0, 4.0)


def test_cost_stays_none_while_none_of_its_runs_reported_one() -> None:
    [only] = yields([factory_row("CF-1")], [board_run("CF-1", "a", "opus")])
    assert only.cost is None
