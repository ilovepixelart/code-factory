"""`config.toml` held to its model: each case is one of the previous implementation's
`config_keys.rs` cases, translated (folder name, intake prefix, ticket prefix renamed, the two
dropped keys reported as unknown). Expected `(line, message)` pairs are copied from its assertions.
"""

import pytest

from code_factory.settings.rules import TomlError, config_problems, parse_toml

EVERY_SETTING = """[checks]
command = "sh scripts/gate.sh --fast"
main = "sh scripts/gate.sh"
main_tickets = "sh scripts/gate.sh --tickets"
timeout = 600
container = "example/checks:1"
container_engine = "podman"
container_mounts = ["~/.cargo/registry:/usr/local/cargo/registry"]
container_slots = 2

[agents]
git_author = "Bot <bot@example.com>"
slots = 2
run_timeout = 3600
idle_tool_calls = 80
setup_timeout = 600
retries = 3
limit_wait = 60
attempts = 2
fix_rounds = 3
max_iterations = 10
budget_usd = 2.5
monthly_budget_usd = 40
judge_sample = 2
judge_share = 0.05
model = "opus"
runtime = "claude"
setup = "pnpm install"
teardown = "rm -rf build"
allowed_domains = ["pypi.org"]
acp_command = "my-agent --stdio"
acp_hosts = ["models.example.com:443"]
review = true
review_other_model = true
escalate = true
review_rounds = 3
ship = true
fix_feedback = true
post_review = true
update_branches = true
plan_critic = true
merge_approval = false
sensitive_paths = ["scripts/**"]
large_change = 400
permission_approval = false
permission_reviewer = "opus"
permission_reviewer_limit = 5
sandbox = true
stall_tickets = true
finding_tickets = true
queue_label = "queue"
coordinator = true
coordinator_tokens = 100000

[agents.models]
brd = "sonnet"

[intake]
github_issues = true
github_label = "code-factory"
github_label_required = true
github_waiting_label = "waiting"
linear_label = "code-factory"
linear_assigned = true
linear_token_env = "CODE_FACTORY_INTAKE_LINEAR"
linear_url = "https://api.linear.app/graphql"
jira_url = "https://acme.atlassian.net"
jira_jql = "project = ENG AND labels = code-factory"
jira_email = "bot@acme.example"
jira_token_env = "CODE_FACTORY_INTAKE_JIRA"
slack_channel = "C1"
slack_reaction = "ticket"
slack_token_env = "CODE_FACTORY_INTAKE_SLACK"
slack_url = "https://slack.com/api"

[telemetry]
endpoint = "http://localhost:4317"
protocol = "grpc"

[tickets]
prefix = "CF"

[documents]
hotfix = ["requirements"]

[github]
review_requests = 2
timeout = 60
token_env = "GH_TOKEN"
allowed_hosts = ["github.com"]

[release]
watch_days = 0
verify = "sh verify.sh"

[memory]
propose_repeats = true

[merge]
unreviewed_lines = 400
sensitive = ["scripts/**"]
recheck_together = ["uv.lock"]

[screens]
paths = ["web/src/**"]

[[recurring]]
title = "Dependency review"
every = "week"
type = "upgrade"
description = "Review the week's dependency updates"
labels = "quality"
budget_usd = 3

[[recurring]]
title = "Release notes"
every = "month"

[[automations]]
name = "nightly"
every = "day"
title = "Nightly sweep"
body = "Sweep the board."
type = "docs"
labels = "ops"
start = true

[[automations]]
name = "broken-main"
on = "main_checks_failed"
title = "Main failed at {commit}"
template = ".code-factory/templates/main.md"

[[scorers]]
name = "tested"
question = "Did the run add a test first?"
stage = "build"
sample = 0.5
threshold = 3

[forge]
kind = "github"

[preview]
command = "pnpm dev"
idle_seconds = 900
"""


def problems(text: str) -> list[tuple[int, str]]:
    return sorted((p.line, p.message) for p in config_problems("c", text))


def messages(text: str) -> list[str]:
    return [message for _, message in problems(text)]


def test_every_setting_of_the_reference_validates() -> None:
    assert problems(EVERY_SETTING) == []


