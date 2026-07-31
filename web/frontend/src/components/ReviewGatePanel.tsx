// components/ReviewGatePanel.tsx — Bảng review nội dung tại chốt kiểm duyệt
// (008-supervised-pipeline).
//
// Dùng CHUNG cho cả 2 chốt: chốt lời thoại (chỉ nội dung) và chốt kịch bản (nội
// dung dịch + câu gốc để đối chiếu). Khác biệt duy nhất do payload quyết định
// (`source_text`, `can_regenerate`), không phải 2 component riêng.
//
// Mốc thời gian chỉ để XEM (FR-016) — người dùng chỉ sửa được chữ.

import { useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  approveReview,
  getReview,
  type HardsubBox,
  regenerateScript,
  saveReview,
  type ReviewPayload,
} from "../api/client";
import Callout from "../components/Callout";
import { REVIEW_GATE_LABELS } from "../lib/labels";

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds)) return "--:--";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

// 009: bề rộng hiển thị cố định cho khung hình mẫu — toạ độ quy đổi ngược về
// độ phân giải gốc qua `scale` (frame_size.width / displayWidth)
const HARDSUB_DISPLAY_WIDTH = 260;

export default function ReviewGatePanel({
  jobId,
  onApproved,
  onDirtyChange,
}: {
  jobId: string;
  /** Gọi sau khi phê duyệt/sinh lại thành công — để trang cha poll lại */
  onApproved: () => void;
  /** Báo trang cha biết có thay đổi chưa lưu (để tạm dừng poll) */
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const [payload, setPayload] = useState<ReviewPayload | null>(null);
  const [texts, setTexts] = useState<Record<number, string>>({});
  // 009: vùng phụ đề gốc người dùng tự khoanh trên khung hình mẫu (toạ độ
  // theo đúng độ phân giải gốc, không phải toạ độ hiển thị)
  const [hardsubBox, setHardsubBox] = useState<HardsubBox | null>(null);
  const [hardsubNoRangesText, setHardsubNoRangesText] = useState("");
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null);
  const imgWrapRef = useRef<HTMLDivElement | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<"save" | "approve" | "regenerate" | null>(null);

  async function load() {
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
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  const frameSize = payload?.hardsub_frame_size ?? null;
  const hardsubDisplayHeight = frameSize
    ? Math.round(HARDSUB_DISPLAY_WIDTH * (frameSize.height / frameSize.width))
    : 0;
  const hardsubScale = frameSize ? frameSize.width / HARDSUB_DISPLAY_WIDTH : 1;

  // Thay đổi chưa lưu = nội dung câu khác server, hoặc vùng/khoảng phụ đề gốc
  // khác giá trị đã lưu
  const dirty = useMemo(() => {
    if (!payload) return false;
    if (payload.hardsub_frame_url) {
      if (JSON.stringify(hardsubBox) !== JSON.stringify(payload.hardsub_box ?? null)) return true;
      if (hardsubNoRangesText !== (payload.hardsub_no_ranges ?? "")) return true;
    }
    return payload.segments.some((s) => (texts[s.index] ?? "") !== s.text);
  }, [payload, texts, hardsubBox, hardsubNoRangesText]);

  // Kéo chuột khoanh vùng trên khung hình mẫu — lắng nghe ở window để không bị
  // "tuột" khi thả chuột ngoài phạm vi ảnh
  useEffect(() => {
    if (!dragStart || !frameSize) return;
    function clamp(v: number, max: number) {
      return Math.max(0, Math.min(max, v));
    }
    function move(e: MouseEvent) {
      const rect = imgWrapRef.current?.getBoundingClientRect();
      if (!rect || !dragStart) return;
      const x = clamp(e.clientX - rect.left, HARDSUB_DISPLAY_WIDTH);
      const y = clamp(e.clientY - rect.top, hardsubDisplayHeight);
      const x0 = Math.min(dragStart.x, x);
      const y0 = Math.min(dragStart.y, y);
      const w = Math.abs(x - dragStart.x);
      const h = Math.abs(y - dragStart.y);
      setNotice(null);
      setHardsubBox({
        x: Math.round(x0 * hardsubScale),
        y: Math.round(y0 * hardsubScale),
        w: Math.round(w * hardsubScale),
        h: Math.round(h * hardsubScale),
      });
    }
    function up() {
      setDragStart(null);
    }
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
  }, [dragStart, frameSize, hardsubDisplayHeight, hardsubScale]);

  function handleHardsubMouseDown(e: React.MouseEvent<HTMLDivElement>) {
    const rect = imgWrapRef.current?.getBoundingClientRect();
    if (!rect) return;
    setDragStart({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  }

  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);

  // Đóng tab/refresh khi còn thay đổi chưa lưu → trình duyệt hỏi lại (FR-015)
  useEffect(() => {
    if (!dirty) return;
    function warn(e: BeforeUnloadEvent) {
      e.preventDefault();
      e.returnValue = "";
    }
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  function changed(index: number, value: string) {
    setNotice(null);
    setTexts((prev) => ({ ...prev, [index]: value }));
  }

  async function handleSave() {
    if (!payload) return;
    setError(null);
    setNotice(null);
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
      setNotice(
        res.dropped_count > 0
          ? `Đã lưu ${res.saved_count} câu, bỏ ${res.dropped_count} câu để trống.`
          : `Đã lưu ${res.saved_count} câu.`,
      );
      // Tải lại để index khớp lại sau khi server bỏ các câu để trống
      await load();
    } catch (err) {
      // Giữ nguyên nội dung đang sửa — không được âm thầm mất phần sửa
      setError(err instanceof ApiError ? err.message : "Lưu thất bại");
    } finally {
      setBusy(null);
    }
  }

  async function handleApprove() {
    if (!payload) return;
    // FR-015: cảnh báo TRƯỚC, không âm thầm duyệt theo nội dung cũ
    if (
      dirty &&
      !window.confirm(
        "Bạn còn thay đổi chưa lưu. Phê duyệt sẽ dùng nội dung ĐÃ LƯU và bỏ " +
          "phần đang sửa. Tiếp tục?",
      )
    ) {
      return;
    }
    setError(null);
    setNotice(null);
    setBusy("approve");
    try {
      await approveReview(jobId, payload.gate);
      onApproved();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? `${err.message}${err.status === 409 ? " (chờ job kia xong rồi bấm lại)" : ""}`
          : "Phê duyệt thất bại",
      );
    } finally {
      setBusy(null);
    }
  }

  async function handleRegenerate() {
    if (!payload) return;
    // FR-020 / US4-2: cảnh báo ghi đè TRƯỚC khi gọi API
    if (
      !window.confirm(
        "Sinh lại kịch bản từ lời thoại đã duyệt. MỌI phần sửa tay ở chốt này " +
          "sẽ bị ghi đè. Tiếp tục?",
      )
    ) {
      return;
    }
    setError(null);
    setNotice(null);
    setBusy("regenerate");
    try {
      await regenerateScript(jobId);
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

  return (
    <div className="card">
      <div className="card__title">
        <h2>Chờ duyệt tại {gateLabel}</h2>
      </div>

      <p className="page-head__lead">
        {payload.gate === "transcript"
          ? "Sửa lại những câu bị nghe sai (tên riêng, thuật ngữ) rồi phê duyệt. Các bước sau sẽ dùng đúng nội dung đã lưu."
          : "Đối chiếu với câu gốc, sửa chỗ dịch chưa mượt rồi phê duyệt. Giọng đọc/phụ đề sẽ theo đúng nội dung đã lưu."}
        {" Xoá trắng một câu = bỏ câu đó. Mốc thời gian chỉ để xem."}
      </p>

      {error && (
        <Callout tone="error" title="Không thực hiện được">
          {error}
        </Callout>
      )}
      {notice && <Callout tone="success">{notice}</Callout>}

      {/* 009: chỉ có mặt khi job bật đồng thời làm mờ phụ đề gốc + Quản lý
          pipeline, VÀ khung hình đại diện đã trích được (FR-012). Vùng cần mờ
          do người dùng tự khoanh bằng tay — không còn OCR tự động (xác nhận
          thật: Tesseract không đọc được phần lớn kiểu chữ có viền/màu nổi bật
          phổ biến trên TikTok/YouTube Shorts). */}
      {payload.hardsub_frame_url && (
        <div className="review-list" style={{ marginBottom: "1rem" }}>
          <p className="page-head__lead" style={{ marginBottom: "0.5rem" }}>
            Kéo chuột trên khung hình để khoanh vùng phụ đề gốc cần làm mờ. Khoanh cao hơn
            dòng chữ đang thấy một chút, để che được cả những cảnh phụ đề gốc xuống 2 dòng.
          </p>
          <div
            ref={imgWrapRef}
            onMouseDown={handleHardsubMouseDown}
            style={{
              position: "relative",
              display: "inline-block",
              cursor: "crosshair",
              userSelect: "none",
            }}
          >
            {/* eslint-disable-next-line jsx-a11y/img-redundant-alt */}
            <img
              src={payload.hardsub_frame_url}
              alt="Khung hình mẫu để khoanh vùng phụ đề gốc"
              draggable={false}
              style={{
                display: "block",
                width: HARDSUB_DISPLAY_WIDTH,
                height: hardsubDisplayHeight,
                border: "1px solid var(--border)",
                borderRadius: "4px",
              }}
            />
            {hardsubBox && (
              <div
                style={{
                  position: "absolute",
                  left: hardsubBox.x / hardsubScale,
                  top: hardsubBox.y / hardsubScale,
                  width: hardsubBox.w / hardsubScale,
                  height: hardsubBox.h / hardsubScale,
                  border: "2px solid var(--accent)",
                  background: "var(--accent-soft)",
                  pointerEvents: "none",
                }}
              />
            )}
          </div>
          <p className="page-head__lead" style={{ marginTop: "0.4rem" }}>
            {hardsubBox
              ? `Vùng đã chọn: ${hardsubBox.w}×${hardsubBox.h}px tại (${hardsubBox.x}, ${hardsubBox.y})`
              : "Chưa chọn vùng nào."}
          </p>
          <div className="field" style={{ marginTop: "0.6rem" }}>
            <label className="field__label" htmlFor="hardsub-no-ranges-review">
              Đoạn không có phụ đề gốc (tuỳ chọn)
            </label>
            <input
              id="hardsub-no-ranges-review"
              type="text"
              className="input"
              placeholder="vd: 0:15-0:30, 1:05-end"
              value={hardsubNoRangesText}
              onChange={(e) => {
                setNotice(null);
                setHardsubNoRangesText(e.target.value);
              }}
            />
            <span className="field__hint">
              Các đoạn này sẽ KHÔNG bị làm mờ; để trống = cả video đều có phụ đề gốc.
            </span>
          </div>
        </div>
      )}

      {payload.segments.length === 0 ? (
        <Callout tone="warning" title="Không có câu nào">
          Bước tách lời không tìm thấy câu nào (video có thể không có lời thoại).
          Phê duyệt để chạy tiếp, hoặc xoá job này ở trang lịch sử.
        </Callout>
      ) : (
        <div className="review-list">
          {payload.segments.map((seg) => (
            <div className="review-row" key={seg.index}>
              <div className="review-row__time mono" title="Mốc thời gian (chỉ để xem)">
                {formatTime(seg.start)} – {formatTime(seg.end)}
              </div>
              <div className="review-row__body">
                {hasSource && (
                  <div className="review-row__source">{seg.source_text ?? ""}</div>
                )}
                <textarea
                  className="review-row__input"
                  value={texts[seg.index] ?? ""}
                  onChange={(e) => changed(seg.index, e.target.value)}
                  rows={2}
                  aria-label={`Nội dung câu ${seg.index + 1}`}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="result__actions" style={{ marginTop: "1rem" }}>
        <button
          type="button"
          className="btn btn--ghost"
          onClick={handleSave}
          disabled={busy !== null || !dirty}
        >
          {busy === "save" ? <span className="btn__spinner" /> : null}
          {busy === "save" ? "Đang lưu..." : dirty ? "Lưu thay đổi" : "Đã lưu"}
        </button>

        <button
          type="button"
          className="btn btn--primary"
          onClick={handleApprove}
          disabled={busy !== null}
        >
          {busy === "approve" ? <span className="btn__spinner" /> : null}
          {busy === "approve" ? "Đang phê duyệt..." : "Phê duyệt, chạy tiếp"}
        </button>

        {payload.can_regenerate && (
          <button
            type="button"
            className="btn btn--ghost"
            onClick={handleRegenerate}
            disabled={busy !== null}
          >
            {busy === "regenerate" ? <span className="btn__spinner" /> : null}
            {busy === "regenerate" ? "Đang sinh lại..." : "Sinh lại kịch bản"}
          </button>
        )}
      </div>

      {dirty && (
        <p className="page-head__lead" style={{ marginTop: "0.5rem" }}>
          Có thay đổi chưa lưu.
        </p>
      )}
    </div>
  );
}
