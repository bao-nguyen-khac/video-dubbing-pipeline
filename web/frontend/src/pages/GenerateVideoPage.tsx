// pages/GenerateVideoPage.tsx — "Tạo video từ chủ đề" (010-topic-video-generation).
//
// US1 (MVP): nhập chủ đề văn bản, submit, poll trạng thái, tải video khi xong.
// US4: bật "Quản lý pipeline" dừng job ở chốt outline/scene để duyệt trước khi
// tốn chi phí tìm ảnh/TTS/render — tái dùng ReviewGatePanel đã có cho luồng dub.

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ApiError,
  GENERATE_RERUN_STEPS,
  generateOutputUrl,
  getGenerateJob,
  listVoices,
  previewVoice,
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
import { IconDownload, IconPlay, IconRetry } from "../components/Icon";
import { confirm } from "../lib/confirm";
import {
  GENERATE_STEP_LABELS,
  POLL_INTERVAL_MS,
  PROVIDER_LABELS,
  TERMINAL_STATUSES,
} from "../lib/labels";

function voiceKey(v: Voice) {
  return `${v.provider}|${v.voice_id}`;
}

// 010: rerun-from-step cho phép ở cả job "done" lẫn "failed" (khác /retry chỉ
// dành cho failed) — job không có thread nền nào đang xử lý ở 2 trạng thái này
const RERUN_ALLOWED_STATUSES = new Set(["done", "failed", "awaiting_review"]);

