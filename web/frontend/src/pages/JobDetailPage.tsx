// pages/JobDetailPage.tsx — Chi tiết job với Dual-Sync Video Comparison Player & Rerun Controls
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ApiError,
  getJob,
  listVoices,
  outputUrl,
  RERUN_STEPS,
  rerunFromStep,
  retryJob,
  sourceUrl,
  type JobDetail,
  type RerunStep,
  type Voice,
} from "../api/client";
import AppShell from "../components/AppShell";
import Callout from "../components/Callout";
import JobProgress from "../components/JobProgress";
import { IconArrowLeft, IconDownload, IconPlay, IconPause, IconRetry, IconShare, IconVolume, IconVolumeMute } from "../components/Icon";
import ReviewGatePanel from "../components/ReviewGatePanel";
import VoiceSelector from "../components/VoiceSelector";
import {
  absoluteTime,
  PLATFORM_LABELS,
  POLL_INTERVAL_MS,
  PROVIDER_LABELS,
  SCRIPT_MODE_LABELS,
  STAGES,
  TERMINAL_STATUSES,
  voiceKey,
} from "../lib/labels";
import { confirm } from "../lib/confirm";
import { useToast } from "../context/ToastContext";

const RERUN_STEP_LABELS: Record<RerunStep, string> = Object.fromEntries(
  STAGES.filter((s) => (RERUN_STEPS as readonly string[]).includes(s.key)).map((s) => [
    s.key,
    s.label,
  ]),
) as Record<RerunStep, string>;

const RERUN_ALLOWED_STATUSES = new Set(["done", "failed", "awaiting_review"]);

