import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, getJob, outputUrl, retryJob, type JobDetail } from "../api/client";
import AppShell from "../components/AppShell";
import Callout from "../components/Callout";
import JobProgress from "../components/JobProgress";
import { IconArrowLeft, IconDownload, IconRetry } from "../components/Icon";
import {
  absoluteTime,
  PLATFORM_LABELS,
  POLL_INTERVAL_MS,
  PROVIDER_LABELS,
  SCRIPT_MODE_LABELS,
  TERMINAL_STATUSES,
} from "../lib/labels";

const WARNING_LABELS: Record<string, string> = {
  watermark: "Video còn watermark/hardsub chưa xoá được",
  duration_mismatch: "Giọng đọc lệch thời lượng đáng kể so với video gốc",
  background_music_lost: "Không giữ được nhạc nền gốc (đã mute toàn bộ audio gốc)",
  tts_segments_failed: "Có câu không tổng hợp được giọng đọc, đã thay bằng khoảng lặng",
};

// 005-natural-pause-dubbing: cảnh báo lỗi TTS cục bộ cần nêu rõ SỐ câu bị ảnh
// hưởng và rằng phần còn lại vẫn có lồng tiếng — để người dùng phân biệt với
// lỗi toàn phần (job failed) và với cảnh báo lệch thời lượng (FR-007)
function warningLabel(key: string, job: JobDetail): string {
  if (key === "tts_segments_failed") {
    const count = job.tts_failed_segments || 0;
    const prefix = count > 0 ? `${count} câu` : "Một số câu";
    return `${prefix} không tổng hợp được giọng đọc, đã thay bằng khoảng lặng — phần còn lại của video vẫn có lồng tiếng bình thường`;
  }
  return WARNING_LABELS[key] ?? key;
}

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
      .then((detail) => {
        setJob(detail);
        if (!TERMINAL_STATUSES.has(detail.status)) {
          startPolling(jobId);
        }
      })
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Không tải được thông tin job"),
      );
    return stopPolling;
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
  // Phụ đề động được yêu cầu (dynamic_captions) nhưng burn thất bại — cảnh
  // báo riêng vì đây không phải field trong job.warnings (FR-003, US4: burn
  // lỗi không fail job, chỉ mất caption, nhưng người dùng phải thấy rõ)
  const dynamicCaptionsFailed =
    job?.status === "done" && job.dynamic_captions && !job.subtitles_burned;

  return (
    <AppShell narrow>
      <Link to="/jobs" className="back-link">
        <IconArrowLeft />
        Lịch sử job
      </Link>

      <div className="page-head">
        <h1>Chi tiết job</h1>
        {job && (
          <p className="page-head__lead mono" style={{ fontSize: "0.8rem" }}>
            {job.job_id}
          </p>
        )}
      </div>

      {error && (
        <Callout tone="error" title="Có lỗi xảy ra">
          {error}
        </Callout>
      )}

      {!job && !error && (
        <div>
          <div className="skeleton skeleton--row" />
          <div className="skeleton skeleton--row" />
        </div>
      )}

      {job && (
        <>
          <div className="card">
            <JobProgress
              status={job.status}
              progressPercent={job.progress_percent}
              scriptMode={job.script_mode}
            />

            {job.can_retry && (
              <div style={{ marginTop: "1.25rem" }}>
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={handleRetry}
                  disabled={retrying}
                >
                  {retrying ? <span className="btn__spinner" /> : <IconRetry />}
                  {retrying ? "Đang thử lại..." : "Thử lại job"}
                </button>
              </div>
            )}
          </div>

          {job.status === "failed" && (
            <Callout tone="error" title="Job thất bại">
              {job.error ?? "Không rõ nguyên nhân"}
            </Callout>
          )}

          {(activeWarnings.length > 0 || dynamicCaptionsFailed) && (
            <Callout tone="warning" title="Cảnh báo chất lượng">
              <ul>
                {activeWarnings.map(([key]) => (
                  <li key={key}>{warningLabel(key, job)}</li>
                ))}
                {dynamicCaptionsFailed && (
                  <li>
                    Đã yêu cầu phụ đề động nhưng không burn được — video vẫn có giọng
                    lồng tiếng bình thường, chỉ thiếu phụ đề
                  </li>
                )}
              </ul>
            </Callout>
          )}

          {job.status === "done" && job.output_video_url && (
            <div className="card">
              <div className="card__title">
                <h2>Kết quả</h2>
              </div>
              <div className="result">
                {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                <video src={outputUrl(job.job_id)} controls preload="metadata" />
                <div className="result__actions">
                  <a className="btn btn--primary" href={outputUrl(job.job_id)} download>
                    <IconDownload />
                    Tải video
                  </a>
                </div>
              </div>
            </div>
          )}

          <div className="card">
            <div className="card__title">
              <h2>Thông tin job</h2>
            </div>
            <div className="detail-grid">
              <div className="detail-item">
                <div className="detail-item__label">Nguồn</div>
                <div className="detail-item__value">
                  <a href={job.source_url} target="_blank" rel="noreferrer">
                    {job.source_url}
                  </a>
                </div>
              </div>
              <div className="detail-item">
                <div className="detail-item__label">Nền tảng</div>
                <div className="detail-item__value">
                  {PLATFORM_LABELS[job.platform] ?? job.platform}
                </div>
              </div>
              <div className="detail-item">
                <div className="detail-item__label">Chế độ xử lý</div>
                <div className="detail-item__value">
                  {SCRIPT_MODE_LABELS[job.script_mode] ?? job.script_mode}
                  <div className="tag-row">
                    {job.dynamic_captions && <span className="badge badge--tag">Phụ đề động</span>}
                    {job.script_mode !== "subtitle" && (
                      <span className="badge badge--tag">
                        {PROVIDER_LABELS[job.tts_provider] ?? job.tts_provider}
                        {job.voice_id ? ` · ${job.voice_id}` : ""}
                      </span>
                    )}
                  </div>
                </div>
              </div>
              <div className="detail-item">
                <div className="detail-item__label">Tạo lúc</div>
                <div className="detail-item__value">{absoluteTime(job.created_at)}</div>
              </div>
            </div>
          </div>
        </>
      )}
    </AppShell>
  );
}
