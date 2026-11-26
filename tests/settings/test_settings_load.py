"""`SettingsService.load` and the readers over the repository's own files: lenient, cached by
`stat`, raising only when a read or the scan runs out of time. Expected values are the previous
implementation's reader behaviour (an invalid key reads unset, a refused entry is skipped) and
hand-worked file cases."""

import os
from pathlib import Path
from typing import override

import pytest

from code_factory.platform.db import UnitOfWork
from code_factory.platform.errors import BadRequestError
from code_factory.settings import service as service_module
from code_factory.settings.adapters import FileKey, Files, FileTimedOut
from code_factory.settings.models.errors import ConfigUnjudgedError
from code_factory.settings.service import SettingsService
from settings_support import write

CONFIG = ".code-factory/config.toml"
TYPES = ("feature", "bug", "refactor", "upgrade", "hotfix", "docs")


class CountingFiles(Files):
    """Files that count the reads of config.toml, to see whether a call reparsed."""

    def __init__(self) -> None:
        super().__init__()
        self.reads = 0

    @override
    async def read_below(
        self, root: Path, relative: str, limit: int, *, strict: bool = False
    ) -> str | None:
        if relative == CONFIG:
            self.reads += 1
        return await super().read_below(root, relative, limit, strict=strict)

    @override
    async def stat(self, root: Path, relative: str, *, strict: bool = False) -> FileKey | None:
        return await super().stat(root, relative, strict=strict)


@pytest.fixture
def files() -> CountingFiles:
    return CountingFiles()


@pytest.fixture
def service(uow: UnitOfWork, files: CountingFiles) -> SettingsService:
    return SettingsService(uow, files=files)


def config_text(root: Path, text: str) -> None:
    write(root, CONFIG, text)


async def test_a_missing_empty_binary_or_broken_file_reads_as_an_empty_config(
    service: SettingsService, tmp_path: Path
) -> None:
    empty = {}
    assert (await service.load(tmp_path)).model_dump(exclude_none=True) == empty
    deep = "a = " + "[" * 100_000 + "]" * 100_000
    for text in ("", "[checks\n", "a = \n", "[[[[" * 10, deep):
        config_text(tmp_path, text)
        assert (await service.load(tmp_path)).model_dump(exclude_none=True) == empty
    (tmp_path / CONFIG).write_bytes(b"[checks]\ncommand = '\xff'\n")
    assert (await service.load(tmp_path)).model_dump(exclude_none=True) == empty


async def test_a_directory_or_a_link_where_the_file_should_be_reads_as_empty(
    service: SettingsService, tmp_path: Path
) -> None:
    (tmp_path / CONFIG).mkdir(parents=True)
    assert (await service.load(tmp_path)).model_dump(exclude_none=True) == {}
    other = tmp_path / "other"
    (other / ".code-factory").mkdir(parents=True)
    (other / "real.toml").write_text('[checks]\ncommand = "x"\n')
    (other / CONFIG).symlink_to(other / "real.toml")
    assert (await service.load(other)).model_dump(exclude_none=True) == {}


async def test_a_file_past_256_kib_reads_as_empty_and_one_at_it_reads(
    service: SettingsService, tmp_path: Path
) -> None:
    head = '[checks]\ncommand = "x"\n# '
    for size, expected in ((256 * 1024, "x"), (256 * 1024 + 1, None)):
        config_text(tmp_path, head + "a" * (size - len(head)))
        config = await service.load(tmp_path)
        assert (config.checks.command if config.checks else None) == expected
        os.utime(tmp_path / CONFIG, ns=(1, size))


async def test_an_invalid_key_reads_unset_while_its_neighbours_read(
    service: SettingsService, tmp_path: Path
) -> None:
    config_text(tmp_path, "[agents]\nslots = 0\nretries = 3\n")
    config = await service.load(tmp_path)
    assert config.agents is not None
    assert (config.agents.slots, config.agents.retries) == (None, 3)


async def test_a_second_load_does_not_read_the_file_again(
    service: SettingsService, files: CountingFiles, tmp_path: Path
) -> None:
    config_text(tmp_path, '[checks]\ncommand = "x"\n')
    first = await service.load(tmp_path)
    second = await service.load(tmp_path)
    assert first is second
    assert files.reads == 1