export default function GenerateVideoPage() {
  // Lịch sử job (JobListPage) trỏ tới job "generate" cũ qua ?job=<id> — mở
  // thẳng tiến trình/kết quả của job đó, không cần submit lại
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
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  // 008/010: có sửa dở ở chốt outline — tạm dừng poll để không mất bản đang gõ
  const [reviewDirty, setReviewDirty] = useState(false);
  const pollRef = useRef<number | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const previewUrlRef = useRef<string | null>(null);

  useEffect(() => {
    listVoices()
      .then((res) => {
        setVoices(res.voices);
        if (res.voices.length > 0) {
          setSelectedVoiceKey(voiceKey(res.voices[0]));
        }
      })
      .catch(() => {
        // Không chặn form nếu lấy danh sách giọng lỗi — vẫn dùng được job
        // với giọng mặc định
      });
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
        }
      } catch {
        stopPolling();
      }
    }, POLL_INTERVAL_MS);
  }

  useEffect(() => stopPolling, []);

  // Mở job "generate" đã có sẵn (từ ?job=<id>, VD link ở trang Lịch sử)
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

  // Dừng/khởi động lại poll theo trạng thái "đang sửa dở" của panel review
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
      /* poll kế tiếp sẽ tự đồng bộ lại */
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
      const detail = await getGenerateJob(job_id);
      setJob(detail);
      startPolling(job_id);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const runningId = err.body?.running_job_id ?? "?";
        setError(`Đang có job xử lý (job_id: ${runningId}), vui lòng chờ job đó xong`);
      } else {
        setError(err instanceof ApiError ? err.message : "Có lỗi xảy ra khi submit job");
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
      if (previewUrlRef.current) {
        URL.revokeObjectURL(previewUrlRef.current);
      }
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
    if (!job) return;
    setError(null);
    setRetrying(true);
    try {
      const { job_id } = await retryGenerateJob(job.job_id);
      const detail = await getGenerateJob(job_id);
      setJob(detail);
      startPolling(job_id);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const runningId = err.body?.running_job_id ?? "?";
        setError(`Đang có job xử lý (job_id: ${runningId}), vui lòng chờ job đó xong`);
      } else {
        setError(err instanceof ApiError ? err.message : "Thử lại thất bại");
      }
    } finally {
      setRetrying(false);
    }
  }

  // Đổi giọng chỉ có tác dụng nếu bước chạy lại còn đi qua synthesizing —
  // "rendering" không tổng hợp lại giọng đọc nên gửi kèm cũng vô nghĩa
  const canChangeVoice = rerunStep !== "rendering";
  const selectedVoice = voices.find((v) => voiceKey(v) === selectedVoiceKey);
  const voiceChanged =
    !!selectedVoice &&
    (selectedVoice.provider !== job?.tts_provider || selectedVoice.voice_id !== job?.voice_id);

  async function handleRerun(step: GenerateRerunStep) {
    if (!job) return;
    const changingVoice = canChangeVoice && voiceChanged && selectedVoice;
    const confirmMsg = changingVoice
      ? `Chạy lại từ bước "${GENERATE_STEP_LABELS[step]}" với giọng đọc "${changingVoice.name}", sẽ XOÁ kết quả của bước này và mọi bước sau (kể cả video kết quả hiện tại nếu có).`
      : `Chạy lại từ bước "${GENERATE_STEP_LABELS[step]}" sẽ XOÁ kết quả của bước này và mọi bước sau (kể cả video kết quả hiện tại nếu có).`;
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
      const detail = await getGenerateJob(job.job_id);
      setJob(detail);
      startPolling(job.job_id);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const runningId = err.body?.running_job_id ?? "?";
        setError(`Đang có job xử lý (job_id: ${runningId}), vui lòng chờ job đó xong`);
      } else {
        setError(err instanceof ApiError ? err.message : "Chạy lại thất bại");
      }
    } finally {
      setRerunning(false);
    }
  }

  const isBusy = job !== null && !TERMINAL_STATUSES.has(job.status);
  const locked = isBusy || submitting;

  // Nhóm giọng theo provider để danh sách dài vẫn dễ chọn
  const voiceGroups = useMemo(() => {
    const groups = new Map<string, Voice[]>();
    for (const v of voices) {
      const list = groups.get(v.provider) ?? [];
      list.push(v);
      groups.set(v.provider, list);
    }
    return [...groups.entries()];
  }, [voices]);

  return (
    <AppShell narrow>
      <div className="page-head">
        <h1>{viewJobId ? "Chi tiết video từ chủ đề" : "Tạo video từ chủ đề"}</h1>
        {viewJobId ? (
          <p className="page-head__lead">
            <Link to="/generate">← Tạo video mới</Link>
          </p>
        ) : (
          <p className="page-head__lead">
            Nhập 1 chủ đề — hệ thống sẽ tự viết kịch bản, tra cứu web khi cần, tìm ảnh
            minh hoạ, đọc giọng và dựng thành video dọc hoàn chỉnh.
          </p>
        )}
      </div>

      {!viewJobId && (
        <form onSubmit={handleSubmit}>
          {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
          <audio ref={audioRef} hidden />

          <div className="card">
            <span className="card__eyebrow">Chủ đề</span>
            <div className="field">
              <label className="field__label" htmlFor="topic">
                Chủ đề video
              </label>
              <textarea
                id="topic"
                className="input"
                rows={3}
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder="VD: tổng quan về các loại tiền tệ trong lịch sử"
                disabled={locked}
                required
                style={{ resize: "vertical", fontFamily: "inherit" }}
              />
              <span className="field__hint">
                Video dọc (9:16), khoảng 1-5 phút, có giọng đọc và ảnh minh hoạ tự động.
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
                  <span className="switch__name">Quản lý pipeline</span>
                  <span className="switch__desc">
                    Dừng lại cho tôi duyệt outline/scene trước khi tìm ảnh và đọc giọng
                  </span>
                </span>
              </label>
            </div>
          </div>

          <div className="card">
            <span className="card__eyebrow">Giọng đọc</span>
            <div className="field">
              <label className="field__label" htmlFor="voice-select">
                Chọn giọng
              </label>
              <div className="voice-picker">
                <select
                  id="voice-select"
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
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={handlePreview}
                  disabled={previewing || !selectedVoiceKey}
                >
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
                {submitting ? "Đang gửi..." : isBusy ? "Đang xử lý job hiện tại" : "Tạo video"}
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
            <h2>Tiến trình</h2>
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

          {/* 010: quay lại 1 bước trước đó để thử lại — cho phép ở cả job
              done lẫn failed, khác nút "Thử lại" ở trên chỉ dành cho failed */}
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

          {/* Đổi giọng đọc trước khi chạy lại — chỉ hiện khi bước chọn còn đi
              qua synthesizing */}
          {RERUN_ALLOWED_STATUSES.has(job.status) && canChangeVoice && (
            <div className="field" style={{ marginTop: "0.75rem" }}>
              <label className="field__label" htmlFor="rerun-voice-select">
                Đổi giọng đọc (tuỳ chọn)
              </label>
              <div className="voice-picker">
                <select
                  id="rerun-voice-select"
                  className="select"
                  value={selectedVoiceKey}
                  onChange={(e) => setSelectedVoiceKey(e.target.value)}
                  disabled={rerunning || voices.length === 0}
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
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={handlePreview}
                  disabled={previewing || !selectedVoiceKey}
                >
                  {previewing ? <span className="btn__spinner" /> : <IconPlay />}
                  {previewing ? "Đang tải" : "Nghe thử"}
                </button>
              </div>
              {previewError && (
                <span className="field__hint" style={{ color: "var(--danger)" }}>
                  {previewError}
                </span>
              )}
              <span className="field__hint">
                {voiceChanged
                  ? 'Bấm "Chạy lại" ở trên để tổng hợp lại toàn bộ giọng đọc với giọng này.'
                  : `Giọng hiện tại: ${selectedVoice?.name ?? job.voice_id ?? "mặc định"}.`}
              </span>
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

      {/* 008: chốt kiểm duyệt — job dừng chờ phê duyệt, không tự chạy tiếp */}
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
