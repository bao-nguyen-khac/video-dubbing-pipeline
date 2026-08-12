// pages/ScriptToVideoPage.tsx — "Script-to-video": nhập nhân vật/premise, hệ
// thống sinh character bible + kịch bản chia nhiều PHẦN (part) kèm prompt
// Google Flow/Omni Flash, người dùng duyệt từng phần rồi tự tạo clip ở
// ngoài, TỰ NỐI LẠI thành 1 file, upload lại — hệ thống lồng tiếng + ghép
// thành video hoàn chỉnh cho từng phần.
//
// 3 cấp điều hướng qua query param:
//   (không có)                    → danh sách dự án đang có / tạo mới
//   ?project=<slug>                → chi tiết dự án: character bible + danh
//                                    sách các phần
//   ?project=<slug>&part=<index>   → chi tiết 1 phần: duyệt/upload/tiến trình

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  ApiError,
  SCRIPT_TO_VIDEO_PART_RERUN_STEPS,
  getScriptToVideoDeliverable,
  getScriptToVideoJob,
  getScriptToVideoPartDeliverable,
  listScriptToVideoJobs,
  listVoices,
  previewVoice,
  rerunScriptToVideoPartFromStep,
  retryScriptToVideoJob,
  retryScriptToVideoPart,
  scriptToVideoPartOutputUrl,
  submitScriptToVideoJob,
  type ScriptToVideoJobDetail,
  type ScriptToVideoJobSummary,
  type ScriptToVideoPartRerunStep,
  type ScriptToVideoPartSummary,
  type Voice,
} from "../api/client";
import AppShell from "../components/AppShell";
import Callout from "../components/Callout";
import PartUploadCard from "../components/PartUploadCard";
import ScriptPromptReviewPanel from "../components/ScriptPromptReviewPanel";
import StatusBadge from "../components/StatusBadge";
import { IconDownload, IconInbox, IconPlay, IconRetry } from "../components/Icon";
import { confirm } from "../lib/confirm";
import {
  POLL_INTERVAL_MS,
  PROVIDER_LABELS,
  SCRIPT_TO_VIDEO_PART_STEP_LABELS,
  TERMINAL_STATUSES,
  absoluteTime,
  relativeTime,
} from "../lib/labels";

function voiceKey(v: Voice) {
  return `${v.provider}|${v.voice_id}`;
}

const PART_RERUN_ALLOWED_STATUSES = new Set(["done", "failed"]);

// ─── Danh sách dự án ────────────────────────────────────────────────────────

function ProjectRow({ project }: { project: ScriptToVideoJobSummary }) {
  return (
    <Link to={`/script-to-video?project=${project.slug}`} className="job-row" title={project.premise}>
      <span className="job-row__url">{project.premise}</span>
      <div className="job-row__meta">
        <span>{project.parts_done}/{project.parts_total} phần xong</span>
        <span>·</span>
        <span title={absoluteTime(project.created_at)}>{relativeTime(project.created_at)}</span>
      </div>
      <div className="job-row__status">
        <StatusBadge status={project.status} reviewGate={project.review_gate} />
        <span className="progress__pct">{project.progress_percent}%</span>
      </div>
    </Link>
  );
}

function ProjectList({ onCreateNew }: { onCreateNew: () => void }) {
  const [projects, setProjects] = useState<ScriptToVideoJobSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  async function refresh() {
    try {
      const res = await listScriptToVideoJobs();
      setProjects(res.jobs);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không tải được danh sách dự án");
    }
  }

  useEffect(() => {
    refresh();
    pollRef.current = window.setInterval(refresh, POLL_INTERVAL_MS);
    return () => {
      if (pollRef.current !== null) window.clearInterval(pollRef.current);
    };
  }, []);

  const loaded = projects !== null;

  return (
    <>
      <div className="page-head__lead" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span>{!loaded ? "Đang tải..." : `${projects.length} dự án đã tạo.`}</span>
        <button type="button" className="btn btn--primary" onClick={onCreateNew}>
          + Tạo dự án mới
        </button>
      </div>

      {error && (
        <Callout tone="error" title="Có lỗi">
          {error}
        </Callout>
      )}

      {!loaded && !error && (
        <div className="card">
          <div className="skeleton skeleton--row" />
        </div>
      )}

      {loaded && projects.length === 0 && (
        <div className="card">
          <div className="empty">
            <IconInbox className="empty__icon" />
            <div className="empty__title">Chưa có dự án nào</div>
            <p>Bấm &quot;+ Tạo dự án mới&quot; để bắt đầu.</p>
          </div>
        </div>
      )}

      {loaded && projects.length > 0 && (
        <div className="card">
          <div className="job-list">
            {projects.map((p) => (
              <ProjectRow key={p.slug} project={p} />
            ))}
          </div>
        </div>
      )}
    </>
  );
}

