// pages/GenerateVideoPage.tsx — Studio: Tạo video từ chủ đề (Topic-to-Video)
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ApiError,
  GENERATE_RERUN_STEPS,
  generateOutputUrl,
  getGenerateJob,
  listVoices,
  rerunGenerateFromStep,
  retryGenerateJob,
  submitGenerateJob,
  type GenerateJobDetail,
  type GenerateRerunStep,
  type Voice,
} from "../api/client";
import AppShell from "../components/AppShell";
import Callout from "../components/Callout";
import ReviewGatePanel from "../components/ReviewGatePanel";
import StatusBadge from "../components/StatusBadge";
import StudioTabs from "../components/StudioTabs";
import VoiceSelector from "../components/VoiceSelector";
import { IconDownload, IconRetry, IconSparkles } from "../components/Icon";
import { confirm } from "../lib/confirm";
import {
  GENERATE_STEP_LABELS,
  POLL_INTERVAL_MS,
  TERMINAL_STATUSES,
  voiceKey,
} from "../lib/labels";
import { useToast } from "../context/ToastContext";

const RERUN_ALLOWED_STATUSES = new Set(["done", "failed", "awaiting_review"]);

export default function GenerateVideoPage() {
  const [searchParams] = useSearchParams();
  const viewJobId = searchParams.get("job");

  const [topic, setTopic] = useState("");
  const [supervised, setSupervised] = useState(false);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [selectedVoiceKey, setSelectedVoiceKey] = useState<string>("");
  const [job, setJob] = useState<GenerateJobDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [rerunStep, setRerunStep] = useState<GenerateRerunStep>(GENERATE_RERUN_STEPS[0]);
  const [rerunning, setRerunning] = useState(false);
  const [loadingExisting, setLoadingExisting] = useState(false);
  const [reviewDirty, setReviewDirty] = useState(false);
  const pollRef = useRef<number | null>(null);
  const toast = useToast();

  useEffect(() => {
    listVoices()
      .then((res) => {
        setVoices(res.voices);
        if (res.voices.length > 0) {
          setSelectedVoiceKey(voiceKey(res.voices[0]));
        }
      })
      .catch(() => {});
  }, []);

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
        const detail = await getGenerateJob(jobId);
        setJob(detail);
        if (TERMINAL_STATUSES.has(detail.status)) {
          stopPolling();
          if (detail.status === "done") {
            toast.success("Video từ chủ đề đã hoàn tất!");
          }
        }
      } catch {
        stopPolling();
      }
    }, POLL_INTERVAL_MS);
  }

  useEffect(() => stopPolling, []);

  useEffect(() => {
    if (!viewJobId) return;
    setLoadingExisting(true);
    setError(null);
    getGenerateJob(viewJobId)
      .then((detail) => {
        setJob(detail);
        if (!TERMINAL_STATUSES.has(detail.status)) startPolling(viewJobId);
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Không tải được job");
      })
      .finally(() => setLoadingExisting(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewJobId]);

  useEffect(() => {
    if (!job) return;
    if (reviewDirty) {
      stopPolling();
    } else if (!TERMINAL_STATUSES.has(job.status) && pollRef.current === null) {
      startPolling(job.job_id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reviewDirty, job?.job_id, job?.status]);

  async function handleReviewAdvanced() {
    if (!job) return;
    setReviewDirty(false);
    try {
      const detail = await getGenerateJob(job.job_id);
      setJob(detail);
      if (!TERMINAL_STATUSES.has(detail.status)) startPolling(job.job_id);
    } catch {
      /* poll kế tiếp sẽ tự đồng bộ */
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const selectedVoice = voices.find((v) => voiceKey(v) === selectedVoiceKey);
      const { job_id } = await submitGenerateJob(
        topic,
        supervised,
        selectedVoice?.provider,
        selectedVoice?.voice_id,
      );
      toast.success("Đã gửi yêu cầu tạo video từ chủ đề!");
      const detail = await getGenerateJob(job_id);
      setJob(detail);
      startPolling(job_id);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const runningId = err.body?.running_job_id ?? "?";
        setError(`Đang có job xử lý (job_id: ${runningId}), vui lòng chờ job đó xong.`);
      } else {
        setError(err instanceof ApiError ? err.message : "Có lỗi xảy ra khi submit job");
      }
      toast.error("Gửi job thất bại");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRetry() {
    if (!job) return;
    setError(null);
    setRetrying(true);
    try {
      const { job_id } = await retryGenerateJob(job.job_id);
      const detail = await getGenerateJob(job_id);
      setJob(detail);
      startPolling(job_id);
      toast.info("Đang thử lại job...");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Thử lại thất bại");
    } finally {
      setRetrying(false);
    }
  }

  const canChangeVoice = rerunStep !== "rendering";
  const selectedVoice = voices.find((v) => voiceKey(v) === selectedVoiceKey);
  const voiceChanged =
    !!selectedVoice &&
    (selectedVoice.provider !== job?.tts_provider || selectedVoice.voice_id !== job?.voice_id);

  async function handleRerun(step: GenerateRerunStep) {
    if (!job) return;
    const changingVoice = canChangeVoice && voiceChanged && selectedVoice;
    const confirmMsg = changingVoice
      ? `Chạy lại từ bước "${GENERATE_STEP_LABELS[step]}" với giọng đọc "${changingVoice.name}", sẽ XOÁ kết quả của bước này và các bước sau.`
      : `Chạy lại từ bước "${GENERATE_STEP_LABELS[step]}" sẽ XOÁ kết quả của bước này và các bước sau.`;
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
      await rerunGenerateFromStep(
        job.job_id,
        step,
        changingVoice
          ? { ttsProvider: changingVoice.provider, voiceId: changingVoice.voice_id }
          : undefined,
      );
      toast.info(`Đang chạy lại từ bước "${GENERATE_STEP_LABELS[step]}"...`);
      const detail = await getGenerateJob(job.job_id);
      setJob(detail);
      startPolling(job.job_id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Chạy lại thất bại");
    } finally {
      setRerunning(false);
    }
  }

  const isBusy = job !== null && !TERMINAL_STATUSES.has(job.status);
  const locked = isBusy || submitting;

  return (
    <AppShell narrow>
      <div className="page-head">
        <h1>{viewJobId ? "Chi tiết video từ chủ đề" : "Tạo video từ chủ đề"}</h1>
        {viewJobId ? (
          <p className="page-head__lead">
            <Link to="/generate">← Tạo video chủ đề mới</Link>
          </p>
        ) : (
          <p className="page-head__lead">
            Nhập 1 chủ đề bất kỳ — AI sẽ tự viết kịch bản, tra cứu thông tin, tìm ảnh minh hoạ, đọc giọng và dựng thành video dọc 9:16.
          </p>
        )}
      </div>

      {!viewJobId && <StudioTabs />}

      {!viewJobId && (
        <form onSubmit={handleSubmit}>
          <div className="card">
            <span className="card__eyebrow">Chủ đề &amp; Ý tưởng</span>
            <div className="field">
              <label className="field__label" htmlFor="topic">
                Chủ đề video (Topic)
              </label>
              <textarea
                id="topic"
                className="input"
                rows={3}
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder="VD: Tổng quan về nguồn gốc các loại tiền tệ trong lịch sử loài người"
                disabled={locked}
                required
                style={{ resize: "vertical", fontFamily: "inherit" }}
              />
              <span className="field__hint">
                Video dọc 9:16 (khoảng 1-3 phút), tối ưu cho TikTok / Shorts / Reels.
              </span>
            </div>

            <div className="field">
              <label className="switch">
                <input
                  type="checkbox"
                  checked={supervised}
                  onChange={(e) => setSupervised(e.target.checked)}
                  disabled={locked}
                />
                <span className="switch__track" />
                <span className="switch__text">
                  <span className="switch__name">Quản lý pipeline (Human-in-the-loop)</span>
                  <span className="switch__desc">
                    Tạm dừng cho bạn duyệt outline/scene trước khi AI tìm ảnh và đọc giọng
                  </span>
                </span>
              </label>
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
                    <span>Đang gửi...</span>
                  </>
                ) : isBusy ? (
                  <span>Đang xử lý job hiện tại</span>
                ) : (
                  <>
                    <IconSparkles size={16} />
                    <span>Tạo video AI</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </form>
      )}

      {loadingExisting && !job && (
        <div className="card">
          <div className="skeleton skeleton--row" />
        </div>
      )}

      {error && (
        <Callout tone="error" title="Không gửi được job">
          {error}
        </Callout>
      )}

      {job && (
        <div className="card">
          <div className="card__title">
            <h2>Tiến trình tạo video</h2>
          </div>
          {viewJobId && <p className="page-head__lead">{job.topic}</p>}

          <div className="progress">
            <div className="progress__head">
              <StatusBadge status={job.status} reviewGate={job.review_gate} />
              <span className="progress__pct">{job.progress_percent}%</span>
            </div>
            <div
              className="progress__bar"
              role="progressbar"
              aria-valuenow={job.progress_percent}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div
                className={`progress__fill${job.status === "done" ? " progress__fill--done" : ""}${
                  job.status === "failed" ? " progress__fill--failed" : ""
                }`}
                style={{ width: `${job.progress_percent}%` }}
              />
            </div>
          </div>

          {job.status === "failed" && (
            <div style={{ marginTop: "1rem" }}>
              <Callout tone="error" title="Job thất bại">
                {job.error ?? "Không rõ nguyên nhân"}
              </Callout>
              {job.can_retry && (
                <button
                  type="button"
                  className="btn btn--primary"
                  style={{ marginTop: "0.75rem" }}
                  onClick={handleRetry}
                  disabled={retrying}
                >
                  {retrying && <span className="btn__spinner" />}
                  {retrying ? "Đang thử lại..." : "Thử lại"}
                </button>
              )}
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
                onChange={(e) => setRerunStep(e.target.value as GenerateRerunStep)}
                disabled={rerunning}
              >
                {GENERATE_RERUN_STEPS.map((step) => (
                  <option key={step} value={step}>
                    {GENERATE_STEP_LABELS[step]}
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

          {job.status === "done" && job.output_video_url && (
            <div className="result" style={{ marginTop: "1.25rem" }}>
              {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
              <video src={generateOutputUrl(job.job_id)} controls preload="metadata" />
              <div className="result__actions">
                <a className="btn btn--primary" href={generateOutputUrl(job.job_id)} download>
                  <IconDownload />
                  Tải video
                </a>
                <Link className="btn btn--ghost" to="/jobs">
                  Xem lịch sử job
                </Link>
              </div>
            </div>
          )}
        </div>
      )}

      {job && job.status === "awaiting_review" && (
        <ReviewGatePanel
          jobId={job.job_id}
          onApproved={handleReviewAdvanced}
          onDirtyChange={setReviewDirty}
        />
      )}
    </AppShell>
  );
}
