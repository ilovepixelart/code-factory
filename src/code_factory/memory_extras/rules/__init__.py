"""The pure memory rules. Callers import from here, never from a file."""

from code_factory.memory_extras.rules.budget import (
    overflow,
    recall_line,
    recall_size,
    title,
    within_budget,
)
from code_factory.memory_extras.rules.cites import gone_cites, plain_cite, stale_mark
from code_factory.memory_extras.rules.consolidation import proposals, retire_reason
from code_factory.memory_extras.rules.edit import (
    DISMISSED,
    MergePatches,
    approved,
    dismissed,
    edited,
    merge_patches,
    retirement,
)
from code_factory.memory_extras.rules.fields import check_fields, is_ticket_id
from code_factory.memory_extras.rules.notices import draft_entry, named, over_budget
from code_factory.memory_extras.rules.pairs import paired_with, pairs
from code_factory.memory_extras.rules.queue import queue_reasons
from code_factory.memory_extras.rules.ranking import rank, scores, words_of
from code_factory.memory_extras.rules.restate import restated
from code_factory.memory_extras.rules.review import (
    guard_state,
    incomplete,
    lapsed,
    loaded,
    overdue,
    review_due,
    stale,
    unused,
)
from code_factory.memory_extras.rules.scope import (
    everywhere,
    for_labels,
    for_role,
    is_archived,
    is_core,
    is_glob,
    loads,
    scope_refusal,
    touches,
)
from code_factory.memory_extras.rules.similar import alike, duplicate_questions
from code_factory.memory_extras.rules.snippets import (
    address,
    entry_text,
    github_web,
    plain_snippet,
    snippet,
)
from code_factory.memory_extras.rules.supersede import (
    plan_supersession,
    superseded,
    superseded_reason,
)

__all__ = [
    "DISMISSED",
    "MergePatches",
    "address",
    "alike",
    "approved",
    "check_fields",
    "dismissed",
    "draft_entry",
    "duplicate_questions",
    "edited",
    "entry_text",
    "everywhere",
    "for_labels",
    "for_role",
    "github_web",
    "gone_cites",
    "guard_state",
    "incomplete",
    "is_archived",
    "is_core",
    "is_glob",
    "is_ticket_id",
    "lapsed",
    "loaded",
    "loads",
    "merge_patches",
    "named",
    "over_budget",
    "overdue",
    "overflow",
    "paired_with",
    "pairs",
    "plain_cite",
    "plain_snippet",
    "plan_supersession",
    "proposals",
    "queue_reasons",
    "rank",
    "recall_line",
    "recall_size",
    "restated",
    "retire_reason",
    "retirement",
    "review_due",
    "scope_refusal",
    "scores",
    "snippet",
    "stale",
    "stale_mark",
    "superseded",
    "superseded_reason",
    "title",
    "touches",
    "unused",
    "within_budget",
    "words_of",
]
