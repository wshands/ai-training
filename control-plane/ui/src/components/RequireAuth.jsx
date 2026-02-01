import React from 'react';
import AuthGate from './AuthGate';

const RequireAuth = ({ children }) => (
  <AuthGate>{children}</AuthGate>
);

export default RequireAuth;
