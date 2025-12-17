import React, { useEffect, useState } from 'react';
import { api, handleApiError } from '../hooks/useApi';
import { WS_BASE_URL } from '../config';
import { useWebSocket } from '../hooks/useWebSocket';
import Spinner from '../components/Spinner';

const Deployments = () => {
  const [deployments, setDeployments] = useState([]);
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await api.get('/deployments');
        setDeployments(res.data || []);
      } catch (e) {
        setErr(handleApiError(e));
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const wsUrl = `${WS_BASE_URL}/ws/deployments`;
  useWebSocket(wsUrl, (msg) => {
    if (!msg.id) return;
    setDeployments((prev) => {
      const existing = prev.find((d) => d.id === msg.id);
      if (existing) {
        return prev.map((d) => (d.id === msg.id ? { ...d, ...msg } : d));
      }
      return [...prev, msg];
    });
  });

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Model Deployments</h1>

      {loading && (
        <div className="flex items-center gap-2 text-slate-400">
          <Spinner /> <span>Loading deployments…</span>
        </div>
      )}

      {err && (
        <div className="text-sm text-rose-300 bg-rose-950/40 border border-rose-800 rounded p-3">
          Could not load deployments: {err}
          <div className="mt-1 text-xs text-rose-200/80">
            (Implement <code>GET /deployments</code> and/or{' '}
            <code>WS /ws/deployments</code> in your backend.)
          </div>
        </div>
      )}

      {deployments.length === 0 && !loading && !err && (
        <div className="text-sm text-slate-400">No deployments.</div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {deployments.map((d) => (
          <div
            key={d.id}
            className="bg-slate-900/60 border border-slate-800 rounded-lg p-4 space-y-2"
          >
            <div className="flex justify-between items-center">
              <div className="font-semibold">{d.name || d.id}</div>
              <span
                className={`text-xs px-2 py-0.5 rounded-full border ${
                  d.status === 'RUNNING'
                    ? 'border-emerald-500/60 text-emerald-300 bg-emerald-500/10'
                    : 'border-slate-600 text-slate-300 bg-slate-600/10'
                }`}
              >
                {d.status || 'UNKNOWN'}
              </span>
            </div>
            <div className="text-xs text-slate-400">
              Version: {d.version || 'n/a'}
            </div>
            {d.endpoint && (
              <div className="text-xs">
                Endpoint:{' '}
                <a
                  href={d.endpoint}
                  className="text-sky-400 underline"
                  target="_blank"
                  rel="noreferrer"
                >
                  {d.endpoint}
                </a>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default Deployments;
