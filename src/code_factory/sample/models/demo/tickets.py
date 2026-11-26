"""The `demo` sample's tickets: what the board holds, in filing order.

Plain data, as `demo/__init__.py` says.
"""

from dataclasses import dataclass
from enum import StrEnum

_GIFT_CARDS = "Gift cards"


class Stage(StrEnum):
    """Where a demo ticket's git facts put it."""

    SPEC = "spec"  # no branch
    BUILD = "build"  # a local branch with a commit
    REVIEW = "review"  # the branch pushed, an open pull request
    MERGED = "merged"  # merged into main by a pull request
    RELEASED = "released"  # merged, then named by the published release


@dataclass(frozen=True)
class DemoTicket:
    """A ticket and the facts that place it; `parent` and `blocked_by` name earlier titles."""

    repository: str
    title: str
    stage: Stage
    type: str = "feature"
    labels: tuple[str, ...] = ()
    priority: str = ""
    description: str = ""
    parent: str = ""
    blocked_by: tuple[str, ...] = ()
    blocked: str = ""
    # Days before the load the pull request was merged; merged and released tickets only.
    merged_days_ago: int = 0
    # The file the ticket's commit adds, under the repository.
    change: str = ""


@dataclass(frozen=True)
class DemoSession:
    """An agent session on a ticket, as its hooks and its transcript record it."""

    session_id: str
    ticket: str
    prompt: str
    tools: tuple[tuple[str, str], ...]
    # Tokens per assistant message: input, output, cache read, cache write.
    messages: tuple[tuple[int, int, int, int], ...]
    model: str = "claude-sonnet-5-5"
    ended: bool = True


DEMO_REPOSITORIES = ("shop-api", "web", "infra")

# In filing order: numbers come from the sequence, CF-1 first.
DEMO_TICKETS: tuple[DemoTicket, ...] = (
    DemoTicket(
        "shop-api",
        "Checkout refunds partial orders",
        Stage.RELEASED,
        labels=("payments",),
        priority="high",
        description="A refund of part of an order refunds the whole order today.",
        merged_days_ago=40,
        change="src/refunds.py",
    ),
    DemoTicket(
        "shop-api",
        "Rate limit the public search endpoint",
        Stage.RELEASED,
        labels=("api", "security"),
        priority="medium",
        merged_days_ago=34,
        change="src/limits.py",
    ),
    DemoTicket(
        "web",
        "Cart badge counts removed items",
        Stage.RELEASED,
        type="bug",
        labels=("cart",),
        priority="high",
        merged_days_ago=31,
        change="src/cart/badge.ts",
    ),
    DemoTicket(
        "infra",
        "Nightly database backups to object storage",
        Stage.RELEASED,
        labels=("ops",),
        priority="high",
        merged_days_ago=27,
        change="backup/nightly.sh",
    ),
    DemoTicket(
        "shop-api",
        "Export orders as CSV",
        Stage.MERGED,
        labels=("reports",),
        priority="medium",
        description="Finance reconciles the month from a spreadsheet of every paid order.",
        merged_days_ago=20,
        change="src/exports.py",
    ),
    DemoTicket(
        "web",
        "Order history page paginates",
        Stage.MERGED,
        labels=("account",),
        merged_days_ago=16,
        change="src/account/history.ts",
    ),
    DemoTicket(
        "shop-api",
        "Webhook retries back off exponentially",
        Stage.MERGED,
        labels=("api",),
        priority="medium",
        merged_days_ago=12,
        change="src/webhooks.py",
    ),
    DemoTicket(
        "infra",
        "Alert when the queue backlog passes ten minutes",
        Stage.MERGED,
        labels=("ops", "alerts"),
        merged_days_ago=9,
        change="alerts/backlog.yml",
    ),
    DemoTicket(
        "web",
        "Product images load lazily below the fold",
        Stage.MERGED,
        labels=("performance",),
        priority="low",
        merged_days_ago=5,
        change="src/catalog/images.ts",
    ),
    DemoTicket(
        "shop-api",
        "Coupons expire at the end of their day in the shop's timezone",
        Stage.MERGED,
        type="bug",
        labels=("payments",),
        priority="high",
        merged_days_ago=2,
        change="src/coupons.py",
    ),
    DemoTicket(
        "shop-api",
        _GIFT_CARDS,
        Stage.SPEC,
        labels=("payments",),
        priority="medium",
        description="Customers buy a gift card and pay with it, in part or in full.",
    ),
    DemoTicket(
        "shop-api",
        "Issue a gift card code on purchase",
        Stage.REVIEW,
        labels=("payments",),
        priority="medium",
        parent=_GIFT_CARDS,
        change="src/gift_cards/issue.py",
    ),
    DemoTicket(
        "shop-api",
        "Pay part of an order with a gift card",
        Stage.BUILD,
        labels=("payments",),
        priority="medium",
        parent=_GIFT_CARDS,
        blocked_by=("Issue a gift card code on purchase",),
        change="src/gift_cards/redeem.py",
    ),
    DemoTicket(
        "web",
        "Gift card field on the checkout page",
        Stage.SPEC,
        labels=("checkout",),
        parent=_GIFT_CARDS,
        blocked_by=("Pay part of an order with a gift card",),
    ),
    DemoTicket(
        "web",
        "Checkout keeps the address after a failed payment",
        Stage.REVIEW,
        type="bug",
        labels=("checkout",),
        priority="high",
        description="A declined card clears every field and the customer types it all again.",
        change="src/checkout/address.ts",
    ),
    DemoTicket(
        "web",
        "Dark theme for the storefront",
        Stage.BUILD,
        labels=("design",),
        priority="low",
        change="src/theme/dark.css",
    ),
    DemoTicket(
        "infra",
        "Move staging to the new cluster",
        Stage.BUILD,
        labels=("ops",),
        priority="medium",
        blocked="waiting on the cluster credentials from the provider",
        change="deploy/staging.yml",
    ),
    DemoTicket(
        "infra",
        "Rotate the payment provider keys every 90 days",
        Stage.REVIEW,
        labels=("security", "ops"),
        priority="high",
        change="ops/rotate_keys.sh",
    ),
    DemoTicket(
        "shop-api",
        "Search ranks in-stock products first",
        Stage.BUILD,
        labels=("search",),
        priority="medium",
        change="src/search/rank.py",
    ),
    DemoTicket(
        "web",
        "Wishlist shared by link",
        Stage.SPEC,
        labels=("account",),
        priority="low",
        description="A customer sends a link to a wishlist; whoever opens it sees it read-only.",
    ),
    DemoTicket(
        "shop-api",
        "Invoice numbers have no gaps",
        Stage.SPEC,
        type="bug",
        labels=("payments", "compliance"),
        priority="high",
        description="Two orders paid in the same second took the same invoice number.",
    ),
    DemoTicket(
        "infra",
        "Logs keep 30 days, not forever",
        Stage.SPEC,
        labels=("ops",),
        priority="low",
    ),
    DemoTicket(
        "web",
        "Accessible names on every icon button",
        Stage.SPEC,
        labels=("accessibility",),
        priority="medium",
    ),
    DemoTicket(
        "shop-api",
        "Stock reservations expire after 15 minutes",
        Stage.SPEC,
        labels=("inventory",),
        priority="medium",
    ),
    DemoTicket(
        "web",
        "Product page shows delivery estimate",
        Stage.SPEC,
        labels=("catalog",),
    ),
)
