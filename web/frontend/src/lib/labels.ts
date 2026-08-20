// lib/labels.ts — Nhãn hiển thị + helper format dùng chung cho các trang.
// Gom về 1 chỗ để không lệch chữ giữa HomePage / JobListPage / JobDetailPage.

export const TERMINAL_STATUSES = new Set(["done", "failed"]);

// Nhịp poll chung cho mọi trang — 3s đủ đáp ứng SC-002 (phản ánh đúng trong
// 10s), tránh WebSocket không cần thiết (002 research.md)
export const POLL_INTERVAL_MS = 3000;

export type ScriptMode = "translate" | "rewrite" | "subtitle" | "visual" | "download";

export const SCRIPT_MODES: {
  value: ScriptMode;
  name: string;
  desc: string;
}[] = [
  {
    value: "translate",
    name: "Dịch chuẩn",
    desc: "Lồng tiếng, dịch sát nội dung gốc",
  },
  {
    value: "rewrite",
    name: "Sáng tạo",
    desc: "Lồng tiếng, viết lại kịch bản mới",
  },
  {
    value: "subtitle",
    name: "Phụ đề tự động",
    desc: "Giữ nguyên âm thanh gốc, chỉ thêm phụ đề",
  },
  {
    value: "visual",
    name: "Thuyết minh theo hình ảnh",
    desc: "LLM xem video viết kịch bản khớp cảnh — cho video không có lời thoại (vd unbox)",
  },
  {
    value: "download",
    name: "Chỉ tải video",
    desc: "Tải video gốc về, không xử lý gì thêm",
  },
];

export const SCRIPT_MODE_LABELS: Record<string, string> = {
  translate: "Dịch chuẩn (lồng tiếng)",
  rewrite: "Sáng tạo (lồng tiếng)",
  subtitle: "Phụ đề tự động (giữ âm thanh gốc)",
  visual: "Thuyết minh theo hình ảnh (lồng tiếng)",
  download: "Chỉ tải video (không xử lý)",
};

// "lucyai" hiển thị là "Vivibe" — tên người dùng biết tới, khác định danh nội
// bộ khớp API thật (004 research.md §2)
export const PROVIDER_LABELS: Record<string, string> = {
  "edge-tts": "edge-tts",
  lucyai: "Vivibe",
  omnivoice: "OmniVoice",
  // "router-tts" (9router) tạm tắt — giữ nhãn để job cũ vẫn hiển thị đúng tên
  "router-tts": "9router",
};

export const PLATFORM_LABELS: Record<string, string> = {
  tiktok: "TikTok",
  douyin: "Douyin",
  youtube: "YouTube",
  upload: "Tải lên",
};

export const STATUS_LABELS: Record<string, string> = {
  pending: "Chờ xử lý",
  downloading: "Đang tải video",
  transcribing: "Đang tách lời",
  scripting: "Đang viết kịch bản",
  synthesizing: "Đang tạo giọng đọc",
  merging: "Đang ghép video",
  awaiting_review: "Chờ duyệt",
  done: "Hoàn tất",
  failed: "Thất bại",
  // 010-topic-video-generation: trạng thái riêng của luồng "generate" — 3 giá
  // trị pending/awaiting_review/done/failed đã dùng chung ở trên
  outlining: "Đang lên outline",
  sourcing_assets: "Đang tìm ảnh minh hoạ",
  rendering: "Đang dựng video",
  // Script-to-video v3: premise → nhiều PHẦN (part), mỗi phần: kịch bản →
  // duyệt → upload merge.mp4 → TTS → ghép. "pending"/"scripting"/
  // "awaiting_review"/"synthesizing"/"merging"/"done"/"failed" đã dùng chung
  // ở trên (cùng ý nghĩa, dùng lại nguyên nhãn — "merging" của dub cũng là
  // "ghép giọng vào video"). "ready" là trạng thái CẤP DỰ ÁN (đã sinh xong
  // kịch bản mọi phần, tiến trình tiếp theo nằm ở từng phần) — cố ý không
  // trùng nghĩa "done".
  ready: "Đã sinh kịch bản",
  awaiting_upload: "Chờ tải video lên",
};

// 010-topic-video-generation: nhãn ngắn (dạng danh từ) cho dropdown "Chạy lại
// từ bước" của GenerateVideoPage — cùng tinh thần STAGES bên dub nhưng thứ tự
// bước khác hẳn (không có download/transcribe/merge)
export const GENERATE_STEP_LABELS: Record<string, string> = {
  scripting: "Kịch bản (outline + lời thoại)",
  sourcing_assets: "Tìm ảnh minh hoạ",
  synthesizing: "Giọng đọc",
  rendering: "Dựng video",
};

