import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@clerk/clerk-react';

const AuthGate = ({ children, redirectTo = '/login', requireOrg = true }) => {
  const { isLoaded, isSignedIn, orgId } = useAuth();
  const location = useLocation();
  if (!isLoaded) return null;
  if (!isSignedIn) return <Navigate to={redirectTo} replace />;
  if (requireOrg && !orgId && location.pathname !== '/select-org') {
    return <Navigate to="/select-org" replace />;
  }
  return children;
};

export default AuthGate;
