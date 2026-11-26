import pytest

from database_guard import UnsafeDatabaseError, assert_test_database

BASE = "postgresql+asyncpg://u:pw@127.0.0.1:5432"


@pytest.mark.parametrize(
    "url",
    [
        f"{BASE}/code_factory_test",
        f"{BASE}/code_factory_store_test",
        f"{BASE}/other_test",
        "postgresql+asyncpg://u:pw@localhost:5432/code_factory_test",
        "postgresql+asyncpg://u:pw@[::1]:5432/code_factory_test",
    ],
)
def test_accepts_a_test_database_on_a_loopback_host(url: str) -> None:
    assert_test_database(url)


@pytest.mark.parametrize("name", ["code_factory", "postgres", "code_factory_test_old", "test", ""])
def test_refuses_any_other_database(name: str) -> None:
    with pytest.raises(UnsafeDatabaseError, match="_test"):
        assert_test_database(f"{BASE}/{name}")


@pytest.mark.parametrize(
    "url",
    [
        f"{BASE}/code_factory_test?database=code_factory",
        f"{BASE}/code_factory_test?host=db.example.com",
        f"{BASE}/code_factory_test?port=5433",
        f"{BASE}/code_factory_test?user=postgres",
        f"{BASE}/code_factory_test?sslmode=disable",
    ],
)
def test_refuses_a_query_parameter_that_can_retarget_the_connection(url: str) -> None:
    with pytest.raises(UnsafeDatabaseError, match="query parameter"):
        assert_test_database(url)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://u:pw@db.example.com:5432/code_factory_test",
        "postgresql+asyncpg://u:pw@10.0.0.5:5432/code_factory_test",
        "postgresql+asyncpg://u:pw@/code_factory_test",
    ],
)
def test_refuses_a_host_that_is_not_loopback(url: str) -> None:
    with pytest.raises(UnsafeDatabaseError, match="loopback"):
        assert_test_database(url)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://u:s3cr3t-pw@127.0.0.1:5432/code_factory?database=x_test",
        "postgresql+asyncpg://u:s3cr3t-pw@db.example.com:5432/code_factory_test",
        "postgresql+asyncpg://u:s3cr3t-pw@127.0.0.1:5432/code_factory",
        "not a url s3cr3t-pw",
    ],
)
def test_refusal_never_prints_the_password(url: str) -> None:
    with pytest.raises(UnsafeDatabaseError) as raised:
        assert_test_database(url)
    assert "s3cr3t-pw" not in str(raised.value)
