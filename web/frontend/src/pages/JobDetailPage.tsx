import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, getJob, outputUrl, retryJob, type JobDetail } from "../api/client";

const WARNING_LABELS: Record<string, string> = {
  watermark: "Video còn watermark/hardsub chưa xoá được",
  duration_mismatch: "Giọng đọc lệch thời lượng đáng kể so với video gốc",
  background_music_lost: "Không giữ được nhạc nền gốc (đã mute toàn bộ audio gốc)",
};

const TERMINAL_STATUSES = new Set(["done", "failed"]);
// Cùng nhịp poll với HomePage (research.md → Cập nhật tiến trình phía frontend)
const POLL_INTERVAL_MS = 3000;

export default function JobDetailPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const [job, setJob] = useState<JobDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const pollRef = useRef<number | null>(null);

  function stopPolling() {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  function startPolling(id: string) {
    stopPolling();
    pollRef.current = window.setInterval(async () => {
      try {
        const detail = await getJob(id);
        setJob(detail);
        if (TERMINAL_STATUSES.has(detail.status)) {
          stopPolling();
        }
      } catch {
        stopPolling();
      }
    }, POLL_INTERVAL_MS);
  }

  useEffect(() => {
    if (!jobId) return;
    getJob(jobId)
      .then(setJob)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Không tải được job"));
    return stopPolling;
  }, [jobId]);

  async function handleRetry() {
    if (!jobId) return;
    setError(null);
    setRetrying(true);
    try {
      await retryJob(jobId);
      const detail = await getJob(jobId);
      setJob(detail);
      startPolling(jobId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Thử lại thất bại");
    } finally {
      setRetrying(false);
    }
  }

  const activeWarnings = job
    ? Object.entries(job.warnings || {}).filter(([, value]) => value)
    : [];

  return (
    <div className="page job-detail-page">
      <h1>Chi tiết job</h1>
      <p>
        <Link to="/jobs">← Quay lại danh sách job</Link>
      </p>

      {error && <p className="error">{error}</p>}
      {!job && !error && <p>Đang tải...</p>}

      {job && (
        <div>
          <p>
            <strong>URL:</strong> {job.source_url}
          </p>
          <p>
            <strong>Nền tảng:</strong> {job.platform}
          </p>
          <p>
            <strong>Chế độ kịch bản:</strong>{" "}
            {job.script_mode === "translate" ? "Dịch" : "Tự soạn"}
          </p>
          <p>
            <strong>Trạng thái:</strong> {job.status} ({job.progress_percent}%)
          </p>

          {job.status === "failed" && (
            <p className="error">Lỗi: {job.error ?? "Không rõ nguyên nhân"}</p>
          )}

          {job.can_retry && (
            <button type="button" onClick={handleRetry} disabled={retrying}>
              {retrying ? "Đang thử lại..." : "Thử lại"}
            </button>
          )}

          {activeWarnings.length > 0 && (
            <div>
              <strong>Cảnh báo chất lượng:</strong>
              <ul className="warnings-list">
                {activeWarnings.map(([key]) => (
                  <li key={key}>{WARNING_LABELS[key] ?? key}</li>
                ))}
              </ul>
            </div>
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
