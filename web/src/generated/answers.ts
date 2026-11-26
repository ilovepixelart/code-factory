// Written by the_answer_contracts_are_current.
import type { Board } from '../lib/board'
import type { Archive } from '../lib/memory'
import type { Flow, Inbox } from '../lib/metrics'
import type { TicketView } from '../lib/ticket'
export const board = {
  "today": "2026-09-21",
  "columns": {
    "spec": [
      {
        "id": "AB-1",
        "title": "Other repository, first",
        "type": "feature",
        "branch": "",
        "repository": "second",
        "stage": "spec",
        "evidence_stage": "spec",
        "description": "",
        "labels": [],
        "priority": "",
        "assignee": "",
        "due": "",
        "blocked": "",
        "archived": false,
        "rank": 1,
        "stage_since": "",
        "checklist": [
          0,
          0
        ],
        "open_questions": 0,
        "sessions": [],
        "runs": [
          {
            "id": "eeeeeeeeeeee",
            "stage": "spec",
            "iteration": 3,
            "loop": true,
            "max_iterations": 12,
            "attempt": 0,
            "agent": "",
            "started_at": 1790000950.0
          }
        ],
        "repository_path": "{second}",
        "declared": "",
        "parent": "",
        "due_state": "",
        "days_in_column": null,
        "links": {
          "open_blockers": [],
          "children": 0,
          "children_done": 0
        },
        "check": null,
        "pull": null,
        "due_date": null,
        "spent": 0.0,
        "budget": null,
        "halted": "",
        "limited_until": null,
        "hold": {
          "stage": "spec",
          "detail": "a branch",
          "summary": "a branch"
        },
        "subagents": []
      },
      {
        "id": "AB-2",
        "title": "Other repository, second",
        "type": "feature",
        "branch": "",
        "repository": "second",
        "stage": "spec",
        "evidence_stage": "spec",
        "description": "",
        "labels": [
          "ui"
        ],
        "priority": "",
        "assignee": "",
        "due": "",
        "blocked": "",
        "archived": false,
        "rank": 0,
        "stage_since": "",
        "checklist": [
          0,
          0
        ],
        "open_questions": 0,
        "sessions": [],
        "runs": [],
        "repository_path": "{second}",
        "declared": "",
        "parent": "",
        "due_state": "",
        "days_in_column": null,
        "links": {
          "open_blockers": [],
          "children": 0,
          "children_done": 0
        },
        "check": {
          "passed": false,
          "commit": "fedcba9876543"
        },
        "pull": null,
        "due_date": null,
        "spent": 0,
        "budget": null,
        "halted": "",
        "limited_until": null,
        "hold": {
          "stage": "spec",
          "detail": "a branch",
          "summary": "a branch"
        },
        "subagents": []
      },
      {
        "id": "CF-1",
        "title": "Questions waiting",
        "type": "feature",
        "branch": "",
        "repository": "sample",
        "stage": "spec",
        "evidence_stage": "spec",
        "description": "- [x] one\n- [ ] two\n- [ ] three",
        "labels": [],
        "priority": "",
        "assignee": "",
        "due": "",
        "blocked": "",
        "archived": false,
        "rank": 0,
        "stage_since": "",
        "checklist": [
          1,
          3
        ],
        "open_questions": 3,
        "sessions": [],
        "runs": [],
        "repository_path": "{root}",
        "declared": "",
        "parent": "",
        "due_state": "",
        "days_in_column": null,
        "links": {
          "open_blockers": [],
          "children": 2,
          "children_done": 0
        },
        "check": null,
        "pull": null,
        "due_date": null,
        "spent": 0.5,
        "budget": 5.0,
        "halted": "agent failed (exit 1)",
        "limited_until": null,
        "hold": {
          "stage": "spec",
          "detail": "a branch",
          "summary": "a branch"
        },
        "subagents": []
      },
      {
        "id": "CF-3",
        "title": "Worked on main",
        "type": "feature",
        "branch": "main",
        "repository": "sample",
        "stage": "spec",
        "evidence_stage": "build",
        "description": "",
        "labels": [
          "agents"
        ],
        "priority": "low",
        "assignee": "",
        "due": "",
        "blocked": "",
        "archived": false,
        "rank": 0,
        "stage_since": "2026-09-20T08:00:00Z",
        "checklist": [
          0,
          0
        ],
        "open_questions": 0,
        "sessions": [],
        "runs": [],
        "repository_path": "{root}",
        "declared": "spec",
        "parent": "CF-1",
        "due_state": "",
        "days_in_column": 1,
        "links": {
          "open_blockers": [
            "CF-2"
          ],
          "children": 0,
          "children_done": 0
        },
        "check": null,
        "pull": null,
        "due_date": null,
        "spent": 0,
        "budget": 5.0,
        "halted": "",
        "limited_until": null,
        "hold": {
          "stage": "build",
          "detail": "a commit on main",
          "summary": "a commit on main"
        },
        "subagents": []
      }
    ],
    "build": [
      {
        "id": "CF-2",
        "title": "A bug in flight",
        "type": "bug",
        "branch": "feat/CF-2",
        "repository": "sample",
        "stage": "build",
        "evidence_stage": "build",
        "description": "A description long enough to be cut. A description long enough to be cut. A description long enough to be cut. A description long enough to be cut. A description long enough to be cut. A description long enough to be cut. A description long enough to be cut. A description long e…",
        "labels": [
          "ui",
          "agents"
        ],
        "priority": "high",
        "assignee": "alex",
        "due": "2026-10-10",
        "blocked": "waiting on design",
        "archived": false,
        "rank": 1,
        "stage_since": "2026-10-01T09:00:00Z",
        "checklist": [
          0,
          0
        ],
        "open_questions": 0,
        "sessions": [
          {
            "session_id": "s-rest",
            "state": "idle"
          }
        ],
        "runs": [
          {
            "id": "aaaaaaaaaaaa",
            "stage": "build",
            "iteration": 2,
            "loop": true,
            "max_iterations": 8,
            "attempt": 0,
            "agent": "",
            "started_at": 1790000500.0
          }
        ],
        "repository_path": "{root}",
        "declared": "",
        "parent": "CF-1",
        "due_state": "",
        "days_in_column": -10,
        "links": {
          "open_blockers": [],
          "children": 0,
          "children_done": 0
        },
        "check": {
          "passed": true,
          "commit": "1234567abcdef"
        },
        "pull": {
          "state": "open",
          "review": "approved",
          "ci": "failed",
          "head": "1234567abcdef",
          "url": "https://github.com/o/r/pull/2",
          "at": "1790000000.0"
        },
        "due_date": "2026-10-10",
        "spent": 4.25,
        "budget": 2.5,
        "halted": "",
        "limited_until": null,
        "hold": {
          "stage": "build",
          "detail": "a commit on feat/CF-2",
          "summary": "a commit on feat/CF-2"
        },
        "subagents": []
      }
    ],
    "review": [],
    "merged": []
  },
  "problems": [
    {
      "repository": "sample",
      "file": ".code-factory/tickets/broken/ticket.md",
      "path": "{root}/.code-factory/tickets/broken/ticket.md",
      "reason": "no front matter"
    }
  ],
  "totals": {
    "spec": 4,
    "build": 1,
    "review": 0,
    "merged": 0
  },
  "limits": {
    "spec": 1
  },
  "options": {
    "type": [
      "bug",
      "feature"
    ],
    "priority": [
      "high",
      "low"
    ],
    "label": [
      "agents",
      "ui"
    ],
    "assignee": [
      "alex"
    ],
    "repository": [
      "sample",
      "second"
    ]
  }
} satisfies Board
export const tickets = [
  {
    "runs": [],
    "spent": 0.5,
    "cost": {
      "total": 0.5,
      "review": null,
      "cache_read": null,
      "turns": null
    },
    "budget": 5.0,
    "default_budget": 5.0,
    "halted": "agent failed (exit 1)",
    "ticket": {
      "id": "CF-1",
      "title": "Questions waiting",
      "type": "feature",
      "branch": "",
      "e2e": "",
      "tests": "",
      "description": "- [x] one\n- [ ] two\n- [ ] three",
      "stage": "",
      "labels": "",
      "priority": "",
      "assignee": "",
      "due": "",
      "blocked": "",
      "archived": false,
      "rank": 0,
      "stage_since": "",
      "blocked_by": "",
      "caused_by": "",
      "parent": "",
      "budget": "",
      "parallel": "",
      "source": "",
      "steps": "",
      "pages": ""
    },
    "repository": "sample",
    "work_done": false,
    "checklist": [
      {
        "stage": "spec",
        "required": true,
        "present": false,
        "detail": "a branch"
      },
      {
        "stage": "build",
        "required": true,
        "present": false,
        "detail": "a branch"
      },
      {
        "stage": "review",
        "required": true,
        "present": false,
        "detail": "no branch declared"
      },
      {
        "stage": "merged",
        "required": true,
        "present": false,
        "detail": "main"
      },
      {
        "stage": "released",
        "required": false,
        "present": false,
        "detail": ".code-factory/releases/<version>.md"
      }
    ],
    "summary": {
      "gate": null,
      "verdict": "",
      "capture": null,
      "not_proven": []
    },
    "current_stage": "spec",
    "questions": [
      {
        "document": "spec.md",
        "index": 0,
        "text": "Which colour?",
        "answer": "blue",
        "answered_by": "",
        "choices": [],
        "several": false
      },
      {
        "document": "spec.md",
        "index": 1,
        "text": "Which size?",
        "answer": "",
        "answered_by": "",
        "choices": [],
        "several": false
      },
      {
        "document": "spec.md",
        "index": 2,
        "text": "Which name?",
        "answer": "",
        "answered_by": "",
        "choices": [],
        "several": false
      },
      {
        "document": "uat.md",
        "index": 0,
        "text": "Ship when?",
        "answer": "",
        "answered_by": "",
        "choices": [],
        "several": false
      }
    ],
    "documents": [
      {
        "stage": "requirements",
        "html": null
      },
      {
        "stage": "spec",
        "html": "<h1>BRD</h1>\n<p>Problem.</p>\n<h2>Open questions</h2>\n<ul>\n<li>Which colour?\nAnswer: blue</li>\n<li>Which size?</li>\n<li>Which name?\nAnswer: not indented, so not an answer</li>\n</ul>\n<h2>Next</h2>\n<ul>\n<li>not a question</li>\n</ul>\n"
      },
      {
        "stage": "uat",
        "html": "<h1>UAT</h1>\n<h3>Open Questions</h3>\n<ul>\n<li>Ship when?</li>\n</ul>\n"
      }
    ],
    "plan": null,
    "link": {
      "open_blockers": [],
      "blocks": [],
      "parent": "",
      "children": 2,
      "children_done": 0,
      "child_ids": [
        "CF-2",
        "CF-3"
      ]
    },
    "titles": {
      "CF-1": "Questions waiting",
      "CF-2": "A bug in flight",
      "CF-3": "Worked on main",
      "CF-4": "Archived",
      "CF-5": "Released already"
    },
    "stages_by_id": {
      "CF-1": "spec",
      "CF-3": "spec",
      "CF-4": "spec",
      "CF-5": "released",
      "CF-2": "build"
    },
    "linked": {
      "CF-2": {
        "repository": "sample",
        "title": "A bug in flight",
        "stage": "build"
      },
      "CF-3": {
        "repository": "sample",
        "title": "Worked on main",
        "stage": "spec"
      }
    },
    "description_html": "<ul>\n<li>[x] one</li>\n<li>[ ] two</li>\n<li>[ ] three</li>\n</ul>\n",
    "check": null,
    "check_log": "",
    "checks_configured": false,
    "activity": [],
    "checking": false,
    "month_budget": null,
    "subagents": [],
    "card": {
      "id": "CF-1",
      "title": "Questions waiting",
      "type": "feature",
      "branch": "",
      "repository": "sample",
      "stage": "spec",
      "evidence_stage": "spec",
      "description": "- [x] one\n- [ ] two\n- [ ] three",
      "labels": [],
      "priority": "",
      "assignee": "",
      "due": "",
      "blocked": "",
      "archived": false,
      "rank": 0,
      "stage_since": "",
      "checklist": [
        1,
        3
      ],
      "open_questions": 3,
      "sessions": [],
      "runs": [],
      "repository_path": "{root}",
      "declared": "",
      "parent": "",
      "due_state": "",
      "days_in_column": null,
      "links": {
        "open_blockers": [],
        "children": 2,
        "children_done": 0
      },
      "check": null,
      "pull": null,
      "due_date": null,
      "spent": 0.5,
      "budget": 5.0,
      "halted": "agent failed (exit 1)",
      "limited_until": null,
      "hold": {
        "stage": "spec",
        "detail": "a branch",
        "summary": "a branch"
      },
      "subagents": []
    },
    "columns": {
      "spec": null,
      "build": null,
      "review": null
    },
    "branch": "",
    "status": {
      "conflict": null,
      "capture": null
    }
  },
  {
    "runs": [
      {
        "id": "aaaaaaaaaaaa",
        "stage": "build",
        "iteration": 2,
        "loop": true,
        "started_at": 1790000500.0,
        "progress": {
          "tool_calls": null,
          "reads": null,
          "changes": null,
          "files": {
            "count": 3,
            "names": [
              ".code-factory/releases/0.1.0.md",
              ".code-factory/tickets/CF-2/activity.jsonl",
              "notes.md"
            ]
          },
          "tokens": null,
          "last_activity": null
        },
        "memory": null,
        "context_at": null
      }
    ],
    "spent": 4.25,
    "cost": {
      "total": 4.25,
      "review": null,
      "cache_read": null,
      "turns": null
    },
    "budget": 2.5,
    "default_budget": 5.0,
    "halted": "iteration cap reached (8)",
    "ticket": {
      "id": "CF-2",
      "title": "A bug in flight",
      "type": "bug",
      "branch": "feat/CF-2",
      "e2e": "",
      "tests": "",
      "description": "A description long enough to be cut. A description long enough to be cut. A description long enough to be cut. A description long enough to be cut. A description long enough to be cut. A description long enough to be cut. A description long enough to be cut. A description long enough to be cut. A description long enough to be cut. A description long enough to be cut. A description long enough to be cut. A description long enough to be cut.",
      "stage": "",
      "labels": "ui, agents",
      "priority": "high",
      "assignee": "alex",
      "due": "2026-10-10",
      "blocked": "waiting on design",
      "archived": false,
      "rank": 1,
      "stage_since": "2026-10-01T09:00:00Z",
      "blocked_by": "",
      "caused_by": "",
      "parent": "CF-1",
      "budget": "2.5",
      "parallel": "",
      "source": "",
      "steps": "",
      "pages": ""
    },
    "repository": "sample",
    "work_done": false,
    "checklist": [
      {
        "stage": "spec",
        "required": true,
        "present": true,
        "detail": "a branch"
      },
      {
        "stage": "build",
        "required": true,
        "present": false,
        "detail": "a commit on feat/CF-2"
      },
      {
        "stage": "review",
        "required": true,
        "present": false,
        "detail": "origin/feat/CF-2"
      },
      {
        "stage": "merged",
        "required": true,
        "present": false,
        "detail": "main"
      },
      {
        "stage": "released",
        "required": false,
        "present": false,
        "detail": ".code-factory/releases/<version>.md"
      }
    ],
    "summary": {
      "gate": {
        "held": true,
        "commit": "1234567abcdef",
        "tree": ""
      },
      "verdict": "",
      "capture": null,
      "not_proven": []
    },
    "current_stage": "build",
    "questions": [],
    "documents": [
      {
        "stage": "requirements",
        "html": null
      },
      {
        "stage": "mock",
        "html": null,
        "files": []
      },
      {
        "stage": "spec",
        "html": "<h1>BRD</h1>\n<p>Started.</p>\n"
      },
      {
        "stage": "uat",
        "html": null
      }
    ],
    "plan": null,
    "link": {
      "open_blockers": [],
      "blocks": [
        "CF-3"
      ],
      "parent": "CF-1",
      "children": 0,
      "children_done": 0,
      "child_ids": []
    },
    "titles": {
      "CF-1": "Questions waiting",
      "CF-2": "A bug in flight",
      "CF-3": "Worked on main",
      "CF-4": "Archived",
      "CF-5": "Released already"
    },
    "stages_by_id": {
      "CF-3": "spec",
      "CF-1": "spec",
      "CF-2": "build",
      "CF-4": "spec",
      "CF-5": "released"
    },
    "linked": {
      "CF-1": {
        "repository": "sample",
        "title": "Questions waiting",
        "stage": "spec"
      },
      "CF-3": {
        "repository": "sample",
        "title": "Worked on main",
        "stage": "spec"
      }
    },
    "description_html": "<p>A description long enough to be cut. A description long enough to be cut. A description long enough to be cut. A description long enough to be cut. A description long enough to be cut. A description long enough to be cut. A description long enough to be cut. A description long enough to be cut. A description long enough to be cut. A description long enough to be cut. A description long enough to be cut. A description long enough to be cut.</p>\n",
    "check": {
      "at": "2026-10-04T11:00:00Z",
      "commit": "1234567abcdef",
      "exit_code": 0,
      "log": "y.log",
      "tree": ""
    },
    "check_log": "",
    "checks_configured": false,
    "activity": [
      {
        "at": 1791111600.0,
        "sentence": "Checks passed on 1234567",
        "kind": "checks",
        "text": ""
      },
      {
        "at": 1791108000.0,
        "sentence": "Checks failed on abcdef1 with exit code 1",
        "kind": "checks",
        "text": ""
      }
    ],
    "checking": false,
    "month_budget": null,
    "subagents": [],
    "card": {
      "id": "CF-2",
      "title": "A bug in flight",
      "type": "bug",
      "branch": "feat/CF-2",
      "repository": "sample",
      "stage": "build",
      "evidence_stage": "build",
      "description": "A description long enough to be cut. A description long enough to be cut. A description long enough to be cut. A description long enough to be cut. A description long enough to be cut. A description long enough to be cut. A description long enough to be cut. A description long e…",
      "labels": [
        "ui",
        "agents"
      ],
      "priority": "high",
      "assignee": "alex",
      "due": "2026-10-10",
      "blocked": "waiting on design",
      "archived": false,
      "rank": 1,
      "stage_since": "2026-10-01T09:00:00Z",
      "checklist": [
        0,
        0
      ],
      "open_questions": 0,
      "sessions": [
        {
          "session_id": "s-rest",
          "state": "idle"
        }
      ],
      "runs": [
        {
          "id": "aaaaaaaaaaaa",
          "stage": "build",
          "iteration": 2,
          "loop": true,
          "max_iterations": 8,
          "attempt": 0,
          "agent": "",
          "started_at": 1790000500.0
        }
      ],
      "repository_path": "{root}",
      "declared": "",
      "parent": "CF-1",
      "due_state": "",
      "days_in_column": -10,
      "links": {
        "open_blockers": [],
        "children": 0,
        "children_done": 0
      },
      "check": {
        "passed": true,
        "commit": "1234567abcdef"
      },
      "pull": {
        "state": "open",
        "review": "approved",
        "ci": "failed",
        "head": "1234567abcdef",
        "url": "https://github.com/o/r/pull/2",
        "at": "1790000000.0"
      },
      "due_date": "2026-10-10",
      "spent": 4.25,
      "budget": 2.5,
      "halted": "",
      "limited_until": null,
      "hold": {
        "stage": "build",
        "detail": "a commit on feat/CF-2",
        "summary": "a commit on feat/CF-2"
      },
      "subagents": []
    },
    "columns": {
      "spec": null,
      "build": null,
      "review": null
    },
    "branch": "feat/CF-2",
    "status": {
      "conflict": {
        "tip": "dcf92c3f9bd63977895faf16a3de7cf8d416cc21"
      },
      "capture": null
    }
  },
  {
    "runs": [],
    "spent": 0,
    "cost": {
      "total": null,
      "review": null,
      "cache_read": null,
      "turns": null
    },
    "budget": 5.0,
    "default_budget": 5.0,
    "halted": "",
    "ticket": {
      "id": "CF-3",
      "title": "Worked on main",
      "type": "feature",
      "branch": "main",
      "e2e": "",
      "tests": "",
      "description": "",
      "stage": "spec",
      "labels": "agents",
      "priority": "low",
      "assignee": "",
      "due": "",
      "blocked": "",
      "archived": false,
      "rank": 0,
      "stage_since": "2026-09-20T08:00:00Z",
      "blocked_by": "CF-2",
      "caused_by": "",
      "parent": "CF-1",
      "budget": "",
      "parallel": "",
      "source": "",
      "steps": "",
      "pages": ""
    },
    "repository": "sample",
    "work_done": false,
    "checklist": [
      {
        "stage": "spec",
        "required": true,
        "present": true,
        "detail": "a branch"
      },
      {
        "stage": "build",
        "required": true,
        "present": false,
        "detail": "a commit on main"
      },
      {
        "stage": "review",
        "required": true,
        "present": false,
        "detail": "origin/main"
      },
      {
        "stage": "merged",
        "required": true,
        "present": false,
        "detail": "main"
      },
      {
        "stage": "released",
        "required": false,
        "present": false,
        "detail": ".code-factory/releases/<version>.md"
      }
    ],
    "summary": {
      "gate": null,
      "verdict": "",
      "capture": null,
      "not_proven": []
    },
    "current_stage": "spec",
    "questions": [],
    "documents": [
      {
        "stage": "requirements",
        "html": null
      },
      {
        "stage": "spec",
        "html": null
      },
      {
        "stage": "uat",
        "html": null
      }
    ],
    "plan": null,
    "link": {
      "open_blockers": [
        "CF-2"
      ],
      "blocks": [],
      "parent": "CF-1",
      "children": 0,
      "children_done": 0,
      "child_ids": []
    },
    "titles": {
      "CF-1": "Questions waiting",
      "CF-2": "A bug in flight",
      "CF-3": "Worked on main",
      "CF-4": "Archived",
      "CF-5": "Released already"
    },
    "stages_by_id": {
      "CF-5": "released",
      "CF-3": "spec",
      "CF-2": "build",
      "CF-1": "spec",
      "CF-4": "spec"
    },
    "linked": {
      "CF-1": {
        "repository": "sample",
        "title": "Questions waiting",
        "stage": "spec"
      },
      "CF-2": {
        "repository": "sample",
        "title": "A bug in flight",
        "stage": "build"
      }
    },
    "description_html": "",
    "check": null,
    "check_log": "",
    "checks_configured": false,
    "activity": [],
    "checking": false,
    "month_budget": null,
    "subagents": [],
    "card": {
      "id": "CF-3",
      "title": "Worked on main",
      "type": "feature",
      "branch": "main",
      "repository": "sample",
      "stage": "spec",
      "evidence_stage": "build",
      "description": "",
      "labels": [
        "agents"
      ],
      "priority": "low",
      "assignee": "",
      "due": "",
      "blocked": "",
      "archived": false,
      "rank": 0,
      "stage_since": "2026-09-20T08:00:00Z",
      "checklist": [
        0,
        0
      ],
      "open_questions": 0,
      "sessions": [],
      "runs": [],
      "repository_path": "{root}",
      "declared": "spec",
      "parent": "CF-1",
      "due_state": "",
      "days_in_column": 1,
      "links": {
        "open_blockers": [
          "CF-2"
        ],
        "children": 0,
        "children_done": 0
      },
      "check": null,
      "pull": null,
      "due_date": null,
      "spent": 0,
      "budget": 5.0,
      "halted": "",
      "limited_until": null,
      "hold": {
        "stage": "build",
        "detail": "a commit on main",
        "summary": "a commit on main"
      },
      "subagents": []
    },
    "columns": {
      "spec": null,
      "build": null,
      "review": null
    },
    "branch": "main",
    "status": {
      "conflict": {
        "tip": "dcf92c3f9bd63977895faf16a3de7cf8d416cc21"
      },
      "capture": null
    }
  },
  {
    "runs": [],
    "spent": 0,
    "cost": {
      "total": null,
      "review": null,
      "cache_read": null,
      "turns": null
    },
    "budget": 5.0,
    "default_budget": 5.0,
    "halted": "",
    "ticket": {
      "id": "CF-4",
      "title": "Archived",
      "type": "feature",
      "branch": "",
      "e2e": "",
      "tests": "",
      "description": "",
      "stage": "",
      "labels": "",
      "priority": "",
      "assignee": "",
      "due": "",
      "blocked": "",
      "archived": true,
      "rank": 0,
      "stage_since": "",
      "blocked_by": "",
      "caused_by": "",
      "parent": "",
      "budget": "",
      "parallel": "",
      "source": "",
      "steps": "",
      "pages": ""
    },
    "repository": "sample",
    "work_done": false,
    "checklist": [
      {
        "stage": "spec",
        "required": true,
        "present": false,
        "detail": "a branch"
      },
      {
        "stage": "build",
        "required": true,
        "present": false,
        "detail": "a branch"
      },
      {
        "stage": "review",
        "required": true,
        "present": false,
        "detail": "no branch declared"
      },
      {
        "stage": "merged",
        "required": true,
        "present": false,
        "detail": "main"
      },
      {
        "stage": "released",
        "required": false,
        "present": false,
        "detail": ".code-factory/releases/<version>.md"
      }
    ],
    "summary": {
      "gate": null,
      "verdict": "",
      "capture": null,
      "not_proven": []
    },
    "current_stage": "spec",
    "questions": [],
    "documents": [
      {
        "stage": "requirements",
        "html": null
      },
      {
        "stage": "spec",
        "html": null
      },
      {
        "stage": "uat",
        "html": null
      }
    ],
    "plan": null,
    "link": {
      "open_blockers": [],
      "blocks": [],
      "parent": "",
      "children": 0,
      "children_done": 0,
      "child_ids": []
    },
    "titles": {
      "CF-1": "Questions waiting",
      "CF-2": "A bug in flight",
      "CF-3": "Worked on main",
      "CF-4": "Archived",
      "CF-5": "Released already"
    },
    "stages_by_id": {
      "CF-5": "released",
      "CF-4": "spec",
      "CF-2": "build",
      "CF-3": "spec",
      "CF-1": "spec"
    },
    "linked": {},
    "description_html": "",
    "check": null,
    "check_log": "",
    "checks_configured": false,
    "activity": [],
    "checking": false,
    "month_budget": null,
    "subagents": [],
    "card": {
      "id": "CF-4",
      "title": "Archived",
      "type": "feature",
      "branch": "",
      "repository": "sample",
      "stage": "spec",
      "evidence_stage": "spec",
      "description": "",
      "labels": [],
      "priority": "",
      "assignee": "",
      "due": "",
      "blocked": "",
      "archived": true,
      "rank": 0,
      "stage_since": "",
      "checklist": [
        0,
        0
      ],
      "open_questions": 0,
      "sessions": [],
      "runs": [],
      "repository_path": "{root}",
      "declared": "",
      "parent": "",
      "due_state": "",
      "days_in_column": null,
      "links": {
        "open_blockers": [],
        "children": 0,
        "children_done": 0
      },
      "check": null,
      "pull": null,
      "due_date": null,
      "spent": 0,
      "budget": 5.0,
      "halted": "",
      "limited_until": null,
      "hold": {
        "stage": "spec",
        "detail": "a branch",
        "summary": "a branch"
      },
      "subagents": []
    },
    "columns": {
      "spec": null,
      "build": null,
      "review": null
    },
    "branch": "",
    "status": {
      "conflict": null,
      "capture": null
    }
  },
  {
    "runs": [],
    "spent": 0,
    "cost": {
      "total": null,
      "review": null,
      "cache_read": null,
      "turns": null
    },
    "budget": 5.0,
    "default_budget": 5.0,
    "halted": "",
    "ticket": {
      "id": "CF-5",
      "title": "Released already",
      "type": "feature",
      "branch": "",
      "e2e": "",
      "tests": "",
      "description": "",
      "stage": "",
      "labels": "",
      "priority": "",
      "assignee": "",
      "due": "",
      "blocked": "",
      "archived": false,
      "rank": 0,
      "stage_since": "",
      "blocked_by": "",
      "caused_by": "",
      "parent": "",
      "budget": "",
      "parallel": "",
      "source": "",
      "steps": "",
      "pages": ""
    },
    "repository": "sample",
    "work_done": false,
    "checklist": [
      {
        "stage": "spec",
        "required": true,
        "present": false,
        "detail": "a branch"
      },
      {
        "stage": "build",
        "required": true,
        "present": false,
        "detail": "a branch"
      },
      {
        "stage": "review",
        "required": true,
        "present": false,
        "detail": "no branch declared"
      },
      {
        "stage": "merged",
        "required": true,
        "present": false,
        "detail": "main"
      },
      {
        "stage": "released",
        "required": false,
        "present": true,
        "detail": "0.1.0.md"
      }
    ],
    "summary": {
      "gate": null,
      "verdict": "",
      "capture": null,
      "not_proven": []
    },
    "current_stage": "released",
    "questions": [],
    "documents": [
      {
        "stage": "requirements",
        "html": null
      },
      {
        "stage": "spec",
        "html": null
      },
      {
        "stage": "uat",
        "html": null
      }
    ],
    "plan": null,
    "link": {
      "open_blockers": [],
      "blocks": [],
      "parent": "",
      "children": 0,
      "children_done": 0,
      "child_ids": []
    },
    "titles": {
      "CF-1": "Questions waiting",
      "CF-2": "A bug in flight",
      "CF-3": "Worked on main",
      "CF-4": "Archived",
      "CF-5": "Released already"
    },
    "stages_by_id": {
      "CF-4": "spec",
      "CF-5": "released",
      "CF-1": "spec",
      "CF-2": "build",
      "CF-3": "spec"
    },
    "linked": {},
    "description_html": "",
    "check": null,
    "check_log": "",
    "checks_configured": false,
    "activity": [],
    "checking": false,
    "month_budget": null,
    "subagents": [],
    "card": {
      "id": "CF-5",
      "title": "Released already",
      "type": "feature",
      "branch": "",
      "repository": "sample",
      "stage": "released",
      "evidence_stage": "released",
      "description": "",
      "labels": [],
      "priority": "",
      "assignee": "",
      "due": "",
      "blocked": "",
      "archived": false,
      "rank": 0,
      "stage_since": "",
      "checklist": [
        0,
        0
      ],
      "open_questions": 0,
      "sessions": [],
      "runs": [],
      "repository_path": "{root}",
      "declared": "",
      "parent": "",
      "due_state": "",
      "days_in_column": null,
      "links": {
        "open_blockers": [],
        "children": 0,
        "children_done": 0
      },
      "check": null,
      "pull": null,
      "due_date": null,
      "spent": 0,
      "budget": 5.0,
      "halted": "",
      "limited_until": null,
      "hold": null,
      "subagents": []
    },
    "columns": {
      "spec": null,
      "build": null,
      "review": null
    },
    "branch": "",
    "status": {
      "conflict": null,
      "capture": null
    }
  },
  {
    "runs": [
      {
        "id": "eeeeeeeeeeee",
        "stage": "spec",
        "iteration": 3,
        "loop": true,
        "started_at": 1790000950.0,
        "progress": {
          "tool_calls": null,
          "reads": null,
          "changes": null,
          "files": {
            "count": 1,
            "names": [
              ".code-factory/tickets/AB-2/activity.jsonl"
            ]
          },
          "tokens": null,
          "last_activity": null
        },
        "memory": null,
        "context_at": null
      }
    ],
    "spent": 0.0,
    "cost": {
      "total": null,
      "review": null,
      "cache_read": null,
      "turns": null
    },
    "budget": null,
    "default_budget": null,
    "halted": "",
    "ticket": {
      "id": "AB-1",
      "title": "Other repository, first",
      "type": "feature",
      "branch": "",
      "e2e": "",
      "tests": "",
      "description": "",
      "stage": "",
      "labels": "",
      "priority": "",
      "assignee": "",
      "due": "",
      "blocked": "",
      "archived": false,
      "rank": 1,
      "stage_since": "",
      "blocked_by": "",
      "caused_by": "",
      "parent": "",
      "budget": "",
      "parallel": "",
      "source": "",
      "steps": "",
      "pages": ""
    },
    "repository": "second",
    "work_done": false,
    "checklist": [
      {
        "stage": "spec",
        "required": true,
        "present": false,
        "detail": "a branch"
      },
      {
        "stage": "build",
        "required": true,
        "present": false,
        "detail": "a branch"
      },
      {
        "stage": "review",
        "required": true,
        "present": false,
        "detail": "no branch declared"
      },
      {
        "stage": "merged",
        "required": true,
        "present": false,
        "detail": "main"
      },
      {
        "stage": "released",
        "required": false,
        "present": false,
        "detail": ".code-factory/releases/<version>.md"
      }
    ],
    "summary": {
      "gate": null,
      "verdict": "",
      "capture": null,
      "not_proven": []
    },
    "current_stage": "spec",
    "questions": [],
    "documents": [
      {
        "stage": "requirements",
        "html": null
      },
      {
        "stage": "spec",
        "html": "<h1>BRD</h1>\n<p>Started.</p>\n"
      },
      {
        "stage": "uat",
        "html": null
      }
    ],
    "plan": null,
    "link": {
      "open_blockers": [],
      "blocks": [],
      "parent": "",
      "children": 0,
      "children_done": 0,
      "child_ids": []
    },
    "titles": {
      "AB-1": "Other repository, first",
      "AB-2": "Other repository, second"
    },
    "stages_by_id": {
      "AB-1": "spec",
      "AB-2": "spec"
    },
    "linked": {},
    "description_html": "",
    "check": null,
    "check_log": "",
    "checks_configured": false,
    "activity": [],
    "checking": false,
    "month_budget": null,
    "subagents": [],
    "card": {
      "id": "AB-1",
      "title": "Other repository, first",
      "type": "feature",
      "branch": "",
      "repository": "second",
      "stage": "spec",
      "evidence_stage": "spec",
      "description": "",
      "labels": [],
      "priority": "",
      "assignee": "",
      "due": "",
      "blocked": "",
      "archived": false,
      "rank": 1,
      "stage_since": "",
      "checklist": [
        0,
        0
      ],
      "open_questions": 0,
      "sessions": [],
      "runs": [
        {
          "id": "eeeeeeeeeeee",
          "stage": "spec",
          "iteration": 3,
          "loop": true,
          "max_iterations": 12,
          "attempt": 0,
          "agent": "",
          "started_at": 1790000950.0
        }
      ],
      "repository_path": "{second}",
      "declared": "",
      "parent": "",
      "due_state": "",
      "days_in_column": null,
      "links": {
        "open_blockers": [],
        "children": 0,
        "children_done": 0
      },
      "check": null,
      "pull": null,
      "due_date": null,
      "spent": 0.0,
      "budget": null,
      "halted": "",
      "limited_until": null,
      "hold": {
        "stage": "spec",
        "detail": "a branch",
        "summary": "a branch"
      },
      "subagents": []
    },
    "columns": {
      "spec": null,
      "build": null,
      "review": null
    },
    "branch": "",
    "status": {
      "conflict": null,
      "capture": null
    }
  },
  {
    "runs": [],
    "spent": 0,
    "cost": {
      "total": null,
      "review": null,
      "cache_read": null,
      "turns": null
    },
    "budget": null,
    "default_budget": null,
    "halted": "",
    "ticket": {
      "id": "AB-2",
      "title": "Other repository, second",
      "type": "feature",
      "branch": "",
      "e2e": "",
      "tests": "",
      "description": "",
      "stage": "",
      "labels": "ui",
      "priority": "",
      "assignee": "",
      "due": "",
      "blocked": "",
      "archived": false,
      "rank": 0,
      "stage_since": "",
      "blocked_by": "",
      "caused_by": "",
      "parent": "",
      "budget": "",
      "parallel": "",
      "source": "",
      "steps": "",
      "pages": ""
    },
    "repository": "second",
    "work_done": false,
    "checklist": [
      {
        "stage": "spec",
        "required": true,
        "present": false,
        "detail": "a branch"
      },
      {
        "stage": "build",
        "required": true,
        "present": false,
        "detail": "a branch"
      },
      {
        "stage": "review",
        "required": true,
        "present": false,
        "detail": "no branch declared"
      },
      {
        "stage": "merged",
        "required": true,
        "present": false,
        "detail": "main"
      },
      {
        "stage": "released",
        "required": false,
        "present": false,
        "detail": ".code-factory/releases/<version>.md"
      }
    ],
    "summary": {
      "gate": {
        "held": false,
        "commit": "fedcba9876543",
        "tree": ""
      },
      "verdict": "",
      "capture": null,
      "not_proven": []
    },
    "current_stage": "spec",
    "questions": [],
    "documents": [
      {
        "stage": "requirements",
        "html": null
      },
      {
        "stage": "mock",
        "html": null,
        "files": []
      },
      {
        "stage": "spec",
        "html": "<h1>BRD</h1>\n<p>Started too.</p>\n"
      },
      {
        "stage": "uat",
        "html": null
      }
    ],
    "plan": null,
    "link": {
      "open_blockers": [],
      "blocks": [],
      "parent": "",
      "children": 0,
      "children_done": 0,
      "child_ids": []
    },
    "titles": {
      "AB-1": "Other repository, first",
      "AB-2": "Other repository, second"
    },
    "stages_by_id": {
      "AB-1": "spec",
      "AB-2": "spec"
    },
    "linked": {},
    "description_html": "",
    "check": {
      "at": "2026-10-04T10:00:00Z",
      "commit": "fedcba9876543",
      "exit_code": 2,
      "log": "{second}/logs/ot2.log",
      "tree": ""
    },
    "check_log": "line 6\nline 7\nline 8\nline 9\nline 10\nline 11\nline 12\nline 13\nline 14\nline 15\nline 16\nline 17\nline 18\nline 19\nline 20\nline 21\nline 22\nline 23\nline 24\nline 25\nline 26\nline 27\nline 28\nline 29\nline 30\nline 31\nline 32\nline 33\nline 34\nline 35\nline 36\nline 37\nline 38\nline 39\nline 40\nline 41\nline 42\nline 43\nline 44\nline 45",
    "checks_configured": false,
    "activity": [
      {
        "at": 1791108000.0,
        "sentence": "Checks failed on fedcba9 with exit code 2",
        "kind": "checks",
        "text": ""
      }
    ],
    "checking": false,
    "month_budget": null,
    "subagents": [],
    "card": {
      "id": "AB-2",
      "title": "Other repository, second",
      "type": "feature",
      "branch": "",
      "repository": "second",
      "stage": "spec",
      "evidence_stage": "spec",
      "description": "",
      "labels": [
        "ui"
      ],
      "priority": "",
      "assignee": "",
      "due": "",
      "blocked": "",
      "archived": false,
      "rank": 0,
      "stage_since": "",
      "checklist": [
        0,
        0
      ],
      "open_questions": 0,
      "sessions": [],
      "runs": [],
      "repository_path": "{second}",
      "declared": "",
      "parent": "",
      "due_state": "",
      "days_in_column": null,
      "links": {
        "open_blockers": [],
        "children": 0,
        "children_done": 0
      },
      "check": {
        "passed": false,
        "commit": "fedcba9876543"
      },
      "pull": null,
      "due_date": null,
      "spent": 0,
      "budget": null,
      "halted": "",
      "limited_until": null,
      "hold": {
        "stage": "spec",
        "detail": "a branch",
        "summary": "a branch"
      },
      "subagents": []
    },
    "columns": {
      "spec": null,
      "build": null,
      "review": null
    },
    "branch": "",
    "status": {
      "conflict": null,
      "capture": null
    }
  }
] satisfies TicketView[]
export const archive = [
  {
    "rows": [
      {
        "repository": "sample",
        "id": "CF-5",
        "title": "Released already",
        "type": "feature",
        "stage": "released",
        "archived": false,
        "archived_at": 1790001000.0,
        "release": "0.1.0"
      },
      {
        "repository": "sample",
        "id": "CF-4",
        "title": "Archived",
        "type": "feature",
        "stage": "spec",
        "archived": true,
        "archived_at": 0.0,
        "release": ""
      }
    ],
    "sort": "",
    "dir": "",
    "archived_count": 2
  },
  {
    "rows": [
      {
        "repository": "sample",
        "id": "CF-4",
        "title": "Archived",
        "type": "feature",
        "stage": "spec",
        "archived": true,
        "archived_at": 0.0,
        "release": ""
      },
      {
        "repository": "sample",
        "id": "CF-5",
        "title": "Released already",
        "type": "feature",
        "stage": "released",
        "archived": false,
        "archived_at": 1790001000.0,
        "release": "0.1.0"
      }
    ],
    "sort": "id",
    "dir": "asc",
    "archived_count": 2
  },
  {
    "rows": [
      {
        "repository": "sample",
        "id": "CF-5",
        "title": "Released already",
        "type": "feature",
        "stage": "released",
        "archived": false,
        "archived_at": 1790001000.0,
        "release": "0.1.0"
      },
      {
        "repository": "sample",
        "id": "CF-4",
        "title": "Archived",
        "type": "feature",
        "stage": "spec",
        "archived": true,
        "archived_at": 0.0,
        "release": ""
      }
    ],
    "sort": "title",
    "dir": "desc",
    "archived_count": 2
  },
  {
    "rows": [
      {
        "repository": "sample",
        "id": "CF-5",
        "title": "Released already",
        "type": "feature",
        "stage": "released",
        "archived": false,
        "archived_at": 1790001000.0,
        "release": "0.1.0"
      }
    ],
    "sort": "",
    "dir": "",
    "archived_count": 2
  },
  {
    "rows": [],
    "sort": "",
    "dir": "",
    "archived_count": 2
  }
] satisfies Archive[]
export const flows = [
  {
    "range": "7d",
    "since": 1789396200.0,
    "now": 1790001000.0,
    "merged": [
      {
        "repository": "sample",
        "pull": 7,
        "url": null,
        "branch": "ticket/cf-50",
        "ticket": "CF-50",
        "title": "Idea 50",
        "at": 1790000240.0,
        "lead": 180.0,
        "from": "filed",
        "autonomy": "unknown",
        "reverted": false,
        "fixes": [],
        "checks": "none"
      }
    ],
    "lead": {
      "median": 180.0,
      "p85": 180.0,
      "p95": 180.0,
      "count": 1
    },
    "completion": {
      "started": 0,
      "merged": 0
    },
    "cost": {
      "median": null,
      "estimated": false,
      "count": 0,
      "of": 1
    },
    "autonomy": {
      "share": null,
      "autonomous": 0,
      "assisted": 0,
      "unknown": 1
    },
    "columns": {
      "spec": 4320.0,
      "build": null,
      "review": null
    },
    "in_flight": 0,
    "stuck_after": 86400.0,
    "stuck": [],
    "agents": [
      {
        "agent": "the default agent",
        "model": "opus",
        "connection": "",
        "runs": 1,
        "finished": 1,
        "failed": 0,
        "stopped": 0,
        "running": 0,
        "endings": [],
        "tokens": null,
        "cost": 0.2
      }
    ]
  },
  {
    "range": "24h",
    "since": 1789914600.0,
    "now": 1790001000.0,
    "merged": [
      {
        "repository": "sample",
        "pull": 7,
        "url": null,
        "branch": "ticket/cf-50",
        "ticket": "CF-50",
        "title": "Idea 50",
        "at": 1790000240.0,
        "lead": 180.0,
        "from": "filed",
        "autonomy": "unknown",
        "reverted": false,
        "fixes": [],
        "checks": "none"
      }
    ],
    "lead": {
      "median": 180.0,
      "p85": 180.0,
      "p95": 180.0,
      "count": 1
    },
    "completion": {
      "started": 0,
      "merged": 0
    },
    "cost": {
      "median": null,
      "estimated": false,
      "count": 0,
      "of": 1
    },
    "autonomy": {
      "share": null,
      "autonomous": 0,
      "assisted": 0,
      "unknown": 1
    },
    "columns": {
      "spec": 4320.0,
      "build": null,
      "review": null
    },
    "in_flight": 0,
    "stuck_after": 86400.0,
    "stuck": [],
    "agents": [
      {
        "agent": "the default agent",
        "model": "opus",
        "connection": "",
        "runs": 1,
        "finished": 1,
        "failed": 0,
        "stopped": 0,
        "running": 0,
        "endings": [],
        "tokens": null,
        "cost": 0.2
      }
    ]
  },
  {
    "range": "30d",
    "since": 1787409000.0,
    "now": 1790001000.0,
    "merged": [
      {
        "repository": "sample",
        "pull": 7,
        "url": null,
        "branch": "ticket/cf-50",
        "ticket": "CF-50",
        "title": "Idea 50",
        "at": 1790000240.0,
        "lead": 180.0,
        "from": "filed",
        "autonomy": "unknown",
        "reverted": false,
        "fixes": [],
        "checks": "none"
      }
    ],
    "lead": {
      "median": 180.0,
      "p85": 180.0,
      "p95": 180.0,
      "count": 1
    },
    "completion": {
      "started": 4,
      "merged": 0
    },
    "cost": {
      "median": null,
      "estimated": false,
      "count": 0,
      "of": 1
    },
    "autonomy": {
      "share": null,
      "autonomous": 0,
      "assisted": 0,
      "unknown": 1
    },
    "columns": {
      "spec": 4320.0,
      "build": null,
      "review": null
    },
    "in_flight": 0,
    "stuck_after": 86400.0,
    "stuck": [],
    "agents": [
      {
        "agent": "the default agent",
        "model": "opus",
        "connection": "",
        "runs": 5,
        "finished": 5,
        "failed": 0,
        "stopped": 0,
        "running": 0,
        "endings": [],
        "tokens": null,
        "cost": 4.5
      },
      {
        "agent": "the default agent",
        "model": "",
        "connection": "",
        "runs": 1,
        "finished": 1,
        "failed": 0,
        "stopped": 0,
        "running": 0,
        "endings": [],
        "tokens": null,
        "cost": 0.7
      }
    ]
  }
] satisfies Flow[]
export const inbox = {
  "main": [],
  "questions": [
    {
      "since": 1790001000.0,
      "kind": "",
      "reason": "",
      "note": "",
      "count": 0,
      "images": [],
      "ticket": {
        "repository": "sample",
        "id": "CF-11",
        "title": "Pick a palette"
      },
      "question": {
        "document": "spec.md",
        "index": 0,
        "text": "Which colour?",
        "choices": [],
        "several": false
      },
      "session": null,
      "request": null,
      "memory": null,
      "main": null,
      "diagnosis": null
    }
  ],
  "permissions": [
    {
      "since": 1790000880.0,
      "kind": "permission",
      "reason": "Bash npm test --watch",
      "note": "allowed 2 of 3 times before",
      "count": 0,
      "images": [],
      "ticket": {
        "repository": "sample",
        "id": "CF-5",
        "title": "Export a report"
      },
      "question": null,
      "session": null,
      "request": {
        "id": "0123456789ab",
        "tool": "Bash",
        "summary": "npm test --watch"
      },
      "memory": null,
      "main": null,
      "diagnosis": null
    }
  ],
  "rules": [
    {
      "since": null,
      "kind": "rule",
      "reason": "Bash uv run pytest",
      "note": "",
      "count": 5,
      "images": [],
      "ticket": null,
      "question": null,
      "session": null,
      "request": null,
      "memory": null,
      "main": null,
      "diagnosis": null
    }
  ],
  "memory": [],
  "sessions": [
    {
      "since": 1790000821.0,
      "kind": "",
      "reason": "",
      "note": "",
      "count": 0,
      "images": [],
      "ticket": null,
      "question": null,
      "session": {
        "session_id": "s-block",
        "cwd": "{root}",
        "action": {
          "tool": "Edit",
          "summary": "/x/a.py"
        }
      },
      "request": null,
      "memory": null,
      "main": null,
      "diagnosis": null
    }
  ],
  "stopped": [
    {
      "since": 1789923240.0,
      "kind": "",
      "reason": "no progress in 3 iterations",
      "note": "",
      "count": 0,
      "images": [],
      "ticket": {
        "repository": "sample",
        "id": "CF-7",
        "title": "Rewrite the importer"
      },
      "question": null,
      "session": null,
      "request": null,
      "memory": null,
      "main": null,
      "diagnosis": null
    }
  ],
  "screens": [
    {
      "since": 1790000400.0,
      "kind": "screens",
      "reason": "e9d00393a69552ae",
      "note": "",
      "count": 0,
      "images": [
        "tickets-light.png",
        "tickets-dark.png"
      ],
      "ticket": {
        "repository": "sample",
        "id": "CF-9",
        "title": "New sidebar"
      },
      "question": null,
      "session": null,
      "request": null,
      "memory": null,
      "main": null,
      "diagnosis": null
    }
  ],
  "mergeable": [
    {
      "since": 1790000200.0,
      "kind": "merge",
      "reason": "https://github.com/o/r/pull/12",
      "note": "",
      "count": 0,
      "images": [],
      "ticket": {
        "repository": "sample",
        "id": "CF-12",
        "title": "Audit log"
      },
      "question": null,
      "session": null,
      "request": null,
      "memory": null,
      "main": null,
      "diagnosis": null
    }
  ],
  "failing": [
    {
      "since": 1790000300.0,
      "kind": "failing",
      "reason": "https://github.com/o/r/pull/13",
      "note": "",
      "count": 0,
      "images": [],
      "ticket": {
        "repository": "sample",
        "id": "CF-13",
        "title": "Retry uploads"
      },
      "question": null,
      "session": null,
      "request": null,
      "memory": null,
      "main": null,
      "diagnosis": null
    }
  ],
  "reviews": [
    {
      "since": 1789828200.0,
      "kind": "",
      "reason": "",
      "note": "",
      "count": 0,
      "images": [],
      "ticket": {
        "repository": "sample",
        "id": "CF-12",
        "title": "Audit log"
      },
      "question": null,
      "session": null,
      "request": null,
      "memory": null,
      "main": null,
      "diagnosis": null
    }
  ],
  "diagnoses": [],
  "count": 7,
  "latest": "CF-11 asks: Which colour?",
  "push": null,
  "next_up": {
    "section": "stopped",
    "index": 0
  }
} satisfies Inbox
