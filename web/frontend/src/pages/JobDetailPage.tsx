import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ApiError,
  getJob,
  listVoices,
  outputUrl,
  previewVoice,
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
import { IconArrowLeft, IconDownload, IconPlay, IconRetry } from "../components/Icon";
import ReviewGatePanel from "../components/ReviewGatePanel";
import {
  absoluteTime,
  PLATFORM_LABELS,
  POLL_INTERVAL_MS,
  PROVIDER_LABELS,
  SCRIPT_MODE_LABELS,
  STAGES,
  TERMINAL_STATUSES,
} from "../lib/labels";

// 010-rerun-from-step: nhãn tiếng Việt cho từng bước, tái dùng đúng chữ đã có
// ở dải tiến trình (STAGES) để không lệch tên bước ở 2 chỗ khác nhau
const RERUN_STEP_LABELS: Record<RerunStep, string> = Object.fromEntries(
  STAGES.filter((s) => (RERUN_STEPS as readonly string[]).includes(s.key)).map((s) => [
    s.key,
    s.label,
  ]),
) as Record<RerunStep, string>;

// Job ở trạng thái này KHÔNG có thread nền nào đang xử lý — an toàn để quay
// lại một bước trước đó (khớp guard 409 phía backend)
const RERUN_ALLOWED_STATUSES = new Set(["done", "failed", "awaiting_review"]);

