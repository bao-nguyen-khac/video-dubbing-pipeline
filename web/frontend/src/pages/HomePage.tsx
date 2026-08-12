import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ApiError,
  getJob,
  listVoices,
  outputUrl,
  previewVoice,
  submitJob,
  submitJobUpload,
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
  // Nguồn: dán link (mặc định) hoặc tải file local lên — vd video xuất sẵn
  // từ Google Flow/Veo, ElevenLabs... không có API tải tự động.
  const [sourceMode, setSourceMode] = useState<"url" | "file">("url");
  const [file, setFile] = useState<File | null>(null);
  const [scriptMode, setScriptMode] = useState<ScriptMode>("translate");
  const [dynamicCaptions, setDynamicCaptions] = useState(false);
  // Ghi chú định hướng tự do cho LLM — chỉ có tác dụng ở script_mode="visual"
  const [userPrompt, setUserPrompt] = useState("");
  // 008-supervised-pipeline: mặc định TẮT — job chạy liền mạch như trước (FR-002)
  const [supervised, setSupervised] = useState(false);
  // 009-hardsub-blur-reposition: mặc định TẮT (FR-002)
  const [hardsubBlurEnabled, setHardsubBlurEnabled] = useState(false);
  const [hardsubNoRanges, setHardsubNoRanges] = useState("");
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

  // 009: tắt "Quản lý pipeline" thì làm mờ phụ đề gốc cũng phải tắt theo —
  // không có chốt nào để tự khoanh vùng nếu supervised=false (backend từ chối)
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
      return;
    }

    setSubmitting(true);
    try {
      const selectedVoice = voices.find((v) => voiceKey(v) === selectedVoiceKey);
      // "visual" cũng lồng tiếng (giọng đọc sinh từ kịch bản LLM viết theo
      // hình ảnh) nên cần giọng/khoảng giữ audio gốc như translate/rewrite.
      const hasVoice =
        scriptMode === "translate" || scriptMode === "rewrite" || scriptMode === "visual";
      // Làm mờ phụ đề gốc (hardsub-blur) chỉ áp dụng translate/rewrite kèm
      // phụ đề động — KHÔNG áp dụng "visual" (backend chưa hỗ trợ, pipeline.py
      // chỉ trích khung hình khoanh vùng cho 2 mode này).
      const dubbing = scriptMode === "translate" || scriptMode === "rewrite";
      // 009 FR-009: tính năng chỉ có ý nghĩa khi thực sự có phụ đề hiển thị —
      // phụ đề tự động, hoặc lồng tiếng có bật phụ đề động. Không gửi cờ ở
      // các chế độ khác cho đỡ gây hiểu nhầm (cùng tinh thần FR-008 của 008).
      const hasSubtitleDisplay = scriptMode === "subtitle" || (dubbing && dynamicCaptions);
      const submitArgs = [
        scriptMode,
        hasVoice && dynamicCaptions,
        hasVoice ? selectedVoice?.provider : undefined,
        hasVoice ? selectedVoice?.voice_id : undefined,
        hasVoice && keepRanges.trim() ? keepRanges.trim() : undefined,
        // Chế độ "chỉ tải" không có bước tách lời/sinh kịch bản nên không có
        // chốt nào để dừng — không gửi cờ cho đỡ gây hiểu nhầm (FR-008)
        scriptMode !== "download" && supervised,
        hasSubtitleDisplay && hardsubBlurEnabled,
        hasSubtitleDisplay && hardsubBlurEnabled && hardsubNoRanges.trim()
          ? hardsubNoRanges.trim()
          : undefined,
        // Chỉ áp dụng script_mode="visual" — mode khác không gửi, tránh gây
        // hiểu nhầm là có tác dụng.
        scriptMode === "visual" && userPrompt.trim() ? userPrompt.trim() : undefined,
      ] as const;

      const { job_id } =
        sourceMode === "file"
          ? await submitJobUpload(file as File, ...submitArgs)
          : await submitJob(url, ...submitArgs);

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
  // "visual" cũng lồng tiếng — hiện thẻ "Giọng đọc" + phụ đề động giống
  // translate/rewrite, nhưng KHÔNG tính vào hardsub-blur (giữ isDubbing riêng
  // cho hasSubtitleDisplay bên dưới, khớp đúng điều kiện backend hỗ trợ).
  const hasVoice = isDubbing || scriptMode === "visual";
  const locked = isBusy || submitting;
  // 009 FR-009: chỉ chế độ có phụ đề hiển thị thật sự mới có gì để làm mờ/chèn đè
  const hasSubtitleDisplay = scriptMode === "subtitle" || (isDubbing && dynamicCaptions);

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

  const showAdvancedCard = scriptMode !== "download";

  return (
    <AppShell>
      <div className="page-head">
        <h1>Tạo job mới</h1>
        <p className="page-head__lead">
          Dán link TikTok, Douyin hoặc YouTube — hệ thống sẽ tải video, tách lời, viết
          kịch bản tiếng Việt và lồng tiếng khớp nhịp ngắt nghỉ của bản gốc.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="home-layout">
        {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
        <audio ref={audioRef} hidden />

        <div className={`card${hasVoice ? "" : " home-layout__full"}`}>
          <span className="card__eyebrow">Nguồn</span>

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
                  <span className="mode-option__name">Dán link</span>
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
                  <span className="mode-option__name">Tải file lên</span>
                </span>
              </label>
            </div>
          </div>

          {sourceMode === "url" ? (
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
          ) : (
            <div className="field">
              <label className="field__label" htmlFor="video-file">
                File video
              </label>
              <input
                id="video-file"
                className="input"
                type="file"
                accept="video/*"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                disabled={locked}
              />
              <span className="field__hint">
                Dùng cho video xuất sẵn từ nơi khác (vd Google Flow/Veo) không có URL công khai.
                {file && ` Đã chọn: ${file.name}`}
              </span>
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
                Prompt định hướng (tuỳ chọn)
              </label>
              <textarea
                id="user-prompt"
                className="input"
                rows={3}
                value={userPrompt}
                onChange={(e) => setUserPrompt(e.target.value)}
                placeholder="VD: nhấn mạnh tính năng chống nước, giọng điệu hài hước"
                disabled={locked}
                style={{ resize: "vertical", fontFamily: "inherit" }}
              />
              <span className="field__hint">
                Ghi chú thêm để LLM viết kịch bản đúng hướng bạn muốn thay vì tự đoán.
              </span>
            </div>
          )}
        </div>

        {hasVoice && (
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
          </div>
        )}

        {/* 008: chốt kiểm duyệt chỉ có ở bước tách lời + sinh kịch bản, nên
            chế độ "chỉ tải video" không có gì để gom vào thẻ này (FR-008) */}
        {showAdvancedCard && (
          <div className="card home-layout__full">
            <span className="card__eyebrow">Tuỳ chọn nâng cao</span>
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
                    Dừng lại cho tôi duyệt sau bước tách lời và sau bước sinh kịch bản
                  </span>
                </span>
              </label>
            </div>

            {/* 009: chỉ có ý nghĩa khi thực sự có phụ đề hiển thị (FR-009), và
                BẮT BUỘC kèm Quản lý pipeline — vùng cần mờ do người dùng tự
                khoanh tại chốt lời thoại, không có chốt nào nếu tắt supervised */}
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
                    <span className="switch__name">Làm mờ phụ đề gốc</span>
                    <span className="switch__desc">
                      Che phụ đề tiếng Anh có sẵn trên hình và chèn phụ đề mới đúng chỗ đó —
                      bạn sẽ tự khoanh vùng trên khung hình mẫu ở chốt lời thoại
                    </span>
                  </span>
                </label>
              </div>
            )}
            {hasSubtitleDisplay && !supervised && (
              <p className="field__hint">
                Bật "Quản lý pipeline" ở trên để dùng tính năng làm mờ phụ đề gốc (cần chốt lời
                thoại để bạn tự khoanh vùng).
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
                <span className="field__hint">
                  Các đoạn này sẽ KHÔNG bị làm mờ; để trống = cả video đều có phụ đề gốc.
                </span>
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
          </div>
        )}

        <div className="home-layout__full home-submit">
          <button type="submit" className="btn btn--primary btn--block" disabled={locked}>
            {submitting && <span className="btn__spinner" />}
            {submitting ? "Đang gửi..." : isBusy ? "Đang xử lý job hiện tại" : "Chạy pipeline"}
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
