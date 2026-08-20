// components/ScriptPromptReviewPanel.tsx — Bảng review kịch bản + prompt tại chốt "script_to_video"
// Tích hợp: Screen Timeline Tabs + 2 Cột Visual vs Audio + 1-Click Copy Prompt với Toast feedback.

import { useEffect, useMemo, useState } from "react";
import {
  approveScriptToVideoReview,
  getScriptToVideoReview,
  saveScriptToVideoReview,
  type ScriptToVideoReviewEdit,
  type ScriptToVideoReviewPayload,
} from "../api/client";
import Callout from "../components/Callout";
import { IconCheck, IconCopy, IconFilm, IconSparkles } from "./Icon";
import { confirm } from "../lib/confirm";
import { useToast } from "../context/ToastContext";

type TextField = "role_label" | "ingredients_used" | "prompt_detail_md" | "visual_prompt" | "vi_voiceover_text";
const TEXT_FIELDS: { key: TextField; label: string; rows: number }[] = [
  { key: "vi_voiceover_text", label: "Lời thoại lồng tiếng (tiếng Việt)", rows: 2 },
  { key: "role_label", label: "Vai trò screen (mô tả ngắn)", rows: 1 },
  { key: "ingredients_used", label: "Ingredients dùng cho screen này", rows: 1 },
  { key: "visual_prompt", label: "Visual Prompt (tiếng Anh, dán thẳng vào Google Flow)", rows: 4 },
  { key: "prompt_detail_md", label: "Ghi chú chi tiết (nối cảnh/nhịp — markdown)", rows: 4 },
];

type ScreenEdits = Record<TextField, string> & { duration_seconds: number };

