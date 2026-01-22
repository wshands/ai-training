import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@clerk/clerk-react';

const RequireAuth = ({ children, requireOrg = false }) => {
  const location = useLocation();
  const { isLoaded, isSignedIn, orgId, sessionId } = useAuth();
  if (!isLoaded) return null;
  if (!isSignedIn && !sessionId) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  if (requireOrg && isSignedIn && !orgId) {
    return <Navigate to="/select-org" replace state={{ from: location.pathname }} />;
  }
  return children;
};

export default RequireAuth;
