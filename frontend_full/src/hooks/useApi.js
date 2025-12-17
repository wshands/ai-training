import axios from 'axios';
import { API_BASE_URL } from '../config';

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
});

export const handleApiError = (err) => {
  if (err.response) {
    console.error('API error:', err.response.status, err.response.data);
    return err.response.data?.detail || `API error ${err.response.status}`;
  }
  if (err.request) {
    console.error('Network error:', err.message);
    return 'Network error contacting API';
  }
  console.error('Unexpected error:', err);
  return 'Unexpected error';
};
