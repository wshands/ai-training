import React, { useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { ClerkProvider, useAuth } from '@clerk/clerk-react';
import Navbar from './components/Navbar';
import RequireAuth from './components/RequireAuth';
import AuthGate from './components/AuthGate';
import Dashboard from './pages/Dashboard';
import NewJobWizard from './pages/NewJobWizard';
import JobDetail from './pages/JobDetail';
import AdminTokens from './pages/AdminTokens';
import AdminUsers from './pages/AdminUsers';
import Login from './pages/Login';
import OrgSelect from './pages/OrgSelect';
import { setTokenGetter } from './auth';
import AuthDebug from './components/AuthDebug';
import { AppAuthProvider } from './context/AppAuthContext';
import { MARKETING_SITE_URL } from './config';

const AuthTokenBridge = () => {
  const { getToken } = useAuth();
  useEffect(() => {
    setTokenGetter(() => getToken());
  }, [getToken]);
  return null;
};

const SignedOutOnly = ({ children }) => {
  const { isLoaded, isSignedIn } = useAuth();
  if (!isLoaded) return null;
  if (isSignedIn) return <Navigate to="/app" replace />;
  return children;
};

const RootRoute = () => {
  const { isLoaded, isSignedIn } = useAuth();

  useEffect(() => {
    if (!isLoaded || isSignedIn) return;
    window.location.replace(MARKETING_SITE_URL);
  }, [isLoaded, isSignedIn]);

  if (!isLoaded) return null;
  if (isSignedIn) return <Navigate to="/app" replace />;
  return null;
};

const ExternalRedirect = ({ to }) => {
  useEffect(() => {
    window.location.replace(to);
  }, [to]);
  return null;
};

const AppShell = () => (
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
              <ExternalRedirect to={MARKETING_SITE_URL} />
            </SignedOutOnly>
          }
        />
        <Route
          path="/select-org"
          element={
            <AuthGate requireOrg={false}>
              <OrgSelect />
            </AuthGate>
          }
        />
        <Route
          path="/app"
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
        <Route
          path="/admin/tokens"
          element={
            <RequireAuth>
              <AdminTokens />
            </RequireAuth>
          }
        />
        <Route
          path="/admin/users/*"
          element={
            <RequireAuth>
              <AdminUsers />
            </RequireAuth>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <AuthDebug />
    </div>
  </main>
);

const AppRoutes = () => (
  <div className="min-h-screen flex flex-col">
    <Navbar />
    <Routes>
      <Route path="/" element={<RootRoute />} />
      <Route path="/*" element={<AppShell />} />
    </Routes>
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
      <AppAuthProvider>
        <AppRoutes />
      </AppAuthProvider>
    </ClerkProvider>
  );
};

export default App;
