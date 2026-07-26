import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ApiError, getJob, outputUrl, submitJob, type JobDetail } from "../api/client";

// Polling 3s — đủ đáp ứng SC-002 (phản ánh đúng trong 10s), tránh WebSocket
// không cần thiết (research.md → Cập nhật tiến trình phía frontend)
const POLL_INTERVAL_MS = 3000;

const TERMINAL_STATUSES = new Set(["done", "failed"]);

export default function HomePage() {
  const [url, setUrl] = useState("");
  const [scriptMode, setScriptMode] = useState<"translate" | "rewrite">("translate");
  const [job, setJob] = useState<JobDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const pollRef = useRef<number | null>(null);

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
      const { job_id } = await submitJob(url, scriptMode);
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
            onChange={(e) => setScriptMode(e.target.value as "translate" | "rewrite")}
            disabled={isBusy || submitting}
          >
            <option value="translate">Dịch</option>
            <option value="rewrite">Tự soạn</option>
          </select>
        </label>
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
