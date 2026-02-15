import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useAuth } from '@clerk/clerk-react';
import { api, handleApiError } from '../hooks/useApi';

const AppAuthContext = createContext({
  role: null,
  roleRaw: null,
  loading: false,
  error: null,
  refresh: async () => {},
});

export const AppAuthProvider = ({ children }) => {
  const { isSignedIn } = useAuth();
  const [state, setState] = useState({
    role: null,
    roleRaw: null,
    loading: false,
    error: null,
  });

  const refresh = useCallback(async () => {
    if (!isSignedIn) {
      setState({ role: null, roleRaw: null, loading: false, error: null });
      return;
    }
    setState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const res = await api.get('/auth/me');
      setState({
        role: res.data?.role || 'viewer',
        roleRaw: res.data?.role_raw || null,
        loading: false,
        error: null,
      });
    } catch (err) {
      setState((prev) => ({
        ...prev,
        loading: false,
        error: handleApiError(err),
      }));
    }
  }, [isSignedIn]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const value = useMemo(
    () => ({
      ...state,
      refresh,
    }),
    [state, refresh]
  );

  return <AppAuthContext.Provider value={value}>{children}</AppAuthContext.Provider>;
};

export const useAppAuth = () => useContext(AppAuthContext);
