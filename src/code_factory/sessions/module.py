"""The `sessions` module as the platform sees it."""

from code_factory.platform.background import BackgroundTasks
from code_factory.platform.db import connection_url
from code_factory.platform.module import Module, Resources
from code_factory.platform.services import Services
from code_factory.sessions import tables  # noqa: F401  # puts the tables on Base.metadata
from code_factory.sessions.cli import sessions_command
from code_factory.sessions.routes import router
from code_factory.sessions.service import SessionService
from code_factory.team.models import AtWork as TeamAtWork
from code_factory.team.service import SessionSource

_ASYNCPG_SCHEME = "postgresql+asyncpg"


class TeamSessions:
    """The team's view of the sessions (`SessionSource`)."""

    def __init__(self, sessions: SessionService) -> None:
        self._sessions = sessions

    async def subagents_at_work(self) -> list[TeamAtWork]:
        """Every running subagent of a live session on a ticket, quiet ones included."""
        return [
            TeamAtWork(
                agent_id=found.agent_id,
                ticket_id=found.ticket,
                kind=found.kind,
                name=found.name,
                doing=found.doing,
                since=found.since,
                last_event_at=found.last_event_at,
            )
            for found in await self._sessions.subagents_at_work()
        ]


def _provide(services: Services, resources: Resources) -> None:
    url = connection_url(resources.settings).render_as_string(hide_password=False)
    # The listener's own connection speaks plain Postgres: the driver name is SQLAlchemy's.
    dsn = url.replace(_ASYNCPG_SCHEME, "postgresql", 1)
    service = SessionService(
        resources.uow,
        state_dir=resources.settings.state_dir,
        listen_dsn=dsn,
        schema=resources.settings.db_schema,
    )
    services.add(SessionService, service)
    services.add(SessionSource, TeamSessions(service))
    resources.on_stopping.append(service.shutdown)


def _background(services: Services, tasks: BackgroundTasks) -> None:
    service = services.get(SessionService)
    tasks.start("sessions.ingest", service.run_ingest)
    tasks.start("sessions.listen", service.run_listen)
    tasks.start("sessions.maintenance", service.run_maintenance)


module = Module(
    name="sessions",
    provide=_provide,
    background=_background,
    commands=(sessions_command,),
    router=router,
)
