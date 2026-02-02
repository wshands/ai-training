import React from 'react';
import { useAuth, useUser } from '@clerk/clerk-react';

const AuthDebug = () => {
  const { isLoaded, isSignedIn, sessionId, orgId } = useAuth();
  const { user } = useUser();
  if (process.env.NODE_ENV === 'production') return null;

  return (
    <div className="mt-6 text-xs text-slate-400 border border-slate-800 rounded p-3">
      <div>Auth debug (dev only)</div>
      <div>loaded: {String(isLoaded)}</div>
      <div>signed in: {String(isSignedIn)}</div>
      <div>session id: {sessionId || 'none'}</div>
      <div>org id: {orgId || 'none'}</div>
      <div>user id: {user?.id || 'none'}</div>
      <div>email: {user?.primaryEmailAddress?.emailAddress || 'none'}</div>
    </div>
  );
};

export default AuthDebug;
