import React from 'react';
import { OrganizationProfile } from '@clerk/clerk-react';
import { useAppAuth } from '../context/AppAuthContext';
import { hasMinRole } from '../utils/roles';

const AdminUsers = () => {
  const { role, loading } = useAppAuth();
  if (loading) return null;

  if (!hasMinRole(role, 'admin')) {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-slate-900">Admin only</h2>
        <p className="mt-2 text-sm text-slate-600">
          You don’t have permission to manage users for this organization.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-slate-100">Users & roles</h1>
        <p className="mt-2 text-sm text-slate-300">
          Invite team members and manage organization roles.
        </p>
      </div>
      <div className="bg-white rounded-2xl border border-slate-200 p-2">
        <OrganizationProfile
          routing="path"
          path="/admin/users"
          appearance={{
            variables: {
              colorPrimary: '#0f172a',
              colorText: '#0f172a',
              colorTextSecondary: '#475569',
              colorBackground: '#ffffff',
              colorInputBackground: '#ffffff',
              colorInputText: '#0f172a',
              colorShadows: 'rgba(15, 23, 42, 0.08)',
              borderRadius: '12px',
              fontFamily: 'Space Grotesk, system-ui, sans-serif',
            },
            elements: {
              rootBox: 'bg-transparent',
              card: 'shadow-none border border-slate-200 rounded-xl',
              navbar: 'bg-slate-50 border-b border-slate-200',
              headerTitle: 'text-slate-900',
              headerSubtitle: 'text-slate-500',
              formButtonPrimary: 'bg-slate-900 hover:bg-slate-800 text-white',
              formButtonReset: 'text-slate-700 hover:text-slate-900',
              formFieldLabel: 'text-slate-700',
              formFieldInput: 'border-slate-300 focus:border-slate-400',
              badge: 'bg-slate-100 text-slate-700',
              memberListItem: 'border border-slate-200 rounded-lg',
              profileSectionTitle: 'text-slate-900',
              profileSectionContent: 'text-slate-600',
              footer: 'hidden',
              footerAction: 'hidden',
              footerActionText: 'hidden',
              footerActionLink: 'hidden',
            },
          }}
        />
      </div>
    </div>
  );
};

export default AdminUsers;