def test_the_preview_settings_are_text_and_a_count() -> None:
    assert problems('[preview]\ncommand = "pnpm dev"\nidle_seconds = 900\n') == []
    assert problems("[preview]\ncommand = 3\nidle_seconds = 0\n") == [
        (2, "preview.command: expected text, not empty"),
        (3, "preview.idle_seconds: expected a positive integer"),
    ]


def test_a_timeout_is_a_positive_whole_number() -> None:
    text = '[checks]\ncommand = "true"\ntimeout = "ten"\n\n[github]\ntimeout = 0\n'
    assert problems(text) == [
        (3, "checks.timeout: expected a positive integer"),
        (6, "github.timeout: expected a positive integer"),
    ]


def test_the_main_command_is_text() -> None:
    assert problems('[checks]\nmain = "sh scripts/gate.sh"\n') == []
    assert problems("[checks]\nmain = true\n") == [(2, "checks.main: expected text, not empty")]


def test_a_recurring_entry_is_held_to_its_reader() -> None:
    text = (
        '[[recurring]]\ntitle = "a"\nevery = "day"\n\n'
        '[[recurring]]\nevery = "year"\ntype = "chore"\n'
    )
    assert problems(text) == [
        (6, "recurring.every: expected one of day, week, month"),
        (7, "recurring.type: expected one of feature, bug, refactor, upgrade, hotfix, docs"),
    ]
    assert messages('[recurring]\ntitle = "a"\n') == ["recurring: expected a list of tables"]


def test_a_repeated_automation_name_is_refused_naming_both_lines() -> None:
    text = (
        '[[automations]]\nname = "a"\nevery = "day"\ntitle = "t"\n\n'
        '[[automations]]\nname = "b"\nevery = "day"\ntitle = "t"\n\n'
        '[[automations]]\nname = "a"\non = "main_checks_failed"\ntitle = "u"\n'
    )
    assert problems(text) == [(12, 'automations.name: "a" is already the name on line 2')]


def test_two_automations_with_distinct_names_are_accepted() -> None:
    text = (
        '[[automations]]\nname = "a"\nevery = "day"\ntitle = "t"\n\n'
        '[[automations]]\nname = "b"\nevery = "day"\ntitle = "t"\n'
    )
    assert problems(text) == []


def test_an_automation_is_held_to_its_model() -> None:
    text = (
        '[[automations]]\nname = "a@b"\nevery = "year"\non = "dependency_update"\ntitle = "t"\n'
        'body = "x"\ntemplate = "../x.md"\nstart = "yes"\nbogus = 1\n\n'
        '[[automations]]\ntitle = "t"\n'
    )
    assert problems(text) == [
        (0, "automations.name: required"),
        (0, "automations: set one trigger, every or on"),
        (2, "automations.name: must not contain @ or a line break"),
        (3, "automations.every: expected one of day, week, month"),
        (4, "automations.on: an automation has one trigger, every or on"),
        (4, "automations.on: expected one of main_checks_failed"),
        (7, "automations.template: expected a path inside the repository"),
        (7, "automations.template: set body or template, not both"),
        (8, "automations.start: expected true or false"),
        (9, "automations.bogus: unknown field"),
    ]


def test_an_automation_needs_a_title() -> None:
    text = '[[automations]]\nname = "a"\nevery = "day"\n'
    assert problems(text) == [(0, "automations.title: required")]


def test_an_automation_with_a_trigger_and_a_template_is_accepted() -> None:
    text = (
        '[[automations]]\nname = "a"\non = "main_checks_failed"\ntitle = "t"\n'
        'template = "docs/t.md"\n'
    )
    assert problems(text) == []


def test_a_scorer_is_held_to_its_model() -> None:
    text = (
        '[[scorers]]\nname = "a@b"\nquestion = "q"\nsample = 1.5\n\n'
        '[[scorers]]\nname = "ok"\n\n'
        '[[scorers]]\nname = "edge"\nquestion = "q"\nsample = 0\n\n'
        '[[scorers]]\nname = "edge2"\nquestion = "q"\nsample = 1\n\n'
        '[[scorers]]\nname = "a@b"\nquestion = "q"\n'
    )
    assert problems(text) == [
        (0, "scorers.question: required"),
        (2, "scorers.name: must not contain @ or a line break"),
        (4, "scorers.sample: expected a number from 0 to 1"),
        (20, 'scorers.name: "a@b" is already the name on line 2'),
        (20, "scorers.name: must not contain @ or a line break"),
    ]


