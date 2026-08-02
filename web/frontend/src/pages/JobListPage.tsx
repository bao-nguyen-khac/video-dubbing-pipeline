import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ApiError,
  deleteJob,
  listGenerateJobs,
  listJobs,
  pinJob,
  type GenerateJobSummary,
  type JobSummary,
} from "../api/client";
import AppShell from "../components/AppShell";
import Callout from "../components/Callout";
import StatusBadge from "../components/StatusBadge";
import { IconInbox, IconPin, IconTrash } from "../components/Icon";
import { PLATFORM_LABELS, relativeTime, absoluteTime, shortUrl } from "../lib/labels";
import { confirm } from "../lib/confirm";

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
        <StatusBadge status={job.status} reviewGate={job.review_gate} />
        <button
          type="button"
          className={`btn btn--subtle${job.pinned ? " btn--pinned" : ""}`}
          onClick={() => onPin(job)}
          disabled={busy}
          title={job.pinned ? "Bỏ ghim" : "Ghim lên mục Ưu tiên"}
        >
          <IconPin />
          {job.pinned ? "Bỏ ghim" : "Ghim"}
        </button>
        <button
          type="button"
          className="btn btn--subtle"
          onClick={() => onDelete(job)}
          disabled={busy}
          title="Xoá job và toàn bộ file trên server"
        >
          <IconTrash />
          Xoá
        </button>
      </div>
    </div>
  );
}

// 010-topic-video-generation: job "generate" chưa có pin/xoá ở backend (chỉ
// dub job có 2 thao tác đó) — hàng riêng, đơn giản hơn, chỉ có link xem.
function GenerateJobRow({ job }: { job: GenerateJobSummary }) {
  return (
    <Link to={`/generate?job=${job.job_id}`} className="job-row" title={job.topic}>
      <span className="job-row__url">{job.topic}</span>
      <div className="job-row__meta">
        <span>Tạo từ chủ đề</span>
        <span>·</span>
        <span title={absoluteTime(job.created_at)}>{relativeTime(job.created_at)}</span>
      </div>
      <div className="job-row__status">
        <StatusBadge status={job.status} reviewGate={job.review_gate} />
      </div>
    </Link>
  );
}

type UnifiedRest =
  | { kind: "dub"; job: JobSummary }
  | { kind: "generate"; job: GenerateJobSummary };

export default function JobListPage() {
  const [jobs, setJobs] = useState<JobSummary[] | null>(null);
  const [generateJobs, setGenerateJobs] = useState<GenerateJobSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [dubRes, generateRes] = await Promise.all([listJobs(), listGenerateJobs()]);
      setJobs(dubRes.jobs);
      setGenerateJobs(generateRes.jobs);
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
    const ok = await confirm({
      title: "Xoá job này?",
      message: `Xoá hẳn job này và toàn bộ file trên server:\n${shortUrl(job.source_url)}`,
      confirmLabel: "Xoá",
      tone: "danger",
    });
    if (!ok) return;
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

  const loaded = jobs !== null && generateJobs !== null;
  const totalCount = (jobs?.length ?? 0) + (generateJobs?.length ?? 0);

  // Ghim lên đầu (mục Ưu tiên) — chỉ dub job có khái niệm ghim
  const pinned = (jobs ?? [])
    .filter((j) => j.pinned)
    .sort((a, b) => (b.pinned_at ?? "").localeCompare(a.pinned_at ?? ""));

  // "Còn lại" = dub job chưa ghim + MỌI job generate, trộn theo thời gian tạo
  const rest: UnifiedRest[] = [
    ...(jobs ?? []).filter((j) => !j.pinned).map((job): UnifiedRest => ({ kind: "dub", job })),
    ...(generateJobs ?? []).map((job): UnifiedRest => ({ kind: "generate", job })),
  ].sort((a, b) => b.job.created_at.localeCompare(a.job.created_at));

  return (
    <AppShell>
      <div className="page-head">
        <h1>Lịch sử job</h1>
        <p className="page-head__lead">
          {!loaded ? "Đang tải..." : `${totalCount} job đã chạy trên máy này.`}
        </p>
      </div>

      {error && (
        <Callout tone="error" title="Có lỗi">
          {error}
        </Callout>
      )}

      {!loaded && !error && (
        <div>
          <div className="skeleton skeleton--row" />
          <div className="skeleton skeleton--row" />
          <div className="skeleton skeleton--row" />
        </div>
      )}

      {loaded && totalCount === 0 && (
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

      {loaded && totalCount > 0 && (
        <>
          {pinned.length > 0 && (
            <div className="card card--pinned">
              <span className="card__eyebrow">
                <IconPin size={12} /> Ưu tiên · {pinned.length} đã ghim
              </span>
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
            {pinned.length > 0 && <span className="card__eyebrow">Còn lại · {rest.length}</span>}
            {rest.length === 0 ? (
              <p className="page-head__lead" style={{ margin: 0 }}>
                Tất cả job đang được ghim ở mục Ưu tiên.
              </p>
            ) : (
              <div className="job-list">
                {rest.map((item) =>
                  item.kind === "dub" ? (
                    <JobRow
                      key={item.job.job_id}
                      job={item.job}
                      busy={busyId === item.job.job_id}
                      onPin={handlePin}
                      onDelete={handleDelete}
                    />
                  ) : (
                    <GenerateJobRow key={item.job.job_id} job={item.job} />
                  ),
                )}
              </div>
            )}
          </div>
        </>
      )}
    </AppShell>
  );
}
