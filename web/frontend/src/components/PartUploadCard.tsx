// components/PartUploadCard.tsx — ô upload video ĐÃ TỰ NỐI cho 1 PHẦN (part)
// của dự án script-to-video — người dùng tự tạo clip từng screen ở Google
// Flow bằng prompt đã duyệt, TỰ NỐI LẠI thành 1 file, rồi upload lại đây
// (khác v2: không còn 1 ô upload / screen).
//
// Input file thô modeled theo HomePage.tsx (chưa có dropzone component nào
// trong repo) + uploadRequest() convention của api/client.ts.

import { useState } from "react";
import { ApiError, uploadPartVideo, type ScriptToVideoPartSummary } from "../api/client";
import { IconCheck } from "./Icon";
import { confirm } from "../lib/confirm";

export default function PartUploadCard({
  slug,
  part,
  disabled,
  onUploaded,
}: {
  slug: string;
  part: ScriptToVideoPartSummary;
  disabled?: boolean;
  onUploaded: () => void;
}) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const uploaded = part.status !== "awaiting_upload";

  async function handleFile(file: File | null) {
    if (!file) return;
    if (uploaded) {
      const ok = await confirm({
        title: "Thay video đã upload?",
        message: `Phần ${part.index + 1} đã có video — upload file mới sẽ THAY THẾ file cũ (chỉ áp dụng khi phần đang chờ upload).`,
        confirmLabel: "Thay video",
        tone: "danger",
      });
      if (!ok) return;
    }
    setError(null);
    setUploading(true);
    try {
      await uploadPartVideo(slug, part.index, file);
      onUploaded();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload thất bại");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <strong>
          Phần {part.index + 1}
          {part.title ? ` · "${part.title}"` : ""}
        </strong>
        {uploaded && (
          <span className="badge badge--done">
            <IconCheck size={12} /> Đã upload
          </span>
        )}
      </div>
      <span className="page-head__lead" style={{ margin: 0 }}>
        {part.screen_count} screen · tự tạo clip từng screen ở Google Flow rồi nối lại thành 1 file
        trước khi upload.
      </span>

      <div className="field">
        <input
          type="file"
          className="input"
          accept="video/*"
          disabled={disabled || uploading}
          onChange={(e) => {
            const file = e.target.files?.[0] ?? null;
            handleFile(file);
            e.target.value = "";
          }}
        />
        <span className="field__hint">
          {uploading
            ? "Đang tải lên..."
            : uploaded
              ? "Đã upload — chọn file khác để THAY THẾ (vd sửa nhầm file)."
              : "Chọn video đã tự nối cho phần này."}
        </span>
      </div>

      {error && (
        <span className="field__hint" style={{ color: "var(--danger)" }}>
          {error}
        </span>
      )}
    </div>
  );
}
