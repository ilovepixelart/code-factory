# A ticket's ETag tags its fields

`GET /api/tickets/{repository}/{id}` sends an `ETag` over the page's `ticket` object only, and
`PATCH` with that tag in `If-Match` applies only while the fields are unchanged, else 412.

**Why.** The page also holds each stage's seconds measured against the clock, so a tag of the whole
page changes every second and could never be sent back. A strong tag is required: RFC 9110 compares
`If-Match` strongly, so a weak tag never matches.

**What follows.** The ticket page is not answered 304; the board and the Inbox, which hold no clock,
are. `If-Match` is optional: without it an edit applies as before. Code: `board/routes.py`,
`ticket_writes/routes.py`, `platform/web/conditional.py`.
