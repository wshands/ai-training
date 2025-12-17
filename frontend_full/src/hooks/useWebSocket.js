import { useEffect, useRef, useState } from 'react';

export const useWebSocket = (url, onMessage, options = {}) => {
  const { reconnectInterval = 2000, maxReconnectAttempts = 8 } = options;
  const [status, setStatus] = useState('disconnected');
  const wsRef = useRef(null);
  const retryCountRef = useRef(0);

  useEffect(() => {
    if (!url) return;
    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      setStatus('connecting');
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (cancelled) return;
        retryCountRef.current = 0;
        setStatus('connected');
      };

      ws.onmessage = (event) => {
        if (!onMessage) return;
        try {
          const data = JSON.parse(event.data);
          onMessage(data);
        } catch (e) {
          console.warn('WS message parse error', e);
        }
      };

      ws.onerror = () => {
        if (cancelled) return;
        setStatus('error');
      };

      ws.onclose = () => {
        if (cancelled) return;
        setStatus('disconnected');
        if (retryCountRef.current < maxReconnectAttempts) {
          retryCountRef.current += 1;
          const delay = reconnectInterval * retryCountRef.current;
          setTimeout(connect, delay);
        }
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.close();
      }
    };
  }, [url, onMessage, reconnectInterval, maxReconnectAttempts]);

  return { status, ws: wsRef.current };
};
