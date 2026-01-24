import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, handleApiError } from '../hooks/useApi';
import { useWebSocket } from '../hooks/useWebSocket';
import { WS_BASE_URL } from '../config';
import { useClerkToken } from '../hooks/useClerkToken';
import JobStatusBadge from '../components/JobStatusBadge';
import Spinner from '../components/Spinner';

const Dashboard = () => {
  const pageSize = 50;
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [err, setErr] = useState('');
  const [hasMore, setHasMore] = useState(true);
  const [offset, setOffset] = useState(0);

  const fetchJobs = useCallback(
    async (nextOffset = 0) => {
      if (nextOffset === 0) {
        setLoading(true);
      } else {
        setLoadingMore(true);
      }
      setErr('');
      try {
        const res = await api.get('/jobs', {
          params: { limit: pageSize, offset: nextOffset },
        });
        const data = res.data || [];
        setJobs((prev) => (nextOffset === 0 ? data : [...prev, ...data]));
        setHasMore(data.length === pageSize);
        setOffset(nextOffset + data.length);
      } catch (e) {
        setErr(handleApiError(e));
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [pageSize]
  );

  useEffect(() => {
    fetchJobs(0);
  }, [fetchJobs]);

  const token = useClerkToken();
  const wsUrl = token ? `${WS_BASE_URL}/ws/jobs?token=${encodeURIComponent(token)}` : null;
  useWebSocket(wsUrl, (msg) => {
    const jobId = msg?.job_id;
    if (!jobId) return;
    const state = msg?.state;
    const eventType = (msg?.event_type || '').toUpperCase();
    const nextStatus = state || (eventType.startsWith('JOB_') ? eventType.replace('JOB_', '') : '');
    setJobs((prev) =>
      prev.map((job) => {
        if (job.job_id !== jobId) return job;
        const updates = {};
        if (nextStatus) updates.status = nextStatus;
        if (eventType === 'JOB_FAILED') {
          updates.last_error = msg?.data?.error || msg?.data || null;
        }
        return { ...job, ...updates };
      })
    );
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">Training Jobs</h1>
        <Link
          to="/jobs/new"
          className="px-3 py-1.5 rounded-md bg-sky-500 text-sm font-medium hover:bg-sky-400"
        >
          + New Job
        </Link>
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-slate-400">
          <Spinner /> <span>Loading jobs…</span>
        </div>
      )}

      {err && !loading && (
        <div className="text-sm text-rose-300 bg-rose-950/40 border border-rose-700/60 rounded p-3 mb-3">
          Could not load jobs from API: {err}
          <div className="mt-1 text-xs text-rose-200/80">
            (You may not have implemented <code>GET /jobs</code> yet.)
          </div>
        </div>
      )}

      {!loading && jobs.length === 0 && !err && (
        <div className="text-slate-400 text-sm">No jobs yet. Launch one!</div>
      )}

      {jobs.length > 0 && (
        <>
          <div className="border border-slate-800 rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-900/80">
                <tr>
                  <th className="px-3 py-2 text-left">Job ID</th>
                  <th className="px-3 py-2 text-left">Model</th>
                  <th className="px-3 py-2 text-left">Dataset</th>
                  <th className="px-3 py-2 text-left">Status</th>
                  <th className="px-3 py-2 text-left">Last Error</th>
                  <th className="px-3 py-2 text-left">Created</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.job_id} className="border-t border-slate-800/70">
                    <td className="px-3 py-2 font-mono text-xs">
                      <Link
                        to={`/jobs/${job.job_id}`}
                        className="text-sky-400 hover:underline"
                      >
                        {job.job_id}
                      </Link>
                    </td>
                    <td className="px-3 py-2">
                      {job.config?.model_id || job.model_id || '—'}
                    </td>
                    <td className="px-3 py-2">
                      {job.config?.dataset_id || job.dataset_id || '—'}
                    </td>
                    <td className="px-3 py-2">
                      <JobStatusBadge status={job.status} />
                    </td>
                    <td className="px-3 py-2 text-xs text-rose-300">
                      {job.last_error?.message || job.last_error?.type || ''}
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-400">
                      {job.created_at || ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {hasMore && (
            <div className="flex justify-center mt-4">
              <button
                type="button"
                onClick={() => {
                  setErr('');
                  fetchJobs(offset);
                }}
                className="px-3 py-1.5 rounded-md border border-slate-700 text-sm text-slate-200 hover:border-slate-500"
                disabled={loadingMore}
              >
                {loadingMore ? 'Loading…' : 'Load more'}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default Dashboard;