async def test_a_change_of_size_mtime_or_file_is_read_again(
    service: SettingsService, files: CountingFiles, tmp_path: Path
) -> None:
    path = tmp_path / CONFIG
    config_text(tmp_path, '[checks]\ncommand = "a"\n')
    os.utime(path, ns=(10**18, 10**18))
    await service.load(tmp_path)
    config_text(tmp_path, '[checks]\ncommand = "bb"\n')  # another size, same mtime
    os.utime(path, ns=(10**18, 10**18))
    config = await service.load(tmp_path)
    assert (files.reads, config.checks.command if config.checks else None) == (2, "bb")
    config_text(tmp_path, '[checks]\ncommand = "cc"\n')  # same size, another mtime
    os.utime(path, ns=(10**18 + 5, 10**18 + 5))
    config = await service.load(tmp_path)
    assert (files.reads, config.checks.command if config.checks else None) == (3, "cc")
    replacement = tmp_path / "replacement"
    replacement.write_text('[checks]\ncommand = "dd"\n')  # same size, same mtime, another file
    os.utime(replacement, ns=(10**18 + 5, 10**18 + 5))
    replacement.replace(path)
    config = await service.load(tmp_path)
    assert (files.reads, config.checks.command if config.checks else None) == (4, "dd")


async def test_a_file_that_is_removed_reads_as_empty_again(
    service: SettingsService, tmp_path: Path
) -> None:
    config_text(tmp_path, '[checks]\ncommand = "x"\n')
    assert (await service.load(tmp_path)).checks is not None
    (tmp_path / CONFIG).unlink()
    assert (await service.load(tmp_path)).checks is None


async def test_the_cache_keeps_the_sixty_four_newest_roots(
    service: SettingsService, files: CountingFiles, tmp_path: Path
) -> None:
    roots = [tmp_path / f"r{n}" for n in range(65)]
    for root in roots:
        config_text(root, '[checks]\ncommand = "x"\n')
        await service.load(root)
    assert files.reads == 65
    await service.load(roots[-1])
    assert files.reads == 65
    await service.load(roots[0])
    assert files.reads == 66


async def test_the_ticket_prefix_is_the_valid_setting_or_cf(
    service: SettingsService, tmp_path: Path
) -> None:
    assert await service.ticket_prefix(tmp_path) == "CF"
    config_text(tmp_path, '[tickets]\nprefix = "ENG"\n')
    assert await service.ticket_prefix(tmp_path) == "ENG"
    os.utime(tmp_path / CONFIG, ns=(1, 1))
    config_text(tmp_path, '[tickets]\nprefix = "eng"\n')
    assert await service.ticket_prefix(tmp_path) == "CF"


async def test_the_documents_of_a_type_come_in_canonical_order_or_none(
    service: SettingsService, tmp_path: Path
) -> None:
    config_text(tmp_path, '[documents]\nhotfix = ["uat", "requirements"]\nbug = ["spec"]\n')
    assert await service.documents_for(tmp_path, "hotfix") == ("requirements", "uat")
    assert await service.documents_for(tmp_path, "bug") is None
    assert await service.documents_for(tmp_path, "feature") is None


async def test_the_documents_of_an_unknown_type_are_refused(
    service: SettingsService, tmp_path: Path
) -> None:
    with pytest.raises(BadRequestError, match=r"^unknown type epic$"):
        await service.documents_for(tmp_path, "epic")


@pytest.mark.parametrize("ticket_type", TYPES)
async def test_the_template_of_each_ticket_type_is_read(
    service: SettingsService, tmp_path: Path, ticket_type: str
) -> None:
    write(tmp_path, f".code-factory/templates/ticket-{ticket_type}.md", f"## Steps {ticket_type}\n")
    assert await service.ticket_template(tmp_path, ticket_type) == f"## Steps {ticket_type}\n"


async def test_a_missing_template_is_empty_and_an_unknown_type_is_refused(
    service: SettingsService, tmp_path: Path
) -> None:
    assert await service.ticket_template(tmp_path, "bug") == ""
    with pytest.raises(BadRequestError, match=r"^unknown type epic$"):
        await service.ticket_template(tmp_path, "epic")


async def test_a_template_that_is_a_link_or_too_big_reads_as_empty(
    service: SettingsService, tmp_path: Path
) -> None:
    folder = tmp_path / ".code-factory" / "templates"
    folder.mkdir(parents=True)
    (tmp_path / "secret.md").write_text("secret")
    (folder / "ticket-bug.md").symlink_to(tmp_path / "secret.md")
    (folder / "ticket-docs.md").write_bytes(b"a" * (64 * 1024))
    (folder / "ticket-feature.md").write_bytes(b"a" * (64 * 1024 + 1))
    assert await service.ticket_template(tmp_path, "bug") == ""
    assert await service.ticket_template(tmp_path, "docs") == "a" * 64 * 1024
    assert await service.ticket_template(tmp_path, "feature") == ""


