import { EventType } from './eventTypes';

export const JobState = Object.freeze({
  SUBMITTED: 'SUBMITTED',
  PENDING: 'PENDING',
  RUNNING: 'RUNNING',
  PREEMPTED: 'PREEMPTED',
  SUCCEEDED: 'SUCCEEDED',
  FAILED: 'FAILED',
  CANCELLED: 'CANCELLED',
  UNKNOWN: 'UNKNOWN',
});

export const jobStateFromEventType = (eventType) => {
  if (!eventType) return null;
  const t = eventType.toUpperCase();
  if (!t.startsWith('JOB_')) return null;

  if (t === EventType.JOB_COMPLETED) return JobState.SUCCEEDED;
  if (t === EventType.JOB_FAILED) return JobState.FAILED;
  if (t === EventType.JOB_STARTED) return JobState.RUNNING;
  if (t === EventType.JOB_SUBMITTED) return JobState.SUBMITTED;
  if (t === EventType.JOB_CANCELLED) return JobState.CANCELLED;
  if (t === EventType.JOB_PREEMPTED) return JobState.PREEMPTED;

  return t.replace('JOB_', '');
};
