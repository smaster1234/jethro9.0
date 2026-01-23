import axios, { type AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from 'axios';
import type { TokenResponse, ApiError } from '../types';

type RuntimeEnv = {
  API_URL?: string;
};

const getRuntimeApiUrl = (): string => {
  if (typeof window === 'undefined') {
    return '';
  }

  const runtimeEnv = (window as Window & { __JETHRO_ENV__?: RuntimeEnv }).__JETHRO_ENV__;
  return runtimeEnv?.API_URL ?? '';
};

const normalizeBaseUrl = (value: string): string => value.replace(/\/+$/, '');

const getApiBaseUrl = (): string =>
  normalizeBaseUrl(getRuntimeApiUrl() || import.meta.env.VITE_API_URL || '');

// Create axios instance
export const apiClient: AxiosInstance = axios.create({
  baseURL: getApiBaseUrl(),
  headers: {
    'Content-Type': 'application/json',
  },
});

// Token management
let accessToken: string | null = localStorage.getItem('access_token');
let refreshToken: string | null = localStorage.getItem('refresh_token');

export const setTokens = (tokens: TokenResponse) => {
  accessToken = tokens.access_token;
  refreshToken = tokens.refresh_token;
  localStorage.setItem('access_token', tokens.access_token);
  localStorage.setItem('refresh_token', tokens.refresh_token);
};

export const clearTokens = () => {
  accessToken = null;
  refreshToken = null;
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
};

export const getAccessToken = () => accessToken;

// Request interceptor - add auth header
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const runtimeBaseUrl = getApiBaseUrl();
    if (runtimeBaseUrl) {
      config.baseURL = runtimeBaseUrl;
    }
    if (accessToken && config.headers) {
      config.headers.Authorization = `Bearer ${accessToken}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor - handle errors
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiError>) => {
    const originalRequest = error.config;

    // If 401 and we have a refresh token, try to refresh
    if (error.response?.status === 401 && refreshToken && originalRequest) {
      try {
        // Try to refresh token (implement if backend supports it)
        // For now, just clear tokens and redirect to login
        clearTokens();
        window.location.href = '/login';
      } catch {
        clearTokens();
        window.location.href = '/login';
      }
    }

    return Promise.reject(error);
  }
);

// Helper to handle API errors
export const handleApiError = (error: unknown): string => {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<ApiError>;
    if (axiosError.response?.data?.detail) {
      return axiosError.response.data.detail;
    }
    if (axiosError.message) {
      return axiosError.message;
    }
  }
  return 'An unexpected error occurred';
};

export default apiClient;
