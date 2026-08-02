// web/frontend/src/api/client.ts — fetch wrapper gọi web/backend (contracts/api.md).
// Xử lý 401 (điều hướng về /login) và để 409/400 ném ApiError cho page tự hiển thị.

export interface JobSummary {
  job_id: string;
  source_url: string;
  platform: string;
  status: string;
  progress_percent: number;
  created_at: string;
  pinned: boolean;
  pinned_at: string | null;
  // 008-supervised-pipeline: chốt đang chờ duyệt (null nếu job không chờ duyệt)
  review_gate: "transcript" | "script" | null;
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
  // 008-supervised-pipeline: job có bật chế độ quản lý pipeline; review_url chỉ
  // khác null khi job thật sự đang chờ duyệt
  supervised: boolean;
  review_url: string | null;
  // 009-hardsub-blur-reposition: job có bật làm mờ phụ đề gốc
  hardsub_blur_enabled: boolean;
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
  scriptMode: "translate" | "rewrite" | "subtitle" | "download",
  dynamicCaptions: boolean = false,
  ttsProvider?: string,
  voiceId?: string,
  keepOriginalRanges?: string,
  supervised: boolean = false,
  hardsubBlurEnabled: boolean = false,
  hardsubNoRanges?: string,
) {
  return request<{ job_id: string }>("/api/jobs", {
    method: "POST",
    body: JSON.stringify({
      url,
      script_mode: scriptMode,
      dynamic_captions: dynamicCaptions,
      supervised,
      hardsub_blur_enabled: hardsubBlurEnabled,
      ...(ttsProvider ? { tts_provider: ttsProvider } : {}),
      ...(voiceId ? { voice_id: voiceId } : {}),
      ...(keepOriginalRanges ? { keep_original_ranges: keepOriginalRanges } : {}),
      ...(hardsubNoRanges ? { hardsub_no_ranges: hardsubNoRanges } : {}),
    }),
  });
}

// ── Chốt kiểm duyệt (008-supervised-pipeline) ───────────────────────────────

export type ReviewGate = "transcript" | "script" | "outline";

export interface ReviewSegment {
  /** 0-based, là KHOÁ định danh khi lưu — không dùng mốc thời gian làm khoá */
  index: number;
  /**
   * Mốc thời gian chỉ để xem, không sửa được ở v1 (FR-016). `null` ở chốt
   * outline (010-topic-video-generation) — scene chưa có timing thật tới
   * bước synthesizing (contracts/api.md §5), client không hiển thị.
   */
  start: number | null;
  end: number | null;
  /** Nội dung sửa được (chốt kịch bản: đây là bản dịch) */
  text: string;
  /** Câu gốc để đối chiếu — chỉ có ở chốt kịch bản (FR-010) */
  source_text: string | null;
}

// 009-hardsub-blur-reposition: vùng phụ đề gốc do người dùng tự khoanh trên
// khung hình đại diện (không còn OCR tự động — xem hardsub/detector.py)
export interface HardsubBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface ReviewPayload {
  job_id: string;
  gate: ReviewGate;
  editable_field: "text" | "translated_text" | "narration_text";
  edited: boolean;
  can_regenerate: boolean;
  reached_at: string | null;
  segments: ReviewSegment[];
  // Chỉ có mặt khi job bật ĐỒNG THỜI hardsub_blur_enabled + supervised, VÀ
  // khung hình đại diện đã trích được (FR-012)
  hardsub_frame_url?: string;
  hardsub_frame_size?: { width: number; height: number } | null;
  hardsub_box?: HardsubBox | null;
  hardsub_no_ranges?: string | null;
}

export function getReview(jobId: string) {
  return request<ReviewPayload>(`/api/jobs/${jobId}/review`);
}

export function hardsubFrameUrl(jobId: string) {
  return `/api/jobs/${jobId}/hardsub-frame`;
}

export function saveReview(
  jobId: string,
  gate: ReviewGate,
  segments: { index: number; text: string }[],
  hardsubBox?: HardsubBox,
  hardsubNoRanges?: string,
) {
  return request<{
    job_id: string;
    gate: ReviewGate;
    saved_count: number;
    dropped_count: number;
  }>(`/api/jobs/${jobId}/review`, {
    method: "PUT",
    body: JSON.stringify({
      gate,
      segments,
      ...(hardsubBox ? { hardsub_box: hardsubBox } : {}),
      ...(hardsubNoRanges !== undefined ? { hardsub_no_ranges: hardsubNoRanges } : {}),
    }),
  });
}

export function approveReview(jobId: string, gate: ReviewGate) {
  return request<{
    job_id: string;
    approved_gate: ReviewGate;
    resumed_status: string;
  }>(`/api/jobs/${jobId}/review/approve`, {
    method: "POST",
    body: JSON.stringify({ gate }),
  });
}

export function regenerateScript(jobId: string) {
  return request<{ job_id: string; regenerated_count: number }>(
    `/api/jobs/${jobId}/review/regenerate`,
    { method: "POST" },
  );
}

