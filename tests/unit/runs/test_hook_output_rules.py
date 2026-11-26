from code_factory.runs.rules.hook_output import RETRY_WORDS, hook_output


def test_an_allow_names_the_permission_request_event_and_the_allow_behaviour() -> None:
    assert hook_output(allow=True) == {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {"behavior": "allow"},
        }
    }


def test_an_owners_deny_carries_its_words_and_interrupts_the_run() -> None:
    assert hook_output(allow=False, message="no", interrupt=True) == {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {"behavior": "deny", "message": "no", "interrupt": True},
        }
    }


def test_a_deny_the_board_settles_itself_does_not_interrupt_the_run() -> None:
    decision = hook_output(allow=False, message="outside your tree")["hookSpecificOutput"][
        "decision"
    ]
    assert decision == {"behavior": "deny", "message": "outside your tree"}


def test_the_retry_words_are_the_boards_sentence() -> None:
    assert RETRY_WORDS == (
        "Nobody answered this permission request from the board in time; do it another way "
        "inside your worktree, or ask in the ticket's Open questions."
    )
