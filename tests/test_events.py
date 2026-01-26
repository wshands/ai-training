"""Unit tests for event schema helpers."""

from common.ai_training_common.events import EventType, JobEventIn


def test_job_event_make_defaults() -> None:
    ev = JobEventIn.make(
        event_type=EventType.JOB_SUBMITTED,
        job_id="job-123",
        tenant_id="tenant-1",
        user_id="user-1",
        seq=1,
        producer="test-suite",
    )

    assert ev.event_type == EventType.JOB_SUBMITTED
    assert ev.job_id == "job-123"
    assert ev.tenant_id == "tenant-1"
    assert ev.user_id == "user-1"
    assert ev.seq == 1
    assert ev.producer == "test-suite"
    assert ev.payload == {}
    assert isinstance(ev.event_id, str)