function voiceKey(v: Voice) {
  return `${v.provider}|${v.voice_id}`;
}

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
  const [rerunning, setRerunning] = useState(false);
  const [rerunStep, setRerunStep] = useState<RerunStep>("transcribing");
  // Đổi giọng đọc trước khi chạy lại — chỉ có ý nghĩa khi job có lồng tiếng
  // (translate/rewrite) và bước chạy lại còn đi qua synthesizing lại
  const [voices, setVoices] = useState<Voice[]>([]);
  const [selectedVoiceKey, setSelectedVoiceKey] = useState<string>("");
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const previewUrlRef = useRef<string | null>(null);
  const pollRef = useRef<number | null>(null);
  // 008: có thay đổi chưa lưu trong panel review — poll 3s sẽ setJob() và
  // remount panel, xoá mất nội dung người dùng đang gõ. Tạm dừng poll cho tới
  // khi lưu/phê duyệt xong.
  const [reviewDirty, setReviewDirty] = useState(false);

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

  // Chỉ tải danh sách giọng khi job có lồng tiếng (translate/rewrite) — job
  // "subtitle"/"download" không có khái niệm giọng đọc để đổi
  const isDubbingJob = job?.script_mode === "translate" || job?.script_mode === "rewrite";
  useEffect(() => {
    if (!isDubbingJob || voices.length > 0) return;
    listVoices()
      .then((res) => {
        setVoices(res.voices);
        // Mặc định chọn ĐÚNG giọng job đang dùng, để "chọn lại" bắt đầu từ vị
        // trí hiện tại thay vì luôn nhảy về giọng đầu danh sách
        const current = res.voices.find(
          (v) => v.provider === job?.tts_provider && v.voice_id === job?.voice_id,
        );
        setSelectedVoiceKey(voiceKey(current ?? res.voices[0]));
      })
      .catch(() => {
        // Không tải được danh sách giọng — không chặn trang, chỉ ẩn phần đổi giọng
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDubbingJob]);

  async function handlePreviewVoice() {
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

  // Nhóm giọng theo provider để danh sách dài vẫn dễ chọn (cùng cách làm HomePage)
  const voiceGroups = useMemo(() => {
    const groups = new Map<string, Voice[]>();
    for (const v of voices) {
      const list = groups.get(v.provider) ?? [];
      list.push(v);
      groups.set(v.provider, list);
    }
    return [...groups.entries()];
  }, [voices]);

  // Dừng/khởi động lại poll theo trạng thái "đang sửa dở" của panel review
  useEffect(() => {
    if (!jobId) return;
    if (reviewDirty) {
      stopPolling();
    } else if (job && !TERMINAL_STATUSES.has(job.status) && pollRef.current === null) {
      startPolling(jobId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reviewDirty, jobId, job?.status]);

  /** Sau khi phê duyệt/sinh lại: nạp lại ngay rồi theo dõi tiếp tiến trình. */
  const handleReviewAdvanced = useCallback(async () => {
    if (!jobId) return;
    setReviewDirty(false);
    try {
      const detail = await getJob(jobId);
      setJob(detail);
      if (!TERMINAL_STATUSES.has(detail.status)) startPolling(jobId);
    } catch {
      /* poll kế tiếp sẽ tự đồng bộ lại */
    }
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
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Thử lại thất bại");
    } finally {
      setRetrying(false);
    }
  }

  // Đổi giọng chỉ có tác dụng nếu bước chạy lại còn đi qua synthesizing —
  // "merging" không tổng hợp lại giọng đọc nên gửi kèm cũng vô nghĩa
  const canChangeVoice = isDubbingJob && rerunStep !== "merging";
  const selectedVoice = voices.find((v) => voiceKey(v) === selectedVoiceKey);
  const voiceChanged =
    !!selectedVoice &&
    (selectedVoice.provider !== job?.tts_provider || selectedVoice.voice_id !== job?.voice_id);

  async function handleRerun(step: RerunStep) {
    if (!jobId) return;
    const changingVoice = canChangeVoice && voiceChanged && selectedVoice;
    // Hành động PHÁ HUỶ — xoá artifact của bước này và mọi bước sau (kể cả
    // output.mp4 nếu chạy lại từ trước bước ghép video)
    const confirmMsg = changingVoice
      ? `Chạy lại từ bước "${RERUN_STEP_LABELS[step]}" với giọng đọc "${changingVoice.name}", sẽ XOÁ kết quả của bước này và mọi bước sau (kể cả video kết quả hiện tại nếu có). Tiếp tục?`
      : `Chạy lại từ bước "${RERUN_STEP_LABELS[step]}" sẽ XOÁ kết quả của bước này và mọi bước sau (kể cả video kết quả hiện tại nếu có). Tiếp tục?`;
    if (!window.confirm(confirmMsg)) {
      return;
    }
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
      const detail = await getJob(jobId);
      setJob(detail);
      startPolling(jobId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Chạy lại thất bại");
    } finally {
      setRerunning(false);
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

            {/* 010-rerun-from-step: quay lại một bước trước đó để thử lại,
                thay vì tạo job mới. Chỉ an toàn khi không có thread nền nào
                đang xử lý job (khớp guard 409 phía backend). */}
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

            {/* Đổi giọng đọc trước khi chạy lại — chỉ hiện khi job có lồng
                tiếng và bước chọn còn đi qua synthesizing */}
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
                    {voices.length === 0 && (
                      <option value="">Đang tải danh sách giọng...</option>
                    )}
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
                    onClick={handlePreviewVoice}
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
                    ? "Bấm \"Chạy lại\" ở trên để tổng hợp lại toàn bộ giọng đọc với giọng này."
                    : `Giọng hiện tại: ${selectedVoice?.name ?? job.voice_id ?? "mặc định"}.`}
                </span>
                {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                <audio ref={audioRef} hidden />
              </div>
            )}
          </div>

          {job.status === "failed" && (
            <Callout tone="error" title="Job thất bại">
              {job.error ?? "Không rõ nguyên nhân"}
            </Callout>
          )}

          {/* 008: chốt kiểm duyệt — job dừng chờ phê duyệt, không tự chạy tiếp */}
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
                <h2>So sánh đầu vào / kết quả</h2>
              </div>
              <div className="compare-grid">
                {job.source_video_url && (
                  <div className="compare-grid__item">
                    <div className="compare-grid__label">Đầu vào (video gốc)</div>
                    {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                    <video src={sourceUrl(job.job_id)} controls preload="metadata" />
                  </div>
                )}
                <div className="compare-grid__item">
                  <div className="compare-grid__label">Kết quả</div>
                  {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                  <video src={outputUrl(job.job_id)} controls preload="metadata" />
                </div>
              </div>
              <div className="result__actions">
                <a className="btn btn--primary" href={outputUrl(job.job_id)} download>
                  <IconDownload />
                  Tải video
                </a>
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
