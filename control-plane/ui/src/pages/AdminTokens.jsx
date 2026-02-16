import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { api, handleApiError } from '../hooks/useApi';
import Spinner from '../components/Spinner';
import { useAppAuth } from '../context/AppAuthContext';
import { hasMinRole } from '../utils/roles';

const formatTs = (value) => {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString();
};

const AdminTokens = () => {
  const { role, loading: roleLoading } = useAppAuth();
  const isAdmin = hasMinRole(role, 'admin');
  const [tokens, setTokens] = useState([]);
  const [tenantId, setTenantId] = useState('');
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');
  const [tokenLabel, setTokenLabel] = useState('');
  const [minting, setMinting] = useState(false);
  const [newToken, setNewToken] = useState(null);
  const [retentionDays, setRetentionDays] = useState('');
  const [retentionDefault, setRetentionDefault] = useState(null);
  const [retentionSource, setRetentionSource] = useState('default');
  const [savingRetention, setSavingRetention] = useState(false);
  const [exporting, setExporting] = useState(false);

  const loadTokens = useCallback(async () => {
    if (!isAdmin) return;
    setLoading(true);
    setErr('');
    try {
      const res = await api.get('/admin/data-plane-tokens');
      setTokens(res.data?.tokens || []);
      setTenantId(res.data?.tenant_id || '');
    } catch (e) {
      setErr(handleApiError(e));
    } finally {
      setLoading(false);
    }
  }, [isAdmin]);

  const loadRetention = useCallback(async () => {
    if (!isAdmin) return;
    try {
      const res = await api.get('/admin/settings/retention');
      const days = res.data?.event_retention_days;
      setRetentionDays(days === null || days === undefined ? '' : String(days));
      setRetentionDefault(res.data?.default_event_retention_days ?? null);
      setRetentionSource(res.data?.source || 'default');
    } catch (e) {
      setErr(handleApiError(e));
    }
  }, [isAdmin]);

  useEffect(() => {
    loadTokens();
    loadRetention();
  }, [loadTokens, loadRetention]);

  const activeTokens = useMemo(
    () => tokens.filter((token) => !token.revoked_at),
    [tokens]
  );

  const revokeToken = async (tokenId) => {
    setErr('');
    try {
      await api.delete(`/admin/data-plane-tokens/${tokenId}`);
      await loadTokens();
    } catch (e) {
      setErr(handleApiError(e));
    }
  };

  const mintToken = async () => {
    setErr('');
    setMinting(true);
    try {
      const label = tokenLabel.trim();
      const payload = label ? { token_label: label } : {};
      const res = await api.post('/admin/data-plane-tokens', payload);
      setNewToken(res.data);
      setTokenLabel('');
      await loadTokens();
    } catch (e) {
      setErr(handleApiError(e));
    } finally {
      setMinting(false);
    }
  };

  const saveRetention = async (valueOverride = retentionDays) => {
    setErr('');
    const parsed = valueOverride === '' ? null : Number(valueOverride);
    if (parsed !== null && (!Number.isFinite(parsed) || parsed < 0)) {
      setErr('Retention days must be a non-negative number.');
      return;
    }
    setSavingRetention(true);
    try {
      const res = await api.put('/admin/settings/retention', {
        event_retention_days: parsed,
      });
      const days = res.data?.event_retention_days;
      setRetentionDays(days === null || days === undefined ? '' : String(days));
      setRetentionDefault(res.data?.default_event_retention_days ?? null);
      setRetentionSource(res.data?.source || 'default');
    } catch (e) {
      setErr(handleApiError(e));
    } finally {
      setSavingRetention(false);
    }
  };

  const resetRetention = async () => {
    setRetentionDays('');
    await saveRetention('');
  };

  const downloadAudit = async (format) => {
    setErr('');
    setExporting(true);
    try {
      const res = await api.get(`/admin/audit/export?format=${format}`, {
        responseType: 'blob',
      });
      const blob = new Blob([res.data], {
        type: res.headers['content-type'] || 'application/octet-stream',
      });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `audit-export.${format === 'csv' ? 'csv' : 'json'}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      setErr(handleApiError(e));
    } finally {
      setExporting(false);
    }
  };

  if (roleLoading) {
    return <Spinner />;
  }

  if (!isAdmin) {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-slate-900">Admin only</h2>
        <p className="mt-2 text-sm text-slate-600">
          You don’t have permission to manage data-plane tokens.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-100">Data-plane tokens</h1>
        <p className="mt-2 text-sm text-slate-300">
          Mint and revoke tokens used by data-plane launchers. Tokens are shown
          only once when created.
        </p>
        {tenantId && (
          <div className="mt-2 text-xs text-slate-400">Tenant: {tenantId}</div>
        )}
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-5 text-slate-900">
        <h2 className="text-sm font-semibold text-slate-900">Mint new token</h2>
        <div className="mt-4 flex flex-col gap-3 md:flex-row md:items-center">
          <input
            type="text"
            value={tokenLabel}
            onChange={(e) => setTokenLabel(e.target.value)}
            placeholder="Label (optional) — e.g. prod-eks"
            className="w-full md:flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          <button
            type="button"
            onClick={mintToken}
            disabled={minting}
            className="px-4 py-2 rounded-lg bg-slate-900 text-white text-sm hover:bg-slate-800 disabled:opacity-60"
          >
            {minting ? 'Minting…' : 'Mint token'}
          </button>
        </div>
        {newToken && (
          <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
            <div className="font-semibold">New token created</div>
            <div className="mt-2 font-mono break-all">{newToken.token}</div>
            <div className="mt-2 text-xs text-emerald-700">
              Save this token now — it will not be shown again.
            </div>
          </div>
        )}
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-5 text-slate-900">
        <h2 className="text-sm font-semibold text-slate-900">Retention settings</h2>
        <p className="mt-2 text-sm text-slate-600">
          Control how long job events and logs are retained for this tenant.
          Set to 0 to disable retention-based pruning.
        </p>
        <div className="mt-4 flex flex-col gap-3 md:flex-row md:items-center">
          <input
            type="number"
            min="0"
            value={retentionDays}
            onChange={(e) => setRetentionDays(e.target.value)}
            placeholder="Retention days"
            className="w-full md:flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          <button
            type="button"
            onClick={saveRetention}
            disabled={savingRetention}
            className="px-4 py-2 rounded-lg bg-slate-900 text-white text-sm hover:bg-slate-800 disabled:opacity-60"
          >
            {savingRetention ? 'Saving…' : 'Save'}
          </button>
          <button
            type="button"
            onClick={resetRetention}
            disabled={savingRetention}
            className="px-4 py-2 rounded-lg border border-slate-300 text-sm text-slate-700 hover:border-slate-400 disabled:opacity-60"
          >
            Reset
          </button>
        </div>
        <div className="mt-3 text-xs text-slate-500">
          Source: {retentionSource}
          {retentionDefault !== null && (
            <span className="ml-2">Default: {retentionDefault} days</span>
          )}
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-5 text-slate-900">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-900">Active tokens</h2>
          <button
            type="button"
            onClick={loadTokens}
            className="text-xs text-slate-600 hover:text-slate-900"
          >
            Refresh
          </button>
        </div>

        {err && (
          <div className="mt-3 text-sm text-rose-600">{err}</div>
        )}

        {loading ? (
          <div className="mt-4">
            <Spinner />
          </div>
        ) : activeTokens.length === 0 ? (
          <div className="mt-4 text-sm text-slate-500">No active tokens.</div>
        ) : (
          <div className="mt-4 overflow-auto">
            <table className="min-w-full text-sm text-slate-800">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="py-2 pr-4">Label</th>
                  <th className="py-2 pr-4">Prefix</th>
                  <th className="py-2 pr-4">Created</th>
                  <th className="py-2 pr-4">Last used</th>
                  <th className="py-2 pr-4"></th>
                </tr>
              </thead>
              <tbody>
                {activeTokens.map((token) => (
                  <tr key={token.token_id} className="border-t border-slate-200">
                    <td className="py-2 pr-4">
                      {token.token_label || <span className="text-slate-400">—</span>}
                    </td>
                    <td className="py-2 pr-4 font-mono">{token.token_prefix}</td>
                    <td className="py-2 pr-4">{formatTs(token.created_at)}</td>
                    <td className="py-2 pr-4">{formatTs(token.last_used_at)}</td>
                    <td className="py-2 pr-2 text-right">
                      <button
                        type="button"
                        onClick={() => revokeToken(token.token_id)}
                        className="text-xs text-rose-600 hover:text-rose-700"
                      >
                        Revoke
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-5 text-slate-900">
        <h2 className="text-sm font-semibold text-slate-900">Audit export</h2>
        <p className="mt-2 text-sm text-slate-600">
          Download job history and event activity for compliance reviews.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => downloadAudit('json')}
            disabled={exporting}
            className="px-4 py-2 rounded-lg bg-slate-900 text-white text-sm hover:bg-slate-800 disabled:opacity-60"
          >
            {exporting ? 'Preparing…' : 'Download JSON'}
          </button>
          <button
            type="button"
            onClick={() => downloadAudit('csv')}
            disabled={exporting}
            className="px-4 py-2 rounded-lg border border-slate-300 text-sm text-slate-700 hover:border-slate-400 disabled:opacity-60"
          >
            {exporting ? 'Preparing…' : 'Download CSV'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default AdminTokens;
