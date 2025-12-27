import { useEffect, useRef, useState } from 'react';

export const useWebSocket = (url, onMessage, options = {}) => {
  const { reconnectInterval = 2000, maxReconnectAttempts = 8 } = options;
  const [status, setStatus] = useState('disconnected');
  const wsRef = useRef(null);
  const retryCountRef = useRef(0);

  // ❗ Problem: onMessage is a dependency of useEffect below.
  // That inline (msg) => { ... } is a brand-new function on every render, so onMessage in the dependency array is always “changed”. React then:
  // Runs the cleanup → closes existing WebSocket.
  // Runs the effect again → opens a new WebSocket.
  // This causes an infinite loop of disconnects/reconnects.
  //
  // Solution: use a ref to hold the latest onMessage handler, and refer to that ref inside the effect. 
  // This way, the effect does not depend on onMessage, and won't re-run when onMessage changes.
  const onMessageRef = useRef(onMessage);           // ⭐ NEW

  // Keep latest onMessage in a ref
  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);                                  // ⭐ NEW

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
        const handler = onMessageRef.current;       // ⭐ use ref
        if (!handler) return;
        try {
          const data = JSON.parse(event.data);
          handler(data);
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
  }, [url, reconnectInterval, maxReconnectAttempts]);  // ❗ removed onMessage

  return { status, ws: wsRef.current };
};

