import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ApiError,
  getJob,
  listVoices,
  outputUrl,
  previewVoice,
  submitJob,
  type JobDetail,
  type Voice,
} from "../api/client";
import AppShell from "../components/AppShell";
import Callout from "../components/Callout";
import JobProgress from "../components/JobProgress";
import { IconDownload, IconPlay } from "../components/Icon";
import {
  POLL_INTERVAL_MS,
  PROVIDER_LABELS,
  SCRIPT_MODES,
  TERMINAL_STATUSES,
  type ScriptMode,
} from "../lib/labels";

function voiceKey(v: Voice) {
  return `${v.provider}|${v.voice_id}`;
}

export default function HomePage() {
  const [searchParams] = useSearchParams();
  // "Dùng lại" từ trang Video đã tải điền sẵn link qua ?url= (job mới sẽ clone
  // file có sẵn thay vì tải lại).
  const [url, setUrl] = useState(() => searchParams.get("url") ?? "");
  const [scriptMode, setScriptMode] = useState<ScriptMode>("translate");
  const [dynamicCaptions, setDynamicCaptions] = useState(false);
  const [keepRanges, setKeepRanges] = useState("");
  const [voices, setVoices] = useState<Voice[]>([]);
  const [selectedVoiceKey, setSelectedVoiceKey] = useState<string>("");
  const [job, setJob] = useState<JobDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
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
        // với giọng mặc định (FR-003 áp dụng tinh thần tương tự)
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
        const detail = await getJob(jobId);
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

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const selectedVoice = voices.find((v) => voiceKey(v) === selectedVoiceKey);
      const dubbing = scriptMode === "translate" || scriptMode === "rewrite";
      const { job_id } = await submitJob(
        url,
        scriptMode,
        dubbing && dynamicCaptions,
        dubbing ? selectedVoice?.provider : undefined,
        dubbing ? selectedVoice?.voice_id : undefined,
        dubbing && keepRanges.trim() ? keepRanges.trim() : undefined,
      );
      const detail = await getJob(job_id);
      setJob(detail);
      startPolling(job_id);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const runningId = err.body?.running_job_id ?? "?";
        setError(`Đang có job xử lý (job_id: ${runningId}), vui lòng chờ job đó xong (FR-009)`);
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
      // Dọn URL cũ trước khi tạo URL mới, tránh rò rỉ bộ nhớ khi nghe thử
      // nhiều giọng liên tiếp (Acceptance Scenario 3, US2)
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

  const isBusy = job !== null && !TERMINAL_STATUSES.has(job.status);
  const isDubbing = scriptMode === "translate" || scriptMode === "rewrite";
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
        <h1>Tạo job mới</h1>
        <p className="page-head__lead">
          Dán link TikTok, Douyin hoặc YouTube — hệ thống sẽ tải video, tách lời, viết
          kịch bản tiếng Việt và lồng tiếng khớp nhịp ngắt nghỉ của bản gốc.
        </p>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="card">
          <div className="field">
            <label className="field__label" htmlFor="video-url">
              URL video
            </label>
            <input
              id="video-url"
              className="input"
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://www.tiktok.com/@user/video/..."
              disabled={locked}
              required
            />
            <span className="field__hint">Hỗ trợ TikTok, Douyin (không watermark) và YouTube.</span>
          </div>

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

          {isDubbing && (
            <div className="field">
              <label className="field__label" htmlFor="voice-select">
                Giọng đọc
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
          )}

          {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
          <audio ref={audioRef} hidden />

          {isDubbing && (
            <div className="field">
              <label className="switch">
                <input
                  type="checkbox"
                  checked={dynamicCaptions}
                  onChange={(e) => setDynamicCaptions(e.target.checked)}
                  disabled={locked}
                />
                <span className="switch__track" />
                <span className="switch__text">
                  <span className="switch__name">Phụ đề động</span>
                  <span className="switch__desc">
                    Chữ chạy khớp nhịp giọng đọc, chính xác với cả 3 provider
                  </span>
                </span>
              </label>
            </div>
          )}

          {isDubbing && (
            <div className="field">
              <label className="field__label" htmlFor="keep-ranges">
                Giữ nguyên audio gốc (tuỳ chọn)
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
              <span className="field__hint">
                Khoảng thời gian giữ nguyên nhạc/tiếng hát gốc, KHÔNG lồng tiếng đè.
                Nhiều khoảng ngăn bằng dấu phẩy; dùng "end" cho tới hết video.
              </span>
            </div>
          )}

          <div className="field">
            <button type="submit" className="btn btn--primary btn--block" disabled={locked}>
              {submitting && <span className="btn__spinner" />}
              {submitting ? "Đang gửi..." : isBusy ? "Đang xử lý job hiện tại" : "Chạy pipeline"}
            </button>
          </div>
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
            <h2>Tiến trình</h2>
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
                  Tải video
                </a>
                <Link className="btn btn--ghost" to={`/jobs/${job.job_id}`}>
                  Xem chi tiết job
                </Link>
              </div>
            </div>
          )}
        </div>
      )}
    </AppShell>
  );
}