export default function ScriptPromptReviewPanel({
  slug,
  partIndex,
  onApproved,
  onDirtyChange,
}: {
  slug: string;
  partIndex: number;
  onApproved: () => void;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const [payload, setPayload] = useState<ScriptToVideoReviewPayload | null>(null);
  const [edits, setEdits] = useState<Record<number, ScreenEdits>>({});
  const [activeScreenIndex, setActiveScreenIndex] = useState<number>(0);
  const [viewMode, setViewMode] = useState<"tab" | "all">("tab");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"save" | "approve" | null>(null);
  const toast = useToast();

  async function load() {
    setError(null);
    try {
      const data = await getScriptToVideoReview(slug, partIndex);
      setPayload(data);
      setEdits(
        Object.fromEntries(
          data.screens.map((s) => [
            s.index,
            {
              duration_seconds: s.duration_seconds,
              role_label: s.role_label,
              ingredients_used: s.ingredients_used,
              prompt_detail_md: s.prompt_detail_md,
              visual_prompt: s.visual_prompt,
              vi_voiceover_text: s.vi_voiceover_text,
            },
          ]),
        ),
      );
    } catch {
      setError("Không tải được nội dung chốt kịch bản & prompt");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug, partIndex]);

  const dirty = useMemo(() => {
    if (!payload) return false;
    return payload.screens.some((s) => {
      const e = edits[s.index];
      if (!e) return false;
      if (e.duration_seconds !== s.duration_seconds) return true;
      return TEXT_FIELDS.some((f) => e[f.key] !== s[f.key]);
    });
  }, [payload, edits]);

  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);

  function changedText(index: number, field: TextField, value: string) {
    setEdits((prev) => ({ ...prev, [index]: { ...prev[index], [field]: value } }));
  }

  function changedDuration(index: number, value: number) {
    setEdits((prev) => ({ ...prev, [index]: { ...prev[index], duration_seconds: value } }));
  }

  async function copyPrompt(screenIndex: number, text: string) {
    try {
      await navigator.clipboard.writeText(text);
      toast.copy(`Đã sao chép Visual Prompt của Screen ${screenIndex + 1}!`);
    } catch {
      toast.error("Không sao chép được vào clipboard");
    }
  }

  async function handleSave() {
    if (!payload) return;
    setError(null);
    setBusy("save");
    try {
      const changedEdits: ScriptToVideoReviewEdit[] = payload.screens
        .filter((s) => {
          const e = edits[s.index];
          return e.duration_seconds !== s.duration_seconds || TEXT_FIELDS.some((f) => e[f.key] !== s[f.key]);
        })
        .map((s) => {
          const e = edits[s.index];
          const edit: ScriptToVideoReviewEdit = { index: s.index };
          if (e.duration_seconds !== s.duration_seconds) edit.duration_seconds = e.duration_seconds;
          for (const f of TEXT_FIELDS) {
            if (e[f.key] !== s[f.key]) edit[f.key] = e[f.key];
          }
          return edit;
        });

      const res = await saveScriptToVideoReview(slug, partIndex, changedEdits);
      toast.success(`Đã lưu ${res.saved_count} screen thành công!`);
      await load();
    } catch {
      setError("Lưu kịch bản thất bại");
      toast.error("Lưu thất bại!");
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
      await approveScriptToVideoReview(slug, partIndex);
      toast.success("Đã phê duyệt kịch bản! Hãy mang prompt đi tạo clip.");
      onApproved();
    } catch {
      setError("Phê duyệt thất bại");
      toast.error("Phê duyệt thất bại!");
    } finally {
      setBusy(null);
    }
  }

  if (!payload) {
    return (
      <div className="card">
        {error ? (
          <Callout tone="error" title="Không tải được nội dung">{error}</Callout>
        ) : (
          <div className="skeleton skeleton--row" />
        )}
      </div>
    );
  }

  const activeScreen = payload.screens.find((s) => s.index === activeScreenIndex) ?? payload.screens[0];

  return (
    <div className="card s2v-review-panel">
      <div className="review-panel__header">
        <div className="card__title" style={{ margin: 0 }}>
          <h2>Chờ duyệt: Phần {partIndex + 1}{payload.title ? ` · "${payload.title}"` : ""}</h2>
        </div>
        <div className="review-panel__badges">
          <span className="badge badge--waiting">{payload.screens.length} Screens</span>
          {dirty && <span className="badge badge--running">Có thay đổi chưa lưu</span>}
        </div>
      </div>

      <p className="page-head__lead" style={{ marginTop: "0.5rem" }}>
        Kiểm tra Visual Prompt (dán vào Google Flow/Veo) và Lời thoại tiếng Việt. Sau khi phê duyệt, mang prompt đi sinh clip rồi nối lại thành 1 file upload.
      </p>

      {payload.continuity_notes.length > 0 && (
        <details className="continuity-bar" style={{ marginTop: "0.8rem", marginBottom: "0.8rem" }}>
          <summary>
            <IconSparkles size={14} />
            <span>Continuity chain ({payload.continuity_notes.length} ghi chú nhất quán)</span>
          </summary>
          <ul className="continuity-list">
            {payload.continuity_notes.map((note, i) => (
              <li key={i}>{note}</li>
            ))}
          </ul>
        </details>
      )}

      {error && <Callout tone="error" title="Lỗi">{error}</Callout>}

      {/* Screen Timeline Bar & View Mode Toggle */}
      <div className="screen-timeline-header">
        <div className="screen-tabs-bar">
          {payload.screens.map((screen) => {
            const isActive = viewMode === "tab" && activeScreenIndex === screen.index;
            return (
              <button
                key={screen.index}
                type="button"
                className={`screen-tab-btn ${isActive ? "screen-tab-btn--active" : ""}`}
                onClick={() => {
                  setActiveScreenIndex(screen.index);
                  setViewMode("tab");
                }}
              >
                <span className="screen-tab-btn__num">#{screen.index + 1}</span>
                <span className="screen-tab-btn__dur">{edits[screen.index]?.duration_seconds ?? screen.duration_seconds}s</span>
              </button>
            );
          })}
        </div>

        <div className="screen-view-toggle">
          <button
            type="button"
            className={`btn btn--subtle btn--sm ${viewMode === "tab" ? "btn--ghost" : ""}`}
            onClick={() => setViewMode("tab")}
          >
            Từng Screen
          </button>
          <button
            type="button"
            className={`btn btn--subtle btn--sm ${viewMode === "all" ? "btn--ghost" : ""}`}
            onClick={() => setViewMode("all")}
          >
            Tất cả ({payload.screens.length})
          </button>
        </div>
      </div>

      {/* Screen Card Content */}
      <div className="screen-cards-container">
        {(viewMode === "tab" ? [activeScreen] : payload.screens).map((screen) => {
          if (!screen) return null;
          const e = edits[screen.index] ?? {
            duration_seconds: screen.duration_seconds,
            role_label: screen.role_label,
            ingredients_used: screen.ingredients_used,
            prompt_detail_md: screen.prompt_detail_md,
            visual_prompt: screen.visual_prompt,
            vi_voiceover_text: screen.vi_voiceover_text,
          };

          return (
            <div key={screen.index} className="screen-card">
              <div className="screen-card__header">
                <div className="screen-card__title">
                  <IconFilm size={16} />
                  <span>Screen {screen.index + 1}</span>
                  {e.role_label && <span className="badge badge--tag">{e.role_label}</span>}
                </div>

                <div className="screen-card__meta">
                  <label className="screen-card__duration-label">
                    <span>Thời lượng:</span>
                    <input
                      type="number"
                      min={1}
                      className="input mono"
                      style={{ width: "4.5rem", padding: "0.25rem 0.5rem" }}
                      value={e.duration_seconds}
                      onChange={(ev) => changedDuration(screen.index, Number(ev.target.value))}
                    />
                    <span>giây</span>
                  </label>
                </div>
              </div>

              <div className="screen-card__grid">
                {/* Cột trái: Visual Prompt (EN) */}
                <div className="screen-card__col screen-card__col--visual">
                  <div className="field">
                    <div className="field__label-row">
                      <label className="field__label" htmlFor={`vp-${screen.index}`}>
                        🎨 Visual Prompt (Google Flow / Veo)
                      </label>
                      <button
                        type="button"
                        className="btn btn--subtle btn--sm copy-prompt-btn"
                        onClick={() => copyPrompt(screen.index, e.visual_prompt)}
                        title="Sao chép prompt này"
                      >
                        <IconCopy size={13} />
                        <span>Sao chép Prompt</span>
                      </button>
                    </div>
                    <textarea
                      id={`vp-${screen.index}`}
                      className="input mono"
                      rows={4}
                      value={e.visual_prompt}
                      onChange={(ev) => changedText(screen.index, "visual_prompt", ev.target.value)}
                      placeholder="Prompt tiếng Anh cho AI Video..."
                    />
                  </div>

                  <div className="field">
                    <label className="field__label" htmlFor="s2v-role-label">Vai trò cảnh &amp; Ingredients</label>
                    <div style={{ display: "flex", gap: "0.5rem" }}>
                      <input
                        id="s2v-role-label"
                        className="input"
                        placeholder="Vai trò screen (VD: Hook mở đầu)"
                        value={e.role_label}
                        onChange={(ev) => changedText(screen.index, "role_label", ev.target.value)}
                        style={{ flex: 1 }}
                      />
                      <input
                        className="input mono"
                        placeholder="Ingredients used"
                        value={e.ingredients_used}
                        onChange={(ev) => changedText(screen.index, "ingredients_used", ev.target.value)}
                        style={{ flex: 1 }}
                      />
                    </div>
                  </div>
                </div>

                {/* Cột phải: Lời thoại Tiếng Việt (VI) */}
                <div className="screen-card__col screen-card__col--audio">
                  <div className="field">
                    <label className="field__label" htmlFor={`vo-${screen.index}`}>
                      🎙️ Lời thoại lồng tiếng (Tiếng Việt)
                    </label>
                    <textarea
                      id={`vo-${screen.index}`}
                      className="input"
                      rows={3}
                      value={e.vi_voiceover_text}
                      onChange={(ev) => changedText(screen.index, "vi_voiceover_text", ev.target.value)}
                      placeholder="Lời đọc tiếng Việt cho screen này..."
                    />
                  </div>

                  <div className="field">
                    <label className="field__label" htmlFor={`md-${screen.index}`}>
                      📝 Ghi chú chuyển cảnh (Continuity Markdown)
                    </label>
                    <textarea
                      id={`md-${screen.index}`}
                      className="input mono"
                      rows={2}
                      value={e.prompt_detail_md}
                      onChange={(ev) => changedText(screen.index, "prompt_detail_md", ev.target.value)}
                      placeholder="Ghi chú chi tiết..."
                    />
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Action buttons */}
      <div className="review-panel__actions" style={{ marginTop: "1.25rem" }}>
        <button
          type="button"
          className="btn btn--ghost"
          onClick={handleSave}
          disabled={busy !== null || !dirty}
        >
          {busy === "save" ? <span className="btn__spinner" /> : null}
          {busy === "save" ? "Đang lưu..." : dirty ? "💾 Lưu thay đổi" : "✓ Đã lưu"}
        </button>

        <button
          type="button"
          className="btn btn--primary"
          onClick={handleApprove}
          disabled={busy !== null}
        >
          {busy === "approve" ? <span className="btn__spinner" /> : <IconCheck size={16} />}
          {busy === "approve" ? "Đang phê duyệt..." : "Phê duyệt, chuyển sang tạo clip"}
        </button>
      </div>
    </div>
  );
}
