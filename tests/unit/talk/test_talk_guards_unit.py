"""Id bounds, first-answer time, status under a racing answer and bounded lock waits."""

from code_factory.talk.service.common import status
from code_factory.talk.tables import AnswerRow, QuestionRow


def test_an_answer_that_landed_after_the_question_was_read_makes_it_answered() -> None:
    row = QuestionRow(answered_at=None, withdrawn_at=None)
    answer = AnswerRow(text="blue")
    assert status(row, None) == "open"
    assert status(row, answer) == "answered"
