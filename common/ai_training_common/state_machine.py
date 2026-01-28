"""State transition rules for job lifecycle events."""

from enum import Enum


class JobState(str, Enum):
    """Supported job lifecycle states."""
    SUBMITTED = "SUBMITTED"
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PREEMPTED = "PREEMPTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


TRANSITIONS = {
    JobState.SUBMITTED: {
        "JOB_SUBMITTED": JobState.SUBMITTED,
        "JOB_PENDING": JobState.PENDING,
        "JOB_STARTED": JobState.RUNNING,
        "JOB_FAILED": JobState.FAILED,
        "JOB_CANCELLED": JobState.CANCELLED,
    },
    JobState.PENDING: {
        "JOB_SUBMITTED": JobState.PENDING,
        "JOB_PENDING": JobState.PENDING,
        "JOB_STARTED": JobState.RUNNING,
        "JOB_FAILED": JobState.FAILED,
        "JOB_CANCELLED": JobState.CANCELLED,
    },
    JobState.RUNNING: {
        "JOB_COMPLETED": JobState.SUCCEEDED,
        "JOB_FAILED": JobState.FAILED,
        "JOB_PREEMPTED": JobState.PREEMPTED,
        "JOB_CANCELLED": JobState.CANCELLED,
    },
    JobState.PREEMPTED: {
        "JOB_RESTARTED": JobState.RUNNING,
        "JOB_FAILED": JobState.FAILED,
        "JOB_CANCELLED": JobState.CANCELLED,
    },
    JobState.SUCCEEDED: {},
    JobState.FAILED: {},
    JobState.CANCELLED: {},
}


def apply_event(current_state: JobState | None, event_type: str) -> JobState:
    """Apply an event type to a job state, returning the next state."""
    if current_state is None:
        current_state = JobState.SUBMITTED
    allowed = TRANSITIONS.get(current_state, {})
    return allowed.get(event_type, current_state)