// ─── Xem file (character bible / deliverable của phần) ──────────────────────

function DeliverableViewer({
  filenames,
  fetchText,
}: {
  filenames: string[];
  fetchText: (filename: string) => Promise<string>;
}) {
  const [name, setName] = useState("");
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSelect(filename: string) {
    setName(filename);
    setError(null);
    setText(null);
    if (!filename) return;
    try {
      setText(await fetchText(filename));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không tải được nội dung file");
    }
  }

  if (filenames.length === 0) return null;

  return (
    <div className="card">
      <div className="card__title">
        <h2>Xem file</h2>
      </div>
      <div className="field" style={{ maxWidth: "320px" }}>
        <label className="field__label" htmlFor="s2v-deliverable-select">
          Chọn file
        </label>
        <select
          id="s2v-deliverable-select"
          className="select"
          value={name}
          onChange={(e) => handleSelect(e.target.value)}
        >
          <option value="">-- chọn file --</option>
          {filenames.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
      </div>
      {error && (
        <Callout tone="error" title="Không tải được file">
          {error}
        </Callout>
      )}
      {text !== null && (
        <pre
          style={{
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            maxHeight: "24rem",
            overflow: "auto",
            marginTop: "0.75rem",
            padding: "0.75rem",
            background: "var(--surface-alt, rgba(127,127,127,0.08))",
            borderRadius: "6px",
          }}
        >
          {text}
        </pre>
      )}
    </div>
  );
}

// ─── Chi tiết dự án: character bible + danh sách phần ────────────────────────

function ProjectDetail({ project }: { project: ScriptToVideoJobDetail }) {
  return (
    <>
      <div className="card">
        <div className="card__title">
          <h2>Tiến trình</h2>
        </div>
        <p className="page-head__lead">{project.premise}</p>
        <div className="progress">
          <div className="progress__head">
            <StatusBadge status={project.status} reviewGate={project.review_gate} />
            <span className="progress__pct">{project.progress_percent}%</span>
          </div>
          <div className="progress__bar" role="progressbar" aria-valuenow={project.progress_percent} aria-valuemin={0} aria-valuemax={100}>
            <div
              className={`progress__fill${project.status === "done" ? " progress__fill--done" : ""}${project.status === "failed" ? " progress__fill--failed" : ""}`}
              style={{ width: `${project.progress_percent}%` }}
            />
          </div>
        </div>
        {project.error && (
          <Callout tone="error" title="Sinh kịch bản thất bại" >
            {project.error}
          </Callout>
        )}
      </div>

      {project.character && (
        <DeliverableViewer
          filenames={["character-bible.md"]}
          fetchText={(f) => getScriptToVideoDeliverable(project.slug, f)}
        />
      )}

      <div className="card">
        <div className="card__title">
          <h2>Các phần</h2>
        </div>
        <div style={{ display: "grid", gap: "0.75rem" }}>
          {project.parts.map((part) => (
            <PartCard key={part.index} slug={project.slug} part={part} />
          ))}
        </div>
      </div>
    </>
  );
}

function PartCard({ slug, part }: { slug: string; part: ScriptToVideoPartSummary }) {
  const pending = part.status === "pending";
  const content = (
    <div className="card" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.75rem" }}>
      <div>
        <strong>
          Phần {part.index + 1}
          {part.title ? ` · "${part.title}"` : ""}
        </strong>
        <div className="page-head__lead" style={{ margin: 0 }}>
          {pending ? "Đang chờ sinh kịch bản..." : `${part.role ?? ""} · ${part.screen_count} screen`}
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <StatusBadge status={part.status} reviewGate={part.status === "awaiting_review" ? "script_to_video" : null} />
        <span className="progress__pct">{part.progress_percent}%</span>
      </div>
    </div>
  );
  if (pending) return content;
  return (
    <Link to={`/script-to-video?project=${slug}&part=${part.index}`} style={{ textDecoration: "none", color: "inherit" }}>
      {content}
    </Link>
  );
}

// ─── Chi tiết 1 phần: duyệt / upload / tiến trình ────────────────────────────

function PartDetail({
  slug,
  part,
  onDirtyChange,
  onRefresh,
}: {
  slug: string;
  part: ScriptToVideoPartSummary;
  onDirtyChange: (dirty: boolean) => void;
  onRefresh: () => void;
}) {
  const [voices, setVoices] = useState<Voice[]>([]);
  const [selectedVoiceKey, setSelectedVoiceKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [rerunStep, setRerunStep] = useState<ScriptToVideoPartRerunStep>(SCRIPT_TO_VIDEO_PART_RERUN_STEPS[0]);
  const [rerunning, setRerunning] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const previewUrlRef = useRef<string | null>(null);

  useEffect(() => {
    listVoices()
      .then((res) => {
        setVoices(res.voices);
        if (res.voices.length > 0) setSelectedVoiceKey(voiceKey(res.voices[0]));
      })
      .catch(() => {});
  }, []);

  async function handlePreview() {
    const selectedVoice = voices.find((v) => voiceKey(v) === selectedVoiceKey);
    if (!selectedVoice) return;
    setPreviewError(null);
    setPreviewing(true);
    try {
      const blob = await previewVoice(selectedVoice.provider, selectedVoice.voice_id);
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
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

  async function handleRetry() {
    setError(null);
    setRetrying(true);
    try {
      await retryScriptToVideoPart(slug, part.index);
      onRefresh();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError(`Đang có dự án khác xử lý (${err.body?.running_job_id ?? "?"}), vui lòng chờ`);
      } else {
        setError(err instanceof ApiError ? err.message : "Thử lại thất bại");
      }
    } finally {
      setRetrying(false);
    }
  }

  const canChangeVoice = rerunStep === "synthesizing";
  const selectedVoice = voices.find((v) => voiceKey(v) === selectedVoiceKey);

  async function handleRerun(step: ScriptToVideoPartRerunStep) {
    const changingVoice = canChangeVoice && selectedVoice;
    const ok = await confirm({
      title: "Chạy lại từ bước trước đó?",
      message: `Chạy lại từ bước "${SCRIPT_TO_VIDEO_PART_STEP_LABELS[step]}" sẽ XOÁ kết quả của bước này và mọi bước sau (kể cả video kết quả hiện tại nếu có).`,
      confirmLabel: "Chạy lại",
      tone: "danger",
    });
    if (!ok) return;
    setError(null);
    setRerunning(true);
    try {
      await rerunScriptToVideoPartFromStep(
        slug, part.index, step,
        changingVoice ? { ttsProvider: changingVoice.provider, voiceId: changingVoice.voice_id } : undefined,
      );
      onRefresh();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError(`Đang có dự án khác xử lý (${err.body?.running_job_id ?? "?"}), vui lòng chờ`);
      } else {
        setError(err instanceof ApiError ? err.message : "Chạy lại thất bại");
      }
    } finally {
      setRerunning(false);
    }
  }

  const deliverableFilenames = useMemo(() => {
    if (part.screen_count === 0) return [];
    return [
      "script.md",
      ...Array.from({ length: part.screen_count }, (_, i) => `prompt-screen-${i + 1}.md`),
      "prompt-screen-vi.md",
      "voiceover.json",
    ];
  }, [part.screen_count]);

  const showUpload = ["awaiting_upload", "synthesizing", "merging", "done", "failed"].includes(part.status);

  return (
    <>
      {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
      <audio ref={audioRef} hidden />
      <div className="card">
        <div className="card__title">
          <h2>
            Phần {part.index + 1}
            {part.title ? `: "${part.title}"` : ""}
          </h2>
        </div>
        {part.role && <p className="page-head__lead">{part.role}</p>}
        <div className="progress">
          <div className="progress__head">
            <StatusBadge status={part.status} reviewGate={part.status === "awaiting_review" ? "script_to_video" : null} />
            <span className="progress__pct">{part.progress_percent}%</span>
          </div>
          <div className="progress__bar" role="progressbar" aria-valuenow={part.progress_percent} aria-valuemin={0} aria-valuemax={100}>
            <div
              className={`progress__fill${part.status === "done" ? " progress__fill--done" : ""}${part.status === "failed" ? " progress__fill--failed" : ""}`}
              style={{ width: `${part.progress_percent}%` }}
            />
          </div>
        </div>

        {error && (
          <Callout tone="error" title="Không thực hiện được">
            {error}
          </Callout>
        )}

        {part.status === "failed" && (
          <div style={{ marginTop: "1rem" }}>
            <Callout tone="error" title="Phần thất bại">
              {part.error ?? "Không rõ nguyên nhân"}
            </Callout>
            {part.can_retry && (
              <button type="button" className="btn btn--primary" style={{ marginTop: "0.75rem" }} onClick={handleRetry} disabled={retrying}>
                {retrying && <span className="btn__spinner" />}
                {retrying ? "Đang thử lại..." : "Thử lại"}
              </button>
            )}
          </div>
        )}

        {PART_RERUN_ALLOWED_STATUSES.has(part.status) && (
          <div style={{ marginTop: "1.25rem", display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
            <span className="field__label" style={{ margin: 0 }}>
              Chạy lại từ bước:
            </span>
            <select
              className="input"
              style={{ width: "auto" }}
              value={rerunStep}
              onChange={(e) => setRerunStep(e.target.value as ScriptToVideoPartRerunStep)}
              disabled={rerunning}
            >
              {SCRIPT_TO_VIDEO_PART_RERUN_STEPS.map((step) => (
                <option key={step} value={step}>
                  {SCRIPT_TO_VIDEO_PART_STEP_LABELS[step]}
                </option>
              ))}
            </select>
            <button type="button" className="btn btn--ghost" onClick={() => handleRerun(rerunStep)} disabled={rerunning}>
              {rerunning ? <span className="btn__spinner" /> : <IconRetry />}
              {rerunning ? "Đang chạy lại..." : "Chạy lại"}
            </button>
          </div>
        )}

        {PART_RERUN_ALLOWED_STATUSES.has(part.status) && canChangeVoice && (
          <div className="field" style={{ marginTop: "0.75rem" }}>
            <label className="field__label" htmlFor="s2v-rerun-voice-select">
              Đổi giọng đọc (tuỳ chọn)
            </label>
            <div className="voice-picker">
              <select
                id="s2v-rerun-voice-select"
                className="select"
                value={selectedVoiceKey}
                onChange={(e) => setSelectedVoiceKey(e.target.value)}
                disabled={rerunning || voices.length === 0}
              >
                {voices.map((v) => (
                  <option key={voiceKey(v)} value={voiceKey(v)}>
                    {PROVIDER_LABELS[v.provider] ?? v.provider} · {v.name}
                  </option>
                ))}
              </select>
              <button type="button" className="btn btn--ghost" onClick={handlePreview} disabled={previewing || !selectedVoiceKey}>
                {previewing ? <span className="btn__spinner" /> : <IconPlay />}
                {previewing ? "Đang tải" : "Nghe thử"}
              </button>
            </div>
            {previewError && (
              <span className="field__hint" style={{ color: "var(--danger)" }}>
                {previewError}
              </span>
            )}
          </div>
        )}

        {part.status === "done" && part.output_video_url && (
          <div className="result" style={{ marginTop: "1.25rem" }}>
            {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
            <video src={scriptToVideoPartOutputUrl(slug, part.index)} controls preload="metadata" />
            <div className="result__actions">
              <a className="btn btn--primary" href={scriptToVideoPartOutputUrl(slug, part.index)} download>
                <IconDownload />
                Tải video
              </a>
            </div>
          </div>
        )}
      </div>

      {part.status === "awaiting_review" && (
        <ScriptPromptReviewPanel
          slug={slug}
          partIndex={part.index}
          onApproved={onRefresh}
          onDirtyChange={onDirtyChange}
        />
      )}

      {showUpload && (
        <div className="card">
          <div className="card__title">
            <h2>Upload video</h2>
          </div>
          <p className="page-head__lead">
            Dùng Visual Prompt (tiếng Anh) đã duyệt để tạo clip từng screen ở Google Flow, tự nối
            lại thành 1 file, rồi upload ở đây. Hệ thống tự lồng tiếng + ghép khi upload xong.
          </p>
          <PartUploadCard slug={slug} part={part} onUploaded={onRefresh} />
        </div>
      )}

      <DeliverableViewer
        filenames={deliverableFilenames}
        fetchText={(f) => getScriptToVideoPartDeliverable(slug, part.index, f)}
      />
    </>
  );
}

// ─── Trang chính ────────────────────────────────────────────────────────────

export default function ScriptToVideoPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const viewSlug = searchParams.get("project");
  const viewPartIndexRaw = searchParams.get("part");
  const viewPartIndex = viewPartIndexRaw !== null ? Number(viewPartIndexRaw) : null;
  const [showCreateForm, setShowCreateForm] = useState(false);

  const [premise, setPremise] = useState("");
  const [numParts, setNumParts] = useState(2);
  const [targetScreensPerPart, setTargetScreensPerPart] = useState(10);
  const [seriesNotes, setSeriesNotes] = useState("");
  const [voices, setVoices] = useState<Voice[]>([]);
  const [selectedVoiceKey, setSelectedVoiceKey] = useState("");
  const [project, setProject] = useState<ScriptToVideoJobDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [retryingProject, setRetryingProject] = useState(false);
  const [loadingExisting, setLoadingExisting] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [reviewDirty, setReviewDirty] = useState(false);
  const pollRef = useRef<number | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const previewUrlRef = useRef<string | null>(null);

  useEffect(() => {
    listVoices()
      .then((res) => {
        setVoices(res.voices);
        if (res.voices.length > 0) setSelectedVoiceKey(voiceKey(res.voices[0]));
      })
      .catch(() => {});
  }, []);

  function stopPolling() {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  function startPolling(slug: string) {
    stopPolling();
    pollRef.current = window.setInterval(async () => {
      try {
        const detail = await getScriptToVideoJob(slug);
        setProject(detail);
        if (TERMINAL_STATUSES.has(detail.status)) stopPolling();
      } catch {
        stopPolling();
      }
    }, POLL_INTERVAL_MS);
  }

  useEffect(() => stopPolling, []);

  useEffect(() => {
    if (!viewSlug) {
      setProject(null);
      stopPolling();
      return;
    }
    setLoadingExisting(true);
    setError(null);
    getScriptToVideoJob(viewSlug)
      .then((detail) => {
        setProject(detail);
        if (!TERMINAL_STATUSES.has(detail.status)) startPolling(viewSlug);
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Không tải được dự án");
      })
      .finally(() => setLoadingExisting(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewSlug]);

  useEffect(() => {
    if (!project) return;
    if (reviewDirty) {
      stopPolling();
    } else if (!TERMINAL_STATUSES.has(project.status) && pollRef.current === null) {
      startPolling(project.slug);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reviewDirty, project?.slug, project?.status]);

  async function refreshProject() {
    if (!viewSlug) return;
    setReviewDirty(false);
    try {
      const detail = await getScriptToVideoJob(viewSlug);
      setProject(detail);
      if (!TERMINAL_STATUSES.has(detail.status)) startPolling(viewSlug);
    } catch {
      /* poll kế tiếp tự đồng bộ lại */
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const selectedVoice = voices.find((v) => voiceKey(v) === selectedVoiceKey);
      const { slug } = await submitScriptToVideoJob(
        premise, numParts, targetScreensPerPart, seriesNotes || undefined,
        selectedVoice?.provider, selectedVoice?.voice_id,
      );
      setShowCreateForm(false);
      navigate(`/script-to-video?project=${slug}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError(`Đang có dự án xử lý (${err.body?.running_job_id ?? "?"}), vui lòng chờ dự án đó xong`);
      } else {
        setError(err instanceof ApiError ? err.message : "Có lỗi xảy ra khi tạo dự án");
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
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
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

  async function handleRetryProject() {
    if (!project) return;
    setError(null);
    setRetryingProject(true);
    try {
      await retryScriptToVideoJob(project.slug);
      await refreshProject();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError(`Đang có dự án khác xử lý (${err.body?.running_job_id ?? "?"}), vui lòng chờ`);
      } else {
        setError(err instanceof ApiError ? err.message : "Thử lại thất bại");
      }
    } finally {
      setRetryingProject(false);
    }
  }

  const isBusy = project !== null && !TERMINAL_STATUSES.has(project.status);
  const locked = isBusy || submitting;

  const voiceGroups = useMemo(() => {
    const groups = new Map<string, Voice[]>();
    for (const v of voices) {
      const list = groups.get(v.provider) ?? [];
      list.push(v);
      groups.set(v.provider, list);
    }
    return [...groups.entries()];
  }, [voices]);

  const showDetail = !!viewSlug;
  const showPartDetail = showDetail && viewPartIndex !== null;
  const showForm = !showDetail && showCreateForm;
  const showList = !showDetail && !showCreateForm;
  const currentPart = showPartDetail ? project?.parts.find((p) => p.index === viewPartIndex) ?? null : null;

  return (
    <AppShell narrow>
      <div className="page-head">
        <h1>
          {showPartDetail ? `Phần ${(viewPartIndex ?? 0) + 1}` : showDetail ? "Chi tiết dự án" : showForm ? "Tạo dự án mới" : "Script-to-video"}
        </h1>
        {showPartDetail ? (
          <p className="page-head__lead">
            <Link to={`/script-to-video?project=${viewSlug}`}>← Danh sách các phần</Link>
          </p>
        ) : showDetail ? (
          <p className="page-head__lead">
            <Link to="/script-to-video">← Danh sách dự án</Link>
          </p>
        ) : showForm ? (
          <p className="page-head__lead">
            <button type="button" className="btn btn--subtle" onClick={() => setShowCreateForm(false)} style={{ padding: 0 }}>
              ← Danh sách dự án
            </button>
          </p>
        ) : (
          <p className="page-head__lead">
            Nhập 1 nhân vật/premise — hệ thống viết character bible + kịch bản chia nhiều phần
            (part), kèm prompt Google Flow/Gemini Omni Flash. Bạn tự tạo clip từng screen, tự nối
            lại thành 1 file rồi upload lại từng phần, hệ thống sẽ lồng tiếng và ghép video.
          </p>
        )}
      </div>

      {showList && <ProjectList onCreateNew={() => setShowCreateForm(true)} />}

      {showForm && (
        <form onSubmit={handleSubmit}>
          {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
          <audio ref={audioRef} hidden />

          <div className="card">
            <span className="card__eyebrow">Nhân vật / Premise</span>
            <div className="field">
              <label className="field__label" htmlFor="s2v-premise">
                Ý tưởng nhân vật/bối cảnh
              </label>
              <textarea
                id="s2v-premise"
                className="input"
                rows={3}
                value={premise}
                onChange={(e) => setPremise(e.target.value)}
                placeholder="VD: kỹ sư hệ thống quản lý đàn robot khai thác tiểu hành tinh năm 2100"
                disabled={locked}
                required
                style={{ resize: "vertical", fontFamily: "inherit" }}
              />
              <span className="field__hint">
                Hệ thống tự viết character bible (nhân vật/thế giới) + kịch bản POV chia nhiều
                phần, khung hình dọc 9:16.
              </span>
            </div>

            <div className="field" style={{ display: "flex", gap: "1rem" }}>
              <div style={{ flex: 1 }}>
                <label className="field__label" htmlFor="s2v-num-parts">
                  Số phần
                </label>
                <input
                  id="s2v-num-parts" type="number" className="input" min={1}
                  value={numParts} onChange={(e) => setNumParts(Number(e.target.value))}
                  disabled={locked} required
                />
              </div>
              <div style={{ flex: 1 }}>
                <label className="field__label" htmlFor="s2v-screens-per-part">
                  Screen / phần
                </label>
                <input
                  id="s2v-screens-per-part" type="number" className="input" min={1}
                  value={targetScreensPerPart} onChange={(e) => setTargetScreensPerPart(Number(e.target.value))}
                  disabled={locked} required
                />
              </div>
            </div>

            <div className="field">
              <label className="field__label" htmlFor="s2v-series-notes">
                Ghi chú / quy tắc series (tuỳ chọn)
              </label>
              <textarea
                id="s2v-series-notes"
                className="input"
                rows={3}
                value={seriesNotes}
                onChange={(e) => setSeriesNotes(e.target.value)}
                placeholder="VD: giữ tông hard sci-fi công nghiệp, không fantasy, AI đồng hành tên Vega..."
                disabled={locked}
                style={{ resize: "vertical", fontFamily: "inherit" }}
              />
              <span className="field__hint">Dùng để giữ nhất quán nếu bạn có nhiều dự án trong cùng 1 series.</span>
            </div>
          </div>

          <div className="card">
            <span className="card__eyebrow">Giọng đọc</span>
            <div className="field">
              <label className="field__label" htmlFor="s2v-voice-select">
                Chọn giọng
              </label>
              <div className="voice-picker">
                <select
                  id="s2v-voice-select"
                  className="select"
                  value={selectedVoiceKey}
                  onChange={(e) => setSelectedVoiceKey(e.target.value)}
                  disabled={locked || voices.length === 0}
                >
                  {voices.length === 0 && <option value="">Đang tải danh sách giọng...</option>}
                  {voiceGroups.map(([provider, list]) => (
                    <optgroup key={provider} label={PROVIDER_LABELS[provider] ?? provider}>
                      {list.map((v) => (
                        <option key={voiceKey(v)} value={voiceKey(v)}>
                          {v.name}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
                <button type="button" className="btn btn--ghost" onClick={handlePreview} disabled={previewing || !selectedVoiceKey}>
                  {previewing ? <span className="btn__spinner" /> : <IconPlay />}
                  {previewing ? "Đang tải" : "Nghe thử"}
                </button>
              </div>
              {previewError && (
                <span className="field__hint" style={{ color: "var(--danger)" }}>
                  {previewError}
                </span>
              )}
            </div>

            <div className="field">
              <button type="submit" className="btn btn--primary btn--block" disabled={locked}>
                {submitting && <span className="btn__spinner" />}
                {submitting ? "Đang gửi..." : isBusy ? "Đang xử lý dự án hiện tại" : "Tạo dự án"}
              </button>
            </div>
          </div>
        </form>
      )}

      {loadingExisting && !project && (
        <div className="card">
          <div className="skeleton skeleton--row" />
        </div>
      )}

      {error && (
        <Callout tone="error" title="Không thực hiện được">
          {error}
        </Callout>
      )}

      {showDetail && project && !showPartDetail && (
        <>
          <ProjectDetail project={project} />
          {project.status === "failed" && project.can_retry && (
            <div className="card">
              <button type="button" className="btn btn--primary" onClick={handleRetryProject} disabled={retryingProject}>
                {retryingProject && <span className="btn__spinner" />}
                {retryingProject ? "Đang thử lại..." : "Thử lại sinh kịch bản"}
              </button>
            </div>
          )}
        </>
      )}

      {showPartDetail && project && currentPart && (
        <PartDetail slug={project.slug} part={currentPart} onDirtyChange={setReviewDirty} onRefresh={refreshProject} />
      )}

      {showPartDetail && project && !currentPart && (
        <Callout tone="error" title="Không tìm thấy phần này">
          Phần chưa tồn tại hoặc chưa được sinh kịch bản.
        </Callout>
      )}
    </AppShell>
  );
}