def test_a_repeated_scorer_name_is_refused_naming_both_lines() -> None:
    text = '[[scorers]]\nname = "a"\nquestion = "q"\n\n[[scorers]]\nname = "a"\nquestion = "q"\n'
    assert problems(text) == [(6, 'scorers.name: "a" is already the name on line 2')]


def test_linear_intake_settings_validate() -> None:
    good = (
        '[intake]\nlinear_label = "x"\nlinear_token_env = "CODE_FACTORY_INTAKE_LINEAR"\n'
        'linear_url = "https://api.linear.app/graphql"\n'
    )
    bad = '[intake]\nlinear_label = 3\nlinear_token_env = "CODE_FACTORY_INTAKE_LINEAR"\n'
    assert problems(good) == []
    assert problems(bad) == [(2, "intake.linear_label: expected text, not empty")]


def test_linear_assigned_takes_true_or_false() -> None:
    assert problems("[intake]\nlinear_assigned = true\n") == []
    assert problems("[intake]\nlinear_assigned = false\n") == []
    assert problems('[intake]\nlinear_label = "x"\nlinear_assigned = "yes"\n') == [
        (3, "intake.linear_assigned: expected true or false")
    ]


def test_jira_intake_settings_validate() -> None:
    good = (
        '[intake]\njira_url = "https://acme.atlassian.net"\njira_jql = "project = ENG"\n'
        'jira_email = "bot@acme.example"\njira_token_env = "CODE_FACTORY_INTAKE_JIRA"\n'
    )
    bad = '[intake]\njira_url = "https://acme.atlassian.net"\njira_jql = true\n'
    assert problems(good) == []
    assert problems(bad) == [(3, "intake.jira_jql: expected text, not empty")]


def test_an_unknown_key_is_reported_on_its_line() -> None:
    text = '[github]\ntimout = 60\n\n[[recurring]]\ntitel = "x"\n'
    assert problems(text) == [
        (2, "github.timout: unknown field"),
        (5, "recurring.titel: unknown field"),
    ]
    assert problems("[githab]\ntimeout = 1\n") == [(1, "githab: unknown table")]


def test_settings_nothing_reads_are_unknown_keys() -> None:
    text = (
        '[agents]\nread_documents = true\ncodex_command = "codex"\n\n[checks]\n'
        'models = "sh models.sh"\n'
    )
    assert problems(text) == [
        (2, "agents.read_documents: unknown field"),
        (3, "agents.codex_command: unknown field"),
        (6, "checks.models: unknown field"),
    ]


def test_the_two_keys_of_the_previous_board_are_unknown() -> None:
    assert problems("[board]\nread_model = true\n") == [(1, "board: unknown table")]
    assert problems("[memory]\nfile_after = 3\n") == [(2, "memory.file_after: unknown field")]


def test_a_table_given_as_a_scalar_is_not_a_table() -> None:
    assert problems("agents = 3\n") == [(0, "agents: expected a table")]
    assert problems('checks = "x"\n') == [(0, "checks: expected a table")]


def test_a_list_of_tables_given_as_scalars_is_refused_once() -> None:
    assert problems("automations = [1, 2]\n") == [(0, "automations: expected a list of tables")]


def test_a_tracker_address_is_held_to_its_own_hosts() -> None:
    elsewhere = (
        '[intake]\nlinear_url = "https://linear.example/graphql"\n'
        'jira_url = "https://evil.example.com"\n'
    )
    lookalike = (
        '[intake]\nlinear_url = "https://api.linear.app.evil.example"\n'
        'jira_url = "https://acme.atlassian.net.evil.example"\n'
    )
    local = (
        '[intake]\nlinear_url = "http://127.0.0.1:4100/graphql"\n'
        'jira_url = "http://localhost:4100"\n'
    )
    with_user = '[intake]\njira_url = "https://user@acme.atlassian.net"\n'
    assert [n for n, _ in problems(elsewhere)] == [2, 3]
    assert [n for n, _ in problems(lookalike)] == [2, 3]
    assert [n for n, _ in problems(with_user)] == [2]
    assert problems(local) == []


