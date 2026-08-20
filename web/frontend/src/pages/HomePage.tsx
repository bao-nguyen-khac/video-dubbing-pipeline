// pages/HomePage.tsx — Studio: Lồng tiếng & Tái tạo video
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ApiError,
  getJob,
  listVoices,
  outputUrl,
  submitJob,
  submitJobUpload,
  type JobDetail,
  type Voice,
} from "../api/client";
import AppShell from "../components/AppShell";
import Callout from "../components/Callout";
import JobProgress from "../components/JobProgress";
import VideoDropzone from "../components/VideoDropzone";
import VoiceSelector from "../components/VoiceSelector";
import { IconDownload, IconSparkles } from "../components/Icon";
import {
  POLL_INTERVAL_MS,
  SCRIPT_MODES,
  TERMINAL_STATUSES,
  voiceKey,
  type ScriptMode,
} from "../lib/labels";
import { useToast } from "../context/ToastContext";

export default function HomePage() {
  const [searchParams] = useSearchParams();
  const [url, setUrl] = useState(() => searchParams.get("url") ?? "");
  const [sourceMode, setSourceMode] = useState<"url" | "file">("url");
  const [file, setFile] = useState<File | null>(null);
  const [scriptMode, setScriptMode] = useState<ScriptMode>("translate");
  const [dynamicCaptions, setDynamicCaptions] = useState(false);
  const [userPrompt, setUserPrompt] = useState("");
  const [supervised, setSupervised] = useState(false);
  const [hardsubBlurEnabled, setHardsubBlurEnabled] = useState(false);
  const [hardsubNoRanges, setHardsubNoRanges] = useState("");
  const [keepRanges, setKeepRanges] = useState("");
  const [voices, setVoices] = useState<Voice[]>([]);
  const [selectedVoiceKey, setSelectedVoiceKey] = useState<string>("");
  const [job, setJob] = useState<JobDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
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

  useEffect(() => {
    if (!supervised && hardsubBlurEnabled) {
      setHardsubBlurEnabled(false);
    }
  }, [supervised, hardsubBlurEnabled]);

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
        const detail = await getJob(jobId);
        setJob(detail);
        if (TERMINAL_STATUSES.has(detail.status)) {
          stopPolling();
          if (detail.status === "done") {
            toast.success("Job đã hoàn thành! Video đã sẵn sàng.");
            if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "granted") {
              new Notification("Video Dubbing Studio", {
                body: "Video của bạn đã được xử lý xong!",
              });
            }
          } else if (detail.status === "failed") {
            toast.error("Job xử lý thất bại!");
          }
        } else if (detail.status === "awaiting_review") {
          if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "granted") {
            new Notification("Video Dubbing Studio", {
              body: `Job đang chờ bạn phê duyệt tại ${detail.review_gate ?? "chốt kiểm duyệt"}!`,
            });
          }
        }
      } catch {
        stopPolling();
      }
    }, POLL_INTERVAL_MS);
  }

  useEffect(() => stopPolling, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (sourceMode === "file" && !file) {
      setError("Chưa chọn file video để tải lên");
      toast.error("Chưa chọn file video để tải lên");
      return;
    }

    setSubmitting(true);
    try {
      const selectedVoice = voices.find((v) => voiceKey(v) === selectedVoiceKey);
      const hasVoice =
        scriptMode === "translate" || scriptMode === "rewrite" || scriptMode === "visual";
      const dubbing = scriptMode === "translate" || scriptMode === "rewrite";
      const hasSubtitleDisplay = scriptMode === "subtitle" || (dubbing && dynamicCaptions);
      const submitArgs = [
        scriptMode,
        hasVoice && dynamicCaptions,
        hasVoice ? selectedVoice?.provider : undefined,
        hasVoice ? selectedVoice?.voice_id : undefined,
        hasVoice && keepRanges.trim() ? keepRanges.trim() : undefined,
        scriptMode !== "download" && supervised,
        hasSubtitleDisplay && hardsubBlurEnabled,
        hasSubtitleDisplay && hardsubBlurEnabled && hardsubNoRanges.trim()
          ? hardsubNoRanges.trim()
          : undefined,
        scriptMode === "visual" && userPrompt.trim() ? userPrompt.trim() : undefined,
      ] as const;

      const { job_id } =
        sourceMode === "file"
          ? await submitJobUpload(file as File, ...submitArgs)
          : await submitJob(url, ...submitArgs);

      toast.success("Đã gửi job thành công, đang khởi chạy pipeline...");
      const detail = await getJob(job_id);
      setJob(detail);
      startPolling(job_id);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const runningId = err.body?.running_job_id ?? "?";
        setError(`Đang có job xử lý (job_id: ${runningId}), vui lòng chờ job đó xong.`);
      } else {
        setError(err instanceof ApiError ? err.message : "Có lỗi xảy ra khi submit job");
      }
      toast.error("Không gửi được job");
    } finally {
      setSubmitting(false);
    }
  }

  const isBusy = job !== null && !TERMINAL_STATUSES.has(job.status);
  const isDubbing = scriptMode === "translate" || scriptMode === "rewrite";
  const hasVoice = isDubbing || scriptMode === "visual";
  const locked = isBusy || submitting;
  const hasSubtitleDisplay = scriptMode === "subtitle" || (isDubbing && dynamicCaptions);
  const showAdvancedCard = scriptMode !== "download";

  return (
    <AppShell>
      <div className="page-head">
        <h1>Lồng tiếng &amp; Tái tạo Video</h1>
        <p className="page-head__lead">
          Tải video, tách lời, viết kịch bản tiếng Việt bằng AI và lồng tiếng khớp nhịp với bản gốc.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="home-layout">
        <div className={`card${hasVoice ? "" : " home-layout__full"}`}>
          <span className="card__eyebrow">Nguồn video</span>

          <div className="field">
            <div className="mode-grid">
              <label className="mode-option">
                <input
                  type="radio"
                  name="source-mode"
                  checked={sourceMode === "url"}
                  onChange={() => setSourceMode("url")}
                  disabled={locked}
                />
                <span className="mode-option__body">
                  <span className="mode-option__name">🔗 Dán link trực tuyến</span>
                  <span className="mode-option__desc">TikTok, Douyin (xoá watermark) hoặc YouTube</span>
                </span>
              </label>

              <label className="mode-option">
                <input
                  type="radio"
                  name="source-mode"
                  checked={sourceMode === "file"}
                  onChange={() => setSourceMode("file")}
                  disabled={locked}
                />
                <span className="mode-option__body">
                  <span className="mode-option__name">📁 Tải file lên</span>
                  <span className="mode-option__desc">File từ máy (Google Flow, Veo, ElevenLabs...)</span>
                </span>
              </label>
            </div>
          </div>

          {sourceMode === "url" ? (
            <div className="field">
              <label className="field__label" htmlFor="video-url">
                URL video nguồn
              </label>
              <input
                id="video-url"
                className="input"
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://www.tiktok.com/@user/video/... hoặc Douyin, YouTube"
                disabled={locked}
                required
              />
              <span className="field__hint">Hệ thống tự động cào video chuẩn HD không watermark.</span>
            </div>
          ) : (
            <div className="field">
              <label className="field__label">File video từ máy tính</label>
              <VideoDropzone
                file={file}
                onFileChange={setFile}
                disabled={locked}
                hint="Kéo thả hoặc bấm để chọn video MP4, MOV, WebM"
              />
            </div>
          )}

          <div className="field">
            <span className="field__label">Chế độ xử lý</span>
            <div className="mode-grid">
              {SCRIPT_MODES.map((mode) => (
                <label key={mode.value} className="mode-option">
                  <input
                    type="radio"
                    name="script-mode"
                    value={mode.value}
                    checked={scriptMode === mode.value}
                    onChange={() => setScriptMode(mode.value)}
                    disabled={locked}
                  />
                  <span className="mode-option__body">
                    <span className="mode-option__name">{mode.name}</span>
                    <span className="mode-option__desc">{mode.desc}</span>
                  </span>
                </label>
              ))}
            </div>
          </div>

          {scriptMode === "visual" && (
            <div className="field">
              <label className="field__label" htmlFor="user-prompt">
                Prompt định hướng cho AI (tuỳ chọn)
              </label>
              <textarea
                id="user-prompt"
                className="input"
                rows={3}
                value={userPrompt}
                onChange={(e) => setUserPrompt(e.target.value)}
                placeholder="VD: nhấn mạnh tính năng chống nước, giọng điệu hài hước, phong cách review Gen Z"
                disabled={locked}
                style={{ resize: "vertical", fontFamily: "inherit" }}
              />
            </div>
          )}
        </div>

        {hasVoice && (
          <div className="card">
            <span className="card__eyebrow">Giọng đọc &amp; Phụ đề</span>
            <VoiceSelector
              voices={voices}
              selectedVoiceKey={selectedVoiceKey}
              onChange={setSelectedVoiceKey}
              disabled={locked}
            />

            <div className="field" style={{ marginTop: "1rem" }}>
              <label className="switch">
                <input
                  type="checkbox"
                  checked={dynamicCaptions}
                  onChange={(e) => setDynamicCaptions(e.target.checked)}
                  disabled={locked}
                />
                <span className="switch__track" />
                <span className="switch__text">
                  <span className="switch__name">Phụ đề động (Word-level Captions)</span>
                  <span className="switch__desc">
                    Hiệu ứng chữ chạy khớp từng từ theo nhịp giọng đọc
                  </span>
                </span>
              </label>
            </div>
          </div>
        )}

        {showAdvancedCard && (
          <div className="card home-layout__full">
            <span className="card__eyebrow">Tuỳ chọn giám sát &amp; Nâng cao</span>
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
                    Tạm dừng pipeline sau bước tách lời và sinh kịch bản để bạn kiểm duyệt &amp; đối chiếu video trước khi render
                  </span>
                </span>
              </label>
            </div>

            {hasSubtitleDisplay && supervised && (
              <div className="field">
                <label className="switch">
                  <input
                    type="checkbox"
                    checked={hardsubBlurEnabled}
                    onChange={(e) => setHardsubBlurEnabled(e.target.checked)}
                    disabled={locked}
                  />
                  <span className="switch__track" />
                  <span className="switch__text">
                    <span className="switch__name">Làm mờ phụ đề gốc (Hardsub Mask)</span>
                    <span className="switch__desc">
                      Khoanh vùng che phụ đề ngoại ngữ có sẵn trên video và chèn phụ đề tiếng Việt đè lên
                    </span>
                  </span>
                </label>
              </div>
            )}

            {hasSubtitleDisplay && !supervised && (
              <p className="field__hint">
                💡 Bật &quot;Quản lý pipeline&quot; để dùng tính năng làm mờ phụ đề gốc (cần chốt lời thoại để bạn tự khoanh vùng).
              </p>
            )}

            {hasSubtitleDisplay && hardsubBlurEnabled && (
              <div className="field">
                <label className="field__label" htmlFor="hardsub-no-ranges">
                  Đoạn không có phụ đề gốc (tuỳ chọn)
                </label>
                <input
                  id="hardsub-no-ranges"
                  type="text"
                  className="input"
                  placeholder="vd: 0:15-0:30, 1:05-end"
                  value={hardsubNoRanges}
                  onChange={(e) => setHardsubNoRanges(e.target.value)}
                  disabled={locked}
                />
              </div>
            )}

            {isDubbing && (
              <div className="field">
                <label className="field__label" htmlFor="keep-ranges">
                  Giữ nguyên âm thanh gốc (tuỳ chọn)
                </label>
                <input
                  id="keep-ranges"
                  type="text"
                  className="input"
                  placeholder="vd: 0:15-0:30, 1:05-end"
                  value={keepRanges}
                  onChange={(e) => setKeepRanges(e.target.value)}
                  disabled={locked}
                />
              </div>
            )}
          </div>
        )}

        <div className="home-layout__full home-submit">
          <button type="submit" className="btn btn--primary btn--block" disabled={locked}>
            {submitting ? (
              <>
                <span className="btn__spinner" />
                <span>Đang gửi job...</span>
              </>
            ) : isBusy ? (
              <span>Đang xử lý job hiện tại</span>
            ) : (
              <>
                <IconSparkles size={16} />
                <span>Khởi chạy Pipeline</span>
              </>
            )}
          </button>
        </div>
      </form>

      {error && (
        <Callout tone="error" title="Không gửi được job">
          {error}
        </Callout>
      )}

      {job && (
        <div className="card">
          <div className="card__title">
            <h2>Tiến trình xử lý</h2>
            <Link
              to={`/jobs/${job.job_id}`}
              style={{ marginLeft: "auto", fontSize: "0.85rem" }}
            >
              Xem chi tiết →
            </Link>
          </div>

          <JobProgress
            status={job.status}
            progressPercent={job.progress_percent}
            scriptMode={job.script_mode}
            reviewGate={job.review_gate}
          />

          {job.status === "failed" && (
            <div style={{ marginTop: "1rem" }}>
              <Callout tone="error" title="Job thất bại">
                {job.error ?? "Không rõ nguyên nhân"}
              </Callout>
            </div>
          )}

          {job.status === "done" && job.output_video_url && (
            <div className="result" style={{ marginTop: "1.25rem" }}>
              {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
              <video src={outputUrl(job.job_id)} controls preload="metadata" />
              <div className="result__actions">
                <a className="btn btn--primary" href={outputUrl(job.job_id)} download>
                  <IconDownload />
                  Tải video kết quả
                </a>
                <Link className="btn btn--ghost" to={`/jobs/${job.job_id}`}>
                  Xem chi tiết &amp; So sánh
                </Link>
              </div>
            </div>
          )}
        </div>
      )}
    </AppShell>
  );
}
