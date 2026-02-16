import React from 'react';
import { Link } from 'react-router-dom';

const Landing = () => {
  return (
    <div className="landing min-h-screen bg-[#f7f3ea] text-slate-900">
      <div className="relative overflow-hidden">
        <div className="absolute -top-24 -right-24 h-72 w-72 rounded-full bg-amber-200/60 blur-3xl" />
        <div className="absolute top-32 -left-24 h-80 w-80 rounded-full bg-emerald-200/50 blur-3xl" />
        <div className="absolute bottom-0 right-8 h-64 w-64 rounded-full bg-sky-200/60 blur-3xl" />

        <div className="relative max-w-6xl mx-auto px-6 pt-10 pb-16">
          <div className="mt-16 grid grid-cols-1 lg:grid-cols-[1.1fr_0.9fr] gap-10 items-center">
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-slate-500">
                Private ML training control plane
              </p>
              <h1 className="mt-4 text-4xl md:text-5xl font-semibold leading-tight">
                Run training jobs in your own cloud,
                <span className="landing-serif text-amber-700"> without the MLOps sprawl.</span>
              </h1>
              <p className="mt-5 text-lg text-slate-700">
                AiTrainOps gives you orchestration, live logs, and audit trails for
                Kubernetes training workloads. Built-in retries and role-based access
                keep every run safe and resilient.
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link
                  to="/register"
                  className="px-5 py-2 rounded-full bg-emerald-600 text-white hover:bg-emerald-500"
                >
                  Get early access
                </Link>
                <a
                  href="mailto:hello@aitrainops.com"
                  className="px-5 py-2 rounded-full border border-slate-300 text-slate-700 hover:border-slate-500"
                >
                  Talk to us
                </a>
              </div>
              <div className="mt-8 flex flex-wrap gap-4 text-xs text-slate-600">
                <span className="px-3 py-1 rounded-full bg-white/70 border border-slate-200">
                  Runs in your VPC
                </span>
                <span className="px-3 py-1 rounded-full bg-white/70 border border-slate-200">
                  No data egress
                </span>
                <span className="px-3 py-1 rounded-full bg-white/70 border border-slate-200">
                  Kubernetes-native
                </span>
              </div>
            </div>

            <div className="bg-white/80 backdrop-blur border border-slate-200 rounded-2xl p-6 shadow-lg">
              <p className="text-xs uppercase tracking-[0.25em] text-slate-500">
                Control + execution split
              </p>
              <div className="mt-4 space-y-4">
                {[
                  {
                    title: 'Your cloud',
                    body: 'Training jobs run inside your Kubernetes cluster with your GPUs and datasets.',
                  },
                  {
                    title: 'Our control plane',
                    body: 'Submit jobs, stream logs, and keep a reliable job history with audit trails.',
                  },
                  {
                    title: 'One install',
                    body: 'Deploy a lightweight agent with Helm and start running jobs in minutes.',
                  },
                ].map((item) => (
                  <div key={item.title} className="rounded-xl border border-slate-200 bg-white p-4">
                    <div className="text-sm font-semibold text-slate-900">{item.title}</div>
                    <div className="mt-1 text-sm text-slate-600">{item.body}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      <section className="bg-slate-900 text-white">
        <div className="max-w-6xl mx-auto px-6 py-14">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[
              {
                title: 'Job orchestration',
                body: 'Reliable state transitions, retries with backoff, cancellations, and audit history.',
              },
              {
                title: 'Live observability',
                body: 'Stream logs and metrics without stitching together ad-hoc tools.',
              },
              {
                title: 'Role-based access',
                body: 'Operator, viewer, and admin roles keep teams secure and compliant.',
              },
              {
                title: 'Tenant-safe control',
                body: 'Multi-tenant by design so teams can run multiple models safely.',
              },
            ].map((item) => (
              <div key={item.title} className="rounded-2xl border border-white/10 bg-white/5 p-5">
                <h3 className="text-lg font-semibold">{item.title}</h3>
                <p className="mt-2 text-sm text-slate-300">{item.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-[#f7f3ea]">
        <div className="max-w-6xl mx-auto px-6 py-16">
          <div className="grid grid-cols-1 lg:grid-cols-[0.9fr_1.1fr] gap-10 items-start">
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-slate-500">
                How it works
              </p>
              <h2 className="mt-4 text-3xl font-semibold">
                A control plane that respects your boundary.
              </h2>
              <p className="mt-4 text-slate-700">
                Install the AiTrainOps agent once. Every training job stays in your
                cluster, while the control plane keeps the metadata, logs, and history
                you need to operate reliably.
              </p>
              <div className="mt-6 space-y-3 text-sm text-slate-700">
                <div className="flex gap-3">
                  <span className="mt-1 h-2 w-2 rounded-full bg-emerald-500" />
                  Submit training jobs with a single API call
                </div>
                <div className="flex gap-3">
                  <span className="mt-1 h-2 w-2 rounded-full bg-emerald-500" />
                  Stream events and logs back to your team
                </div>
                <div className="flex gap-3">
                  <span className="mt-1 h-2 w-2 rounded-full bg-emerald-500" />
                  Apply role-based access for operators and viewers
                </div>
                <div className="flex gap-3">
                  <span className="mt-1 h-2 w-2 rounded-full bg-emerald-500" />
                  Retry failed jobs with backoff for reliability
                </div>
                <div className="flex gap-3">
                  <span className="mt-1 h-2 w-2 rounded-full bg-emerald-500" />
                  Keep a complete audit trail for compliance
                </div>
              </div>
            </div>
            <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-xl">
              <div className="text-xs uppercase tracking-[0.3em] text-slate-500">
                Install in minutes
              </div>
              <pre className="mt-4 rounded-2xl bg-slate-950 text-emerald-200 text-sm p-5 overflow-auto">
{`helm repo add aitrainops https://charts.aitrainops.com
helm install aitrainops-agent \\
  --set orgId=org_123 \\
  --set apiKey=token_abc`}
              </pre>
              <div className="mt-4 text-xs text-slate-500">
                Works with EKS, GKE, AKS, or on-prem Kubernetes.
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="bg-white">
        <div className="max-w-6xl mx-auto px-6 py-16">
          <div className="grid grid-cols-1 lg:grid-cols-[1.1fr_0.9fr] gap-10 items-center">
            <div className="rounded-3xl border border-slate-200 bg-slate-50 p-8">
              <h3 className="text-2xl font-semibold">Built for private ML teams</h3>
              <p className="mt-3 text-slate-600">
                Teams in biotech, finance, healthcare, and enterprise SaaS choose
                AiTrainOps because it works with their security posture from day one.
              </p>
              <div className="mt-6 grid grid-cols-2 gap-3 text-sm text-slate-700">
                <span className="rounded-full border border-slate-200 bg-white px-3 py-1">
                  No data egress
                </span>
                <span className="rounded-full border border-slate-200 bg-white px-3 py-1">
                  Audit-ready logs
                </span>
                <span className="rounded-full border border-slate-200 bg-white px-3 py-1">
                  GPU-aware jobs
                </span>
                <span className="rounded-full border border-slate-200 bg-white px-3 py-1">
                  Multi-tenant
                </span>
              </div>
            </div>
            <div>
              <h2 className="text-3xl font-semibold">Ready to see it in your cluster?</h2>
              <p className="mt-4 text-slate-700">
                We’ll help you install the agent, connect your cluster, and get the
                first training job running in under an hour.
              </p>
              <div className="mt-6 flex flex-wrap gap-3">
                <Link
                  to="/register"
                  className="px-5 py-2 rounded-full bg-slate-900 text-white hover:bg-slate-800"
                >
                  Request a demo
                </Link>
                <Link
                  to="/login"
                  className="px-5 py-2 rounded-full border border-slate-300 text-slate-700 hover:border-slate-500"
                >
                  Sign in
                </Link>
              </div>
            </div>
          </div>
          <div className="mt-10 border-t border-slate-200 pt-6 text-xs text-slate-500">
            © 2026 AiTrainOps. Private training orchestration for Kubernetes teams.
          </div>
        </div>
      </section>
    </div>
  );
};

export default Landing;
