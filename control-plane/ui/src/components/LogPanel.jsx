import React from 'react';

const LogPanel = ({ lines, emptyMessage = 'Waiting for logs…' }) => (
  <div className="bg-black/80 border border-slate-700 rounded-lg p-3 font-mono text-xs text-emerald-200 h-72 overflow-auto">
    {lines.length === 0 ? (
      <div className="text-slate-500 italic">{emptyMessage}</div>
    ) : (
      lines.map((line, idx) => <div key={idx}>{line}</div>)
    )}
  </div>
);

export default LogPanel;
