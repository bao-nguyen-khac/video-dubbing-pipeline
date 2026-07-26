import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  ApiError,
  getJob,
  listVoices,
  outputUrl,
  previewVoice,
  submitJob,
  type JobDetail,
  type Voice,
} from "../api/client";

// Polling 3s — đủ đáp ứng SC-002 (phản ánh đúng trong 10s), tránh WebSocket
// không cần thiết (research.md → Cập nhật tiến trình phía frontend)
const POLL_INTERVAL_MS = 3000;

const TERMINAL_STATUSES = new Set(["done", "failed"]);

// Nhãn hiển thị cho provider — "lucyai" hiện là "Vivibe" (tên người dùng
// biết tới), khác định danh nội bộ khớp API thật (004, research.md §2)
const PROVIDER_LABELS: Record<string, string> = {
  "edge-tts": "edge-tts",
  lucyai: "Vivibe",
  "router-tts": "9router",
};

function voiceKey(v: Voice) {
  return `${v.provider}|${v.voice_id}`;
}

export default function HomePage() {
  const [url, setUrl] = useState("");
  const [scriptMode, setScriptMode] = useState<"translate" | "rewrite" | "subtitle">("translate");
  const [dynamicCaptions, setDynamicCaptions] = useState(false);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [selectedVoiceKey, setSelectedVoiceKey] = useState<string>("");
  const [job, setJob] = useState<JobDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const previewUrlRef = useRef<string | null>(null);

  useEffect(() => {
    listVoices()
      .then((res) => {
        setVoices(res.voices);
        if (res.voices.length > 0) {
          setSelectedVoiceKey(voiceKey(res.voices[0]));
        }
      })
      .catch(() => {
        // Không chặn form nếu lấy danh sách giọng lỗi — vẫn dùng được job
        // với giọng mặc định (FR-003 áp dụng tinh thần tương tự)
      });
  }, []);

  function stopPolling() {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  function startPolling(jobId: string) {
    stopPolling();
    pollRef.current = window.setInterval(async () => {
      try {
        const detail = await getJob(jobId);
        setJob(detail);
        if (TERMINAL_STATUSES.has(detail.status)) {
          stopPolling();
        }
      } catch {
        stopPolling();
      }
    }, POLL_INTERVAL_MS);
  }

  useEffect(() => stopPolling, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const selectedVoice = voices.find((v) => voiceKey(v) === selectedVoiceKey);
      const { job_id } = await submitJob(
        url,
        scriptMode,
        scriptMode !== "subtitle" && dynamicCaptions,
        scriptMode !== "subtitle" ? selectedVoice?.provider : undefined,
        scriptMode !== "subtitle" ? selectedVoice?.voice_id : undefined,
      );
      const detail = await getJob(job_id);
      setJob(detail);
      startPolling(job_id);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const runningId = err.body?.running_job_id ?? "?";
        setError(`Đang có job xử lý (job_id: ${runningId}), vui lòng chờ job đó xong (FR-009)`);
      } else {
        setError(err instanceof ApiError ? err.message : "Có lỗi xảy ra khi submit job");
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function handlePreview() {
    const selectedVoice = voices.find((v) => voiceKey(v) === selectedVoiceKey);
    if (!selectedVoice) return;

    setPreviewError(null);
    setPreviewing(true);
    try {
      const blob = await previewVoice(selectedVoice.provider, selectedVoice.voice_id);
      // Dọn URL cũ trước khi tạo URL mới, tránh rò rỉ bộ nhớ khi nghe thử
      // nhiều giọng liên tiếp (Acceptance Scenario 3, US2)
      if (previewUrlRef.current) {
        URL.revokeObjectURL(previewUrlRef.current);
      }
      const objectUrl = URL.createObjectURL(blob);
      previewUrlRef.current = objectUrl;
      if (audioRef.current) {
        audioRef.current.src = objectUrl;
        await audioRef.current.play();
      }
    } catch (err) {
      setPreviewError(err instanceof ApiError ? err.message : "Nghe thử thất bại");
    } finally {
      setPreviewing(false);
    }
  }

  const isBusy = job !== null && !TERMINAL_STATUSES.has(job.status);

  return (
    <div className="page home-page">
      <h1>Video Repurpose Pipeline</h1>
      <p>
        <Link to="/jobs">Xem lịch sử job</Link>
      </p>

      <form onSubmit={handleSubmit}>
        <label>
          URL video (TikTok / Douyin / YouTube)
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.tiktok.com/@user/video/..."
            disabled={isBusy || submitting}
            required
          />
        </label>
        <label>
          Chế độ kịch bản
          <select
            value={scriptMode}
            onChange={(e) => setScriptMode(e.target.value as "translate" | "rewrite" | "subtitle")}
            disabled={isBusy || submitting}
          >
            <option value="translate">Dịch chuẩn (lồng tiếng)</option>
            <option value="rewrite">Sáng tạo (lồng tiếng)</option>
            <option value="subtitle">Phụ đề tự động (giữ âm thanh gốc)</option>
          </select>
        </label>
        {scriptMode !== "subtitle" && (
          <label>
            Giọng đọc
            <div className="voice-picker">
              <select
                value={selectedVoiceKey}
                onChange={(e) => setSelectedVoiceKey(e.target.value)}
                disabled={isBusy || submitting || voices.length === 0}
              >
                {voices.length === 0 && <option value="">Đang tải danh sách giọng...</option>}
                {voices.map((v) => (
                  <option key={voiceKey(v)} value={voiceKey(v)}>
                    {v.name} ({PROVIDER_LABELS[v.provider] ?? v.provider})
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={handlePreview}
                disabled={previewing || !selectedVoiceKey}
              >
                {previewing ? "Đang tải..." : "Nghe thử"}
              </button>
            </div>
            {previewError && <span className="error">{previewError}</span>}
          </label>
        )}
        {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
        <audio ref={audioRef} hidden />
        {scriptMode !== "subtitle" && (
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={dynamicCaptions}
              onChange={(e) => setDynamicCaptions(e.target.checked)}
              disabled={isBusy || submitting}
            />
            Phụ đề động (chữ khớp nhịp giọng đọc)
          </label>
        )}
        <button type="submit" disabled={isBusy || submitting}>
          {submitting ? "Đang gửi..." : "Chạy"}
        </button>
      </form>

      {error && <p className="error">{error}</p>}

      {job && (
        <div className="job-progress">
          <p>
            Trạng thái: <strong>{job.status}</strong> ({job.progress_percent}%)
          </p>
          <progress value={job.progress_percent} max={100} style={{ width: "100%" }} />

          {job.status === "failed" && (
            <p className="error">Lỗi: {job.error ?? "Không rõ nguyên nhân"}</p>
          )}

          {job.status === "done" && job.output_video_url && (
            <div className="job-result">
              <video src={outputUrl(job.job_id)} controls width={360} />
              <p>
                <a href={outputUrl(job.job_id)} download>
                  Tải video
                </a>
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
