import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, handleApiError } from '../hooks/useApi';
import Spinner from '../components/Spinner';

const steps = ['Model & Dataset', 'Hyperparameters', 'Extras'];

const NewJobWizard = () => {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState({
    modelId: '',
    datasetId: '',
    epochs: 1,
    batchSize: 32,
    learningRate: 0.001,
    distributed: false,
    displayName: '',
    notes: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [jobId, setJobId] = useState('');
  const navigate = useNavigate();

  const updateField = (key, value) => setForm((f) => ({ ...f, [key]: value }));
  const next = () => setStep((s) => Math.min(s + 1, steps.length - 1));
  const back = () => setStep((s) => Math.max(s - 1, 0));

  const onSubmit = async () => {
    setSubmitting(true);
    setError('');
    try {
      const payload = {
        model_id: form.modelId,
        dataset_id: form.datasetId,
        epochs: Number(form.epochs),
        batch_size: Number(form.batchSize),
        lr: Number(form.learningRate),
        distributed: !!form.distributed,
        extra_config: {
          display_name: form.displayName || undefined,
          notes: form.notes || undefined,
        },
      };
      const res = await api.post('/jobs/train', payload);
      setJobId(res.data.job_id);
    } catch (e) {
      setError(handleApiError(e));
    } finally {
      setSubmitting(false);
    }
  };

  const goToJob = () => {
    if (jobId) navigate(`/jobs/${jobId}`);
  };

  return (
    <div className="max-w-xl space-y-4">
      <h1 className="text-xl font-semibold">Launch Training Job</h1>

      <div className="flex gap-2 text-xs">
        {steps.map((label, idx) => (
          <div
            key={label}
            className={`flex-1 px-2 py-1 rounded border ${
              idx === step
                ? 'border-sky-500 bg-sky-500/10 text-sky-300'
                : 'border-slate-700 text-slate-400'
            }`}
          >
            {idx + 1}. {label}
          </div>
        ))}
      </div>

      <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-4 space-y-4">
        {step === 0 && (
          <>
            <div>
              <label className="block text-sm mb-1">Model ID</label>
              <input
                className="w-full rounded-md bg-slate-950 border border-slate-700 px-3 py-2 text-sm"
                value={form.modelId}
                onChange={(e) => updateField('modelId', e.target.value)}
                placeholder="e.g. resnet50-v1"
              />
            </div>
            <div>
              <label className="block text-sm mb-1">Dataset ID</label>
              <input
                className="w-full rounded-md bg-slate-950 border border-slate-700 px-3 py-2 text-sm"
                value={form.datasetId}
                onChange={(e) => updateField('datasetId', e.target.value)}
                placeholder="e.g. imagenet-1k"
              />
            </div>
          </>
        )}

        {step === 1 && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label className="block text-sm mb-1">Epochs</label>
              <input
                type="number"
                min={1}
                className="w-full rounded-md bg-slate-950 border border-slate-700 px-3 py-2 text-sm"
                value={form.epochs}
                onChange={(e) => updateField('epochs', e.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm mb-1">Batch size</label>
              <input
                type="number"
                min={1}
                className="w-full rounded-md bg-slate-950 border border-slate-700 px-3 py-2 text-sm"
                value={form.batchSize}
                onChange={(e) => updateField('batchSize', e.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm mb-1">Learning rate</label>
              <input
                type="number"
                step="0.00001"
                className="w-full rounded-md bg-slate-950 border border-slate-700 px-3 py-2 text-sm"
                value={form.learningRate}
                onChange={(e) => updateField('learningRate', e.target.value)}
              />
            </div>
            <div className="md:col-span-3">
              <label className="inline-flex gap-2 items-center text-sm">
                <input
                  type="checkbox"
                  checked={form.distributed}
                  onChange={(e) => updateField('distributed', e.target.checked)}
                />
                <span>Distributed (multi-GPU / multi-node)</span>
              </label>
            </div>
          </div>
        )}

        {step === 2 && (
          <>
            <div>
              <label className="block text-sm mb-1">Display name</label>
              <input
                className="w-full rounded-md bg-slate-950 border border-slate-700 px-3 py-2 text-sm"
                value={form.displayName}
                onChange={(e) => updateField('displayName', e.target.value)}
                placeholder="Optional friendly name"
              />
            </div>
            <div>
              <label className="block text-sm mb-1">Notes</label>
              <textarea
                className="w-full rounded-md bg-slate-950 border border-slate-700 px-3 py-2 text-sm"
                rows={3}
                value={form.notes}
                onChange={(e) => updateField('notes', e.target.value)}
                placeholder="Optional run notes / ticket IDs"
              />
            </div>
          </>
        )}
      </div>

      {error && (
        <div className="text-sm text-rose-300 bg-rose-950/40 border border-rose-800 rounded p-3">
          Failed to submit job: {error}
        </div>
      )}

      <div className="flex items-center justify-between">
        <button
          onClick={back}
          disabled={step === 0}
          className="px-3 py-1.5 rounded-md border border-slate-700 text-sm text-slate-200 disabled:opacity-40"
        >
          Back
        </button>
        {step < steps.length - 1 ? (
          <button
            onClick={next}
            className="px-4 py-1.5 rounded-md bg-sky-500 text-sm font-medium hover:bg-sky-400"
          >
            Next
          </button>
        ) : (
          <button
            onClick={onSubmit}
            disabled={submitting}
            className="px-4 py-1.5 rounded-md bg-emerald-500 text-sm font-medium hover:bg-emerald-400 disabled:opacity-60 flex items-center gap-2"
          >
            {submitting && <Spinner />}
            <span>Launch job</span>
          </button>
        )}
      </div>

      {jobId && (
        <div className="mt-4 text-sm bg-emerald-950/40 border border-emerald-700 rounded p-3">
          Job submitted with ID:{' '}
          <button className="text-emerald-300 underline" onClick={goToJob}>
            {jobId}
          </button>
        </div>
      )}
    </div>
  );
};

export default NewJobWizard;
