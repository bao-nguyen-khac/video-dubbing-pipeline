// components/ScriptPromptReviewPanel.tsx — Bảng review kịch bản + prompt tại
// chốt "script_to_video" cho 1 PHẦN (part) của dự án script-to-video.
//
// Sibling của ReviewGatePanel.tsx (KHÔNG tái dùng): payload/schema khác hẳn —
// mỗi screen có 6 trường sửa được thay vì 1 trường "text" như chốt
// transcript/script/outline. Vẫn giữ ĐÚNG flow load/dirty-tracking/
// save/approve/confirm của ReviewGatePanel.

import { useEffect, useMemo, useState } from "react";
import {
  ApiError,
  approveScriptToVideoReview,
  getScriptToVideoReview,
  saveScriptToVideoReview,
  type ScriptToVideoReviewEdit,
  type ScriptToVideoReviewPayload,
} from "../api/client";
import Callout from "../components/Callout";
import { confirm } from "../lib/confirm";

type TextField = "role_label" | "ingredients_used" | "prompt_detail_md" | "visual_prompt" | "vi_voiceover_text";
const TEXT_FIELDS: { key: TextField; label: string; rows: number }[] = [
  { key: "vi_voiceover_text", label: "Lời thoại lồng tiếng (tiếng Việt)", rows: 2 },
  { key: "role_label", label: "Vai trò screen (mô tả ngắn)", rows: 1 },
  { key: "ingredients_used", label: "Ingredients dùng cho screen này", rows: 1 },
  { key: "visual_prompt", label: "Visual Prompt (tiếng Anh, dán thẳng vào Google Flow)", rows: 4 },
  { key: "prompt_detail_md", label: "Ghi chú chi tiết (nối cảnh/nhịp — markdown)", rows: 6 },
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
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<"save" | "approve" | null>(null);

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
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không tải được nội dung chốt");
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

  useEffect(() => {
    if (!dirty) return;
    function warn(e: BeforeUnloadEvent) {
      e.preventDefault();
      e.returnValue = "";
    }
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  function changedText(index: number, field: TextField, value: string) {
    setNotice(null);
    setEdits((prev) => ({ ...prev, [index]: { ...prev[index], [field]: value } }));
  }

  function changedDuration(index: number, value: number) {
    setNotice(null);
    setEdits((prev) => ({ ...prev, [index]: { ...prev[index], duration_seconds: value } }));
  }

  async function handleSave() {
    if (!payload) return;
    setError(null);
    setNotice(null);
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
      setNotice(`Đã lưu ${res.saved_count} screen.`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Lưu thất bại");
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
    setNotice(null);
    setBusy("approve");
    try {
      await approveScriptToVideoReview(slug, partIndex);
      onApproved();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? `${err.message}${err.status === 409 ? " (chờ dự án kia xong rồi bấm lại)" : ""}`
          : "Phê duyệt thất bại",
      );
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

  return (
    <div className="card">
      <div className="card__title">
        <h2>
          Chờ duyệt — Phần {partIndex + 1}{payload.title ? `: "${payload.title}"` : ""}
        </h2>
      </div>

      <p className="page-head__lead">
        Sửa lại lời thoại/prompt từng screen nếu cần rồi phê duyệt. Sau khi phê duyệt, mang
        Visual Prompt (tiếng Anh) đi tạo video ở Google Flow, tự nối các clip lại thành 1 file
        rồi quay lại upload. Không sửa được sau khi đã phê duyệt.
      </p>

      {payload.continuity_notes.length > 0 && (
        <details style={{ marginBottom: "0.75rem" }}>
          <summary>Continuity chain ({payload.continuity_notes.length} mục — chỉ xem)</summary>
          <ul style={{ marginTop: "0.5rem" }}>
            {payload.continuity_notes.map((note, i) => (
              <li key={i} className="page-head__lead">
                {note}
              </li>
            ))}
          </ul>
        </details>
      )}

      {error && (
        <Callout tone="error" title="Không thực hiện được">
          {error}
        </Callout>
      )}
      {notice && <Callout tone="success">{notice}</Callout>}

      <div className="review-list">
        {payload.screens.map((screen) => (
          <div className="card" key={screen.index} style={{ marginBottom: "1rem" }}>
            <div className="card__title">
              <h3 style={{ margin: 0 }}>Screen {screen.index + 1}</h3>
            </div>
            <div className="field" style={{ marginTop: "0.6rem", maxWidth: "10rem" }}>
              <label className="field__label" htmlFor={`s2v-${screen.index}-duration`}>
                Thời lượng (giây)
              </label>
              <input
                id={`s2v-${screen.index}-duration`}
                type="number"
                className="input"
                min={1}
                value={edits[screen.index]?.duration_seconds ?? screen.duration_seconds}
                onChange={(e) => changedDuration(screen.index, Number(e.target.value))}
              />
            </div>
            {TEXT_FIELDS.map((f) => (
              <div className="field" key={f.key} style={{ marginTop: "0.6rem" }}>
                <label className="field__label" htmlFor={`s2v-${screen.index}-${f.key}`}>
                  {f.label}
                </label>
                <textarea
                  id={`s2v-${screen.index}-${f.key}`}
                  className="input"
                  rows={f.rows}
                  style={{ resize: "vertical", fontFamily: f.key === "prompt_detail_md" ? "monospace" : "inherit" }}
                  value={edits[screen.index]?.[f.key] ?? ""}
                  onChange={(e) => changedText(screen.index, f.key, e.target.value)}
                />
              </div>
            ))}
          </div>
        ))}
      </div>

      <div className="result__actions" style={{ marginTop: "1rem" }}>
        <button type="button" className="btn btn--ghost" onClick={handleSave} disabled={busy !== null || !dirty}>
          {busy === "save" ? <span className="btn__spinner" /> : null}
          {busy === "save" ? "Đang lưu..." : dirty ? "Lưu thay đổi" : "Đã lưu"}
        </button>

        <button type="button" className="btn btn--primary" onClick={handleApprove} disabled={busy !== null}>
          {busy === "approve" ? <span className="btn__spinner" /> : null}
          {busy === "approve" ? "Đang phê duyệt..." : "Phê duyệt, chờ upload video"}
        </button>
      </div>

      {dirty && (
        <p className="page-head__lead" style={{ marginTop: "0.5rem" }}>
          Có thay đổi chưa lưu.
        </p>
      )}
    </div>
  );
}
