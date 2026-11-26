"""The `demo` sample's records about its tickets.

Its documents, questions, memory, agents, reviews, releases, sessions, prices, checks, the
scorer's answers and the owner's comments. Plain data, as `demo/__init__.py` says.
"""

from code_factory.sample.models.demo.tickets import DemoSession

_ISSUE_PY = "src/gift_cards/issue.py"

_ADDRESS_TS = "src/checkout/address.ts"

_STAGING_MOVE = "Move staging to the new cluster"

_CHECKOUT_ADDRESS = "Checkout keeps the address after a failed payment"

_GIFT_CARD_CODE = "Issue a gift card code on purchase"

# Documents by the title of the ticket that holds them.
DEMO_DOCUMENTS: dict[str, dict[str, str]] = {
    "Gift cards": {
        "requirements": (
            "# Gift cards\n\n## Requirements\n\n"
            "| ID | Requirement | Named check |\n|---|---|---|\n"
            "| GC-1 | A purchased card has a unique 16 character code | test_codes_are_unique |\n"
            "| GC-2 | A card pays part or all of an order | test_partial_payment |\n"
            "| GC-3 | A card's balance never goes below zero | test_no_negative_balance |\n"
        ),
        "spec": (
            "# Spec\n\nCustomers buy a gift card for a value and pay with it later.\n\n"
            "## Clauses\n\n- GC-1: one code per card, 16 characters, no ambiguous letters\n"
            "- GC-2: the card is spent first, the rest goes to the card on file\n\n"
            "## Open questions\n\n- Do cards expire?\n"
        ),
    },
    _GIFT_CARD_CODE: {
        "spec": "# Spec\n\nIssue the code once the payment settles, never before.\n",
        "uat": "# UAT\n\n1. Buy a card for 50.\n2. The confirmation shows a code.\n",
    },
    _CHECKOUT_ADDRESS: {
        "spec": "# Spec\n\nKeep every address field across a declined payment.\n",
    },
    "Export orders as CSV": {
        "spec": "# Spec\n\nOne row per paid order, in the shop's timezone.\n",
        "uat": "# UAT\n\n1. Export last month.\n2. The totals match the dashboard.\n",
    },
    "Invoice numbers have no gaps": {
        "spec": "# Spec\n\nTake invoice numbers from one sequence inside the payment.\n",
    },
}

# The questions agents ask, in the shape `ask_question` takes: a topic, the question, two to four
# choices (label, recommended, description, preview), pick-many or not, and the document.
DEMO_QUESTIONS: tuple[dict[str, object], ...] = (
    {
        "title": "Gift cards",
        "topic": "Expiry",
        "text": "Do gift cards expire?",
        "document": "spec",
        "choices": (
            (
                "Never",
                True,
                "The law in most of our markets forbids an expiry under five years.",
                "",
            ),
            (
                "After five years",
                False,
                "Allowed everywhere we sell, but needs a reminder email.",
                "",
            ),
        ),
    },
    {
        "title": "Pay part of an order with a gift card",
        "topic": "Spend order",
        "text": "Which is spent first when an order has a gift card and a coupon?",
        "choices": (
            ("The coupon, then the card", True, "The customer keeps more of the card.", ""),
            ("The card, then the coupon", False, "Simpler totals; the coupon may go unused.", ""),
        ),
    },
    {
        "title": _STAGING_MOVE,
        "topic": "Rollback",
        "text": "Keep the old staging running until the move is checked?",
        "choices": (
            (
                "Keep it for a week",
                True,
                "A rollback stays one command; costs a week of hosting.",
                "",
            ),
            ("Remove it now", False, "Saves the cost; a rollback means rebuilding it.", ""),
        ),
    },
    {
        "title": "Wishlist shared by link",
        "topic": "Share scope",
        "text": "What may someone with the link do to the wishlist?",
        "several": True,
        "choices": (
            ("See the items", True, "The point of sharing it.", ""),
            (
                "See prices",
                False,
                "Useful for gifts, but shows what the owner paid attention to.",
                "",
            ),
            ("Mark an item bought", False, "Stops two people buying the same gift.", ""),
        ),
    },
    {
        "title": "Export orders as CSV",
        "topic": "Columns",
        "text": "Which layout should the export use?",
        "choices": (
            (
                "One row per order",
                True,
                "Totals add up in any spreadsheet; items are joined in one cell.",
                'order,date,total,items\n1042,2026-11-02,58.00,"Mug x2; Card"',
            ),
            (
                "One row per item",
                False,
                "Easy to pivot by product; an order's total repeats on each row.",
                "order,date,item,qty,price\n1042,2026-11-02,Mug,2,19.00\n1042,2026-11-02,Card,1,20.00",
            ),
        ),
    },
)

