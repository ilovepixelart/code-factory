# Push and reply

How the push pass turns waiting Inbox items into delivered messages, and how a reply link answers a permission request or a question without the sign-in.

Source: `src/code_factory/push/module.py`, `src/code_factory/push/service.py`, `src/code_factory/push/rules.py`, `src/code_factory/push/repository.py`, `src/code_factory/push/adapters.py`, `src/code_factory/push/routes.py`, `src/code_factory/platform/web/guard.py`, `src/code_factory/runs/service/permissions.py`, `web/src/router.ts`

```mermaid
sequenceDiagram
    autonumber
    participant Push as PushService (background task push)
    participant DB as push tables
    participant Inbox as InboxService
    participant Target as ntfy or webhook target
    actor Owner as Owner's phone
    participant Route as /api/reply/{token}
    participant Perm as PermissionService
    participant Talk as TalkService

    loop every CODE_FACTORY_PUSH_SECONDS (default 5), while the board has a base URL
        Push->>DB: target()
        Push->>Inbox: page()
        Push->>Push: messages(page): main, questions, permissions, screens, sessions, stopped, failing, mergeable
        Push->>DB: keep_only_sent(waiting digests), forget tokens older than 24 h
        loop each message whose digest was not sent
            Push->>DB: claim(digest), skipped when another pass holds it
            opt a permission request or a question
                Push->>Push: token = 32 random bytes, hex
                Push->>DB: mint(sha256(token), request or question), replacing an earlier token
            end
            Push->>Target: POST text or JSON, link {board}/inbox at the item's anchor, reply {board}/reply/{token}
            alt 2xx
                Target-->>Push: taken
            else error or no answer
                Push->>DB: unclaim(digest), set_failure(now, problem)
                Note over Push,DB: the pass stops at the first failure
            end
        end
        Push->>DB: clear_failure()
    end
    Target->>Owner: notification with the reply link
    Owner->>Route: GET /api/reply/{token} (the /reply/{token} page)
    Route->>Push: read(token)
    Push->>DB: find(sha256(token)), still within 540 s (request) or 24 h (question)
    Push->>Inbox: page(), the item must still wait
    Push-->>Owner: ticket, title, tool, summary, time, or the question and its choices
    Owner->>Route: POST /api/reply/{token} {verdict} or {choices, answer}
    Route->>Push: press(token, verdict, choices, answer)
    Push->>Push: checks the reply before spending (press allow or deny, bad_reply)
    Push->>DB: spend(sha256(token)), deleted whatever happens next
    alt permission request
        Push->>Perm: answer(request, allow, by owner:owner)
        Push-->>Owner: Allowed or Denied
    else question
        Push->>Talk: answer_shown(ticket, document, index, text, Reply, channel reply)
        Push-->>Owner: Answered
    end
```

## Notes

- Every link failure answers 404 with one sentence, `this link was used, has expired or is not known`, so a holder cannot tell a used token from an expired or unknown one. A refused permission answer (`NotFoundError`, `ConflictError`) is turned into the same 404.
- A GET changes nothing (link scanners and notification previews fetch links); only the POST answers and spends the token.
- The guard lets `GET` and `POST` on `/api/reply/<64 hex>` through without the owner's cookie; the origin and JSON rules still apply to the POST.
- Only the token's SHA-256 digest is stored. A request token answers for 540 s (the hook's wait), a question token for 86 400 s.
- Only messages for permissions and questions carry a reply link; every other section's message links to the Inbox only.
- A message names its kind, ticket and Inbox anchor, nothing else an item holds. Delivery uses no proxy and follows no redirect; timeout 3 s, connect 2 s. A plain `http://` target is refused unless its host is `localhost`, `127.0.0.1` or `::1`.
- The Inbox header shows the target's host and the last failure (`PushService.summary`, reported to `InboxService` at start).
- The `sessions` section is in the pushed list, but the Inbox has no source for it yet, so it never sends.
