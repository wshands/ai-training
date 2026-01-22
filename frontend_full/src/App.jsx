import React, { useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { ClerkProvider, useAuth } from '@clerk/clerk-react';
import Navbar from './components/Navbar';
import RequireAuth from './components/RequireAuth';
import Dashboard from './pages/Dashboard';
import NewJobWizard from './pages/NewJobWizard';
import JobDetail from './pages/JobDetail';
import Login from './pages/Login';
import Register from './pages/Register';
import OrgSelect from './pages/OrgSelect';
import { setTokenGetter } from './auth';

const AuthTokenBridge = () => {
  const { getToken } = useAuth();
  useEffect(() => {
    setTokenGetter(() => getToken());
  }, [getToken]);
  return null;
};

const SignedInRedirect = () => {
  const { isLoaded, sessionId } = useAuth();
  if (!isLoaded) return null;
  if (!sessionId) return null;
  return (
    <div className="max-w-md mx-auto text-sm text-slate-300">
      You are already signed in. Redirecting…
      <Navigate to="/" replace />
    </div>
  );
};

const SignedOutOnly = ({ children }) => {
  const { isLoaded, isSignedIn, sessionId } = useAuth();
  if (!isLoaded) return null;
  if (!isSignedIn && sessionId) {
    return <Navigate to="/" replace />;
  }
  if (isSignedIn) {
    return <SignedInRedirect />;
  }
  return children;
};

const AppRoutes = () => (
  <div className="min-h-screen flex flex-col">
    <Navbar />
    <main className="flex-1">
      <div className="max-w-6xl mx-auto px-4 py-6">
        <Routes>
          <Route
            path="/login/*"
            element={
              <SignedOutOnly>
                <Login />
              </SignedOutOnly>
            }
          />
          <Route
            path="/register/*"
            element={
              <SignedOutOnly>
                <Register />
              </SignedOutOnly>
            }
          />
          <Route
            path="/select-org"
            element={
              <RequireAuth requireOrg={false}>
                <OrgSelect />
              </RequireAuth>
            }
          />
          <Route
            path="/"
            element={
              <RequireAuth>
                <Dashboard />
              </RequireAuth>
            }
          />
          <Route
            path="/jobs/new"
            element={
              <RequireAuth>
                <NewJobWizard />
              </RequireAuth>
            }
          />
          <Route
            path="/jobs/:jobId"
            element={
              <RequireAuth>
                <JobDetail />
              </RequireAuth>
            }
          />
        </Routes>
      </div>
    </main>
  </div>
);

const App = () => {
  const publishableKey = process.env.REACT_APP_CLERK_PUBLISHABLE_KEY;
  if (!publishableKey) {
    return (
      <div className="min-h-screen flex items-center justify-center text-sm text-rose-300">
        Missing `REACT_APP_CLERK_PUBLISHABLE_KEY`
      </div>
    );
  }

  return (
    <ClerkProvider publishableKey={publishableKey}>
      <AuthTokenBridge />
      <AppRoutes />
    </ClerkProvider>
  );
};

export default App;
