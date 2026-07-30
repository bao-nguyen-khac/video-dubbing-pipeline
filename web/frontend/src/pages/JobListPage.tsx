import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ApiError,
  deleteJob,
  listJobs,
  pinJob,
  type JobSummary,
} from "../api/client";
import AppShell from "../components/AppShell";
import Callout from "../components/Callout";
import StatusBadge from "../components/StatusBadge";
import { IconInbox } from "../components/Icon";
import { PLATFORM_LABELS, relativeTime, absoluteTime, shortUrl } from "../lib/labels";

function JobRow({
  job,
  busy,
  onPin,
  onDelete,
}: {
  job: JobSummary;
  busy: boolean;
  onPin: (job: JobSummary) => void;
  onDelete: (job: JobSummary) => void;
}) {
  return (
    <div className="job-row">
      <Link to={`/jobs/${job.job_id}`} className="job-row__url" title={job.source_url}>
        {shortUrl(job.source_url)}
      </Link>
      <div className="job-row__meta">
        <span>{PLATFORM_LABELS[job.platform] ?? job.platform}</span>
        <span>·</span>
        <span title={absoluteTime(job.created_at)}>{relativeTime(job.created_at)}</span>
      </div>
      <div className="job-row__status">
        <StatusBadge status={job.status} />
        <button
          type="button"
          className="btn btn--subtle"
          onClick={() => onPin(job)}
          disabled={busy}
          title={job.pinned ? "Bỏ ghim" : "Ghim lên mục Ưu tiên"}
        >
          {job.pinned ? "📌 Bỏ ghim" : "📌 Ghim"}
        </button>
        <button
          type="button"
          className="btn btn--subtle"
          onClick={() => onDelete(job)}
          disabled={busy}
          title="Xoá job và toàn bộ file trên server"
        >
          🗑 Xoá
        </button>
      </div>
    </div>
  );
}

export default function JobListPage() {
  const [jobs, setJobs] = useState<JobSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await listJobs();
      setJobs(res.jobs);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không tải được danh sách job");
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function handlePin(job: JobSummary) {
    setBusyId(job.job_id);
    setError(null);
    try {
      await pinJob(job.job_id, !job.pinned);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ghim thất bại");
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(job: JobSummary) {
    if (!window.confirm(`Xoá hẳn job này và toàn bộ file trên server?\n${shortUrl(job.source_url)}`)) {
      return;
    }
    setBusyId(job.job_id);
    setError(null);
    try {
      await deleteJob(job.job_id);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Xoá thất bại");
    } finally {
      setBusyId(null);
    }
  }

  // Ghim lên đầu (mục Ưu tiên), sắp theo lúc ghim mới nhất; còn lại theo lúc tạo
  const pinned = (jobs ?? [])
    .filter((j) => j.pinned)
    .sort((a, b) => (b.pinned_at ?? "").localeCompare(a.pinned_at ?? ""));
  const rest = (jobs ?? [])
    .filter((j) => !j.pinned)
    .sort((a, b) => b.created_at.localeCompare(a.created_at));

  return (
    <AppShell>
      <div className="page-head">
        <h1>Lịch sử job</h1>
        <p className="page-head__lead">
          {jobs === null ? "Đang tải..." : `${jobs.length} job đã chạy trên máy này.`}
        </p>
      </div>

      {error && (
        <Callout tone="error" title="Có lỗi">
          {error}
        </Callout>
      )}

      {jobs === null && !error && (
        <div>
          <div className="skeleton skeleton--row" />
          <div className="skeleton skeleton--row" />
          <div className="skeleton skeleton--row" />
        </div>
      )}

      {jobs !== null && jobs.length === 0 && (
        <div className="card">
          <div className="empty">
            <IconInbox className="empty__icon" />
            <div className="empty__title">Chưa có job nào</div>
            <p>
              Dán link video ở <Link to="/">trang tạo job</Link> để bắt đầu.
            </p>
          </div>
        </div>
      )}

      {jobs !== null && jobs.length > 0 && (
        <>
          {pinned.length > 0 && (
            <div className="card">
              <div className="card__title">📌 Ưu tiên (đã ghim)</div>
              <div className="job-list">
                {pinned.map((job) => (
                  <JobRow
                    key={job.job_id}
                    job={job}
                    busy={busyId === job.job_id}
                    onPin={handlePin}
                    onDelete={handleDelete}
                  />
                ))}
              </div>
            </div>
          )}

          <div className="card">
            {pinned.length > 0 && <div className="card__title">Còn lại</div>}
            {rest.length === 0 ? (
              <p className="page-head__lead" style={{ margin: 0 }}>
                Tất cả job đang được ghim ở mục Ưu tiên.
              </p>
            ) : (
              <div className="job-list">
                {rest.map((job) => (
                  <JobRow
                    key={job.job_id}
                    job={job}
                    busy={busyId === job.job_id}
                    onPin={handlePin}
                    onDelete={handleDelete}
                  />
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </AppShell>
  );
}