def test_a_tracker_key_is_named_only_under_the_intake_prefix() -> None:
    elsewhere = (
        '[intake]\nlinear_token_env = "ANTHROPIC_API_KEY"\n'
        'jira_token_env = "CODE_FACTORY_INTAKE_"\n'
    )
    lowercase = '[intake]\nlinear_token_env = "CODE_FACTORY_INTAKE_linear"\n'
    named = (
        '[intake]\nlinear_token_env = "CODE_FACTORY_INTAKE_LINEAR"\n'
        'jira_token_env = "CODE_FACTORY_INTAKE_JIRA_2"\n'
    )
    assert [n for n, _ in problems(elsewhere)] == [2, 3]
    assert [n for n, _ in problems(lowercase)] == [2]
    assert problems(named) == []


def test_idle_tool_calls_is_a_count_that_may_be_zero() -> None:
    assert problems("[agents]\nidle_tool_calls = 80\n") == []
    assert problems("[agents]\nidle_tool_calls = 0\n") == []
    assert messages('[agents]\nidle_tool_calls = "many"\n') == [
        "agents.idle_tool_calls: expected a whole number, 0 or more"
    ]


@pytest.mark.parametrize(
    "refused",
    [
        '["models.example.com"]',
        '["models.example.com:443", "other.example.com"]',
        '["models.example.com:0"]',
        '["models.example.com:70000"]',
        '[":443"]',
        '["*:443"]',
        '["https://models.example.com:443"]',
        "[443]",
        '"models.example.com:443"',
    ],
)
def test_an_acp_host_without_a_port_is_refused(refused: str) -> None:
    assert problems(f"[agents]\nacp_hosts = {refused}\n") == [
        (2, "agents.acp_hosts: expected a list of <host>:<port> texts")
    ]


def test_acp_hosts_accepts_named_ports_and_an_empty_list() -> None:
    assert problems('[agents]\nacp_hosts = ["models.example.com:443", "127.0.0.1:9"]\n') == []
    assert problems("[agents]\nacp_hosts = []\n") == []


def test_the_judge_settings_validate() -> None:
    budget = "[agents]\nmonthly_budget_usd = 10\n"
    sample = "agents.judge_sample: expected a whole number from 1 to 50"
    share = "agents.judge_share: expected a number above 0 and at most 0.2"
    assert problems(budget + "judge_sample = 50\njudge_share = 0.2\n") == []
    assert problems(budget + "judge_sample = 1\njudge_share = 0.001\n") == []
    assert problems(budget + "judge_sample = 51\njudge_share = 0.25\n") == [(3, sample), (4, share)]
    assert problems(budget + "judge_sample = 0\njudge_share = 0\n") == [(3, sample), (4, share)]


def test_a_judge_sample_needs_a_monthly_budget() -> None:
    assert problems("[agents]\njudge_sample = 2\n") == [
        (2, "agents.judge_sample: judge_sample needs monthly_budget_usd")
    ]


def test_a_checks_file_is_under_the_folder_and_not_beside_an_image() -> None:
    outside = "checks.container_file: expected a file under .code-factory/"
    inside = '[checks]\ncontainer_file = ".code-factory/checks.Containerfile"\n'
    assert problems(inside) == []
    assert problems('[checks]\ncontainer_file = "Dockerfile"\n') == [(2, outside)]
    assert problems('[checks]\ncontainer_file = ".code-factory/../Dockerfile"\n') == [(2, outside)]
    assert problems('[checks]\ncontainer_file = "/.code-factory/c"\n') == [(2, outside)]
    assert problems('[checks]\ncontainer_file = ".code-factory"\n') == [(2, outside)]
    assert problems(
        '[checks]\ncontainer = "example/checks:1"\ncontainer_file = ".code-factory/c"\n'
    ) == [(3, "checks.container_file: set container or container_file, not both")]


def test_a_malformed_container_mount_is_named_on_its_line() -> None:
    good = '[checks]\ncontainer_mounts = ["~/.cargo/registry:/usr/local/cargo/registry"]\n'
    assert problems(good) == []
    assert problems('[checks]\ncontainer_mounts = ["cache:/cache"]\n') == [
        (
            2,
            (
                "checks.container_mounts: cache:/cache: expected <host folder>:<folder inside>, "
                "the host one absolute or under ~/, the inside one absolute"
            ),
        )
    ]