// Script-to-video v3: nhãn ngắn cho dropdown "Chạy lại từ bước" của 1 PHẦN —
// chỉ 2 bước cuối (synthesizing/merging), rerun "kịch bản" của riêng 1 phần
// không hỗ trợ (có nguy cơ phá continuity với phần khác đã dựa vào bản cũ).
export const SCRIPT_TO_VIDEO_PART_STEP_LABELS: Record<string, string> = {
  synthesizing: "Giọng đọc",
  merging: "Ghép giọng vào video",
};

// 008-supervised-pipeline: tên chốt hiển thị cho người dùng
export const REVIEW_GATE_LABELS: Record<string, string> = {
  transcript: "chốt lời thoại",
  script: "chốt kịch bản",
  // 010-topic-video-generation
  outline: "chốt outline",
  // script-to-video
  script_to_video: "chốt kịch bản & prompt",
};

export type StatusKind = "running" | "waiting" | "done" | "failed";

/**
 * Nhóm màu/ý nghĩa của trạng thái.
 *
 * "waiting" (008) là nhóm RIÊNG: job chờ duyệt không đang xử lý (nó đã nhả suất
 * cho job khác) và cũng không lỗi — gộp vào "running" hay "failed" đều làm người
 * dùng hiểu sai việc cần làm (FR-006).
 *
 * "awaiting_upload" (script-to-video, theo phần) CŨNG thuộc nhóm "waiting"
 * cùng lý do — phần đang chờ người dùng tự upload video, không phải hệ
 * thống đang xử lý gì.
 */
export function statusKind(status: string): StatusKind {
  if (status === "done") return "done";
  if (status === "failed") return "failed";
  if (status === "awaiting_review" || status === "awaiting_upload") return "waiting";
  return "running";
}

/**
 * Các bước của pipeline kèm mốc % tương ứng do backend trả về
 * (`_STATUS_PROGRESS_MAP` trong web/backend/jobs_api.py). Dùng % thay vì tên
 * status để suy ra bước hiện tại, vì job `failed` không mang tên bước dở dang
 * — backend đã suy sẵn ra % từ artifact đã có.
 */
export const STAGES = [
  { key: "downloading", label: "Tải video", pct: 15 },
  { key: "transcribing", label: "Tách lời", pct: 32 },
  { key: "scripting", label: "Kịch bản", pct: 48 },
  { key: "synthesizing", label: "Giọng đọc", pct: 65 },
  { key: "merging", label: "Ghép video", pct: 82 },
  { key: "done", label: "Hoàn tất", pct: 100 },
] as const;

export type StageState = "done" | "active" | "failed" | "pending" | "skipped";

/**
 * Trạng thái hiển thị của từng bước cho 1 job.
 *
 * `script_mode="subtitle"` không có bước tạo giọng đọc (giữ nguyên audio gốc)
 * nên bước đó hiện dạng gạch ngang thay vì giả vờ đã chạy.
 *
 * Job `awaiting_review` (008) có kind "waiting" — không phải "failed" nên bước
 * kế tiếp hiện "active" (bước trước đã xong, bước này chờ phê duyệt để chạy),
 * KHÔNG bị vẽ thành dấu lỗi.
 */
export function stageStates(
  progressPercent: number,
  status: string,
  scriptMode?: string,
): StageState[] {
  const kind = statusKind(status);
  const currentIndex = Math.max(
    0,
    STAGES.findIndex((s) => s.pct >= progressPercent),
  );

  // "download" chỉ tải rồi xong — mọi bước xử lý sau tải đều gạch ngang.
  const downloadOnlySkipped = new Set([
    "transcribing", "scripting", "synthesizing", "merging",
  ]);

  return STAGES.map((stage, i) => {
    if (scriptMode === "subtitle" && stage.key === "synthesizing") return "skipped";
    if (scriptMode === "download" && downloadOnlySkipped.has(stage.key)) return "skipped";
    if (i < currentIndex) return "done";
    if (i > currentIndex) return "pending";
    if (kind === "failed") return "failed";
    if (kind === "done") return "done";
    return "active";
  });
}

/** Thời gian tương đối kiểu "3 phút trước", fallback về ngày giờ tuyệt đối. */
export function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;

  const diffSeconds = Math.round((then - Date.now()) / 1000);
  const abs = Math.abs(diffSeconds);
  const rtf = new Intl.RelativeTimeFormat("vi", { numeric: "auto" });

  if (abs < 60) return rtf.format(Math.round(diffSeconds), "second");
  if (abs < 3600) return rtf.format(Math.round(diffSeconds / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diffSeconds / 3600), "hour");
  if (abs < 604800) return rtf.format(Math.round(diffSeconds / 86400), "day");
  return new Date(then).toLocaleString("vi-VN");
}

