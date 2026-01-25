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

const stripEnvPrefix = (value: string): string => {
  const trimmed = value.trim();
  if (trimmed.startsWith('API_URL=')) {
    return trimmed.slice('API_URL='.length);
  }
  if (trimmed.startsWith('VITE_API_URL=')) {
    return trimmed.slice('VITE_API_URL='.length);
  }
  return trimmed;
};

const normalizeBaseUrl = (value: string): string => stripEnvPrefix(value).replace(/\/+$/, '');

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
let isRefreshing = false;
let refreshSubscribers: ((token: string) => void)[] = [];

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
export const getRefreshToken = () => refreshToken;

// Subscribe to token refresh
const subscribeTokenRefresh = (callback: (token: string) => void) => {
  refreshSubscribers.push(callback);
};

// Notify all subscribers with new token
const onTokenRefreshed = (newToken: string) => {
  refreshSubscribers.forEach((callback) => callback(newToken));
  refreshSubscribers = [];
};

// Refresh the access token
const refreshAccessToken = async (): Promise<string | null> => {
  if (!refreshToken) return null;

  try {
    const response = await axios.post<TokenResponse>(
      `${getApiBaseUrl()}/auth/refresh`,
      { refresh_token: refreshToken },
      { headers: { 'Content-Type': 'application/json' } }
    );

    const tokens = response.data;
    setTokens(tokens);
    return tokens.access_token;
  } catch (error) {
    clearTokens();
    return null;
  }
};

// Logout and revoke token on server
export const logout = async (): Promise<void> => {
  if (accessToken) {
    try {
      await axios.post(
        `${getApiBaseUrl()}/auth/logout`,
        {},
        { headers: { Authorization: `Bearer ${accessToken}` } }
      );
    } catch {
      // Ignore errors during logout
    }
  }
  clearTokens();
};

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

// Response interceptor - handle errors and token refresh
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiError>) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    // If 401 and we have a refresh token, try to refresh
    if (error.response?.status === 401 && refreshToken && originalRequest && !originalRequest._retry) {
      if (isRefreshing) {
        // Wait for the refresh to complete
        return new Promise((resolve) => {
          subscribeTokenRefresh((newToken: string) => {
            originalRequest.headers.Authorization = `Bearer ${newToken}`;
            resolve(apiClient(originalRequest));
          });
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        const newToken = await refreshAccessToken();
        if (newToken) {
          isRefreshing = false;
          onTokenRefreshed(newToken);
          originalRequest.headers.Authorization = `Bearer ${newToken}`;
          return apiClient(originalRequest);
        } else {
          isRefreshing = false;
          window.location.href = '/login';
          return Promise.reject(error);
        }
      } catch {
        isRefreshing = false;
        clearTokens();
        window.location.href = '/login';
        return Promise.reject(error);
      }
    }

    return Promise.reject(error);
  }
);

// Helper to handle API errors
export const handleApiError = (error: unknown): string => {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<ApiError>;
    const apiError = axiosError.response?.data;
    if (apiError?.error?.message) {
      return apiError.error.message;
    }
    if (apiError?.detail) {
      return apiError.detail;
    }
    if (apiError?.message) {
      return apiError.message;
    }
    if (axiosError.message) {
      return axiosError.message;
    }
  }
  return 'An unexpected error occurred';
};

export default apiClient;
