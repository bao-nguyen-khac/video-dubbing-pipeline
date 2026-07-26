import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, listJobs, type JobSummary } from "../api/client";
import AppShell from "../components/AppShell";
import Callout from "../components/Callout";
import StatusBadge from "../components/StatusBadge";
import { IconInbox } from "../components/Icon";
import { PLATFORM_LABELS, relativeTime, absoluteTime, shortUrl } from "../lib/labels";

export default function JobListPage() {
  const [jobs, setJobs] = useState<JobSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listJobs()
      .then((res) => setJobs(res.jobs))
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Không tải được danh sách job"),
      );
  }, []);

  return (
    <AppShell>
      <div className="page-head">
        <h1>Lịch sử job</h1>
        <p className="page-head__lead">
          {jobs === null ? "Đang tải..." : `${jobs.length} job đã chạy trên máy này.`}
        </p>
      </div>

      {error && (
        <Callout tone="error" title="Không tải được danh sách">
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
        <div className="job-list">
          {jobs.map((job) => (
            <Link key={job.job_id} to={`/jobs/${job.job_id}`} className="job-row">
              <div className="job-row__url" title={job.source_url}>
                {shortUrl(job.source_url)}
              </div>
              <div className="job-row__meta">
                <span>{PLATFORM_LABELS[job.platform] ?? job.platform}</span>
                <span>·</span>
                <span title={absoluteTime(job.created_at)}>{relativeTime(job.created_at)}</span>
              </div>
              <div className="job-row__status">
                <StatusBadge status={job.status} />
                <span className="job-row__pct">{job.progress_percent}%</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </AppShell>
  );
}