# Approved entries first, then the proposals that wait in the Inbox.
DEMO_MEMORY: tuple[dict[str, str], ...] = (
    {
        "kind": "rule",
        "statement": "Money is stored in integer cents, never floats",
        "why": "A float total was a cent off on every tenth order",
        "source": "conversation",
    },
    {
        "kind": "decision",
        "statement": "Payments go through the provider's hosted fields only",
        "why": "Card numbers never touch our servers",
        "source": "CF-1",
    },
    {
        "kind": "lesson",
        "statement": "Migrations that add a column with a default run in two steps",
        "why": "A single step locked the orders table for four minutes",
        "source": "CF-4",
    },
)
DEMO_PROPOSALS: tuple[dict[str, str], ...] = (
    {
        "kind": "lesson",
        "statement": "Read the shop's timezone from settings, never from the server",
        "why": "Coupons expired at midnight UTC instead of the shop's midnight",
        "source": "CF-10",
    },
)

DEMO_CONNECTIONS: tuple[dict[str, str], ...] = (
    {"name": "anthropic", "kind": "anthropic", "key_env": "ANTHROPIC_DEMO_API_KEY"},
    {"name": "local", "kind": "ollama"},
)
DEMO_AGENTS: tuple[dict[str, object], ...] = (
    {
        "name": "builder",
        "runtime": "claude",
        "connection": "anthropic",
        "model": "claude-sonnet-5-5",
        "roles": ["spec", "build"],
        "max_daily_usd": 20,
    },
    {
        "name": "reviewer",
        "runtime": "claude",
        "connection": "anthropic",
        "model": "claude-opus-5-5",
        "roles": ["review"],
        "max_daily_usd": 10,
    },
)

# (ticket title, verdict, summary, findings as (severity, text, path, line)).
DEMO_REVIEWS: tuple[tuple[str, str, str, tuple[tuple[str, str, str, int], ...]], ...] = (
    (
        _GIFT_CARD_CODE,
        "pass",
        "Codes come from the secure generator and the uniqueness test covers collisions.",
        (),
    ),
    (
        _CHECKOUT_ADDRESS,
        "changes",
        "The fields survive a decline, but the saved address is never cleared after success.",
        (
            (
                "major",
                "Clear the kept address once the order is paid",
                _ADDRESS_TS,
                1,
            ),
        ),
    ),
)

# (version, published): the published one names the released tickets, the draft the merged ones.
DEMO_RELEASES: tuple[tuple[str, bool], ...] = (("1.3.0", True), ("1.4.0", False))

_CHECKOUT_SESSION = DemoSession(
    session_id="demo-checkout-address",
    ticket=_CHECKOUT_ADDRESS,
    prompt="Keep the checkout address when a payment is declined",
    tools=(
        ("Read", _ADDRESS_TS),
        ("Edit", _ADDRESS_TS),
        ("Bash", "pnpm test checkout"),
    ),
    messages=((5200, 900, 42000, 3100), (2100, 1400, 51000, 900), (1800, 600, 53000, 0)),
)

