// pages/ScriptToVideoPage.tsx — Studio: Script-to-video (Character Bible & POV Multi-part)
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  SCRIPT_TO_VIDEO_PART_RERUN_STEPS,
  getScriptToVideoDeliverable,
  getScriptToVideoJob,
  getScriptToVideoPartDeliverable,
  listScriptToVideoJobs,
  listVoices,
  rerunScriptToVideoPartFromStep,
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
import StudioTabs from "../components/StudioTabs";
import VoiceSelector from "../components/VoiceSelector";
import { IconDownload, IconInbox, IconRetry, IconSparkles } from "../components/Icon";
import { confirm } from "../lib/confirm";
import {
  POLL_INTERVAL_MS,
  SCRIPT_TO_VIDEO_PART_STEP_LABELS,
  TERMINAL_STATUSES,
  absoluteTime,
  relativeTime,
  voiceKey,
} from "../lib/labels";
import { useToast } from "../context/ToastContext";

const PART_RERUN_ALLOWED_STATUSES = new Set(["done", "failed"]);

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
    } catch {
      setError("Không tải được danh sách dự án");
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
      <div className="page-head__lead" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
        <span>{!loaded ? "Đang tải..." : `${projects.length} dự án đã tạo.`}</span>
        <button type="button" className="btn btn--primary" onClick={onCreateNew}>
          + Tạo dự án mới
        </button>
      </div>

      {error && <Callout tone="error" title="Có lỗi">{error}</Callout>}

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
            <p>Bấm &quot;+ Tạo dự án mới&quot; để bắt đầu kịch bản đầu tiên.</p>
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
    } catch {
      setError("Không tải được nội dung file");
    }
  }

  if (filenames.length === 0) return null;

  return (
    <div className="card">
      <div className="card__title">
        <h2>Tài liệu đã sinh (Deliverables)</h2>
      </div>
      <div className="field" style={{ maxWidth: "320px" }}>
        <label className="field__label" htmlFor="s2v-deliverable-select">
          Chọn file để xem
        </label>
        <select
          id="s2v-deliverable-select"
          className="select"
          value={name}
          onChange={(e) => handleSelect(e.target.value)}
        >
          <option value="">-- Chọn file tài liệu --</option>
          {filenames.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
      </div>
      {error && <Callout tone="error" title="Lỗi">{error}</Callout>}
      {text !== null && (
        <pre
          style={{
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            maxHeight: "24rem",
            overflow: "auto",
            marginTop: "0.75rem",
            padding: "0.85rem",
            background: "var(--surface-2)",
            border: "1px solid var(--border)",
            borderRadius: "6px",
            fontSize: "0.85rem",
          }}
        >
          {text}
        </pre>
      )}
    </div>
  );
}

