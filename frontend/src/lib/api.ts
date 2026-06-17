import Cookies from 'js-cookie';

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

let isRefreshing = false;
let refreshSubscribers: ((token: string) => void)[] = [];

function onRefreshed(token: string) {
  refreshSubscribers.forEach((cb) => cb(token));
  refreshSubscribers = [];
}

function addRefreshSubscriber(cb: (token: string) => void) {
  refreshSubscribers.push(cb);
}

export async function fetchAPI(endpoint: string, options: RequestInit = {}) {
  const url = `${API_URL}${endpoint}`;
  let token = Cookies.get("access_token");

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> || {}),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  let response = await fetch(url, { ...options, headers });

  // Handle 401 Unauthorized by attempting a silent token refresh
  if (response.status === 401) {
    const refreshToken = Cookies.get("refresh_token");
    if (refreshToken) {
      if (!isRefreshing) {
        isRefreshing = true;
        try {
          const refreshRes = await fetch(`${API_URL}/api/auth/refresh`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({ refresh_token: refreshToken })
          });

          if (refreshRes.ok) {
            const data = await refreshRes.json();
            if (data && data.access_token) {
              Cookies.set("access_token", data.access_token, { path: '/', expires: 1 });
              if (data.refresh_token) {
                Cookies.set("refresh_token", data.refresh_token, { path: '/', expires: 30 });
              }
              token = data.access_token;
              onRefreshed(data.access_token);
            } else {
              throw new Error("Missing access token in refresh response");
            }
          } else {
            // Refresh failed, clear tokens and redirect to login
            Cookies.remove("access_token", { path: '/' });
            Cookies.remove("refresh_token", { path: '/' });
            if (typeof window !== "undefined") {
              window.location.href = "/login";
            }
          }
        } catch (e) {
          Cookies.remove("access_token", { path: '/' });
          Cookies.remove("refresh_token", { path: '/' });
          if (typeof window !== "undefined") {
            window.location.href = "/login";
          }
        } finally {
          isRefreshing = false;
        }
      }

      // Wait for the refresh to complete before retrying the original request
      return new Promise<any>((resolve, reject) => {
        addRefreshSubscriber(async (newToken: string) => {
          try {
            headers["Authorization"] = `Bearer ${newToken}`;
            const retryResponse = await fetch(url, { ...options, headers });
            if (!retryResponse.ok) {
              let errorDetail = "API request failed";
              try {
                const err = await retryResponse.json();
                errorDetail = err.detail || errorDetail;
              } catch { /* ignore */ }
              reject(new Error(errorDetail));
            } else {
              const retryContentType = retryResponse.headers.get("content-type") || "";
              if (retryContentType.includes("text/plain")) {
                resolve(retryResponse.text());
              } else {
                resolve(retryResponse.json());
              }
            }
          } catch (err) {
            reject(err);
          }
        });
      });
    } else {
      // No refresh token available, redirect to login
      Cookies.remove("access_token", { path: '/' });
      if (typeof window !== "undefined") {
        window.location.href = "/login";
      }
    }
  }

  if (!response.ok) {
    let errorDetail = "API request failed";
    try {
      const err = await response.json();
      errorDetail = err.detail || errorDetail;
    } catch {
      // ignore
    }
    throw new Error(errorDetail);
  }
  
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("text/plain")) {
    return response.text();
  }
  return response.json();
}
