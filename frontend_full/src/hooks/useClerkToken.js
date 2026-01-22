import { useEffect, useState } from 'react';
import { useAuth } from '@clerk/clerk-react';

export const useClerkToken = () => {
  const { getToken, isSignedIn } = useAuth();
  const [token, setToken] = useState(null);

  useEffect(() => {
    let cancelled = false;
    if (!isSignedIn) {
      setToken(null);
      return () => {
        cancelled = true;
      };
    }

    const loadToken = async () => {
      const next = await getToken();
      if (!cancelled) setToken(next);
    };

    loadToken();
    return () => {
      cancelled = true;
    };
  }, [getToken, isSignedIn]);

  return token;
};
