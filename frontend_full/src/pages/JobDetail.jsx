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

  useEffect(() => {
    const loadJob = async () => {
      try {
        const res = await api.get(`/jobs/${jobId}`);
        setJob(res.data);
      } catch (e) {
        setErr(handleApiError(e));
      } finally {
        setLoading(false);
      }
    };
    loadJob();
  }, [jobId]);

  const wsUrl = `${WS_BASE_URL}/ws/jobs/${jobId}`;

  useWebSocket(
    wsUrl,
    (msg) => {
      switch (msg.type) {
        case 'log':
          setLogs((prev) => [...prev, msg.message].slice(-500));
          break;
        case 'metric':
          setMetrics((prev) => [...prev, msg.metric]);
          break;
        case 'status':
          setJob((prev) => (prev ? { ...prev, status: msg.status } : prev));
          break;
        default:
          break;
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
          (Implement <code>GET /jobs/{{job_id}}</code> in your control-plane.)
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
