"""Delivering one message to the target over HTTP.

No proxy and no redirect: the environment's proxy variables would carry the message, and any
secret in the address's path, to another host, and a redirect could move it there too.
"""

import httpx

from code_factory.push.models import Message, Target
from code_factory.push.rules import ntfy_headers, webhook_body

TIMEOUT = httpx.Timeout(3.0, connect=2.0)
NO_ANSWER = "no answer"


class HttpDelivery:
    """POSTs a message to the target; the problem when it was not taken, else None."""

    async def deliver(self, target: Target, message: Message, link: str, reply: str) -> str | None:
        """Deliver `message` linking to `link`, with the reply link when there is one."""
        if target.format == "webhook":
            headers = {"Content-Type": "application/json"}
            body = webhook_body(message, link, reply)
        else:
            headers, body = ntfy_headers(link, reply), message.text
        try:
            async with httpx.AsyncClient(
                timeout=TIMEOUT, trust_env=False, follow_redirects=False
            ) as client:
                response = await client.post(target.url, content=body.encode(), headers=headers)
        except httpx.HTTPError:
            return NO_ANSWER
        if response.is_success:
            return None
        return f"HTTP {response.status_code}"
