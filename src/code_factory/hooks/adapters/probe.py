"""Asks whether a board answers at an address."""

import httpx

CONNECT_S = 1.0
TOTAL_S = 2.0


class BoardProbe:
    """GET `<base>/health/ready`, redirects not followed, proxies from the environment ignored."""

    async def up(self, base: str) -> bool:
        """Whether a board answers ready at `base`."""
        timeout = httpx.Timeout(TOTAL_S, connect=CONNECT_S)
        try:
            async with httpx.AsyncClient(
                trust_env=False, follow_redirects=False, timeout=timeout
            ) as client:
                answer = await client.get(f"{base.rstrip('/')}/health/ready")
        except httpx.HTTPError:
            return False
        return answer.status_code == httpx.codes.OK
