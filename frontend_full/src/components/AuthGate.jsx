import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '@clerk/clerk-react';

const AuthGate = ({ children, redirectTo = '/login' }) => {
  const { isLoaded, isSignedIn } = useAuth();
  if (!isLoaded) return null;
  if (!isSignedIn) return <Navigate to={redirectTo} replace />;
  return children;
};

export default AuthGate;
