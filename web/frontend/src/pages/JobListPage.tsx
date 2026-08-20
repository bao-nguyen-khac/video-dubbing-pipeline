// pages/JobListPage.tsx — Lịch sử & Quản lý Job với Search, Status Filters, và Stats Banner
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  deleteJob,
  listGenerateJobs,
  listJobs,
  listScriptToVideoJobs,
  pinJob,
  type GenerateJobSummary,
  type JobSummary,
  type ScriptToVideoJobSummary,
} from "../api/client";
import AppShell from "../components/AppShell";
import Callout from "../components/Callout";
import StatusBadge from "../components/StatusBadge";
import { IconClose, IconInbox, IconPin, IconSearch, IconTrash } from "../components/Icon";
import { PLATFORM_LABELS, relativeTime, absoluteTime, shortUrl } from "../lib/labels";
import { confirm } from "../lib/confirm";
import { useToast } from "../context/ToastContext";

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
          className="btn btn--subtle text-danger"
          onClick={() => onDelete(job)}
          disabled={busy}
          title="Xoá job và file trên server"
        >
          <IconTrash />
          Xoá
        </button>
      </div>
    </div>
  );
}

function GenerateJobRow({ job }: { job: GenerateJobSummary }) {
  return (
    <Link to={`/generate?job=${job.job_id}`} className="job-row" title={job.topic}>
      <span className="job-row__url">{job.topic}</span>
      <div className="job-row__meta">
        <span className="badge badge--tag">Tạo từ chủ đề</span>
        <span>·</span>
        <span title={absoluteTime(job.created_at)}>{relativeTime(job.created_at)}</span>
      </div>
      <div className="job-row__status">
        <StatusBadge status={job.status} reviewGate={job.review_gate} />
      </div>
    </Link>
  );
}

function ScriptToVideoJobRow({ job }: { job: ScriptToVideoJobSummary }) {
  return (
    <Link to={`/script-to-video?project=${job.slug}`} className="job-row" title={job.premise}>
      <span className="job-row__url">{job.premise}</span>
      <div className="job-row__meta">
        <span className="badge badge--tag">Script-to-video</span>
        <span>·</span>
        <span>{job.parts_done}/{job.parts_total} phần hoàn thành</span>
        <span>·</span>
        <span title={absoluteTime(job.created_at)}>{relativeTime(job.created_at)}</span>
      </div>
      <div className="job-row__status">
        <StatusBadge status={job.status} reviewGate={job.review_gate} />
      </div>
    </Link>
  );
}

type UnifiedJob =
  | { kind: "dub"; job: JobSummary }
  | { kind: "generate"; job: GenerateJobSummary }
  | { kind: "script_to_video"; job: ScriptToVideoJobSummary };

