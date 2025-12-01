from enum import Enum

class JobState(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PREEMPTED = "PREEMPTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

TRANSITIONS = {
    JobState.PENDING: {"JOB_STARTED": JobState.RUNNING, "JOB_FAILED": JobState.FAILED, "JOB_CANCELLED": JobState.CANCELLED},
    JobState.RUNNING: {"JOB_COMPLETED": JobState.SUCCEEDED, "JOB_FAILED": JobState.FAILED, "JOB_PREEMPTED": JobState.PREEMPTED, "JOB_CANCELLED": JobState.CANCELLED},
}

def apply_event(current_state: JobState | None, event_type: str) -> JobState:
    if current_state is None:
        current_state = JobState.PENDING
    allowed = TRANSITIONS.get(current_state, {})
    return allowed.get(event_type, current_state)
