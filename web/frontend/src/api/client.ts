// web/frontend/src/api/client.ts — fetch wrapper gọi web/backend (contracts/api.md).
// Xử lý 401 (điều hướng về /login) và để 409/400 ném ApiError cho page tự hiển thị.

export interface JobSummary {
  job_id: string;
  source_url: string;
  platform: string;
  status: string;
  progress_percent: number;
  created_at: string;
}

export interface JobDetail extends JobSummary {
  script_mode: string;
  error: string | null;
  warnings: {
    watermark?: boolean;
    duration_mismatch?: boolean;
    background_music_lost?: boolean;
  };
  output_video_url: string | null;
  can_retry: boolean;
}

export class ApiError extends Error {
  status: number;
  body: any;

  constructor(status: number, body: any) {
    super(body?.error || body?.detail || `Lỗi API (${status})`);
    this.status = status;
    this.body = body;
  }
}

async function safeJson(res: Response): Promise<any> {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    credentials: "include",
  });

  const body = await safeJson(res);

  if (res.status === 401) {
    if (window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
    throw new ApiError(401, body);
  }

  if (!res.ok) {
    throw new ApiError(res.status, body);
  }

  return body as T;
}

export function login(username: string, password: string) {
  return request<{ ok: boolean }>("/api/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function logout() {
  return request<{ ok: boolean }>("/api/logout", { method: "POST" });
}

export function submitJob(url: string, scriptMode: "translate" | "rewrite") {
  return request<{ job_id: string }>("/api/jobs", {
    method: "POST",
    body: JSON.stringify({ url, script_mode: scriptMode }),
  });
}

export function getJob(jobId: string) {
  return request<JobDetail>(`/api/jobs/${jobId}`);
}

export function listJobs() {
  return request<{ jobs: JobSummary[] }>("/api/jobs");
}

export function retryJob(jobId: string) {
  return request<{ job_id: string }>(`/api/jobs/${jobId}/retry`, { method: "POST" });
}

export function outputUrl(jobId: string) {
  return `/api/jobs/${jobId}/output`;
}
