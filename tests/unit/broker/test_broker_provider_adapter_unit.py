"""The client that sends requests to the provider and the calls that make and delete run keys."""

from code_factory.broker.adapters.provider import ProviderClient


def test_the_client_neither_follows_redirects_nor_reads_the_environment() -> None:
    made = ProviderClient(read_s=1, connect_s=1, write_s=1, pool_s=1, max_connections=4)
    assert made._client.follow_redirects is False
    assert made._client._trust_env is False
