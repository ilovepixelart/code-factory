"""The stages module's public API: where a ticket stands, how it moves, what a head's checks say.

Other modules call `StageService` and read `code_factory.stages.models`; the pure readers
(`read_log`, `feedback_reason`, `fails_on_main`, `no_verdict`) are methods so no other module
imports the rules.
"""

from code_factory.stages.service.assess import Assessing
from code_factory.stages.service.base import Agents, Ports
from code_factory.stages.service.fixloop import FixLoop
from code_factory.stages.service.observe import Observing
from code_factory.stages.service.review import Reviewing
from code_factory.stages.service.stage import StageService

__all__ = [
    "Agents",
    "Assessing",
    "FixLoop",
    "Observing",
    "Ports",
    "Reviewing",
    "StageService",
]
