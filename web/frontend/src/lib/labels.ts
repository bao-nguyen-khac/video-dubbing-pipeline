// lib/labels.ts — Nhãn hiển thị + helper format dùng chung cho các trang.
// Gom về 1 chỗ để không lệch chữ giữa HomePage / JobListPage / JobDetailPage.

export const TERMINAL_STATUSES = new Set(["done", "failed"]);

// Nhịp poll chung cho mọi trang — 3s đủ đáp ứng SC-002 (phản ánh đúng trong
// 10s), tránh WebSocket không cần thiết (002 research.md)
export const POLL_INTERVAL_MS = 3000;

export type ScriptMode = "translate" | "rewrite" | "subtitle";

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
];

export const SCRIPT_MODE_LABELS: Record<string, string> = {
  translate: "Dịch chuẩn (lồng tiếng)",
  rewrite: "Sáng tạo (lồng tiếng)",
  subtitle: "Phụ đề tự động (giữ âm thanh gốc)",
};

// "lucyai" hiển thị là "Vivibe" — tên người dùng biết tới, khác định danh nội
// bộ khớp API thật (004 research.md §2)
export const PROVIDER_LABELS: Record<string, string> = {
  "edge-tts": "edge-tts",
  lucyai: "Vivibe",
  "router-tts": "9router",
};

export const PLATFORM_LABELS: Record<string, string> = {
  tiktok: "TikTok",
  douyin: "Douyin",
  youtube: "YouTube",
};

export const STATUS_LABELS: Record<string, string> = {
  pending: "Chờ xử lý",
  downloading: "Đang tải video",
  transcribing: "Đang tách lời",
  scripting: "Đang viết kịch bản",
  synthesizing: "Đang tạo giọng đọc",
  merging: "Đang ghép video",
  done: "Hoàn tất",
  failed: "Thất bại",
};

export type StatusKind = "running" | "done" | "failed";

export function statusKind(status: string): StatusKind {
  if (status === "done") return "done";
  if (status === "failed") return "failed";
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

  return STAGES.map((stage, i) => {
    if (scriptMode === "subtitle" && stage.key === "synthesizing") return "skipped";
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
