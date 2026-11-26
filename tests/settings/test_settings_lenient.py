"""The lenient reading of config.toml: an invalid key reads as unset while its neighbours read, a
failing list entry is skipped and the next one kept (the previous implementation's `entry_of`)."""

from code_factory.settings.rules import lenient_config


def read(text: str):  # noqa: ANN201
    return lenient_config(text)


def test_an_invalid_key_reads_unset_and_its_neighbours_read() -> None:
    config = read('[agents]\nslots = 0\nretries = 3\nreview = "yes"\nship = true\n')
    assert config.agents is not None
    assert (config.agents.slots, config.agents.retries, config.agents.review) == (None, 3, None)
    assert config.agents.ship is True


def test_an_unknown_table_or_key_is_ignored_and_the_rest_read() -> None:
    config = read("[board]\nread_model = true\n[memory]\nfile_after = 3\npropose_repeats = true\n")
    assert config.memory is not None
    assert config.memory.propose_repeats is True


def test_a_table_given_as_a_scalar_reads_as_absent() -> None:
    config = read('agents = 3\n[checks]\ncommand = "x"\n')
    assert (config.agents, config.checks.command if config.checks else None) == (None, "x")


def test_a_failing_automation_is_skipped_and_the_next_kept() -> None:
    config = read(
        '[[automations]]\nname = "a@b"\nevery = "day"\ntitle = "t"\n\n'
        '[[automations]]\nname = "ok"\nevery = "day"\ntitle = "t"\n\n'
        '[[automations]]\nevery = "day"\ntitle = "no name"\n'
    )
    assert [a.name for a in config.automations or []] == ["ok"]


def test_an_automation_with_an_invalid_key_is_skipped_whole() -> None:
    config = read(
        '[[automations]]\nname = "a"\nevery = "year"\ntitle = "t"\n\n'
        '[[automations]]\nname = "b"\nevery = "day"\ntitle = "t"\n'
    )
    assert [a.name for a in config.automations or []] == ["b"]


def test_a_repeated_name_keeps_the_first_entry() -> None:
    config = read(
        '[[scorers]]\nname = "a"\nquestion = "first"\n\n'
        '[[scorers]]\nname = "a"\nquestion = "second"\n'
    )
    assert [s.question for s in config.scorers or []] == ["first"]


def test_a_recurring_entry_loses_its_invalid_key_only() -> None:
    config = read('[[recurring]]\ntitle = "t"\nevery = "year"\ntype = "bug"\n')
    (entry,) = config.recurring or []
    assert (entry.title, entry.every, entry.type) == ("t", None, "bug")


def test_a_mount_that_reaches_a_secret_is_dropped_and_the_checks_otherwise_read() -> None:
    config = read('[checks]\ncommand = "x"\ncontainer_mounts = ["~/.ssh:/ssh"]\n')
    assert config.checks is not None
    assert (config.checks.command, config.checks.container_mounts) == ("x", None)


def test_a_checks_file_beside_an_image_is_dropped() -> None:
    config = read('[checks]\ncontainer = "i"\ncontainer_file = ".code-factory/f"\n')
    assert config.checks is not None
    assert (config.checks.container, config.checks.container_file) == ("i", None)


def test_a_judge_sample_without_a_budget_is_dropped() -> None:
    config = read("[agents]\njudge_sample = 3\n")
    assert config.agents is not None
    assert config.agents.judge_sample is None


def test_documents_read_in_canonical_order() -> None:
    config = read('[documents]\nbug = ["uat", "requirements"]\n')
    assert config.documents is not None
    assert config.documents.bug == ["requirements", "uat"]


def test_text_that_is_not_toml_reads_as_an_empty_config() -> None:
    assert read("[checks\n").model_dump(exclude_none=True) == {}
    assert read("").model_dump(exclude_none=True) == {}
