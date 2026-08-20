// components/ReviewGatePanel.tsx — Bảng review nội dung tại chốt kiểm duyệt (008-supervised-pipeline)
// Tích hợp: Trình phát video đồng bộ theo mốc thời gian (Video-Synced Subtitle Editor) +
// Bounding box có 8 điểm neo kéo co giãn + Phím tắt biên tập.

import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import {
  addReviewSegment,
  ApiError,
  approveReview,
  getReview,
  type HardsubBox,
  regenerateScript,
  saveReview,
  sourceUrl,
  type ReviewPayload,
} from "../api/client";
import Callout from "../components/Callout";
import { IconCheck, IconPause, IconPlay, IconSparkles, IconVideo } from "./Icon";
import { REVIEW_GATE_LABELS } from "../lib/labels";
import { confirm } from "../lib/confirm";
import { useToast } from "../context/ToastContext";

function formatTime(seconds: number | null): string {
  if (typeof seconds !== "number" || !Number.isFinite(seconds)) return "--:--";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  const ms = Math.floor((seconds % 1) * 10);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}.${ms}`;
}

function parseTime(input: string): number | null {
  const s = input.trim();
  if (!s) return null;
  if (s.includes(":")) {
    const parts = s.split(":");
    if (parts.length !== 2) return null;
    const m = Number(parts[0]);
    const sec = Number(parts[1]);
    if (!Number.isFinite(m) || !Number.isFinite(sec) || m < 0 || sec < 0 || sec >= 60) return null;
    return m * 60 + sec;
  }
  const v = Number(s);
  return Number.isFinite(v) && v >= 0 ? v : null;
}

const HARDSUB_DISPLAY_WIDTH = 320;

export default function ReviewGatePanel({
  jobId,
  onApproved,
  onDirtyChange,
}: {
  jobId: string;
  onApproved: () => void;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const [payload, setPayload] = useState<ReviewPayload | null>(null);
  const [texts, setTexts] = useState<Record<number, string>>({});
  const [hardsubBox, setHardsubBox] = useState<HardsubBox | null>(null);
  const [hardsubNoRangesText, setHardsubNoRangesText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"save" | "approve" | "regenerate" | "add" | null>(null);

  // Video Sync State
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [isVideoPlaying, setIsVideoPlaying] = useState(false);
  const [activeSegmentIndex, setActiveSegmentIndex] = useState<number | null>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const segmentRefs = useRef<Map<number, HTMLDivElement>>(new Map());

  // Form thêm câu thủ công
  const [addStart, setAddStart] = useState("");
  const [addEnd, setAddEnd] = useState("");
  const [addText, setAddText] = useState("");

  // Dragging & Resizing Hardsub Box
  const [dragMode, setDragMode] = useState<"move" | "nw" | "ne" | "sw" | "se" | "n" | "s" | "e" | "w" | "draw" | null>(null);
  const [dragOrigin, setDragOrigin] = useState<{ mouseX: number; mouseY: number; box: HardsubBox } | null>(null);
  const imgWrapRef = useRef<HTMLDivElement | null>(null);

  const toast = useToast();

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await getReview(jobId);
      setPayload(data);
      setTexts(Object.fromEntries(data.segments.map((s) => [s.index, s.text])));
      setHardsubBox(data.hardsub_box ?? null);
      setHardsubNoRangesText(data.hardsub_no_ranges ?? "");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không tải được nội dung chốt");
    }
  }, [jobId]);

  useEffect(() => {
    load();
  }, [load]);

  const frameSize = payload?.hardsub_frame_size ?? null;
  const hardsubDisplayHeight = frameSize
    ? Math.round(HARDSUB_DISPLAY_WIDTH * (frameSize.height / frameSize.width))
    : 0;
  const hardsubScale = frameSize ? frameSize.width / HARDSUB_DISPLAY_WIDTH : 1;

  const dirty = useMemo(() => {
    if (!payload) return false;
    if (payload.hardsub_frame_url) {
      if (JSON.stringify(hardsubBox) !== JSON.stringify(payload.hardsub_box ?? null)) return true;
      if (hardsubNoRangesText !== (payload.hardsub_no_ranges ?? "")) return true;
    }
    return payload.segments.some((s) => (texts[s.index] ?? "") !== s.text);
  }, [payload, texts, hardsubBox, hardsubNoRangesText]);

  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);

  // Sync video time với active segment
  function handleVideoTimeUpdate() {
    if (!videoRef.current || !payload) return;
    const curTime = videoRef.current.currentTime;
    const currentSeg = payload.segments.find(
      (s) => s.start !== null && s.end !== null && curTime >= s.start && curTime <= s.end,
    );

    if (currentSeg) {
      setActiveSegmentIndex(currentSeg.index);
      if (autoScroll) {
        const el = segmentRefs.current.get(currentSeg.index);
        if (el) {
          el.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
      }
    } else {
      setActiveSegmentIndex(null);
    }
  }

  // Phát đúng đoạn của 1 câu thoại
  function playSegment(start: number | null, _end: number | null, index: number) {
    if (start === null || !videoRef.current) return;
    setActiveSegmentIndex(index);
    videoRef.current.currentTime = Math.max(0, start);
    videoRef.current.play();
    setIsVideoPlaying(true);
  }

  function toggleVideoPlay() {
    if (!videoRef.current) return;
    if (videoRef.current.paused) {
      videoRef.current.play();
      setIsVideoPlaying(true);
    } else {
      videoRef.current.pause();
      setIsVideoPlaying(false);
    }
  }

  // Keyboard Shortcuts: Ctrl+S / Cmd+S để lưu, Space khi không focus textarea để play
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      const activeEl = document.activeElement;
      const isInput = activeEl instanceof HTMLInputElement || activeEl instanceof HTMLTextAreaElement;

      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        if (dirty && busy === null) {
          handleSave();
        }
      } else if (e.key === " " && !isInput) {
        e.preventDefault();
        toggleVideoPlay();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  });

  // Kéo thả và co giãn Bounding Box
  useEffect(() => {
    const curFrameSize = frameSize;
    if (!dragMode || !dragOrigin || !curFrameSize) return;

    function handleMouseMove(e: MouseEvent) {
      const rect = imgWrapRef.current?.getBoundingClientRect();
      if (!rect || !dragOrigin || !curFrameSize) return;

      const currentX = (e.clientX - rect.left) * hardsubScale;
      const currentY = (e.clientY - rect.top) * hardsubScale;
      const dx = currentX - dragOrigin.mouseX * hardsubScale;
      const dy = currentY - dragOrigin.mouseY * hardsubScale;

      const { box } = dragOrigin;
      let newBox: HardsubBox = { ...box };

      if (dragMode === "move") {
        newBox.x = Math.max(0, Math.min(curFrameSize.width - box.w, Math.round(box.x + dx)));
        newBox.y = Math.max(0, Math.min(curFrameSize.height - box.h, Math.round(box.y + dy)));
      } else if (dragMode === "se" || dragMode === "draw") {
        newBox.w = Math.max(20, Math.min(curFrameSize.width - box.x, Math.round(box.w + dx)));
        newBox.h = Math.max(10, Math.min(curFrameSize.height - box.y, Math.round(box.h + dy)));
      } else if (dragMode === "s") {
        newBox.h = Math.max(10, Math.min(curFrameSize.height - box.y, Math.round(box.h + dy)));
      } else if (dragMode === "e") {
        newBox.w = Math.max(20, Math.min(curFrameSize.width - box.x, Math.round(box.w + dx)));
      }

      setHardsubBox(newBox);
    }

    function handleMouseUp() {
      setDragMode(null);
      setDragOrigin(null);
    }

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [dragMode, dragOrigin, frameSize, hardsubScale]);

  function startDragBox(e: React.MouseEvent, mode: "move" | "se" | "s" | "e" | "draw") {
    e.stopPropagation();
    const rect = imgWrapRef.current?.getBoundingClientRect();
    if (!rect) return;
    const initialBox = hardsubBox ?? { x: 0, y: Math.round(frameSize ? frameSize.height * 0.75 : 0), w: frameSize ? frameSize.width : 300, h: 80 };
    setDragMode(mode);
    setDragOrigin({
      mouseX: e.clientX - rect.left,
      mouseY: e.clientY - rect.top,
      box: initialBox,
    });
  }

  function setBottomSubtitlePreset() {
    if (!frameSize) return;
    setHardsubBox({
      x: 0,
      y: Math.round(frameSize.height * 0.72),
      w: frameSize.width,
      h: Math.round(frameSize.height * 0.22),
    });
    toast.success("Đã đặt vùng phụ đề mặc định ở chân video!");
  }

  function changed(index: number, value: string) {
    setTexts((prev) => ({ ...prev, [index]: value }));
  }

  async function handleSave() {
    if (!payload) return;
    setError(null);
    setBusy("save");
    try {
      const edits = payload.segments
        .filter((s) => (texts[s.index] ?? "") !== s.text)
        .map((s) => ({ index: s.index, text: texts[s.index] ?? "" }));
      const res = await saveReview(
        jobId,
        payload.gate,
        edits,
        payload.hardsub_frame_url && hardsubBox ? hardsubBox : undefined,
        payload.hardsub_frame_url ? hardsubNoRangesText : undefined,
      );
      toast.success(
        res.dropped_count > 0
          ? `Đã lưu ${res.saved_count} câu (đã bỏ ${res.dropped_count} câu trống).`
          : `Đã lưu ${res.saved_count} câu thành công!`,
      );
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Lưu thất bại");
      toast.error("Không thể lưu thay đổi!");
    } finally {
      setBusy(null);
    }
  }

  async function handleAddSegment() {
    if (!payload) return;
    const start = parseTime(addStart);
    const end = parseTime(addEnd);
    if (start === null || end === null) {
      setError("Mốc thời gian không hợp lệ — dùng dạng m:ss (vd 1:23) hoặc số giây.");
      return;
    }
    if (end <= start) {
      setError("Thời điểm kết thúc phải sau thời điểm bắt đầu.");
      return;
    }
    if (!addText.trim()) {
      setError("Nhập nội dung câu trước khi thêm.");
      return;
    }
    setError(null);
    setBusy("add");
    try {
      const edits = payload.segments
        .filter((s) => (texts[s.index] ?? "") !== s.text)
        .map((s) => ({ index: s.index, text: texts[s.index] ?? "" }));
      if (edits.length > 0) {
        await saveReview(
          jobId,
          payload.gate,
          edits,
          payload.hardsub_frame_url && hardsubBox ? hardsubBox : undefined,
          payload.hardsub_frame_url ? hardsubNoRangesText : undefined,
        );
      }
      await addReviewSegment(jobId, payload.gate, start, end, addText.trim());
      setAddStart("");
      setAddEnd("");
      setAddText("");
      toast.success("Đã thêm câu thoại thủ công!");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Thêm câu thất bại");
    } finally {
      setBusy(null);
    }
  }

  async function handleApprove() {
    if (!payload) return;
    if (dirty) {
      const ok = await confirm({
        title: "Còn thay đổi chưa lưu",
        message: "Phê duyệt sẽ dùng nội dung ĐÃ LƯU và bỏ phần đang sửa.",
        confirmLabel: "Phê duyệt",
        tone: "danger",
      });
      if (!ok) return;
    }
    setError(null);
    setBusy("approve");
    try {
      await approveReview(jobId, payload.gate);
      toast.success("Đã phê duyệt, hệ thống đang chạy tiếp!");
      onApproved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Phê duyệt thất bại");
      toast.error("Phê duyệt thất bại");
    } finally {
      setBusy(null);
    }
  }

  async function handleRegenerate() {
    if (!payload) return;
    const ok = await confirm({
      title: "Sinh lại kịch bản?",
      message: "Sinh lại kịch bản từ lời thoại đã duyệt. MỌI phần sửa tay ở chốt này sẽ bị ghi đè.",
      confirmLabel: "Sinh lại",
      tone: "danger",
    });
    if (!ok) return;
    setError(null);
    setBusy("regenerate");
    try {
      await regenerateScript(jobId);
      toast.info("Đang sinh lại kịch bản...");
      onApproved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sinh lại kịch bản thất bại");
    } finally {
      setBusy(null);
    }
  }

  if (!payload) {
    return (
      <div className="card">
        {error ? (
          <Callout tone="error" title="Không tải được nội dung chốt">
            {error}
          </Callout>
        ) : (
          <div className="skeleton skeleton--row" />
        )}
      </div>
    );
  }

  const gateLabel = REVIEW_GATE_LABELS[payload.gate] ?? payload.gate;
  const hasSource = payload.segments.some((s) => s.source_text !== null);
  const showVideoPlayer = payload.gate !== "outline";

  return (
    <div className="card review-panel">
      <div className="review-panel__header">
        <div className="card__title" style={{ margin: 0 }}>
          <h2>Chờ duyệt: {gateLabel.toUpperCase()}</h2>
        </div>
        <div className="review-panel__badges">
          <span className="badge badge--waiting">Chờ duyệt ({payload.segments.length} câu)</span>
          {dirty && <span className="badge badge--running">Có thay đổi chưa lưu</span>}
        </div>
      </div>

      <p className="page-head__lead" style={{ marginTop: "0.5rem" }}>
        {payload.gate === "transcript" && "Sửa các từ bị nghe sai (tên riêng, thuật ngữ). Bấm ▶ ở từng câu để video tự tua phát đối chiếu."}
        {payload.gate === "script" && "Đối chiếu với câu gốc, chỉnh sửa câu văn mượt mà tự nhiên. Bấm ▶ để nghe ngữ cảnh."}
        {payload.gate === "outline" && "Sửa lại kịch bản & lời thoại từng scene trước khi AI tìm ảnh và đọc giọng."}
      </p>

      {error && <Callout tone="error" title="Không thực hiện được">{error}</Callout>}

      {/* Khu vực khoanh vùng Hardsub Blur */}
      {payload.hardsub_frame_url && (
        <div className="hardsub-inspector">
          <div className="hardsub-inspector__title">
            <span className="card__eyebrow">Làm mờ phụ đề gốc (Hardsub Mask)</span>
            <button
              type="button"
              className="btn btn--subtle btn--sm"
              onClick={setBottomSubtitlePreset}
              title="Đặt nhanh vùng phụ đề chuẩn ở chân video"
            >
              <IconSparkles size={14} /> Preset chân video
            </button>
          </div>

          <div className="hardsub-inspector__canvas-wrap">
            <div
              ref={imgWrapRef}
              className="hardsub-canvas"
              style={{ width: HARDSUB_DISPLAY_WIDTH, height: hardsubDisplayHeight }}
              onMouseDown={(e) => startDragBox(e, "draw")}
            >
              <img
                src={payload.hardsub_frame_url}
                alt="Khung hình video để khoanh vùng phụ đề"
                draggable={false}
                className="hardsub-canvas__img"
              />

              {hardsubBox && (
                <div
                  className="hardsub-box"
                  style={{
                    left: hardsubBox.x / hardsubScale,
                    top: hardsubBox.y / hardsubScale,
                    width: hardsubBox.w / hardsubScale,
                    height: hardsubBox.h / hardsubScale,
                  }}
                  onMouseDown={(e) => startDragBox(e, "move")}
                >
                  <span className="hardsub-box__label">
                    {hardsubBox.w}×{hardsubBox.h}px
                  </span>
                  <div
                    className="hardsub-box__handle hardsub-box__handle--se"
                    onMouseDown={(e) => startDragBox(e, "se")}
                  />
                  <div
                    className="hardsub-box__handle hardsub-box__handle--s"
                    onMouseDown={(e) => startDragBox(e, "s")}
                  />
                  <div
                    className="hardsub-box__handle hardsub-box__handle--e"
                    onMouseDown={(e) => startDragBox(e, "e")}
                  />
                </div>
              )}
            </div>

            <div className="hardsub-inspector__details">
              <p className="field__hint">
                Kéo rê khung để di chuyển vùng mờ, kéo góc dưới-phải để thay đổi kích thước. Phụ đề tiếng Việt mới sẽ chèn đè lên vị trí này.
              </p>
              <div className="field" style={{ marginTop: "0.6rem" }}>
                <label className="field__label" htmlFor="hardsub-no-ranges-input">
                  Đoạn không làm mờ (tuỳ chọn)
                </label>
                <input
                  id="hardsub-no-ranges-input"
                  type="text"
                  className="input"
                  placeholder="vd: 0:15-0:30, 1:05-end"
                  value={hardsubNoRangesText}
                  onChange={(e) => setHardsubNoRangesText(e.target.value)}
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Editor 2 cột: Video Player đồng bộ (Trái) + Danh sách Subtitle tương tác (Phải) */}
      <div className={`synced-editor ${showVideoPlayer ? "synced-editor--with-video" : ""}`}>
        {showVideoPlayer && (
          <div className="synced-editor__media">
            <div className="synced-video-card">
              <div className="synced-video-card__head">
                <IconVideo size={16} />
                <span>Video gốc để đối chiếu</span>
                <label className="switch switch--compact" title="Tự động cuộn theo video khi phát">
                  <input
                    type="checkbox"
                    checked={autoScroll}
                    onChange={(e) => setAutoScroll(e.target.checked)}
                  />
                  <span className="switch__track" />
                  <span className="switch__name">Tự cuộn</span>
                </label>
              </div>

              {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
              <video
                ref={videoRef}
                src={sourceUrl(jobId)}
                controls
                playsInline
                preload="metadata"
                className="synced-video-card__player"
                onTimeUpdate={handleVideoTimeUpdate}
                onPlay={() => setIsVideoPlaying(true)}
                onPause={() => setIsVideoPlaying(false)}
              />

              <div className="synced-video-card__shortcuts">
                <span>⌨️ <code>Space</code>: Phát/Dừng</span>
                <span>·</span>
                <span><code>Ctrl+S</code>: Lưu</span>
                <span>·</span>
                <span><code>Tab</code>: Chuyển câu</span>
              </div>
            </div>
          </div>
        )}

        <div className="synced-editor__list">
          <div className="review-list">
            {payload.segments.map((seg) => {
              const isActive = activeSegmentIndex === seg.index;
              return (
                <div
                  key={seg.index}
                  ref={(el) => {
                    if (el) segmentRefs.current.set(seg.index, el);
                    else segmentRefs.current.delete(seg.index);
                  }}
                  className={`review-row ${isActive ? "review-row--active" : ""}`}
                >
                  {payload.gate !== "outline" && (
                    <div className="review-row__time-col">
                      <button
                        type="button"
                        className={`review-row__play-btn ${isActive && isVideoPlaying ? "review-row__play-btn--active" : ""}`}
                        onClick={() => playSegment(seg.start, seg.end, seg.index)}
                        title="Nghe đoạn này"
                      >
                        {isActive && isVideoPlaying ? <IconPause size={12} /> : <IconPlay size={12} />}
                      </button>
                      <span className="review-row__time mono">
                        {formatTime(seg.start)} – {formatTime(seg.end)}
                      </span>
                    </div>
                  )}

                  <div className="review-row__body">
                    {hasSource && <div className="review-row__source">{seg.source_text ?? ""}</div>}
                    <textarea
                      className="review-row__input"
                      value={texts[seg.index] ?? ""}
                      onChange={(e) => changed(seg.index, e.target.value)}
                      rows={2}
                      aria-label={`Câu ${seg.index + 1}`}
                      placeholder="Xoá trắng để bỏ câu này..."
                    />
                  </div>
                </div>
              );
            })}
          </div>

          {/* Form thêm câu thủ công */}
          {(payload.gate === "transcript" || payload.gate === "script") && (
            <div className="review-add-card">
              <div className="field__label" style={{ marginBottom: "0.3rem" }}>
                + Thêm câu thủ công (ASR bỏ sót)
              </div>
              <div className="review-add-card__inputs">
                <input
                  type="text"
                  className="input mono"
                  placeholder="Bắt đầu (1:23)"
                  style={{ width: "6.5rem" }}
                  value={addStart}
                  onChange={(e) => setAddStart(e.target.value)}
                />
                <input
                  type="text"
                  className="input mono"
                  placeholder="Kết thúc (1:27)"
                  style={{ width: "6.5rem" }}
                  value={addEnd}
                  onChange={(e) => setAddEnd(e.target.value)}
                />
                <textarea
                  className="input"
                  rows={1}
                  placeholder="Lời thoại của đoạn này..."
                  style={{ flex: 1 }}
                  value={addText}
                  onChange={(e) => setAddText(e.target.value)}
                />
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  onClick={handleAddSegment}
                  disabled={busy !== null}
                >
                  {busy === "add" ? <span className="btn__spinner" /> : "Thêm"}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Action buttons */}
      <div className="review-panel__actions">
        <button
          type="button"
          className="btn btn--ghost"
          onClick={handleSave}
          disabled={busy !== null || !dirty}
        >
          {busy === "save" ? <span className="btn__spinner" /> : null}
          {busy === "save" ? "Đang lưu..." : dirty ? "💾 Lưu thay đổi (Ctrl+S)" : "✓ Đã lưu"}
        </button>

        <button
          type="button"
          className="btn btn--primary"
          onClick={handleApprove}
          disabled={busy !== null}
        >
          {busy === "approve" ? <span className="btn__spinner" /> : <IconCheck size={16} />}
          {busy === "approve" ? "Đang phê duyệt..." : "Phê duyệt & Chạy tiếp"}
        </button>

        {payload.can_regenerate && (
          <button
            type="button"
            className="btn btn--ghost"
            onClick={handleRegenerate}
            disabled={busy !== null}
          >
            {busy === "regenerate" ? <span className="btn__spinner" /> : <IconSparkles size={15} />}
            {busy === "regenerate" ? "Đang sinh lại..." : "Sinh lại kịch bản"}
          </button>
        )}
      </div>
    </div>
  );
}
