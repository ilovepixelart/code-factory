"""Tool calls a caller may make a minute, and what one over the limit is told."""

from dataclasses import replace

from fastmcp import Client

from code_factory.platform.mcp import build_mcp
from code_factory.platform.mcp.rate import CallRate
from code_factory.platform.services import Services
from mcp_support import owner_access


def test_a_window_admits_its_limit_then_refuses_until_the_oldest_call_is_a_minute_old() -> None:
    now = [0.0]
    rate = CallRate(2, clock=lambda: now[0])

    first, second = rate.wait("t1"), rate.wait("t1")
    now[0] = 45.0
    third = rate.wait("t1")
    other = rate.wait("t2")
    now[0] = 60.0
    after = rate.wait("t1")

    assert (first, second, third, other, after) == (None, None, 15.0, None, None)


async def test_a_call_over_the_limit_is_refused_with_how_long_to_wait() -> None:
    now = [0.0]
    access = replace(owner_access(), rate=CallRate(2, clock=lambda: now[0]))

    async with Client(build_mcp(Services(), [], access=access)) as client:
        calls = [await client.call_tool("whoami", {}, raise_on_error=False) for _ in range(3)]

    assert [c.is_error for c in calls] == [False, False, True]
    text = calls[2].content[0].text
    assert text == "rate limited: 2 tool calls in the last minute. Wait 60 s, then call again."
