import axios, { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from 'axios';

/**
 * Reads the bc_csrf cookie value from document.cookie.
 * Used by the CSRF request interceptor for state-changing requests.
 *
 * @returns The CSRF token string or null if not found.
 */
function getCsrfToken(): string | null {
  const match = document.cookie.match(/(?:^|;\s*)bc_csrf=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : null;
}

/**
 * Singleton Axios instance for all API communication.
 * Configured with cookie-based auth, CSRF header injection on
 * state-changing methods, and automatic 401 refresh with retry.
 */
const apiClient: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '/api/v1',
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor: inject CSRF token on POST/PATCH/DELETE
apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const method = config.method?.toUpperCase();
  if (method === 'POST' || method === 'PATCH' || method === 'DELETE') {
    const csrfToken = getCsrfToken();
    if (csrfToken) {
      config.headers['X-CSRF-Token'] = csrfToken;
    }
  }
  return config;
});

// Reason: Deduplicates concurrent 401 refresh attempts so only one POST /auth/refresh fires
let refreshPromise: Promise<void> | null = null;

// Response interceptor: on 401, attempt silent refresh then retry
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      try {
        if (!refreshPromise) {
          // Reason: Use bare axios.post to avoid triggering this interceptor recursively
          refreshPromise = axios
            .post('/api/v1/auth/refresh', null, { withCredentials: true })
            .then(() => undefined)
            .finally(() => {
              refreshPromise = null;
            });
        }
        await refreshPromise;
        return apiClient(originalRequest);
      } catch {
        window.location.href =
          '/api/v1/auth/sso/login?return_to=' + encodeURIComponent(window.location.pathname);
      }
    }
    return Promise.reject(error);
  },
);

export { apiClient };
