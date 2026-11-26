# Inbox

How `GET /api/inbox` is assembled from the module that owns each section, and what the badge counts.

Source: `src/code_factory/inbox/routes.py`, `src/code_factory/inbox/service/__init__.py`, `src/code_factory/inbox/service/neighbours.py`, `src/code_factory/inbox/rules.py`, `src/code_factory/inbox/models.py`, `src/code_factory/platform/web/conditional.py`, `src/code_factory/push/module.py`, `src/code_factory/push/service.py`

```mermaid
sequenceDiagram
    autonumber
    participant Page as Inbox page
    participant Route as GET /api/inbox
    participant Inbox as InboxService
    participant Sources as InboxSources
    participant Checks as CheckService
    participant Talk as TalkService
    participant Perm as PermissionService
    participant Memory as MemoryService
    participant Runs as RunService and QueueService
    participant Screens as ScreensService
    participant Delivery as DeliveryService and SettingsService
    participant Tickets as TicketService
    participant Push as PushService

    Page->>Route: GET, If-None-Match the last ETag
    Route->>Inbox: page()
    Inbox->>Sources: sections()
    Sources->>Checks: failing_default_branches() for main
    Sources->>Talk: list(status open), 100 a page until no cursor, for questions
    Sources->>Perm: answered_counts(), pending(now) for permissions (stale ones expired first)
    Sources->>Perm: suggested() for rules
    Sources->>Memory: list(status proposed) for memory
    Note over Sources: sessions is always empty, no source yet
    Sources->>Runs: runs_since(now - 30 days), latest per ticket with a halted reason, for stopped
    Sources->>Runs: QueueService.plan(), notes starting not started, for stopped
    Sources->>Screens: waiting() for screens
    Sources->>Delivery: open_pulls(): ci failed to failing, green to mergeable unless merge_approval is false
    Note over Sources: reviews is always empty, no source yet
    Sources->>Tickets: list_diagnoses() for diagnoses
    Sources->>Tickets: get(ticket) once per ticket for each item's ref, a missing ticket gives no ref
    Sources-->>Inbox: twelve sections
    Inbox->>Inbox: hide_covered: drop stopped and failing items of a ticket with a question, screens or merge item
    Inbox->>Inbox: oldest_first per section, diagnoses newest first
    Inbox->>Push: summary(): target host and last failure, none without a target
    Inbox->>Inbox: build_page: sections in order, count, latest, next_up, push
    Inbox-->>Route: page
    alt the ETag matches If-None-Match
        Route-->>Page: 304, no body
    else
        Route-->>Page: 200 JSON, ETag, Cache-Control no-cache
    end
```

## Notes

- Sections, in page order: `main`, `questions`, `permissions`, `rules`, `memory`, `sessions`, `stopped`, `screens`, `mergeable`, `failing`, `reviews`, `diagnoses` (`SECTIONS` in `inbox/models.py`).
- Counted: `main`, `questions`, `permissions`, `screens`, `sessions`, `stopped`, `failing`, `mergeable` (`COUNTED`). `rules`, `memory`, `reviews` and `diagnoses` are shown and never counted.
- `count` is the number of items in the counted sections after `hide_covered`; `latest` is the sentence of the newest counted item (an item with no time counts as oldest); `next_up` names the section and index of the oldest counted item. `GET /api/inbox/count` answers `count` and `latest` from the same page.
- A pull request is green when its CI passed or has none, it is not a draft, and its head is the head that was shipped. It joins `mergeable` only while the repository's `[agents] merge_approval` is not false; a repository whose settings cannot be judged counts as waiting.
- A stopped item comes from a run of the last 30 days that ended with a halted reason (only the ticket's latest run counts) or from a follower queue note `not started: <why>`; an item whose ticket no longer exists is dropped.
- Items of every section except `main`, `rules` and `memory` carry the ticket they are about.
- Not built: `sessions` and `reviews` have no source; both are always empty, though `sessions` is in `COUNTED` and the push list.
- The page is built from scratch on every request, the ETag only saves the body; the push pass reads the same `page()` every 5 s.