@pytest.mark.parametrize("entry", ["/a:/b:/c", "/a", "/a/../b:/c", "/a:rel", "/a:/", "/:/x"])
def test_other_malformed_container_mounts_are_refused(entry: str) -> None:
    (message,) = messages(f'[checks]\ncontainer_mounts = ["{entry}"]\n')
    assert message.startswith(f"checks.container_mounts: {entry}: expected <host folder>")


def test_a_slack_address_and_key_name_are_held() -> None:
    good = (
        '[intake]\nslack_channel = "C1"\nslack_reaction = "ticket"\n'
        'slack_token_env = "CODE_FACTORY_INTAKE_SLACK"\nslack_url = "https://slack.com/api"\n'
    )
    bad = '[intake]\nslack_token_env = "SLACK_TOKEN"\nslack_url = "https://evil.example/api"\n'
    assert problems(good) == []
    assert messages(bad) == [
        "intake.slack_token_env: expected CODE_FACTORY_INTAKE_, then capitals, digits or _",
        "intake.slack_url: expected https://slack.com/api or an address on this machine",
    ]


def test_the_forge_is_github_or_gitlab() -> None:
    assert problems('[forge]\nkind = "github"\n') == []
    assert problems('[forge]\nkind = "gitlab"\n') == []
    assert problems('[forge]\nkind = "bitbucket"\n') == [
        (2, "forge.kind: expected one of github, gitlab")
    ]


def test_review_requests_is_a_positive_whole_number() -> None:
    assert problems("[github]\nreview_requests = 2\n") == []
    assert problems("[github]\nreview_requests = 0\n") == [
        (2, "github.review_requests: expected a positive integer")
    ]


def test_the_merge_settings_validate() -> None:
    assert problems('[merge]\nunreviewed_lines = 400\nsensitive = ["scripts/**"]\n') == []
    assert problems('[merge]\nunreviewed_lines = 0\nsensitive = "scripts"\n') == [
        (2, "merge.unreviewed_lines: expected a positive integer"),
        (3, "merge.sensitive: expected a list of text"),
    ]


def test_recheck_together_is_a_list_of_path_patterns() -> None:
    assert problems('[merge]\nrecheck_together = ["uv.lock", "tests/golden/**"]\n') == []
    assert problems('[merge]\nrecheck_together = "uv.lock"\n') == [
        (2, "merge.recheck_together: expected a list of text")
    ]
    assert problems('[merge]\nrecheck_together = ["src/[a"]\n') == [
        (2, 'merge.recheck_together: "src/[a" is not a path pattern')
    ]


def test_a_sensitive_path_that_is_not_a_glob_is_refused_naming_the_entry() -> None:
    assert problems('[agents]\nsensitive_paths = ["scripts/**", "src/[a"]\n') == [
        (2, 'agents.sensitive_paths: "src/[a" is not a path pattern')
    ]
    assert problems('[agents]\nsensitive_paths = ["src/[ab]/**"]\n') == []


def test_large_change_is_a_positive_whole_number() -> None:
    assert problems("[agents]\nlarge_change = 0\n") == [
        (2, "agents.large_change: expected a positive integer")
    ]


def test_a_documents_entry_is_held_and_names_the_key_line() -> None:
    assert problems('[documents]\nhotfix = ["requirements"]\n') == []
    assert problems('[documents]\nbug = ["spec"]\nfeature = ["requirements", "spec", "uat"]\n') == [
        (
            2,
            (
                "documents.bug: expected a list of requirements, spec and uat holding "
                "requirements, "
                "each once"
            ),
        )
    ]


def test_the_agent_models_table_is_a_table_of_text() -> None:
    assert problems('[agents.models]\nbrd = "sonnet"\n') == []
    assert messages("[agents.models]\nbrd = 3\n") == ["agents.models: expected a table of text"]


def test_a_toml_syntax_error_is_reported_with_its_line() -> None:
    result = problems('[checks]\ncommand = "a"\ncommand = "b"\n')
    assert len(result) == 1
    line, message = result[0]
    assert (line, message.startswith("toml: ")) == (3, True)
    assert problems("[checks\n")[0][1].startswith("toml: ")


def test_parse_toml_returns_the_table_or_the_error_with_its_line() -> None:
    assert parse_toml("[a]\nb = 1\n") == {"a": {"b": 1}}
    error = parse_toml("a = 1\nb = \n")
    assert isinstance(error, TomlError)
    assert error.line == 2
    assert error.message.startswith("Invalid value")
