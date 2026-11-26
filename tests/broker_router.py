"""A stand-in OpenRouter: the key API and a model path, with every behaviour a test needs."""

import asyncio
import json

from broker_harness import RUN_KEY
from broker_support import Receive, Seen, Send, read_all, reply


class Router:
    """Answers `POST /v1/keys`, `DELETE /v1/keys/<id>` and any other path with a 200."""

    def __init__(self) -> None:
        self.created: list[dict[str, object]] = []
        self.deleted: list[str] = []
        self.create_status = 201
        self.create_body: dict[str, object] | None = None
        self.hang_for: set[str] = set()  # run ids whose create never answers
        self.delete_status = 200
        self.delete_hangs = False
        self.delete_delay = 0.0
        self.key_id = "hash-1"
        self.on_model: list[Seen] = []

    async def __call__(self, seen: Seen, receive: Receive, send: Send) -> None:
        seen.body = await read_all(receive)
        if seen.method == "POST" and seen.target == "/v1/keys":
            await self._create(seen, send)
        elif seen.method == "DELETE" and seen.target.startswith("/v1/keys/"):
            await self._delete(seen, send)
        else:
            self.on_model.append(seen)
            await reply(send, 200, b'{"id": "gen-1"}')

    async def _create(self, seen: Seen, send: Send) -> None:
        body = json.loads(seen.body)
        if any(run in body["name"] for run in self.hang_for):
            await asyncio.sleep(30)
        self.created.append(body)
        made = self.create_body or {"data": {"hash": self.key_id}, "key": RUN_KEY}
        await reply(send, self.create_status, json.dumps(made).encode())

    async def _delete(self, seen: Seen, send: Send) -> None:
        if self.delete_hangs:
            await asyncio.sleep(30)
        await asyncio.sleep(self.delete_delay)
        self.deleted.append(seen.target.removeprefix("/v1/keys/"))
        await reply(send, self.delete_status, b"{}")
