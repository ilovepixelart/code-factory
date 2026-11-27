"""An answer built without a body streams none."""

from code_factory.broker.service.exchange import ProxyAnswer


async def test_an_answer_without_a_body_streams_no_chunks() -> None:
    answer = ProxyAnswer(status=204, headers=[])

    assert [chunk async for chunk in answer.body] == []
