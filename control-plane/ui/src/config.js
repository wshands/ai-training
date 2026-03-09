const DEFAULT_PROD_API_BASE_URL = 'https://api.aitrainops.com';
const isBrowser = typeof window !== 'undefined';
const host = isBrowser ? window.location.hostname : '';
const isProdAppHost = host === 'app.aitrainops.com';

export const API_BASE_URL =
  process.env.REACT_APP_API_BASE_URL ||
  (isProdAppHost ? DEFAULT_PROD_API_BASE_URL : 'http://localhost:8000');

export const WS_BASE_URL =
  process.env.REACT_APP_WS_BASE_URL || API_BASE_URL.replace('http', 'ws');