export default function JobListPage() {
  const [jobs, setJobs] = useState<JobSummary[] | null>(null);
  const [generateJobs, setGenerateJobs] = useState<GenerateJobSummary[] | null>(null);
  const [scriptToVideoJobs, setScriptToVideoJobs] = useState<ScriptToVideoJobSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  // Filters & Search
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "running" | "waiting" | "done" | "failed" | "pinned">("all");
  const toast = useToast();

  const refresh = useCallback(async () => {
    try {
      const [dubRes, generateRes, scriptToVideoRes] = await Promise.all([
        listJobs(),
        listGenerateJobs(),
        listScriptToVideoJobs(),
      ]);
      setJobs(dubRes.jobs);
      setGenerateJobs(generateRes.jobs);
      setScriptToVideoJobs(scriptToVideoRes.jobs);
    } catch {
      setError("Không tải được danh sách job");
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
      toast.success(job.pinned ? "Đã bỏ ghim job!" : "Đã ghim job vào mục Ưu tiên!");
      await refresh();
    } catch {
      toast.error("Ghim thất bại");
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(job: JobSummary) {
    const ok = await confirm({
      title: "Xoá job này?",
      message: `Xoá hẳn job này và toàn bộ file trên server:\n${shortUrl(job.source_url)}`,
      confirmLabel: "Xoá hẳn",
      tone: "danger",
    });
    if (!ok) return;
    setBusyId(job.job_id);
    setError(null);
    try {
      await deleteJob(job.job_id);
      toast.success("Đã xoá job thành công!");
      await refresh();
    } catch {
      toast.error("Xoá thất bại");
    } finally {
      setBusyId(null);
    }
  }

  const loaded = jobs !== null && generateJobs !== null && scriptToVideoJobs !== null;

  // Unified list of all jobs
  const allUnifiedJobs: UnifiedJob[] = useMemo(() => {
    if (!loaded) return [];
    return [
      ...(jobs ?? []).map((j): UnifiedJob => ({ kind: "dub", job: j })),
      ...(generateJobs ?? []).map((j): UnifiedJob => ({ kind: "generate", job: j })),
      ...(scriptToVideoJobs ?? []).map((j): UnifiedJob => ({ kind: "script_to_video", job: j })),
    ];
  }, [loaded, jobs, generateJobs, scriptToVideoJobs]);

  // Quick stats
  const stats = useMemo(() => {
    const total = allUnifiedJobs.length;
    let waiting = 0;
    let done = 0;
    let failed = 0;
    let running = 0;

    allUnifiedJobs.forEach((item) => {
      const st = item.job.status;
      if (st === "done" || st === "ready") done++;
      else if (st === "failed") failed++;
      else if (st === "awaiting_review" || st === "awaiting_upload") waiting++;
      else running++;
    });

    return { total, waiting, done, failed, running };
  }, [allUnifiedJobs]);

  // Filtered and searched list
  const filteredJobs = useMemo(() => {
    return allUnifiedJobs.filter((item) => {
      // Search term match
      let searchTarget = "";
      if (item.kind === "dub") searchTarget = `${item.job.source_url} ${item.job.job_id}`;
      else if (item.kind === "generate") searchTarget = `${item.job.topic} ${item.job.job_id}`;
      else if (item.kind === "script_to_video") searchTarget = `${item.job.premise} ${item.job.slug}`;

      const matchSearch = !search.trim() || searchTarget.toLowerCase().includes(search.toLowerCase());

      // Status match
      let matchStatus = true;
      const st = item.job.status;
      if (statusFilter === "pinned") {
        matchStatus = item.kind === "dub" && !!item.job.pinned;
      } else if (statusFilter === "waiting") {
        matchStatus = st === "awaiting_review" || st === "awaiting_upload";
      } else if (statusFilter === "done") {
        matchStatus = st === "done" || st === "ready";
      } else if (statusFilter === "failed") {
        matchStatus = st === "failed";
      } else if (statusFilter === "running") {
        matchStatus = st !== "done" && st !== "ready" && st !== "failed" && st !== "awaiting_review" && st !== "awaiting_upload";
      }

      return matchSearch && matchStatus;
    });
  }, [allUnifiedJobs, search, statusFilter]);

  const pinned = useMemo(() => {
    return filteredJobs.filter((item) => item.kind === "dub" && item.job.pinned);
  }, [filteredJobs]);

  const rest = useMemo(() => {
    return filteredJobs
      .filter((item) => !(item.kind === "dub" && item.job.pinned))
      .sort((a, b) => b.job.created_at.localeCompare(a.job.created_at));
  }, [filteredJobs]);

  return (
    <AppShell>
      <div className="page-head">
        <h1>Lịch sử &amp; Quản lý Job</h1>
        <p className="page-head__lead">
          Theo dõi tiến trình, kiểm duyệt và quản lý toàn bộ video đã xử lý trên hệ thống.
        </p>
      </div>

      {error && <Callout tone="error" title="Có lỗi">{error}</Callout>}

      {/* Stats Dashboard Banner */}
      {loaded && stats.total > 0 && (
        <div className="stats-banner">
          <div className="stat-card">
            <div className="stat-card__number">{stats.total}</div>
            <div className="stat-card__label">Tổng số job</div>
          </div>

          <div className={`stat-card ${stats.waiting > 0 ? "stat-card--highlight" : ""}`}>
            <div className="stat-card__number">{stats.waiting}</div>
            <div className="stat-card__label">Chờ duyệt</div>
          </div>

          <div className="stat-card">
            <div className="stat-card__number">{stats.running}</div>
            <div className="stat-card__label">Đang xử lý</div>
          </div>

          <div className="stat-card">
            <div className="stat-card__number">{stats.done}</div>
            <div className="stat-card__label">Hoàn tất</div>
          </div>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="job-filter-bar">
        <div className="job-search-box">
          <IconSearch size={16} className="job-search-icon" />
          <input
            type="text"
            className="input job-search-input"
            placeholder="Tìm theo URL, chủ đề, kịch bản, ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {search && (
            <button
              type="button"
              className="job-search-clear"
              onClick={() => setSearch("")}
              aria-label="Xoá tìm kiếm"
            >
              <IconClose size={14} />
            </button>
          )}
        </div>

        <div className="job-status-chips">
          <button
            type="button"
            className={`filter-chip ${statusFilter === "all" ? "filter-chip--active" : ""}`}
            onClick={() => setStatusFilter("all")}
          >
            Tất cả ({stats.total})
          </button>
          {stats.waiting > 0 && (
            <button
              type="button"
              className={`filter-chip filter-chip--warn ${statusFilter === "waiting" ? "filter-chip--active" : ""}`}
              onClick={() => setStatusFilter("waiting")}
            >
              ⚠️ Chờ duyệt ({stats.waiting})
            </button>
          )}
          <button
            type="button"
            className={`filter-chip ${statusFilter === "running" ? "filter-chip--active" : ""}`}
            onClick={() => setStatusFilter("running")}
          >
            Đang chạy ({stats.running})
          </button>
          <button
            type="button"
            className={`filter-chip ${statusFilter === "done" ? "filter-chip--active" : ""}`}
            onClick={() => setStatusFilter("done")}
          >
            Hoàn tất ({stats.done})
          </button>
          {stats.failed > 0 && (
            <button
              type="button"
              className={`filter-chip ${statusFilter === "failed" ? "filter-chip--active" : ""}`}
              onClick={() => setStatusFilter("failed")}
            >
              Lỗi ({stats.failed})
            </button>
          )}
        </div>
      </div>

      {!loaded && !error && (
        <div>
          <div className="skeleton skeleton--row" />
          <div className="skeleton skeleton--row" />
          <div className="skeleton skeleton--row" />
        </div>
      )}

      {loaded && filteredJobs.length === 0 && (
        <div className="card">
          <div className="empty">
            <IconInbox className="empty__icon" />
            <div className="empty__title">
              {search || statusFilter !== "all" ? "Không có job nào khớp bộ lọc" : "Chưa có job nào"}
            </div>
            <p>
              {search || statusFilter !== "all" ? (
                <button
                  type="button"
                  className="btn btn--subtle"
                  onClick={() => {
                    setSearch("");
                    setStatusFilter("all");
                  }}
                >
                  Xoá bộ lọc tìm kiếm
                </button>
              ) : (
                <>Dán link video ở <Link to="/">trang tạo job</Link> để bắt đầu.</>
              )}
            </p>
          </div>
        </div>
      )}

      {loaded && filteredJobs.length > 0 && (
        <>
          {pinned.length > 0 && (
            <div className="card card--pinned">
              <span className="card__eyebrow">
                <IconPin size={12} /> Ưu tiên · {pinned.length} đã ghim
              </span>
              <div className="job-list">
                {pinned.map((item) => (
                  <JobRow
                    key={(item.job as JobSummary).job_id}
                    job={item.job as JobSummary}
                    busy={busyId === (item.job as JobSummary).job_id}
                    onPin={handlePin}
                    onDelete={handleDelete}
                  />
                ))}
              </div>
            </div>
          )}

          <div className="card">
            {pinned.length > 0 && <span className="card__eyebrow">Danh sách ({rest.length})</span>}
            <div className="job-list">
              {rest.map((item) => {
                if (item.kind === "dub") {
                  return (
                    <JobRow
                      key={item.job.job_id}
                      job={item.job}
                      busy={busyId === item.job.job_id}
                      onPin={handlePin}
                      onDelete={handleDelete}
                    />
                  );
                }
                if (item.kind === "generate") {
                  return <GenerateJobRow key={item.job.job_id} job={item.job} />;
                }
                return <ScriptToVideoJobRow key={item.job.slug} job={item.job} />;
              })}
            </div>
          </div>
        </>
      )}
    </AppShell>
  );
}
