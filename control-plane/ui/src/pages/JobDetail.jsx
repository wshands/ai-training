import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api, handleApiError } from '../hooks/useApi';
import { WS_BASE_URL } from '../config';
import { useWebSocket } from '../hooks/useWebSocket';
import JobStatusBadge from '../components/JobStatusBadge';
import LogPanel from '../components/LogPanel';
import Spinner from '../components/Spinner';
import { useClerkToken } from '../hooks/useClerkToken';
import { EventType } from '../constants/eventTypes';
import { JobState, jobStateFromEventType } from '../constants/jobStates';
import { useAppAuth } from '../context/AppAuthContext';
import { hasMinRole } from '../utils/roles';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  Label,
  ResponsiveContainer,
} from 'recharts';

const parseHistoryEvents = (events) => {
  const logs = [];
  const metrics = [];
  let hasStep = false;
  let hasEpoch = false;
  let lastStatus = null;
  let lastError = null;

  for (const ev of events || []) {
    const t = (ev.event_type || "").toUpperCase();
    const d = ev.data || {};
    const state = ev.state || null;

    if (t === EventType.JOB_LOG) {
      if (d.message) logs.push(d.message);
    }

    if (t === EventType.EPOCH_METRIC || t === EventType.JOB_METRIC) {
      const step = d.step ?? d.epoch ?? null;
      if (d.step !== undefined && d.step !== null) hasStep = true;
      if (d.epoch !== undefined && d.epoch !== null) hasEpoch = true;
      const loss = d.loss ?? d.metrics?.loss; // <-- your data has metrics.loss
      const accuracy = d.accuracy ?? d.metrics?.accuracy;
      if (step !== null && (loss !== undefined || accuracy !== undefined)) {
        metrics.push({ step, loss, accuracy, ...d });
      }
    }

    if (t === EventType.JOB_FAILED) {
      lastError = d?.error || d;
    }

    if (state) {
      lastStatus = state;
    } else if (t.startsWith("JOB_")) {
      lastStatus = jobStateFromEventType(t);
    }
  }

  metrics.sort((a, b) => (a.step ?? 0) - (b.step ?? 0));
  return { logs, metrics, lastStatus, lastError, hasStep, hasEpoch };
};

const formatDateTime = (value) => {
  if (!value) return '—';
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
};

const formatValue = (value) => {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
};

const buildRunSummary = ({
  jobId,
  job,
  cfg,
  metrics,
  lastError,
  historyEvents,
  historyHasMore,
}) => {
  const latestMetric = metrics.length ? metrics[metrics.length - 1] : null;
  const datasetUri = cfg.dataset_uri || cfg.datasetUri || null;
  const artifactUri = cfg.artifact_uri || cfg.artifactUri || null;
  const displayName = cfg.display_name || cfg.extra_config?.display_name || null;
  const notes = cfg.notes || cfg.extra_config?.notes || null;

  return {
    job_id: jobId,
    status: job?.status || null,
    model_id: cfg.model_id || job?.model_id || null,
    dataset_id: cfg.dataset_id || job?.dataset_id || null,
    dataset_uri: datasetUri,
    artifact_uri: artifactUri,
    display_name: displayName,
    notes,
    distributed: cfg.distributed ?? null,
    epochs: cfg.epochs ?? null,
    batch_size: cfg.batch_size ?? null,
    learning_rate: cfg.lr ?? null,
    retry_of: cfg.retry_of ?? null,
    retry_attempt: cfg.retry_attempt ?? null,
    created_at: job?.created_at || null,
    submitted_at: job?.submitted_at || null,
    updated_at: job?.updated_at || null,
    metrics_last_loss: latestMetric?.loss ?? latestMetric?.metrics?.loss ?? null,
    metrics_last_accuracy: latestMetric?.accuracy ?? latestMetric?.metrics?.accuracy ?? null,
    metrics_points: metrics.length,
    events_loaded: historyEvents.length,
    events_partial: !!historyHasMore,
    error: lastError || null,
    generated_at: new Date().toISOString(),
  };
};

const toCsvRow = (summary) => {
  const keys = Object.keys(summary);
  const escape = (value) => {
    if (value === null || value === undefined) return '';
    const str = typeof value === 'string' ? value : JSON.stringify(value);
    if (str.includes('"') || str.includes(',') || str.includes('\n')) {
      return `"${str.replace(/"/g, '""')}"`;
    }
    return str;
  };
  const header = keys.join(',');
  const row = keys.map((key) => escape(summary[key])).join(',');
  return `${header}\n${row}\n`;
};

