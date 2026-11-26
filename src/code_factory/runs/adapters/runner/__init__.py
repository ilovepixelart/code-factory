"""The run wrapper: `python -m code_factory.runs.adapters.runner <exit file> -- <command...>`.

It starts the agent in the group the board gave it, copies the agent's output to its own standard
output (the run's log) through the owner-context redaction, records the agent's exit code in the
exit file with an atomic rename and exits. It never touches the database, so a run finishes and is
recorded while the board is down.

SIGTERM is handled, never ignored: an ignored signal is inherited through exec and the agent would
survive a stop. The group's SIGTERM ends the agent and the wrapper then writes `-15`.
"""