DEMO_SESSIONS: tuple[DemoSession, ...] = (
    _CHECKOUT_SESSION,
    DemoSession(
        session_id="demo-gift-card-issue",
        ticket=_GIFT_CARD_CODE,
        prompt="Issue a gift card code once the payment settles",
        tools=(
            ("Read", _ISSUE_PY),
            ("Write", _ISSUE_PY),
            ("Bash", "uv run pytest tests/gift_cards"),
        ),
        messages=((6100, 2300, 38000, 4200), (2400, 1900, 47000, 600)),
    ),
    DemoSession(
        session_id="demo-gift-card-redeem",
        ticket="Pay part of an order with a gift card",
        prompt="Spend the gift card first, then the card on file",
        tools=(("Read", "src/gift_cards/redeem.py"), ("Grep", "balance")),
        messages=((4300, 800, 22000, 2900),),
        ended=False,
    ),
    DemoSession(
        session_id="demo-staging-move",
        ticket=_STAGING_MOVE,
        prompt=_STAGING_MOVE,
        tools=(("Read", "deploy/staging.yml"), ("Bash", "kubectl get nodes")),
        messages=((3900, 700, 18000, 2500), (1500, 500, 21000, 0)),
        model="claude-haiku-5-5",
    ),
    DemoSession(
        session_id="demo-search-rank",
        ticket="Search ranks in-stock products first",
        prompt="Rank in-stock products above the rest",
        tools=(("Read", "src/search/rank.py"), ("Edit", "src/search/rank.py")),
        messages=((5000, 1600, 30000, 3300),),
        ended=False,
    ),
)

# Dollars per million tokens: input, output, cache read, cache write. The runtime reports the cost
# of a session from these, as its own `cost-state` record does.
DEMO_PRICES: dict[str, tuple[float, float, float, float]] = {
    "claude-sonnet-5-5": (3.0, 15.0, 0.3, 3.75),
    "claude-opus-5-5": (15.0, 75.0, 1.5, 18.75),
    "claude-haiku-5-5": (1.0, 5.0, 0.1, 1.25),
}

# The logs use the gate's grammar so the Flow page can show timing and budget examples.
DEMO_CHECKS: dict[str, str] = {
    "shop-api": "echo 'gate: prepare passed in 2s'; echo 'gate: pytest passed in 18s'",
    "web": "echo 'gate: static passed in 4s'; echo 'gate: web passed in 102s'",
    "infra": "echo 'gate: static passed in 4s'; echo 'gate: pytest failed (exit 1)'; false",
}

# The question every repository's config asks of its sessions, and the scorer's answers about the
# demo's sessions: (session id, answer, evidence).
DEMO_SCORER = (
    "test-first",
    "Did the session see a test fail before it changed the code?",
    "build",
)
DEMO_ANSWERS: tuple[tuple[str, str, str], ...] = (
    ("demo-checkout-address", "yes", "pnpm test checkout failed before the edit to address.ts"),
    ("demo-gift-card-issue", "yes", "pytest tests/gift_cards failed, then the code was written"),
    ("demo-staging-move", "no", "the manifest changed with no test run"),
    ("demo-search-rank", "no", "rank.py was edited before any test ran"),
)

# The owner's comments: (ticket title, text, path, line); an empty path is about the ticket.
DEMO_COMMENTS: tuple[tuple[str, str, str, int], ...] = (
    (
        _CHECKOUT_ADDRESS,
        "Also keep the delivery notes field, support hears about it weekly.",
        "",
        0,
    ),
    (
        _GIFT_CARD_CODE,
        "Leave out 0, O, 1 and I so a code read over the phone is never ambiguous.",
        _ISSUE_PY,
        1,
    ),
)

# The open pull requests' sizes as GitHub would count them: (additions, deletions, changed files).
# One is past what a review reads well, so the board's size signal has something to show.
DEMO_PULL_SIZES: dict[str, tuple[int, int, int]] = {
    _GIFT_CARD_CODE: (86, 12, 4),
    "Rotate the payment provider keys every 90 days": (1240, 380, 27),
}