const WARNING_LABELS: Record<string, string> = {
  watermark: "Video còn watermark/hardsub chưa xoá được",
  duration_mismatch: "Giọng đọc lệch thời lượng đáng kể so với video gốc",
  background_music_lost: "Không giữ được nhạc nền gốc (đã mute toàn bộ audio gốc)",
  tts_segments_failed: "Có câu không tổng hợp được giọng đọc, đã thay bằng khoảng lặng",
};

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
  const [rerunning, setRerunning] = useState(false);
  const [rerunStep, setRerunStep] = useState<RerunStep>("transcribing");
  const [voices, setVoices] = useState<Voice[]>([]);
  const [selectedVoiceKey, setSelectedVoiceKey] = useState<string>("");
  const pollRef = useRef<number | null>(null);
  const [reviewDirty, setReviewDirty] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [shareError, setShareError] = useState<string | null>(null);
  const shareFileRef = useRef<File | null>(null);
  const sharePrefetchJobIdRef = useRef<string | null>(null);

  // Dual-Sync Player State
  const sourceVideoRef = useRef<HTMLVideoElement | null>(null);
  const outputVideoRef = useRef<HTMLVideoElement | null>(null);
  const [isSyncPlaying, setIsSyncPlaying] = useState(false);
  const [audioFocus, setAudioFocus] = useState<"output" | "source" | "both">("output");

  const toast = useToast();

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

  const isDubbingJob =
    job?.script_mode === "translate" ||
    job?.script_mode === "rewrite" ||
    job?.script_mode === "visual";

  useEffect(() => {
    if (!isDubbingJob || voices.length > 0) return;
    listVoices()
      .then((res) => {
        setVoices(res.voices);
        const current = res.voices.find(
          (v) => v.provider === job?.tts_provider && v.voice_id === job?.voice_id,
        );
        setSelectedVoiceKey(voiceKey(current ?? res.voices[0]));
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDubbingJob]);

  useEffect(() => {
    if (!jobId) return;
    if (reviewDirty) {
      stopPolling();
    } else if (job && !TERMINAL_STATUSES.has(job.status) && pollRef.current === null) {
      startPolling(jobId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reviewDirty, jobId, job?.status]);

  const handleReviewAdvanced = useCallback(async () => {
    if (!jobId) return;
    setReviewDirty(false);
    try {
      const detail = await getJob(jobId);
      setJob(detail);
      if (!TERMINAL_STATUSES.has(detail.status)) startPolling(jobId);
    } catch {}
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

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
      toast.info("Đang thử lại job...");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Thử lại thất bại");
    } finally {
      setRetrying(false);
    }
  }

  const canChangeVoice = isDubbingJob && rerunStep !== "merging";
  const selectedVoice = voices.find((v) => voiceKey(v) === selectedVoiceKey);
  const voiceChanged =
    !!selectedVoice &&
    (selectedVoice.provider !== job?.tts_provider || selectedVoice.voice_id !== job?.voice_id);

  async function handleRerun(step: RerunStep) {
    if (!jobId) return;
    const changingVoice = canChangeVoice && voiceChanged && selectedVoice;
    const confirmMsg = changingVoice
      ? `Chạy lại từ bước "${RERUN_STEP_LABELS[step]}" với giọng đọc "${changingVoice.name}", sẽ XOÁ kết quả của bước này và mọi bước sau.`
      : `Chạy lại từ bước "${RERUN_STEP_LABELS[step]}" sẽ XOÁ kết quả của bước này và mọi bước sau.`;
    const ok = await confirm({
      title: "Chạy lại từ bước trước đó?",
      message: confirmMsg,
      confirmLabel: "Chạy lại",
      tone: "danger",
    });
    if (!ok) return;
    setError(null);
    setRerunning(true);
    try {
      await rerunFromStep(
        jobId,
        step,
        changingVoice
          ? { ttsProvider: changingVoice.provider, voiceId: changingVoice.voice_id }
          : undefined,
      );
      toast.info(`Đang chạy lại từ bước "${RERUN_STEP_LABELS[step]}"...`);
      const detail = await getJob(jobId);
      setJob(detail);
      startPolling(jobId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Chạy lại thất bại");
    } finally {
      setRerunning(false);
    }
  }

  useEffect(() => {
    if (job?.status !== "done" || !job.output_video_url) return;
    if (sharePrefetchJobIdRef.current === job.job_id) return;
    sharePrefetchJobIdRef.current = job.job_id;
    const currentJobId = job.job_id;
    fetch(outputUrl(currentJobId))
      .then((res) => (res.ok ? res.blob() : Promise.reject(new Error("prefetch failed"))))
      .then((blob) => {
        shareFileRef.current = new File([blob], `${currentJobId}.mp4`, { type: "video/mp4" });
      })
      .catch(() => {});
  }, [job?.status, job?.output_video_url, job?.job_id]);

  async function handleShareAirDrop() {
    if (!job) return;
    setShareError(null);
    if (typeof navigator === "undefined" || typeof navigator.share !== "function") {
      setShareError(
        "Trình duyệt này không hỗ trợ chia sẻ file trực tiếp. Hãy bấm \"Tải video\" rồi AirDrop file từ Finder.",
      );
      return;
    }
    setSharing(true);
    try {
      let file: File | null = shareFileRef.current;
      if (!file) {
        const res = await fetch(outputUrl(job.job_id));
        if (!res.ok) throw new Error("Không tải được video để chia sẻ");
        const blob = await res.blob();
        file = new File([blob], `${job.job_id}.mp4`, { type: "video/mp4" });
      }

      if (!file) {
        throw new Error("Không tạo được file video để chia sẻ");
      }

      if (typeof navigator.canShare === "function" && !navigator.canShare({ files: [file] })) {
        setShareError(
          "Trình duyệt không hỗ trợ chia sẻ file video. Hãy bấm \"Tải video\" rồi chia sẻ từ thư mục máy.",
        );
        return;
      }
      await navigator.share({ files: [file], title: `Video ${job.job_id}` });
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") return;
      if (err instanceof Error && err.name === "NotAllowedError") {
        setShareError(
          "Chưa kịp chuẩn bị file để chia sẻ ngay lúc bấm — đợi vài giây rồi bấm lại.",
        );
        return;
      }
      setShareError(err instanceof Error ? err.message : "Chia sẻ thất bại");
    } finally {
      setSharing(false);
    }
  }

  // Dual-Sync Player Handlers
  function toggleDualPlay() {
    const src = sourceVideoRef.current;
    const out = outputVideoRef.current;
    if (!out) return;

    if (isSyncPlaying) {
      out.pause();
      if (src) src.pause();
      setIsSyncPlaying(false);
    } else {
      if (src) {
        src.currentTime = out.currentTime;
        src.play().catch(() => {});
      }
      out.play().catch(() => {});
      setIsSyncPlaying(true);
    }
  }

  function handleOutputTimeUpdate() {
    if (!isSyncPlaying || !sourceVideoRef.current || !outputVideoRef.current) return;
    const src = sourceVideoRef.current;
    const out = outputVideoRef.current;
    if (Math.abs(src.currentTime - out.currentTime) > 0.3) {
      src.currentTime = out.currentTime;
    }
  }

  function updateAudioFocus(focus: "output" | "source" | "both") {
    setAudioFocus(focus);
    if (outputVideoRef.current) {
      outputVideoRef.current.muted = focus === "source";
    }
    if (sourceVideoRef.current) {
      sourceVideoRef.current.muted = focus === "output";
    }
  }

  const activeWarnings = job
    ? Object.entries(job.warnings || {}).filter(([, value]) => value)
    : [];
  const dynamicCaptionsFailed =
    job?.status === "done" && job.dynamic_captions && !job.subtitles_burned;

  return (
    <AppShell>
      <Link to="/jobs" className="back-link">
        <IconArrowLeft />
        Lịch sử job
      </Link>

      <div className="page-head">
        <h1>Chi tiết &amp; Quản lý Job</h1>
        {job && (
          <p className="page-head__lead mono" style={{ fontSize: "0.85rem" }}>
            ID: {job.job_id}
          </p>
        )}
      </div>

      {error && <Callout tone="error" title="Có lỗi">{error}</Callout>}

      {!job && !error && (
        <div>
          <div className="skeleton skeleton--row" />
          <div className="skeleton skeleton--row" />
        </div>
      )}

      {job && (
        <div className="detail-layout">
          <div className="detail-layout__main">
            <div className="card">
              <span className="card__eyebrow">Tiến trình xử lý</span>
              <JobProgress
                status={job.status}
                progressPercent={job.progress_percent}
                scriptMode={job.script_mode}
                reviewGate={job.review_gate}
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

              {RERUN_ALLOWED_STATUSES.has(job.status) && (
                <div
                  style={{
                    marginTop: "1.25rem",
                    display: "flex",
                    gap: "0.5rem",
                    alignItems: "center",
                    flexWrap: "wrap",
                  }}
                >
                  <span className="field__label" style={{ margin: 0 }}>
                    Chạy lại từ bước:
                  </span>
                  <select
                    className="input"
                    style={{ width: "auto" }}
                    value={rerunStep}
                    onChange={(e) => setRerunStep(e.target.value as RerunStep)}
                    disabled={rerunning}
                  >
                    {RERUN_STEPS.map((step) => (
                      <option key={step} value={step}>
                        {RERUN_STEP_LABELS[step]}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="btn btn--ghost"
                    onClick={() => handleRerun(rerunStep)}
                    disabled={rerunning}
                  >
                    {rerunning ? <span className="btn__spinner" /> : <IconRetry />}
                    {rerunning ? "Đang chạy lại..." : "Chạy lại"}
                  </button>
                </div>
              )}

              {RERUN_ALLOWED_STATUSES.has(job.status) && canChangeVoice && (
                <div style={{ marginTop: "1rem" }}>
                  <VoiceSelector
                    voices={voices}
                    selectedVoiceKey={selectedVoiceKey}
                    onChange={setSelectedVoiceKey}
                    disabled={rerunning}
                    label="Đổi giọng đọc khi chạy lại (tuỳ chọn)"
                  />
                </div>
              )}
            </div>

            {job.status === "failed" && (
              <Callout tone="error" title="Job thất bại">
                {job.error ?? "Không rõ nguyên nhân"}
              </Callout>
            )}

            {job.status === "awaiting_review" && (
              <ReviewGatePanel
                jobId={job.job_id}
                onApproved={handleReviewAdvanced}
                onDirtyChange={setReviewDirty}
              />
            )}

            {(activeWarnings.length > 0 || dynamicCaptionsFailed) && (
              <Callout tone="warning" title="Cảnh báo chất lượng">
                <ul>
                  {activeWarnings.map(([key]) => (
                    <li key={key}>{warningLabel(key, job)}</li>
                  ))}
                  {dynamicCaptionsFailed && (
                    <li>
                      Đã yêu cầu phụ đề động nhưng không burn được — video vẫn có giọng lồng tiếng, chỉ thiếu phụ đề.
                    </li>
                  )}
                </ul>
              </Callout>
            )}

            {/* Video Comparison with Dual-Sync Playback */}
            {job.status === "done" && job.output_video_url && (
              <div className="card">
                <span className="card__eyebrow">So sánh kết quả</span>
                <div className="card__title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <h2>Video Gốc vs Video Lồng tiếng</h2>
                </div>

                {job.source_video_url && (
                  <div className="dual-player-controls">
                    <button
                      type="button"
                      className={`btn ${isSyncPlaying ? "btn--primary" : "btn--ghost"}`}
                      onClick={toggleDualPlay}
                    >
                      {isSyncPlaying ? <IconPause size={16} /> : <IconPlay size={16} />}
                      <span>{isSyncPlaying ? "Tạm dừng phát song song" : "Phát đồng thời cả 2 video"}</span>
                    </button>

                    <div className="audio-focus-toggle">
                      <span className="field__hint" style={{ marginRight: "0.25rem" }}>Âm thanh:</span>
                      <button
                        type="button"
                        className={`filter-chip ${audioFocus === "output" ? "filter-chip--active" : ""}`}
                        onClick={() => updateAudioFocus("output")}
                      >
                        <IconVolume size={12} /> Tiếng Kết quả
                      </button>
                      <button
                        type="button"
                        className={`filter-chip ${audioFocus === "source" ? "filter-chip--active" : ""}`}
                        onClick={() => updateAudioFocus("source")}
                      >
                        <IconVolume size={12} /> Tiếng Gốc
                      </button>
                      <button
                        type="button"
                        className={`filter-chip ${audioFocus === "both" ? "filter-chip--active" : ""}`}
                        onClick={() => updateAudioFocus("both")}
                      >
                        Cả hai (50/50)
                      </button>
                    </div>
                  </div>
                )}

                <div className="compare-grid">
                  {job.source_video_url && (
                    <div className="compare-grid__item">
                      <div className="compare-grid__label">
                        <span>Video gốc (Đầu vào)</span>
                        {audioFocus === "output" && <span className="text-muted"><IconVolumeMute size={12} /> Mute</span>}
                      </div>
                      {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                      <video
                        ref={sourceVideoRef}
                        src={sourceUrl(job.job_id)}
                        controls
                        preload="metadata"
                        muted={audioFocus === "output"}
                      />
                    </div>
                  )}

                  <div className="compare-grid__item">
                    <div className="compare-grid__label">
                      <span>Video lồng tiếng (Kết quả)</span>
                      {audioFocus === "source" && <span className="text-muted"><IconVolumeMute size={12} /> Mute</span>}
                    </div>
                    {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                    <video
                      ref={outputVideoRef}
                      src={outputUrl(job.job_id)}
                      controls
                      preload="metadata"
                      muted={audioFocus === "source"}
                      onTimeUpdate={handleOutputTimeUpdate}
                      onPlay={() => setIsSyncPlaying(true)}
                      onPause={() => setIsSyncPlaying(false)}
                    />
                  </div>
                </div>

                <div className="result__actions" style={{ marginTop: "1rem" }}>
                  <a className="btn btn--primary" href={outputUrl(job.job_id)} download>
                    <IconDownload />
                    Tải video kết quả
                  </a>
                  <button
                    type="button"
                    className="btn btn--ghost"
                    onClick={handleShareAirDrop}
                    disabled={sharing}
                  >
                    {sharing ? <span className="btn__spinner" /> : <IconShare />}
                    {sharing ? "Đang chuẩn bị..." : "Chia sẻ qua AirDrop / Thiết bị"}
                  </button>
                </div>

                {shareError && (
                  <span className="field__hint" style={{ color: "var(--danger)", marginTop: "0.5rem" }}>
                    {shareError}
                  </span>
                )}
              </div>
            )}
          </div>

          <aside className="detail-layout__side">
            <div className="card">
              <span className="card__eyebrow">Thông tin kỹ thuật</span>
              <div className="detail-grid">
                <div className="detail-item">
                  <div className="detail-item__label">Nguồn</div>
                  <div className="detail-item__value">
                    {job.platform === "upload" ? (
                      job.source_url
                    ) : (
                      <a href={job.source_url} target="_blank" rel="noreferrer">
                        {job.source_url}
                      </a>
                    )}
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
                      {job.supervised && (
                        <span className="badge badge--tag">Quản lý pipeline</span>
                      )}
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
                  <div className="detail-item__label">Thời gian tạo</div>
                  <div className="detail-item__value">{absoluteTime(job.created_at)}</div>
                </div>
              </div>
            </div>
          </aside>
        </div>
      )}
    </AppShell>
  );
}