async def test_a_document_template_is_one_of_four_names(
    service: SettingsService, tmp_path: Path
) -> None:
    for name in ("requirements", "spec", "uat", "mock"):
        write(tmp_path, f".code-factory/templates/{name}.md", f"# {name}\n")
        assert await service.document_template(tmp_path, name) == f"# {name}\n"
    with pytest.raises(BadRequestError, match=r"^unknown document epic$"):
        await service.document_template(tmp_path, "epic")  # ty: ignore[invalid-argument-type]  # the refusal under test


async def test_agent_instructions_are_stripped_and_a_stage_is_a_plain_name(
    service: SettingsService, tmp_path: Path
) -> None:
    write(tmp_path, ".code-factory/agents/build.md", "\n  Be careful.\n\n")
    assert await service.agent_instructions(tmp_path, "build") == "Be careful."
    assert await service.agent_instructions(tmp_path, "review") == ""
    for bad in ("../x", "a/b", "", "A", "a.b", "-a", "build/../build"):
        with pytest.raises(BadRequestError, match=r"^unknown stage"):
            await service.agent_instructions(tmp_path, bad)


async def test_an_automation_template_is_a_file_below_the_repository(
    service: SettingsService, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    write(repo, "docs/t.md", "Main failed\n")
    write(tmp_path, "outside.md", "outside")
    (repo / "docs" / "link.md").symlink_to(tmp_path / "outside.md")
    (repo / "docs" / "big.md").write_bytes(b"a" * (64 * 1024 + 1))
    assert await service.automation_template(repo, "docs/t.md") == "Main failed\n"
    for refused in (
        "docs/link.md",
        "docs/big.md",
        "../outside.md",
        "/etc/hosts",
        "docs/none.md",
        "",
    ):
        assert await service.automation_template(repo, refused) is None


class FlakyFiles(CountingFiles):
    """Files whose first read of config.toml times out."""

    @override
    async def read_below(
        self, root: Path, relative: str, limit: int, *, strict: bool = False
    ) -> str | None:
        if relative == CONFIG and self.reads == 0:
            self.reads += 1
            if strict:
                raise FileTimedOut(relative)
            return None
        return await super().read_below(root, relative, limit, strict=strict)


async def test_a_read_that_timed_out_is_refused_and_not_remembered_as_an_empty_config(
    uow: UnitOfWork, tmp_path: Path
) -> None:
    config_text(tmp_path, '[tickets]\nprefix = "ABC"\n')
    service = SettingsService(uow, files=FlakyFiles())
    with pytest.raises(ConfigUnjudgedError):
        await service.ticket_prefix(tmp_path)
    assert [await service.ticket_prefix(tmp_path) for _ in range(2)] == ["ABC", "ABC"]


async def test_a_parse_that_timed_out_is_not_remembered_as_an_empty_config(
    uow: UnitOfWork, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_text(tmp_path, '[tickets]\nprefix = "ABC"\n')
    real = service_module.in_thread
    calls = []

    async def first_times_out(function, *args):  # noqa: ANN001, ANN002, ANN202
        calls.append(function)
        return None if len(calls) == 1 else await real(function, *args)

    monkeypatch.setattr(service_module, "in_thread", first_times_out)
    service = SettingsService(uow)
    prefixes = [await service.ticket_prefix(tmp_path) for _ in range(3)]
    assert prefixes == ["CF", "ABC", "ABC"]


async def test_a_root_read_again_is_kept_while_older_untouched_ones_go(
    service: SettingsService, files: CountingFiles, tmp_path: Path
) -> None:
    roots = [tmp_path / f"r{n}" for n in range(65)]
    for root in roots[:64]:
        config_text(root, '[checks]\ncommand = "x"\n')
        await service.load(root)
    await service.load(roots[0])  # the oldest is now the most recently used
    config_text(roots[64], '[checks]\ncommand = "x"\n')
    await service.load(roots[64])  # evicts roots[1], not roots[0]
    reads = files.reads
    await service.load(roots[0])
    assert files.reads == reads
    await service.load(roots[1])
    assert files.reads == reads + 1