const JobDetail = () => {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const [job, setJob] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [retryErr, setRetryErr] = useState('');
  const [retrying, setRetrying] = useState(false);
  const [retryNotice, setRetryNotice] = useState('');
  const [logs, setLogs] = useState([]);
  const [metrics, setMetrics] = useState([]);
  const [lastError, setLastError] = useState(null);
  const [xAxisInfo, setXAxisInfo] = useState({ hasStep: false, hasEpoch: false });
  const [historyEvents, setHistoryEvents] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyHasMore, setHistoryHasMore] = useState(false);
  const [historyOldestId, setHistoryOldestId] = useState(null);
  const [retentionDays, setRetentionDays] = useState(null);
  const [retentionSource, setRetentionSource] = useState('default');
  const [retentionDefault, setRetentionDefault] = useState(null);
  const [showSummary, setShowSummary] = useState(false);
  const { role, loading: roleLoading } = useAppAuth();
  const canOperate = hasMinRole(role, 'operator');

  const historyPageSize = 500;


  //  This ensures:
  // loading starts true
  // After the HTTP call finishes (success or error), loading becomes false
  // On success, job is a full object { id, status, config, model_id, dataset_id, ... }
  // So the UI can render even if WS isn’t doing anything yet.
  const applyHistory = useCallback((events) => {
    const { logs, metrics, lastStatus, lastError, hasStep, hasEpoch } =
      parseHistoryEvents(events);
    setLogs(logs.slice(-500));
    setMetrics(metrics);
    setLastError(lastError);
    setXAxisInfo({ hasStep, hasEpoch });
    return lastStatus;
  }, []);

  useEffect(() => {
    let cancelled = false;

    const loadJobAndHistory = async () => {
      setLoading(true);
      setErr('');
      setLogs([]);
      setMetrics([]);
      setHistoryEvents([]);
      setHistoryOldestId(null);
      setHistoryHasMore(false);

      try {
        const [jobRes, evRes] = await Promise.all([
          api.get(`/jobs/${jobId}`),
          api.get(`/jobs/${jobId}/events/latest`, {
            params: { limit: historyPageSize, include_state: false },
          }),
        ]);

        if (cancelled) return;

        const jobData = jobRes.data;
        const events = evRes.data || [];
        const oldestId = events.length ? events[0]?.id : null;

        applyHistory(events);

        setJob(jobData);
        setHistoryEvents(events);
        setHistoryOldestId(oldestId);
        setHistoryHasMore(events.length === historyPageSize && oldestId > 1);

      } catch (e) {
        if (cancelled) return;
        setErr(handleApiError(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    loadJobAndHistory();
    return () => {
      cancelled = true;
    };
  }, [applyHistory, historyPageSize, jobId]);

  useEffect(() => {
    let cancelled = false;
    const loadRetention = async () => {
      try {
        const res = await api.get('/settings/retention');
        if (!cancelled) {
          const days = res.data?.event_retention_days;
          setRetentionDays(
            days === null || days === undefined ? null : Math.max(0, Number(days))
          );
          setRetentionSource(res.data?.source || 'default');
          setRetentionDefault(res.data?.default_event_retention_days ?? null);
        }
      } catch (e) {
        if (!cancelled) {
          setRetentionDays(null);
          setRetentionSource('default');
          setRetentionDefault(null);
        }
      }
    };
    loadRetention();
    return () => {
      cancelled = true;
    };
  }, []);

  const loadOlderEvents = useCallback(async () => {
    if (!historyOldestId || historyLoading) return;
    setHistoryLoading(true);
    setErr('');
    try {
      const res = await api.get(`/jobs/${jobId}/events`, {
        params: {
          before_id: historyOldestId,
          limit: historyPageSize,
          include_state: false,
        },
      });
      const older = res.data || [];
      const nextEvents = [...older, ...historyEvents];
      setHistoryEvents(nextEvents);
      const nextOldest = older.length ? older[0]?.id : historyOldestId;
      setHistoryOldestId(nextOldest);
      setHistoryHasMore(older.length === historyPageSize && nextOldest > 1);
      applyHistory(nextEvents);
    } catch (e) {
      setErr(handleApiError(e));
    } finally {
      setHistoryLoading(false);
    }
  }, [applyHistory, historyEvents, historyLoading, historyOldestId, historyPageSize, jobId]);




  const { getFreshToken } = useClerkToken();
  const getWsUrl = useCallback(async () => {
    const token = await getFreshToken();
    if (!token) return null;
    return `${WS_BASE_URL}/ws/jobs/${jobId}?token=${encodeURIComponent(token)}`;
  }, [getFreshToken, jobId]);

  const applyEvent = (ev) => {
    const t = (ev?.event_type || '').toUpperCase();
    const d = ev?.data || {};

    if (t === EventType.JOB_LOG && d.message) {
      setLogs((prev) => [...prev, d.message].slice(-500));
      setHistoryEvents((prev) => [...prev, ev]);
      return;
    }

    if (t === EventType.EPOCH_METRIC || t === EventType.JOB_METRIC) {
      const step = d.step ?? d.epoch ?? null;
      const loss = d.loss ?? d.metrics?.loss;
      const accuracy = d.accuracy ?? d.metrics?.accuracy;

      if (step !== null && (loss !== undefined || accuracy !== undefined)) {
        if (d.step !== undefined && d.step !== null) {
          setXAxisInfo((prev) => (prev.hasStep ? prev : { ...prev, hasStep: true }));
        } else if (d.epoch !== undefined && d.epoch !== null) {
          setXAxisInfo((prev) => (prev.hasEpoch ? prev : { ...prev, hasEpoch: true }));
        }
        setMetrics((prev) => {
          const next = [...prev, { step, loss, accuracy, ...d }];
          next.sort((a, b) => (a.step ?? 0) - (b.step ?? 0));
          return next;
        });
        setHistoryEvents((prev) => [...prev, ev]);
      }
      return;
    }

    if (t === EventType.JOB_FAILED) {
      setLastError(d?.error || d);
      setHistoryEvents((prev) => [...prev, ev]);
    }

    if (t.startsWith('JOB_')) {
      const status = ev?.state || t.replace('JOB_', '');
      setJob((prev) => (prev ? { ...prev, status } : { id: jobId, status, config: {} }));
    }
    setHistoryEvents((prev) => [...prev, ev]);
  };

  const terminalStates = [JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED, JobState.PREEMPTED];
  const isTerminal = job && terminalStates.includes(job.status);
  const eventsEmpty = historyEvents.length === 0;
  let logsEmptyMessage = 'Waiting for logs…';
  if (isTerminal && eventsEmpty) {
    if (retentionDays && retentionDays > 0) {
      logsEmptyMessage = `Logs expired (retained ${retentionDays} days).`;
    } else {
      logsEmptyMessage = 'No logs available for this job.';
    }
  }

  useWebSocket(
    getWsUrl,
    (msg) => {
      console.log("JobDetail received ws msg", msg);
      applyEvent(msg);
    },
    { reconnectInterval: 2000, maxReconnectAttempts: 10 }
  );



  const handleCancel = async () => {
    setRetryErr('');
    setRetrying(true);
    try {
      await api.post(`/jobs/${jobId}/cancel`);
    } catch (e) {
      setRetryErr(handleApiError(e));
    } finally {
      setRetrying(false);
    }
  };

  const handleRetry = async () => {
    setRetryErr('');
    setRetryNotice('');
    setRetrying(true);
    try {
      const res = await api.post(`/jobs/${jobId}/retry`);
      const newJobId = res?.data?.job_id || res?.data?.jobId;
      if (newJobId) {
        setRetryNotice('Retry started — redirected to the new job.');
        navigate(`/jobs/${newJobId}`);
      } else {
        setRetryErr('Retry request succeeded but no job id was returned.');
      }
    } catch (e) {
      setRetryErr(handleApiError(e));
    } finally {
      setRetrying(false);
    }
  };

  const xAxisLabel = xAxisInfo.hasStep
    ? xAxisInfo.hasEpoch
      ? 'Step/Epoch'
      : 'Step'
    : xAxisInfo.hasEpoch
    ? 'Epoch'
    : 'Step';

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-slate-400">
        <Spinner /> <span>Loading job…</span>
      </div>
    );
  }

  if (err) {
    return (
      <div className="text-sm text-rose-300 bg-rose-950/40 border border-rose-800 rounded p-3">
        Could not load job: {err}
        <div className="mt-1 text-xs text-rose-200/80">
          (Implement <code>{`GET /jobs/${jobId}`}</code> in your control-plane.)
        </div>
      </div>
    );
  }

  if (!job) return null;

  const cfg = job.config || {};
  const runSummary = buildRunSummary({
    jobId,
    job,
    cfg,
    metrics,
    lastError,
    historyEvents,
    historyHasMore,
  });

  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-center justify-between gap-4 mb-1">
          <h1 className="text-xl font-semibold">Job {jobId}</h1>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="px-3 py-1.5 rounded-md border border-slate-700 text-sm text-slate-200 hover:bg-slate-800"
              onClick={() => setShowSummary(true)}
            >
              Run summary
            </button>
            {[JobState.SUBMITTED, JobState.PENDING, JobState.RETRYING, JobState.RUNNING].includes(job?.status) && (
              <button
                type="button"
                className="px-3 py-1.5 rounded-md bg-rose-500 text-sm font-medium hover:bg-rose-400 disabled:opacity-50"
                onClick={handleCancel}
                disabled={retrying || roleLoading || !canOperate}
              >
                Cancel
              </button>
            )}
            {job?.status === JobState.FAILED && (
              <button
                type="button"
                className="px-3 py-1.5 rounded-md bg-sky-500 text-sm font-medium hover:bg-sky-400 disabled:opacity-50"
                onClick={handleRetry}
                disabled={retrying || roleLoading || !canOperate}
              >
                {retrying ? 'Retrying…' : 'Retry'}
              </button>
            )}
          </div>
        </div>
        {!roleLoading && !canOperate && (
          <div className="mt-2 text-xs text-amber-300">
            Read-only role — ask an admin for Operator access to cancel or retry jobs.
          </div>
        )}
        <JobStatusBadge status={job.status} />
        <div className="mt-2 text-xs text-slate-400">
          Model:{' '}
          <span className="font-mono">{cfg.model_id || job.model_id}</span> | Dataset:{' '}
          <span className="font-mono">
            {cfg.dataset_id || job.dataset_id}
          </span>
        </div>
      </div>

      {retryErr && (
        <div className="text-sm text-rose-300 bg-rose-950/40 border border-rose-800 rounded p-3">
          Request failed: {retryErr}
        </div>
      )}
      {retryNotice && (
        <div className="text-sm text-emerald-300 bg-emerald-950/40 border border-emerald-800 rounded p-3">
          {retryNotice}
        </div>
      )}

      {(cfg.dataset_uri || cfg.datasetUri || cfg.artifact_uri || cfg.artifactUri) && (
        <div className="text-sm bg-slate-900/60 border border-slate-800 rounded-lg p-3 space-y-3">
          <div className="text-xs uppercase tracking-wide text-slate-500">
            Run references
          </div>
          {(cfg.dataset_uri || cfg.datasetUri) && (
            <div>
              <div className="text-xs text-slate-400">Dataset URI</div>
              <div className="mt-1">
                <a
                  className="text-sky-300 hover:text-sky-200 break-all"
                  href={cfg.dataset_uri || cfg.datasetUri}
                  target="_blank"
                  rel="noreferrer"
                >
                  {cfg.dataset_uri || cfg.datasetUri}
                </a>
              </div>
            </div>
          )}
          {(cfg.artifact_uri || cfg.artifactUri) && (
            <div>
              <div className="text-xs text-slate-400">Artifact URI</div>
              <div className="mt-1">
                <a
                  className="text-sky-300 hover:text-sky-200 break-all"
                  href={cfg.artifact_uri || cfg.artifactUri}
                  target="_blank"
                  rel="noreferrer"
                >
                  {cfg.artifact_uri || cfg.artifactUri}
                </a>
              </div>
            </div>
          )}
        </div>
      )}

      {lastError && (
        <div className="text-sm text-rose-300 bg-rose-950/40 border border-rose-800 rounded p-3">
          <div className="font-semibold">Job failed</div>
          {lastError?.message && (
            <div className="mt-1">{lastError.message}</div>
          )}
          {lastError?.type && (
            <div className="mt-1 text-xs text-rose-200/80">{lastError.type}</div>
          )}
          {!lastError?.message && !lastError?.type && (
            <pre className="mt-2 whitespace-pre-wrap break-all text-xs">
              {JSON.stringify(lastError, null, 2)}
            </pre>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div>
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-semibold">Logs</h2>
            <div className="text-xs text-slate-400">
              {retentionDays === null
                ? 'Retention: unknown'
                : retentionDays === 0
                ? 'Retention: disabled'
                : `Retention: ${retentionDays} days`}
              {retentionSource === 'org' && (
                <span className="ml-2 text-slate-500">(org override)</span>
              )}
              {retentionSource === 'default' &&
                retentionDefault !== null &&
                retentionDefault !== retentionDays && (
                  <span className="ml-2 text-slate-500">
                    (default {retentionDefault <= 0 ? 'disabled' : `${retentionDefault} days`})
                  </span>
                )}
            </div>
            {historyHasMore && (
              <button
                type="button"
                onClick={loadOlderEvents}
                className="text-xs text-slate-300 hover:text-white border border-slate-700 rounded px-2 py-1"
                disabled={historyLoading}
              >
                {historyLoading ? 'Loading…' : 'Load earlier'}
              </button>
            )}
          </div>
          <LogPanel lines={logs} emptyMessage={logsEmptyMessage} />
        </div>
        <div>
          <h2 className="text-sm font-semibold mb-2">Metrics</h2>
          <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-3 h-72">
            {metrics.length === 0 ? (
              <div className="text-xs text-slate-500 italic">
                Waiting for metrics…
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={metrics}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                  <XAxis dataKey="step" tick={{ fill: '#9ca3af', fontSize: 10 }}>
                    <Label
                      value={xAxisLabel}
                      position="insideBottom"
                      offset={-4}
                      style={{ fill: '#9ca3af', fontSize: 11 }}
                    />
                  </XAxis>
                  <YAxis yAxisId="loss" tick={{ fill: '#9ca3af', fontSize: 10 }}>
                    <Label
                      value="Loss"
                      angle={-90}
                      position="insideLeft"
                      style={{ fill: '#9ca3af', fontSize: 11 }}
                    />
                  </YAxis>
                  <YAxis
                    yAxisId="accuracy"
                    orientation="right"
                    domain={[0, 1]}
                    tick={{ fill: '#9ca3af', fontSize: 10 }}
                  >
                    <Label
                      value="Accuracy"
                      angle={90}
                      position="insideRight"
                      style={{ fill: '#9ca3af', fontSize: 11 }}
                    />
                  </YAxis>
                  <Tooltip />
                  <Legend
                    verticalAlign="top"
                    height={20}
                    wrapperStyle={{ color: '#9ca3af', fontSize: 11 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="loss"
                    stroke="#38bdf8"
                    dot={false}
                    strokeWidth={1.6}
                    yAxisId="loss"
                  />
                  <Line
                    type="monotone"
                    dataKey="accuracy"
                    stroke="#34d399"
                    dot={false}
                    strokeWidth={1.6}
                    yAxisId="accuracy"
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>

      <details className="bg-slate-900/60 border border-slate-800 rounded-lg p-3 text-xs">
        <summary className="cursor-pointer text-slate-300">Raw config</summary>
        <pre className="mt-2 whitespace-pre-wrap break-all">
          {JSON.stringify(cfg, null, 2)}
        </pre>
      </details>

      {showSummary && (
        <div className="fixed inset-0 z-50">
          <div
            className="absolute inset-0 bg-slate-950/70"
            onClick={() => setShowSummary(false)}
          />
          <div className="absolute right-0 top-0 h-full w-full max-w-xl bg-slate-950 border-l border-slate-800 shadow-2xl overflow-y-auto">
            <div className="p-5 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold">Run summary</h2>
                  <div className="text-xs text-slate-500">
                    Lightweight, exportable run record for audit and reproducibility.
                  </div>
                </div>
                <button
                  type="button"
                  className="text-slate-400 hover:text-slate-200"
                  onClick={() => setShowSummary(false)}
                >
                  Close
                </button>
              </div>

              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="px-3 py-1.5 rounded-md bg-sky-500 text-sm font-medium hover:bg-sky-400"
                  onClick={() => {
                    const blob = new Blob([JSON.stringify(runSummary, null, 2)], {
                      type: 'application/json',
                    });
                    const link = document.createElement('a');
                    link.href = URL.createObjectURL(blob);
                    link.download = `run-summary-${jobId}.json`;
                    link.click();
                    URL.revokeObjectURL(link.href);
                  }}
                >
                  Download JSON
                </button>
                <button
                  type="button"
                  className="px-3 py-1.5 rounded-md border border-slate-700 text-sm text-slate-200 hover:bg-slate-800"
                  onClick={() => {
                    const csv = toCsvRow(runSummary);
                    const blob = new Blob([csv], { type: 'text/csv' });
                    const link = document.createElement('a');
                    link.href = URL.createObjectURL(blob);
                    link.download = `run-summary-${jobId}.csv`;
                    link.click();
                    URL.revokeObjectURL(link.href);
                  }}
                >
                  Download CSV
                </button>
              </div>

              <div className="grid grid-cols-1 gap-3 text-sm">
                <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-3 space-y-2">
                  <div className="text-xs uppercase tracking-wide text-slate-500">
                    Identity
                  </div>
                  <div>
                    <div className="text-xs text-slate-400">Job ID</div>
                    <div className="font-mono break-all">{jobId}</div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <div className="text-xs text-slate-400">Status</div>
                      <div>{formatValue(runSummary.status)}</div>
                    </div>
                    <div>
                      <div className="text-xs text-slate-400">Model</div>
                      <div>{formatValue(runSummary.model_id)}</div>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <div className="text-xs text-slate-400">Dataset</div>
                      <div>{formatValue(runSummary.dataset_id)}</div>
                    </div>
                    <div>
                      <div className="text-xs text-slate-400">Distributed</div>
                      <div>{formatValue(runSummary.distributed)}</div>
                    </div>
                  </div>
                  {runSummary.display_name && (
                    <div>
                      <div className="text-xs text-slate-400">Display name</div>
                      <div>{formatValue(runSummary.display_name)}</div>
                    </div>
                  )}
                  {runSummary.notes && (
                    <div>
                      <div className="text-xs text-slate-400">Notes</div>
                      <div className="whitespace-pre-wrap break-words">
                        {formatValue(runSummary.notes)}
                      </div>
                    </div>
                  )}
                </div>

                <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-3 space-y-2">
                  <div className="text-xs uppercase tracking-wide text-slate-500">
                    Data & artifacts
                  </div>
                  <div>
                    <div className="text-xs text-slate-400">Dataset URI</div>
                    {runSummary.dataset_uri ? (
                      <a
                        className="text-sky-300 hover:text-sky-200 break-all"
                        href={runSummary.dataset_uri}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {runSummary.dataset_uri}
                      </a>
                    ) : (
                      <div>—</div>
                    )}
                  </div>
                  <div>
                    <div className="text-xs text-slate-400">Artifact URI</div>
                    {runSummary.artifact_uri ? (
                      <a
                        className="text-sky-300 hover:text-sky-200 break-all"
                        href={runSummary.artifact_uri}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {runSummary.artifact_uri}
                      </a>
                    ) : (
                      <div>—</div>
                    )}
                  </div>
                </div>

                <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-3 space-y-2">
                  <div className="text-xs uppercase tracking-wide text-slate-500">
                    Timing
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <div className="text-xs text-slate-400">Created</div>
                      <div>{formatDateTime(runSummary.created_at)}</div>
                    </div>
                    <div>
                      <div className="text-xs text-slate-400">Submitted</div>
                      <div>{formatDateTime(runSummary.submitted_at)}</div>
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-400">Last update</div>
                    <div>{formatDateTime(runSummary.updated_at)}</div>
                  </div>
                </div>

                <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-3 space-y-2">
                  <div className="text-xs uppercase tracking-wide text-slate-500">
                    Metrics snapshot
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <div className="text-xs text-slate-400">Last loss</div>
                      <div>{formatValue(runSummary.metrics_last_loss)}</div>
                    </div>
                    <div>
                      <div className="text-xs text-slate-400">Last accuracy</div>
                      <div>{formatValue(runSummary.metrics_last_accuracy)}</div>
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-400">Metric points</div>
                    <div>{formatValue(runSummary.metrics_points)}</div>
                  </div>
                </div>

                {runSummary.error && (
                  <div className="bg-rose-950/40 border border-rose-800 rounded-lg p-3 space-y-2">
                    <div className="text-xs uppercase tracking-wide text-rose-300">
                      Error
                    </div>
                    <pre className="text-xs whitespace-pre-wrap break-words text-rose-200">
                      {JSON.stringify(runSummary.error, null, 2)}
                    </pre>
                  </div>
                )}

                <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-3 space-y-2">
                  <div className="text-xs uppercase tracking-wide text-slate-500">
                    Export metadata
                  </div>
                  <div className="grid grid-cols-2 gap-3 text-xs text-slate-400">
                    <div>Events loaded: {formatValue(runSummary.events_loaded)}</div>
                    <div>Partial: {formatValue(runSummary.events_partial)}</div>
                  </div>
                  <div className="text-xs text-slate-500">
                    Generated at {formatDateTime(runSummary.generated_at)}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default JobDetail;
