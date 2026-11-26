"""What a split run is asked: file the brief's pieces as child tickets of the parent."""

STAGE = "split"
BRIEF_LIMIT = 100_000
MAX_CHILDREN = 50

_STEPS = f"""Split the brief below into child tickets of the parent.

1. List the pieces that each deliver one outcome a person can check; one too big for one branch is
   two tickets. Order each after the tickets it needs.
2. File each with the create_ticket tool: a title naming the problem or the outcome in one line,
   its type (feature, bug, refactor, upgrade, hotfix or docs), its labels, and a description of
   what is wanted and why, from the brief, in your own words. The parent is set for you. When a
   ticket waits on one filed before it, name that ticket's id in blocked_by.
3. Never paste the brief's words as a ticket, add no choice the brief does not make, and file at
   most {MAX_CHILDREN}. Change no file and make no commit."""


def split_prompt(ticket_id: str, title: str, description: str, brief: str) -> str:
    """The instruction for a split run of `ticket_id` from the owner's `brief`."""
    parent = f"The parent ticket is {ticket_id}: {title}"
    if description.strip():
        parent += f"\n\n{description.strip()}"
    return f"{_STEPS}\n\n{parent}\n\nThe brief:\n\n{brief.strip()}\n"
