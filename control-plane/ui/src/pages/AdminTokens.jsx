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

const PAID_STATUSES = new Set(['active', 'trialing', 'past_due']);

const AdminTokens = () => {
  const { role, loading: roleLoading } = useAppAuth();
  const isAdmin = hasMinRole(role, 'admin');
  const [tokens, setTokens] = useState([]);
  const [tenantId, setTenantId] = useState('');
  const [loading, setLoading] = useState(false);
  const [tokenErr, setTokenErr] = useState('');
  const [retentionErr, setRetentionErr] = useState('');
  const [exportErr, setExportErr] = useState('');
  const [tokenLabel, setTokenLabel] = useState('');
  const [minting, setMinting] = useState(false);
  const [newToken, setNewToken] = useState(null);
  const [retentionDays, setRetentionDays] = useState('');
  const [retentionDefault, setRetentionDefault] = useState(null);
  const [retentionSource, setRetentionSource] = useState('default');
  const [savingRetention, setSavingRetention] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [billingErr, setBillingErr] = useState('');
  const [billingLoading, setBillingLoading] = useState(false);
  const [syncingBilling, setSyncingBilling] = useState(false);
  const [billingStatus, setBillingStatus] = useState(null);
  const [billingStatusErr, setBillingStatusErr] = useState('');

  const loadTokens = useCallback(async () => {
    if (!isAdmin) return;
    setLoading(true);
    setTokenErr('');
    try {
      const res = await api.get('/admin/data-plane-tokens');
      setTokens(res.data?.tokens || []);
      setTenantId(res.data?.tenant_id || '');
    } catch (e) {
      setTokenErr(handleApiError(e));
    } finally {
      setLoading(false);
    }
  }, [isAdmin]);

  const loadRetention = useCallback(async () => {
    if (!isAdmin) return;
    try {
      const res = await api.get('/admin/settings/retention');
      const days = res.data?.event_retention_days;
      const normalizedDays =
        days === null || days === undefined
          ? ''
          : String(Math.max(0, Math.floor(Number(days))));
      setRetentionDays(normalizedDays);
      setRetentionDefault(res.data?.default_event_retention_days ?? null);
      setRetentionSource(res.data?.source || 'default');
    } catch (e) {
      setRetentionErr(handleApiError(e));
    }
  }, [isAdmin]);

  const loadBillingStatus = useCallback(async () => {
    if (!isAdmin) return;
    setBillingStatusErr('');
    try {
      const res = await api.get('/billing/status');
      setBillingStatus(res.data || null);
    } catch (e) {
      setBillingStatusErr(handleApiError(e));
    }
  }, [isAdmin]);

  useEffect(() => {
    loadTokens();
    loadRetention();
    loadBillingStatus();
  }, [loadTokens, loadRetention, loadBillingStatus]);

  const activeTokens = useMemo(
    () => tokens.filter((token) => !token.revoked_at),
    [tokens]
  );
  const isSubscribed = PAID_STATUSES.has(billingStatus?.status);

  const revokeToken = async (tokenId) => {
    setTokenErr('');
    try {
      await api.delete(`/admin/data-plane-tokens/${tokenId}`);
      await loadTokens();
    } catch (e) {
      setTokenErr(handleApiError(e));
    }
  };

  const mintToken = async () => {
    setTokenErr('');
    setMinting(true);
    try {
      const label = tokenLabel.trim();
      const payload = label ? { token_label: label } : {};
      const res = await api.post('/admin/data-plane-tokens', payload);
      setNewToken(res.data);
      setTokenLabel('');
      await loadTokens();
    } catch (e) {
      setTokenErr(handleApiError(e));
    } finally {
      setMinting(false);
    }
  };

  const saveRetention = async (valueOverride = retentionDays) => {
    setRetentionErr('');
    if (valueOverride && typeof valueOverride === 'object' && valueOverride.nativeEvent) {
      valueOverride = retentionDays;
    }
    const raw = String(valueOverride ?? '').trim();
    const parsed = raw === '' ? null : Number(raw);
    if (parsed !== null && (!Number.isFinite(parsed) || parsed < 0)) {
      setRetentionErr('Retention days must be a non-negative number.');
      return;
    }
    setSavingRetention(true);
    try {
      const res = await api.put('/admin/settings/retention', {
        event_retention_days: parsed,
      });
      const days = res.data?.event_retention_days;
      const normalizedDays =
        days === null || days === undefined
          ? ''
          : String(Math.max(0, Math.floor(Number(days))));
      setRetentionDays(normalizedDays);
      setRetentionDefault(res.data?.default_event_retention_days ?? null);
      setRetentionSource(res.data?.source || 'default');
    } catch (e) {
      setRetentionErr(handleApiError(e));
    } finally {
      setSavingRetention(false);
    }
  };

  const resetRetention = async () => {
    setRetentionDays('');
    await saveRetention('');
  };

  const downloadAudit = async (format) => {
    setExportErr('');
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
      setExportErr(handleApiError(e));
    } finally {
      setExporting(false);
    }
  };

  const openBillingPortal = async () => {
    setBillingErr('');
    setBillingLoading(true);
    try {
      const res = await api.post('/billing/portal', {
        return_url: window.location.href,
      });
      const url = res.data?.url;
      if (url) {
        window.location.href = url;
      } else {
        setBillingErr('Billing portal URL was not returned.');
      }
    } catch (e) {
      setBillingErr(handleApiError(e));
    } finally {
      setBillingLoading(false);
    }
  };

  const startSubscription = async () => {
    setBillingErr('');
    setBillingLoading(true);
    try {
      const res = await api.post('/billing/checkout', {
        return_url: window.location.href,
      });
      const url = res.data?.url;
      if (url) {
        window.location.href = url;
      } else {
        setBillingErr('Checkout URL was not returned.');
      }
    } catch (e) {
      setBillingErr(handleApiError(e));
    } finally {
      setBillingLoading(false);
    }
  };

  const syncBilling = async () => {
    setBillingErr('');
    setSyncingBilling(true);
    try {
      await api.post('/billing/sync');
      await loadBillingStatus();
    } catch (e) {
      setBillingErr(handleApiError(e));
    } finally {
      setSyncingBilling(false);
    }
  };

  const statusLabel = (status) => {
    if (!status) return 'Not subscribed';
    return status.replace('_', ' ');
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
        <h1 className="text-2xl font-semibold text-slate-100">Admin console</h1>
        <p className="mt-2 text-sm text-slate-300">
          Manage data-plane access tokens, retention settings, and audit exports.
        </p>
        {tenantId && (
          <div className="mt-2 text-xs text-slate-400">Tenant: {tenantId}</div>
        )}
      </div>

      <div className="bg-white border border-slate-200 rounded-2xl p-5 text-slate-900">
        <div className="text-xs uppercase tracking-[0.2em] text-slate-500">
          Token management
        </div>
        <div className="mt-4 space-y-6">
          <div className="rounded-xl border border-slate-200 p-4">
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

          <div className="rounded-xl border border-slate-200 p-4">
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

            {tokenErr && (
              <div className="mt-3 text-sm text-rose-600">{tokenErr}</div>
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
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-5 text-slate-900">
        <h2 className="text-sm font-semibold text-slate-900">Retention (days)</h2>
        <p className="mt-2 text-sm text-slate-600">
          Control how long job events and logs are retained for this tenant.
          Set to 0 to disable retention-based pruning.
        </p>
        <div className="mt-4 flex flex-col gap-3 md:flex-row md:items-center">
          <input
            type="number"
            min="0"
            value={retentionDays}
            onChange={(e) => {
              setRetentionDays(e.target.value);
              setRetentionErr('');
            }}
            placeholder="Retention days"
            className="w-full md:flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          <button
            type="button"
            onClick={() => saveRetention()}
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
            <span className="ml-2">
              Default:{' '}
              {retentionDefault <= 0 ? 'disabled' : `${retentionDefault} days`}
            </span>
          )}
        </div>
        {retentionErr && (
          <div className="mt-3 text-sm text-rose-600">{retentionErr}</div>
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
        {exportErr && (
          <div className="mt-3 text-sm text-rose-600">{exportErr}</div>
        )}
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-5 text-slate-900">
        <h2 className="text-sm font-semibold text-slate-900">Billing</h2>
        <p className="mt-2 text-sm text-slate-600">
          Manage your subscription and payment method in Stripe.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-600">
          <span className="uppercase tracking-wide text-slate-500">Status</span>
          <span className="px-2 py-1 rounded-full bg-slate-100 border border-slate-200 text-slate-700">
            {statusLabel(billingStatus?.status)}
          </span>
          {billingStatus?.cancel_at_period_end && (
            <span className="px-2 py-1 rounded-full bg-amber-100 border border-amber-200 text-amber-700">
              Canceling
            </span>
          )}
          {billingStatus?.current_period_end && (
            <span className="text-slate-500">
              Renews {formatTs(billingStatus.current_period_end)}
            </span>
          )}
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={startSubscription}
            disabled={billingLoading || isSubscribed}
            className="px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm hover:bg-emerald-500 disabled:opacity-60"
          >
            {billingLoading ? 'Opening…' : isSubscribed ? 'Subscription active' : 'Start subscription'}
          </button>
          <button
            type="button"
            onClick={openBillingPortal}
            disabled={billingLoading}
            className="px-4 py-2 rounded-lg bg-slate-900 text-white text-sm hover:bg-slate-800 disabled:opacity-60"
          >
            {billingLoading ? 'Opening…' : 'Manage billing'}
          </button>
          <button
            type="button"
            onClick={syncBilling}
            disabled={syncingBilling}
            className="px-4 py-2 rounded-lg border border-slate-300 text-sm text-slate-700 hover:border-slate-400 disabled:opacity-60"
          >
            {syncingBilling ? 'Syncing…' : 'Sync billing'}
          </button>
        </div>
        {(billingErr || billingStatusErr) && (
          <div className="mt-3 text-sm text-rose-600">
            {billingErr || billingStatusErr}
          </div>
        )}
      </div>
    </div>
  );
};

export default AdminTokens;