export interface DownloadedVideo {
  url: string;
  platform: string;
  source_video: string;
  job_id: string;
  created_at: string;
  available: boolean;
}

export function listDownloads() {
  return request<{ videos: DownloadedVideo[] }>("/api/downloads");
}

export function getJob(jobId: string) {
  return request<JobDetail>(`/api/jobs/${jobId}`);
}

export function listJobs() {
  return request<{ jobs: JobSummary[] }>("/api/jobs");
}

export function pinJob(jobId: string, pinned: boolean) {
  return request<{ job_id: string; pinned: boolean }>(`/api/jobs/${jobId}/pin`, {
    method: "PUT",
    body: JSON.stringify({ pinned }),
  });
}

export function deleteJob(jobId: string) {
  return request<{ ok: boolean }>(`/api/jobs/${jobId}`, { method: "DELETE" });
}

export function retryJob(jobId: string) {
  return request<{ job_id: string }>(`/api/jobs/${jobId}/retry`, { method: "POST" });
}

// 010-rerun-from-step: quay lại một bước trước đó để thử lại, thay vì tạo job mới
export const RERUN_STEPS = [
  "downloading",
  "transcribing",
  "scripting",
  "synthesizing",
  "merging",
] as const;
export type RerunStep = (typeof RERUN_STEPS)[number];

export function rerunFromStep(
  jobId: string,
  step: RerunStep,
  voice?: { ttsProvider: string; voiceId: string },
) {
  return request<{ job_id: string; resumed_status: string }>(
    `/api/jobs/${jobId}/rerun-from`,
    {
      method: "POST",
      body: JSON.stringify({
        step,
        ...(voice
          ? { tts_provider: voice.ttsProvider, voice_id: voice.voiceId }
          : {}),
      }),
    },
  );
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

// ── Tạo video từ chủ đề (010-topic-video-generation) ────────────────────────

export type GenerateStatus =
  | "pending"
  | "outlining"
  | "scripting"
  | "awaiting_review"
  | "sourcing_assets"
  | "synthesizing"
  | "rendering"
  | "done"
  | "failed";

export interface GenerateJobSummary {
  job_id: string;
  job_type: "generate";
  topic: string;
  status: GenerateStatus;
  progress_percent: number;
  created_at: string;
  review_gate: "outline" | null;
}

export interface GenerateScene {
  index: number;
  narration_text: string;
}

export interface GenerateJobDetail extends GenerateJobSummary {
  supervised: boolean;
  tts_provider: string;
  voice_id: string | null;
  error: string | null;
  scenes: GenerateScene[];
  review_url: string | null;
  output_video_url: string | null;
  can_retry: boolean;
}

export function submitGenerateJob(
  topic: string,
  supervised: boolean = false,
  ttsProvider?: string,
  voiceId?: string,
) {
  return request<{ job_id: string }>("/api/generate-jobs", {
    method: "POST",
    body: JSON.stringify({
      topic,
      supervised,
      ...(ttsProvider ? { tts_provider: ttsProvider } : {}),
      ...(voiceId ? { voice_id: voiceId } : {}),
    }),
  });
}

export function getGenerateJob(jobId: string) {
  return request<GenerateJobDetail>(`/api/generate-jobs/${jobId}`);
}

export function listGenerateJobs() {
  return request<{ jobs: GenerateJobSummary[] }>("/api/generate-jobs");
}

export function generateOutputUrl(jobId: string) {
  return `/api/generate-jobs/${jobId}/output`;
}

export function retryGenerateJob(jobId: string) {
  return request<{ job_id: string }>(`/api/generate-jobs/${jobId}/retry`, { method: "POST" });
}

// 010: quay lại 1 bước trước đó (cho phép cả job "done" lẫn "failed"), khác
// /retry chỉ dành cho job failed — cùng tinh thần RERUN_STEPS của luồng dub
export const GENERATE_RERUN_STEPS = [
  "scripting",
  "sourcing_assets",
  "synthesizing",
  "rendering",
] as const;
export type GenerateRerunStep = (typeof GENERATE_RERUN_STEPS)[number];

export function rerunGenerateFromStep(
  jobId: string,
  step: GenerateRerunStep,
  voice?: { ttsProvider: string; voiceId: string },
) {
  return request<{ job_id: string; resumed_status: string }>(
    `/api/generate-jobs/${jobId}/rerun-from`,
    {
      method: "POST",
      body: JSON.stringify({
        step,
        ...(voice ? { tts_provider: voice.ttsProvider, voice_id: voice.voiceId } : {}),
      }),
    },
  );
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

export interface SyncResult {
  checked: number;
  updated: number;
  cancelled: number;
  attempts: PublishAttempt[];
}

// Đồng bộ hàng loạt với Zernio (1 call list thay N call get) — bắt cả thay đổi
// chỉnh thẳng trên Zernio: reschedule, đã đăng/thất bại, đã xoá.
export function syncAttempts() {
  return request<SyncResult>("/api/publish/sync", { method: "POST" });
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
