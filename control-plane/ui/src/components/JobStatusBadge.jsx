import React from 'react';

const colors = {
  SUBMITTED: 'bg-blue-500/20 text-blue-300 border-blue-500/40',
  PENDING: 'bg-blue-500/20 text-blue-300 border-blue-500/40',
  RUNNING: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
  PREEMPTED: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
  SUCCEEDED: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
  FAILED: 'bg-rose-500/20 text-rose-300 border-rose-500/40',
  CANCELLED: 'bg-slate-500/20 text-slate-300 border-slate-500/40',
  UNKNOWN: 'bg-slate-500/20 text-slate-300 border-slate-500/40',
};

const JobStatusBadge = ({ status }) => {
  const s = (status || 'UNKNOWN').toUpperCase();
  const cls = colors[s] || colors.UNKNOWN;
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full border text-xs ${cls}`}>
      {s}
    </span>
  );
};

export default JobStatusBadge;
