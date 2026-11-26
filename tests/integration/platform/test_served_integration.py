"""`Served` (what this process serves) and the `serve` command a module may provide."""

from sqlalchemy.ext.asyncio import async_sessionmaker

from app_lifespan import IDLE_MODULES, running_lifespan
from code_factory.app import create_app
from code_factory.platform.config import Settings
from code_factory.platform.served import Served

SERVED = Served(
    address="127.0.0.1", port=4999, both_loopbacks=True, base_url="http://localhost:4999"
)


async def test_the_startup_sign_in_link_names_the_bound_listener(
    settings: Settings,
    connection: object,
    migrated: None,  # noqa: ARG001
) -> None:
    factory = async_sessionmaker(
        bind=connection,  # ty: ignore[invalid-argument-type]
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    app = create_app(settings, factory, served=SERVED, modules=IDLE_MODULES)
    async with running_lifespan(app):
        assert app.state.startup_lines[0].startswith("sign in: http://localhost:4999/owner/")
