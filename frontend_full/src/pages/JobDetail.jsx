import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api, handleApiError } from '../hooks/useApi';
import { WS_BASE_URL } from '../config';
import { useWebSocket } from '../hooks/useWebSocket';
import JobStatusBadge from '../components/JobStatusBadge';
import LogPanel from '../components/LogPanel';
import Spinner from '../components/Spinner';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

const JobDetail = () => {
  const { jobId } = useParams();
  const [job, setJob] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [logs, setLogs] = useState([]);
  const [metrics, setMetrics] = useState([]);



const parseHistoryEvents = (events) => {
  const logs = [];
  const metrics = [];
  let lastStatus = null;

  for (const ev of events) {
    const p = ev.payload || {};
    const t = (p.type || '').toUpperCase();

    if (t === 'JOB_LOG') {
      if (p.message) logs.push(p.message);
    }

    if (t === 'EPOCH_METRIC' || t === 'JOB_METRIC') {
      // Normalize to chart format expected by your <LineChart dataKey="loss" dataKey="step">
      // You currently have epoch + loss; convert epoch -> step
      const step = p.step ?? p.epoch ?? null;
      if (step !== null && p.loss !== undefined) {
        metrics.push({ step, loss: p.loss, ...p });
      }
    }

    if (t.startsWith('JOB_')) {
      // Use a stable set of statuses for badge
      if (t === 'JOB_COMPLETED') lastStatus = 'COMPLETED';
      else if (t === 'JOB_FAILED') lastStatus = 'FAILED';
      else if (t === 'JOB_RUNNING' || t === 'JOB_STARTED') lastStatus = 'RUNNING';
      else if (t === 'JOB_SUBMITTED') lastStatus = 'SUBMITTED';
      else lastStatus = t.replace('JOB_', '');
    }
  }

  // Ensure metrics are in order
  metrics.sort((a, b) => (a.step ?? 0) - (b.step ?? 0));

  return { logs, metrics, lastStatus };
};

  //  This ensures:
  // loading starts true
  // After the HTTP call finishes (success or error), loading becomes false
  // On success, job is a full object { id, status, config, model_id, dataset_id, ... }
  // So the UI can render even if WS isn’t doing anything yet.
  useEffect(() => {
    let cancelled = false;

    const loadJobAndHistory = async () => {
      setLoading(true);
      setErr('');
      setLogs([]);
      setMetrics([]);

      try {
        const [jobRes, evRes] = await Promise.all([
          api.get(`/jobs/${jobId}`),
          api.get(`/jobs/${jobId}/events?since_id=0&limit=5000`),
        ]);

        if (cancelled) return;

        const jobData = jobRes.data;
        const events = evRes.data || [];

        const { logs, metrics, lastStatus } = parseHistoryEvents(events);

        setJob(lastStatus ? { ...jobData, status: jobData.status || lastStatus } : jobData);
        setLogs(logs.slice(-500));
        setMetrics(metrics);

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
  }, [jobId]);




  const wsUrl = `${WS_BASE_URL}/ws/jobs/${jobId}`;

useWebSocket(
  wsUrl,
  (msg) => {
    console.log("JobDetail received ws msg type=%s value=%r", msg.type, msg);
    const t = (msg?.type || '').toLowerCase();

    // UI-friendly messages
    if (t === 'log') {
      setLogs((prev) => [...prev, msg.message].slice(-500));
      return;
    }
    if (t === 'metric') {
      const m = msg.metric || {};
      const step = m.step ?? m.epoch;
      setMetrics((prev) => [...prev, { ...m, step }].sort((a,b)=> (a.step??0)-(b.step??0)));
      return;
    }
    if (t === 'status') {
      setJob((prev) => (prev ? { ...prev, status: msg.status } : { id: jobId, status: msg.status, config: {} }));
      return;
    }

    // If backend ever sends raw events, support them too
    const rawType = (msg?.event_type || msg?.payload?.type || msg?.type || '').toUpperCase();
    if (rawType === 'JOB_LOG' && msg.payload?.message) {
      setLogs((prev) => [...prev, msg.payload.message].slice(-500));
    }
    if ((rawType === 'EPOCH_METRIC' || rawType === 'JOB_METRIC') && msg.payload?.loss !== undefined) {
      const step = msg.payload.step ?? msg.payload.epoch;
      setMetrics((prev) => [...prev, { ...msg.payload, step }].sort((a,b)=> (a.step??0)-(b.step??0)));
    }
  },
  { reconnectInterval: 2000, maxReconnectAttempts: 10 }
);



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

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold mb-1">Job {jobId}</h1>
        <JobStatusBadge status={job.status} />
        <div className="mt-2 text-xs text-slate-400">
          Model:{' '}
          <span className="font-mono">{cfg.model_id || job.model_id}</span> | Dataset:{' '}
          <span className="font-mono">
            {cfg.dataset_id || job.dataset_id}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div>
          <h2 className="text-sm font-semibold mb-2">Logs</h2>
          <LogPanel lines={logs} />
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
                  <XAxis dataKey="step" tick={{ fill: '#9ca3af', fontSize: 10 }} />
                  <YAxis tick={{ fill: '#9ca3af', fontSize: 10 }} />
                  <Tooltip />
                  <Line
                    type="monotone"
                    dataKey="loss"
                    stroke="#38bdf8"
                    dot={false}
                    strokeWidth={1.6}
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
    </div>
  );
};

export default JobDetail;
