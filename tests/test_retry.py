"""Unit tests for retry helpers."""

from common.ai_training_common.retry import (
    compute_retry_delay_seconds,
    build_retry_job_config,
)


def test_compute_retry_delay_seconds_caps() -> None:
    assert compute_retry_delay_seconds(0, 30, 900) == 30
    assert compute_retry_delay_seconds(1, 30, 900) == 60
    assert compute_retry_delay_seconds(10, 30, 900) == 900


def test_build_retry_job_config_new_job_id_and_backoff_fields() -> None:
    cfg = {"model_id": "m1"}
    old_job_id = "job-old"
    new_job_id, new_cfg = build_retry_job_config(
        cfg,
        old_job_id,
        retry_count=1,
        details={"error": {"message": "boom"}},
    )

    assert new_job_id != old_job_id
    assert new_cfg["job_id"] == new_job_id
    assert new_cfg["retry_of"] == old_job_id
    assert new_cfg["retry_attempt"] == 2
    assert new_cfg["seq_start"] == 2
    assert isinstance(new_cfg["submitted_at"], int)
    assert new_cfg["retry_reason"] == {"message": "boom"}
