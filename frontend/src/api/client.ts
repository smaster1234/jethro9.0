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

const getApiBaseUrl = (): string => {
  const url = normalizeBaseUrl(getRuntimeApiUrl() || import.meta.env.VITE_API_URL || '');
  // Warn if API_URL points to the frontend itself (common misconfiguration)
  if (url && typeof window !== 'undefined' && url === window.location.origin) {
    console.warn(
      `[Jethro] API_URL (${url}) points to the frontend origin. ` +
      'API calls will fail. Set API_URL to the backend service URL, or leave it empty for same-origin deployment.'
    );
  }
  return url;
};

// Create axios instance
// Note: Do NOT set a global Content-Type header here.
// Setting 'Content-Type': 'application/json' globally breaks FormData uploads
// because it overrides the automatic multipart/form-data boundary that axios
// sets when the request body is a FormData object.
// Axios automatically sets Content-Type to application/json for object payloads.
export const apiClient: AxiosInstance = axios.create({
  baseURL: getApiBaseUrl(),
});

// Token management
let accessToken: string | null = localStorage.getItem('access_token');
let refreshToken: string | null = localStorage.getItem('refresh_token');
let tokenExpiresAt: number | null = null; // Unix timestamp in milliseconds
let isRefreshing = false;
let refreshSubscribers: ((token: string) => void)[] = [];
let proactiveRefreshTimer: ReturnType<typeof setTimeout> | null = null;

// Parse JWT to get expiration time
const parseJwtExpiration = (token: string): number | null => {
  try {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split('')
        .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    );
    const payload = JSON.parse(jsonPayload);
    return payload.exp ? payload.exp * 1000 : null; // Convert to milliseconds
  } catch {
    return null;
  }
};

// Check if token is expired or about to expire (within 5 minutes)
const isTokenExpiringSoon = (): boolean => {
  if (!tokenExpiresAt) return true;
  const fiveMinutes = 5 * 60 * 1000;
  return Date.now() > tokenExpiresAt - fiveMinutes;
};

// Check if token is completely expired
const isTokenExpired = (): boolean => {
  if (!tokenExpiresAt) return true;
  return Date.now() > tokenExpiresAt;
};

export const setTokens = (tokens: TokenResponse) => {
  accessToken = tokens.access_token;
  refreshToken = tokens.refresh_token;
  tokenExpiresAt = parseJwtExpiration(tokens.access_token);
  
  localStorage.setItem('access_token', tokens.access_token);
  localStorage.setItem('refresh_token', tokens.refresh_token);
  if (tokenExpiresAt) {
    localStorage.setItem('token_expires_at', tokenExpiresAt.toString());
  }
  
  // Schedule proactive refresh
  scheduleProactiveRefresh();
};

export const clearTokens = () => {
  accessToken = null;
  refreshToken = null;
  tokenExpiresAt = null;
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('token_expires_at');
  
  // Clear proactive refresh timer
  if (proactiveRefreshTimer) {
    clearTimeout(proactiveRefreshTimer);
    proactiveRefreshTimer = null;
  }
};

export const getAccessToken = () => accessToken;
export const getRefreshToken = () => refreshToken;

// Initialize token expiration from localStorage
const initTokenExpiration = () => {
  const storedExpiration = localStorage.getItem('token_expires_at');
  if (storedExpiration) {
    tokenExpiresAt = parseInt(storedExpiration, 10);
  } else if (accessToken) {
    tokenExpiresAt = parseJwtExpiration(accessToken);
    if (tokenExpiresAt) {
      localStorage.setItem('token_expires_at', tokenExpiresAt.toString());
    }
  }
};

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
    console.log('[Jethro] Refreshing access token...');
    const response = await axios.post<TokenResponse>(
      `${getApiBaseUrl()}/auth/refresh`,
      { refresh_token: refreshToken },
      { headers: { 'Content-Type': 'application/json' } }
    );

    const tokens = response.data;
    setTokens(tokens);
    console.log('[Jethro] Token refreshed successfully');
    return tokens.access_token;
  } catch (error) {
    console.error('[Jethro] Token refresh failed:', error);
    clearTokens();
    return null;
  }
};

// Schedule proactive token refresh (5 minutes before expiration)
const scheduleProactiveRefresh = () => {
  // Clear existing timer
  if (proactiveRefreshTimer) {
    clearTimeout(proactiveRefreshTimer);
    proactiveRefreshTimer = null;
  }
  
  if (!tokenExpiresAt || !refreshToken) return;
  
  const fiveMinutes = 5 * 60 * 1000;
  const refreshTime = tokenExpiresAt - fiveMinutes - Date.now();
  
  if (refreshTime > 0) {
    console.log(`[Jethro] Scheduling token refresh in ${Math.round(refreshTime / 1000 / 60)} minutes`);
    proactiveRefreshTimer = setTimeout(async () => {
      if (!isRefreshing && refreshToken) {
        isRefreshing = true;
        try {
          await refreshAccessToken();
        } finally {
          isRefreshing = false;
        }
      }
    }, refreshTime);
  } else if (!isTokenExpired()) {
    // Token is expiring soon but not expired - refresh immediately
    console.log('[Jethro] Token expiring soon, refreshing now...');
    if (!isRefreshing && refreshToken) {
      isRefreshing = true;
      refreshAccessToken().finally(() => {
        isRefreshing = false;
      });
    }
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

// Ensure token is valid before making a request
const ensureValidToken = async (): Promise<string | null> => {
  if (!accessToken) return null;
  
  // If token is expired, try to refresh
  if (isTokenExpired()) {
    console.log('[Jethro] Token expired, attempting refresh...');
    if (isRefreshing) {
      // Wait for ongoing refresh
      return new Promise((resolve) => {
        subscribeTokenRefresh((token) => resolve(token));
      });
    }
    isRefreshing = true;
    try {
      const newToken = await refreshAccessToken();
      return newToken;
    } finally {
      isRefreshing = false;
    }
  }
  
  // If token is expiring soon, schedule refresh but continue with current token
  if (isTokenExpiringSoon() && !isRefreshing) {
    console.log('[Jethro] Token expiring soon, scheduling refresh...');
    scheduleProactiveRefresh();
  }
  
  return accessToken;
};

// Request interceptor - add auth header and ensure valid token
apiClient.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    const runtimeBaseUrl = getApiBaseUrl();
    if (runtimeBaseUrl) {
      config.baseURL = runtimeBaseUrl;
    }
    
    // Ensure we have a valid token
    const token = await ensureValidToken();
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
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
      console.log('[Jethro] Received 401, attempting token refresh...');
      
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
          console.log('[Jethro] Token refresh failed, redirecting to login...');
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

// Initialize on load
initTokenExpiration();
scheduleProactiveRefresh();

// Also refresh when tab becomes visible (user returns to tab)
if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && accessToken) {
      console.log('[Jethro] Tab visible, checking token...');
      if (isTokenExpired()) {
        console.log('[Jethro] Token expired while tab was hidden, refreshing...');
        if (!isRefreshing && refreshToken) {
          isRefreshing = true;
          refreshAccessToken().finally(() => {
            isRefreshing = false;
          });
        }
      } else if (isTokenExpiringSoon()) {
        scheduleProactiveRefresh();
      }
    }
  });
}

export default apiClient;
