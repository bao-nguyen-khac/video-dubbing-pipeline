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
  dynamic_captions: boolean;
  subtitles_burned: boolean;
  tts_provider: string;
  voice_id: string | null;
  // 005-natural-pause-dubbing: số nhịp bị thay bằng khoảng lặng do lỗi TTS cục bộ
  tts_failed_segments: number;
  error: string | null;
  warnings: {
    watermark?: boolean;
    duration_mismatch?: boolean;
    background_music_lost?: boolean;
    tts_segments_failed?: boolean;
  };
  output_video_url: string | null;
  // Video gốc đã tải về — để xem song song với kết quả và so sánh (null nếu
  // file gốc không còn/job tạo trước khi có field này)
  source_video_url: string | null;
  can_retry: boolean;
}

export interface Voice {
  provider: "edge-tts" | "lucyai" | "omnivoice";
  voice_id: string;
  name: string;
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

export function submitJob(
  url: string,
  scriptMode: "translate" | "rewrite" | "subtitle",
  dynamicCaptions: boolean = false,
  ttsProvider?: string,
  voiceId?: string,
) {
  return request<{ job_id: string }>("/api/jobs", {
    method: "POST",
    body: JSON.stringify({
      url,
      script_mode: scriptMode,
      dynamic_captions: dynamicCaptions,
      ...(ttsProvider ? { tts_provider: ttsProvider } : {}),
      ...(voiceId ? { voice_id: voiceId } : {}),
    }),
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

export function sourceUrl(jobId: string) {
  return `/api/jobs/${jobId}/source`;
}

export function listVoices() {
  return request<{ voices: Voice[] }>("/api/voices");
}

// ── Đăng video (006-publish-video-tab) ──────────────────────────────────────

export interface PublishableVideo {
  job_id: string;
  source_url: string;
  created_at: string;
  duration_seconds: number;
  already_published_to: string[];
}

export interface ChannelConnection {
  account_id: string;
  platform: string;
  label: string;
  status: "connected" | "expired" | "disconnected";
}

export type PublishMode = "now" | "scheduled";

export interface PublishAttempt {
  attempt_id: string;
  job_id: string;
  platform: string;
  account_label: string;
  title: string;
  status: "pending" | "publishing" | "scheduled" | "success" | "failed" | "cancelled";
  publish_mode: PublishMode;
  // Chuỗi ISO 8601 UTC, null khi publish_mode="now" (007-schedule-publish)
  scheduled_for: string | null;
  error: string | null;
  error_kind: string | null;
  post_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface CancelledAttemptSummary {
  attempt_id: string;
  title: string;
  scheduled_for: string;
}

export function listPublishableVideos() {
  return request<{ videos: PublishableVideo[] }>("/api/publish/videos");
}

export function listConnections() {
  return request<{ connections: ChannelConnection[] }>("/api/publish/connections");
}

export function startConnect(platform: string, redirectUrl?: string) {
  return request<{ authorize_url: string }>(`/api/publish/connections/${platform}`, {
    method: "POST",
    body: JSON.stringify({ redirect_url: redirectUrl ?? null }),
  });
}

export function disconnectChannel(accountId: string) {
  return request<{
    ok: boolean;
    warning?: string;
    // 007-schedule-publish: bài đang chờ đăng của kênh này bị huỷ theo (FR-015)
    cancelled_attempts?: CancelledAttemptSummary[];
  }>(`/api/publish/connections/${accountId}`, {
    method: "DELETE",
  });
}

export function createPublish(
  jobId: string,
  platform: string,
  accountId: string,
  title: string,
  publishMode: PublishMode = "now",
  scheduledFor?: string,
) {
  return request<{ attempt_id: string; status: string }>("/api/publish", {
    method: "POST",
    body: JSON.stringify({
      job_id: jobId,
      platform,
      account_id: accountId,
      title,
      publish_mode: publishMode,
      ...(scheduledFor ? { scheduled_for: scheduledFor } : {}),
    }),
  });
}

export function listAttempts(jobId?: string, status?: string) {
  const params = new URLSearchParams();
  if (jobId) params.set("job_id", jobId);
  if (status) params.set("status", status);
  const query = params.toString() ? `?${params.toString()}` : "";
  return request<{ attempts: PublishAttempt[] }>(`/api/publish/attempts${query}`);
}

export function getAttempt(attemptId: string) {
  return request<PublishAttempt>(`/api/publish/attempts/${attemptId}`);
}

export function cancelAttempt(attemptId: string) {
  return request<{ ok: boolean }>(`/api/publish/attempts/${attemptId}`, {
    method: "DELETE",
  });
}

export async function previewVoice(provider: string, voiceId: string): Promise<Blob> {
  const res = await fetch("/api/voices/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ provider, voice_id: voiceId }),
  });

  if (res.status === 401) {
    if (window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
    throw new ApiError(401, null);
  }

  if (!res.ok) {
    const body = await safeJson(res);
    throw new ApiError(res.status, body);
  }

  return res.blob();
}
