export const API_BASE_URL =
  process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000';

export const WS_BASE_URL =
  process.env.REACT_APP_WS_BASE_URL || API_BASE_URL.replace('http', 'ws');