export function absoluteTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("vi-VN");
}

/**
 * Rút gọn URL cho dễ đọc trong danh sách: bỏ scheme và "www.".
 *
 * GIỮ query string vì với YouTube (`/watch?v=...`) đó mới là phần định danh
 * video — cắt đi thì 2 job YouTube khác nhau trông giống hệt nhau.
 */
export function shortUrl(url: string): string {
  try {
    const u = new URL(url);
    return `${u.hostname.replace(/^www\./, "")}${u.pathname}${u.search}`;
  } catch {
    return url;
  }
}

// ── Hẹn giờ đăng (007-schedule-publish) ─────────────────────────────────────
//
// Giờ Việt Nam KHÔNG có giờ mùa hè (luôn UTC+7 cố định), nên quy đổi bằng cộng
// trừ 7 tiếng thẳng là đủ chính xác — không cần Intl timezone database. Phải
// khớp tuyệt đối với publish/timezones.py phía backend (research.md §2): lệch
// 1 trong 2 chỗ là bài lên sai giờ.

const VN_UTC_OFFSET_HOURS = 7;

/**
 * Giá trị từ `<input type="datetime-local">` (vd "2026-07-29T20:00", không có
 * múi giờ) → chuỗi ISO 8601 UTC để gửi API. Input được hiểu là giờ Việt Nam.
 */
export function localDatetimeToUtcIso(value: string): string {
  const [datePart, timePart] = value.split("T");
  const [year, month, day] = datePart.split("-").map(Number);
  const [hour, minute] = (timePart || "00:00").split(":").map(Number);
  const utcMs = Date.UTC(year, month - 1, day, hour - VN_UTC_OFFSET_HOURS, minute, 0);
  return new Date(utcMs).toISOString();
}

/**
 * Chuỗi ISO 8601 UTC (từ API) → giá trị dùng được cho
 * `<input type="datetime-local">`, hiển thị theo giờ Việt Nam.
 */
export function utcIsoToLocalDatetime(utcIso: string): string {
  const utcMs = new Date(utcIso).getTime();
  const vn = new Date(utcMs + VN_UTC_OFFSET_HOURS * 60 * 60 * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${vn.getUTCFullYear()}-${pad(vn.getUTCMonth() + 1)}-${pad(vn.getUTCDate())}` +
    `T${pad(vn.getUTCHours())}:${pad(vn.getUTCMinutes())}`
  );
}

/** Hiển thị giờ đăng dự kiến theo giờ Việt Nam, kiểu "29/07/2026 20:00". */
export function formatScheduledFor(utcIso: string): string {
  const utcMs = new Date(utcIso).getTime();
  const vn = new Date(utcMs + VN_UTC_OFFSET_HOURS * 60 * 60 * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${pad(vn.getUTCDate())}/${pad(vn.getUTCMonth() + 1)}/${vn.getUTCFullYear()} ` +
    `${pad(vn.getUTCHours())}:${pad(vn.getUTCMinutes())}`
  );
}

export const PUBLISH_ATTEMPT_STATUS_LABELS: Record<string, string> = {
  pending: "Đang chuẩn bị",
  publishing: "Đang đăng",
  scheduled: "Đang chờ đăng",
  success: "Thành công",
  failed: "Thất bại",
  cancelled: "Đã huỷ",
};

export function voiceKey(v: { provider: string; voice_id: string }) {
  return `${v.provider}|${v.voice_id}`;
}

export function inferVoiceTags(name: string, _provider?: string): { gender?: "Nam" | "Nữ"; region?: string } {
  const lower = name.toLowerCase();
  let gender: "Nam" | "Nữ" | undefined;
  if (lower.includes("nữ") || lower.includes("female") || lower.includes("mai") || lower.includes("ngọc") || lower.includes("trang")) {
    gender = "Nữ";
  } else if (lower.includes("nam") || lower.includes("male") || lower.includes("khánh") || lower.includes("minh") || lower.includes("hùng")) {
    gender = "Nam";
  }

  let region: string | undefined;
  if (lower.includes("bắc") || lower.includes("hà nội") || lower.includes("northern")) {
    region = "Miền Bắc";
  } else if (lower.includes("nam") || lower.includes("sài gòn") || lower.includes("southern")) {
    region = "Miền Nam";
  } else if (lower.includes("trung") || lower.includes("huế") || lower.includes("đà nẵng")) {
    region = "Miền Trung";
  }

  return { gender, region };
}