function ProjectDetail({ project }: { project: ScriptToVideoJobDetail }) {
  return (
    <>
      <div className="card">
        <div className="card__title">
          <h2>Tiến trình dự án</h2>
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
        {project.error && <Callout tone="error" title="Lỗi">{project.error}</Callout>}
      </div>

      {project.character && (
        <DeliverableViewer
          filenames={["character-bible.md"]}
          fetchText={(f) => getScriptToVideoDeliverable(project.slug, f)}
        />
      )}

      <div className="card">
        <div className="card__title">
          <h2>Danh sách các phần ({project.parts.length})</h2>
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

  useEffect(() => {
    listVoices()
      .then((res) => {
        setVoices(res.voices);
        if (res.voices.length > 0) setSelectedVoiceKey(voiceKey(res.voices[0]));
      })
      .catch(() => {});
  }, []);

  async function handleRetry() {
    setError(null);
    setRetrying(true);
    try {
      await retryScriptToVideoPart(slug, part.index);
      onRefresh();
    } catch {
      setError("Thử lại thất bại");
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
      message: `Chạy lại từ bước "${SCRIPT_TO_VIDEO_PART_STEP_LABELS[step]}" sẽ XOÁ kết quả của bước này và mọi bước sau.`,
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
    } catch {
      setError("Chạy lại thất bại");
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

        {error && <Callout tone="error" title="Lỗi">{error}</Callout>}

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
            <h2>Upload video đã tạo</h2>
          </div>
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
  const [loadingExisting, setLoadingExisting] = useState(false);
  const [reviewDirty, setReviewDirty] = useState(false);
  const pollRef = useRef<number | null>(null);
  const toast = useToast();

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
      .catch(() => {
        setError("Không tải được dự án");
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
    } catch {}
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
      toast.success("Đã tạo dự án Script-to-video thành công!");
      setShowCreateForm(false);
      navigate(`/script-to-video?project=${slug}`);
    } catch {
      setError("Có lỗi xảy ra khi tạo dự án");
      toast.error("Không tạo được dự án");
    } finally {
      setSubmitting(false);
    }
  }

  const isBusy = project !== null && !TERMINAL_STATUSES.has(project.status);
  const locked = isBusy || submitting;

  const showDetail = !!viewSlug;
  const showPartDetail = showDetail && viewPartIndex !== null;
  const showForm = !showDetail && showCreateForm;
  const showList = !showDetail && !showCreateForm;
  const currentPart = showPartDetail ? project?.parts.find((p) => p.index === viewPartIndex) ?? null : null;

  return (
    <AppShell narrow>
      <div className="page-head">
        <h1>
          {showPartDetail ? `Phần ${(viewPartIndex ?? 0) + 1}` : showDetail ? "Chi tiết dự án" : showForm ? "Tạo dự án mới" : "Script-to-video Studio"}
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
            Nhập 1 nhân vật/premise — hệ thống viết Character Bible + kịch bản chia nhiều phần kèm Visual Prompt cho Google Flow/Veo.
          </p>
        )}
      </div>

      {!viewSlug && !showCreateForm && <StudioTabs />}

      {showList && <ProjectList onCreateNew={() => setShowCreateForm(true)} />}

      {showForm && (
        <form onSubmit={handleSubmit}>
          <div className="card">
            <span className="card__eyebrow">Nhân vật / Bối cảnh</span>
            <div className="field">
              <label className="field__label" htmlFor="s2v-premise">
                Ý tưởng nhân vật/bối cảnh (Premise)
              </label>
              <textarea
                id="s2v-premise"
                className="input"
                rows={3}
                value={premise}
                onChange={(e) => setPremise(e.target.value)}
                placeholder="VD: Kỹ sư hệ thống quản lý đàn robot khai thác tiểu hành tinh năm 2100..."
                disabled={locked}
                required
                style={{ resize: "vertical", fontFamily: "inherit" }}
              />
            </div>

            <div className="field" style={{ display: "flex", gap: "1rem" }}>
              <div style={{ flex: 1 }}>
                <label className="field__label" htmlFor="s2v-num-parts">
                  Số phần (Parts)
                </label>
                <input
                  id="s2v-num-parts" type="number" className="input" min={1}
                  value={numParts} onChange={(e) => setNumParts(Number(e.target.value))}
                  disabled={locked} required
                />
              </div>
              <div style={{ flex: 1 }}>
                <label className="field__label" htmlFor="s2v-screens-per-part">
                  Số Screen / mỗi phần
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
                Ghi chú series (tuỳ chọn)
              </label>
              <textarea
                id="s2v-series-notes"
                className="input"
                rows={2}
                value={seriesNotes}
                onChange={(e) => setSeriesNotes(e.target.value)}
                placeholder="VD: Tông hard sci-fi, không fantasy, nhân vật chính tên Mark..."
                disabled={locked}
                style={{ resize: "vertical", fontFamily: "inherit" }}
              />
            </div>
          </div>

          <div className="card">
            <span className="card__eyebrow">Giọng đọc</span>
            <VoiceSelector
              voices={voices}
              selectedVoiceKey={selectedVoiceKey}
              onChange={setSelectedVoiceKey}
              disabled={locked}
            />

            <div className="field" style={{ marginTop: "1.25rem" }}>
              <button type="submit" className="btn btn--primary btn--block" disabled={locked}>
                {submitting ? (
                  <>
                    <span className="btn__spinner" />
                    <span>Đang sinh kịch bản...</span>
                  </>
                ) : (
                  <>
                    <IconSparkles size={16} />
                    <span>Bắt đầu dự án</span>
                  </>
                )}
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

      {error && <Callout tone="error" title="Lỗi">{error}</Callout>}

      {showDetail && !showPartDetail && project && <ProjectDetail project={project} />}

      {showPartDetail && currentPart && (
        <PartDetail
          slug={viewSlug!}
          part={currentPart}
          onDirtyChange={setReviewDirty}
          onRefresh={refreshProject}
        />
      )}
    </AppShell>
  );
}
