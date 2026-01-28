"""Unit tests for job state transitions."""

from common.ai_training_common.state_machine import JobState, apply_event


def test_apply_event_basic_transitions() -> None:
    assert apply_event(None, "JOB_SUBMITTED") == JobState.SUBMITTED
    assert apply_event(JobState.SUBMITTED, "JOB_PENDING") == JobState.PENDING
    assert apply_event(JobState.PENDING, "JOB_SUBMITTED") == JobState.PENDING
    assert apply_event(JobState.PENDING, "JOB_STARTED") == JobState.RUNNING
    assert apply_event(JobState.RUNNING, "JOB_FAILED") == JobState.FAILED


def test_apply_event_sticky_terminal_states() -> None:
    assert apply_event(JobState.SUCCEEDED, "JOB_FAILED") == JobState.SUCCEEDED
    assert apply_event(JobState.FAILED, "JOB_STARTED") == JobState.FAILED
    assert apply_event(JobState.CANCELLED, "JOB_STARTED") == JobState.CANCELLED


def test_apply_event_unknown_event_is_noop() -> None:
    assert apply_event(JobState.RUNNING, "NOT_A_REAL_EVENT") == JobState.RUNNING
