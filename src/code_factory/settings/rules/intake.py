"""A tracker key may serve only the repository and address this machine stored it for."""

from collections.abc import Mapping

from code_factory.settings.models.config import RepositoryConfig
from code_factory.settings.models.predicates import LINEAR_API, SLACK_API
from code_factory.settings.models.problems import IntakeGrant, Problem
from code_factory.settings.rules.lines import key_line

CONFIG_FILE = ".code-factory/config.toml"


def grant_serves(grant: IntakeGrant, repository: str, address: str) -> bool:
    """Whether the key may serve `repository` at `address`.

    The repository text and the address must be the same, a trailing `/` aside.
    """
    return grant.repository == repository and grant.url.rstrip("/") == address.rstrip("/")


def intake_key_problems(
    config: RepositoryConfig, text: str, grants: Mapping[str, IntakeGrant], repository: str
) -> list[Problem]:
    """Each `[intake]` key name held for another repository or address, on its line.

    `grants` holds the grant of each key name this machine knows.
    """
    intake = config.intake
    if intake is None:
        return []
    pairs = (
        ("linear_token_env", intake.linear_token_env, intake.linear_url or LINEAR_API),
        ("jira_token_env", intake.jira_token_env, intake.jira_url or ""),
        ("slack_token_env", intake.slack_token_env, intake.slack_url or SLACK_API),
    )
    return [
        Problem(
            CONFIG_FILE,
            key_line(text, "intake", key),
            f"intake.{key}: {name} is held on this machine for {grant.repository} at {grant.url}",
        )
        for key, name, address in pairs
        if name is not None
        and (grant := grants.get(name)) is not None
        and not grant_serves(grant, repository, address)
    ]
