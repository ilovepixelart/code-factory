"""The tables of `.code-factory/config.toml`, one model each.

Every key is optional and reads `None` when unset: the default of a key belongs to the module that
acts on it. The two defaults held here are `tickets.prefix` and `preview.idle_seconds`
(`DEFAULT_PREFIX`, `DEFAULT_IDLE_SECONDS`), applied by the service. Field order is the order of
the generated reference page.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict

from code_factory.settings.models.kinds import (
    PERIODS,
    TICKET_TYPES,
    Between,
    Count,
    Documents,
    Flag,
    Globs,
    HostPorts,
    Number,
    OneOf,
    Prefix,
    Share,
    Text,
    Texts,
    TextTable,
    TrackerAddress,
    TrackerKey,
    Whole,
)

DEFAULT_PREFIX = "CF"
DEFAULT_IDLE_SECONDS = 1800
MAIN_FAILED = "main_checks_failed"

Period = Annotated[str, OneOf(*PERIODS)]
TicketTypeName = Annotated[str, OneOf(*TICKET_TYPES)]
Trigger = Annotated[str, OneOf(MAIN_FAILED)]


class Table(BaseModel):
    """A table or list entry: a key nothing reads is an error, not ignored."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ChecksTable(Table):
    """`[checks]`: how a pull request is checked."""

    command: Text | None = None
    fast: Text | None = None
    main: Text | None = None
    main_tickets: Text | None = None
    timeout: Count | None = None
    container: Text | None = None
    container_engine: Text | None = None
    container_file: Text | None = None
    container_mounts: Texts | None = None
    container_slots: Count | None = None


class AgentsTable(Table):
    """`[agents]`: how runs are made."""

    git_author: Text | None = None
    slots: Count | None = None
    run_timeout: Count | None = None
    idle_tool_calls: Whole | None = None
    setup_timeout: Count | None = None
    retries: Count | None = None
    limit_wait: Count | None = None
    attempts: Count | None = None
    fix_rounds: Count | None = None
    max_iterations: Count | None = None
    budget_usd: Number | None = None
    monthly_budget_usd: Number | None = None
    judge_sample: Annotated[int, Between(1, 50)] | None = None
    judge_share: Annotated[int | float, Share(0.2)] | None = None
    model: Text | None = None
    runtime: Text | None = None
    setup: Text | None = None
    teardown: Text | None = None
    models: TextTable | None = None
    allowed_domains: Texts | None = None
    acp_command: Text | None = None
    acp_hosts: HostPorts | None = None
    review: Flag | None = None
    review_other_model: Flag | None = None
    escalate: Flag | None = None
    review_rounds: Count | None = None
    review_roles: Texts | None = None
    ship: Flag | None = None
    fix_feedback: Flag | None = None
    post_review: Flag | None = None
    update_branches: Flag | None = None
    plan_critic: Flag | None = None
    spec_reader: Flag | None = None
    merge_approval: Flag | None = None
    sensitive_paths: Globs | None = None
    large_change: Count | None = None
    permission_approval: Flag | None = None
    permission_reviewer: Text | None = None
    permission_reviewer_limit: Count | None = None
    sandbox: Flag | None = None
    stall_tickets: Flag | None = None
    finding_tickets: Flag | None = None
    queue_label: Text | None = None
    coordinator: Flag | None = None
    coordinator_tokens: Count | None = None


def ships(agents: AgentsTable | None) -> bool:
    """A repository ships its built branches as pull requests unless `ship = false`."""
    return agents is None or agents.ship is not False


def reviews(agents: AgentsTable | None) -> bool:
    """A pull request gets a review run unless `review = false`."""
    return agents is None or agents.review is not False


class IntakeTable(Table):
    """`[intake]`: where tickets are filed from."""

    github_issues: Flag | None = None
    github_label: Text | None = None
    github_label_required: Flag | None = None
    github_waiting_label: Text | None = None
    linear_label: Text | None = None
    linear_assigned: Flag | None = None
    linear_token_env: TrackerKey | None = None
    linear_url: Annotated[str, TrackerAddress("linear")] | None = None
    jira_url: Annotated[str, TrackerAddress("jira")] | None = None
    jira_jql: Text | None = None
    jira_email: Text | None = None
    jira_token_env: TrackerKey | None = None
    slack_channel: Text | None = None
    slack_reaction: Text | None = None
    slack_token_env: TrackerKey | None = None
    slack_url: Annotated[str, TrackerAddress("slack")] | None = None


class TelemetryTable(Table):
    """`[telemetry]`."""

    endpoint: Text | None = None
    protocol: Text | None = None


class TicketsTable(Table):
    """`[tickets]`."""

    prefix: Prefix | None = None


class GithubTable(Table):
    """`[github]`."""

    timeout: Count | None = None
    token_env: Text | None = None
    allowed_hosts: Texts | None = None
    review_requests: Count | None = None


class ReleaseTable(Table):
    """`[release]`."""

    watch_days: Whole | None = None
    verify: Text | None = None


class MemoryTable(Table):
    """`[memory]`."""

    propose_repeats: Flag | None = None


class MergeTable(Table):
    """`[merge]`: which pull request merges unreviewed, and which files recheck together."""

    unreviewed_lines: Count | None = None
    sensitive: Texts | None = None
    recheck_together: Globs | None = None


class ScreensTable(Table):
    """`[screens]`: the paths whose change makes a ticket wait for screens."""

    paths: Texts | None = None


class DocumentsTable(Table):
    """`[documents]`: the Spec documents each ticket type needs."""

    feature: Documents | None = None
    bug: Documents | None = None
    refactor: Documents | None = None
    upgrade: Documents | None = None
    hotfix: Documents | None = None
    docs: Documents | None = None


class ForgeTable(Table):
    """`[forge]`."""

    kind: Annotated[str, OneOf("github", "gitlab")] | None = None


class PreviewTable(Table):
    """`[preview]`: a live preview of a ticket's worktree."""

    command: Text | None = None
    idle_seconds: Count | None = None


class RecurringEntry(Table):
    """`[[recurring]]`: a ticket filed on a schedule."""

    title: Text | None = None
    every: Period | None = None
    type: TicketTypeName | None = None
    description: Text | None = None
    labels: Text | None = None
    budget_usd: Number | None = None


class AutomationEntry(Table):
    """`[[automations]]`: a ticket filed on a schedule or an event.

    The trigger and the body are held across keys by `cross_key_findings`.
    """

    name: Text | None = None
    every: Period | None = None
    on: Trigger | None = None
    title: Text | None = None
    body: Text | None = None
    template: Text | None = None
    type: TicketTypeName | None = None
    labels: Text | None = None
    start: Flag | None = None


class ScorerEntry(Table):
    """`[[scorers]]`: a yes or no question asked of sampled sessions."""

    name: Text | None = None
    question: Text | None = None
    stage: Text | None = None
    sample: Number | None = None
    threshold: Count | None = None


class RepositoryConfig(Table):
    """What `config.toml` says; an unknown table is an error."""

    checks: ChecksTable | None = None
    agents: AgentsTable | None = None
    intake: IntakeTable | None = None
    telemetry: TelemetryTable | None = None
    tickets: TicketsTable | None = None
    github: GithubTable | None = None
    release: ReleaseTable | None = None
    memory: MemoryTable | None = None
    merge: MergeTable | None = None
    screens: ScreensTable | None = None
    documents: DocumentsTable | None = None
    forge: ForgeTable | None = None
    preview: PreviewTable | None = None
    recurring: list[RecurringEntry] | None = None
    automations: list[AutomationEntry] | None = None
    scorers: list[ScorerEntry] | None = None
