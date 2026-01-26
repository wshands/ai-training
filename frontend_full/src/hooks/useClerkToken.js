import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '@clerk/clerk-react';

export const useClerkToken = () => {
  const { getToken, isSignedIn } = useAuth();
  const [token, setToken] = useState(null);

  const getFreshToken = useCallback(async () => {
    if (!isSignedIn) return null;
    return await getToken();
  }, [getToken, isSignedIn]);

  useEffect(() => {
    let cancelled = false;
    if (!isSignedIn) {
      setToken(null);
      return () => {
        cancelled = true;
      };
    }

    const loadToken = async () => {
      const next = await getFreshToken();
      if (!cancelled) setToken(next);
    };

    loadToken();
    return () => {
      cancelled = true;
    };
  }, [getFreshToken, isSignedIn]);

  return { token, getFreshToken, isSignedIn };
};
