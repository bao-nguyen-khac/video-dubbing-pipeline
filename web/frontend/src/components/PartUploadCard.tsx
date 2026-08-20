// components/PartUploadCard.tsx — Ô upload video cho 1 phần của script-to-video với VideoDropzone
import { useState } from "react";
import { uploadPartVideo, type ScriptToVideoPartSummary } from "../api/client";
import { IconCheck } from "./Icon";
import { confirm } from "../lib/confirm";
import VideoDropzone from "./VideoDropzone";
import { useToast } from "../context/ToastContext";

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
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const uploaded = part.status !== "awaiting_upload";
  const toast = useToast();

  async function handleUpload(file: File | null) {
    if (!file) return;
    if (uploaded) {
      const ok = await confirm({
        title: "Thay video đã upload?",
        message: `Phần ${part.index + 1} đã có video — upload file mới sẽ THAY THẾ file cũ.`,
        confirmLabel: "Thay video",
        tone: "danger",
      });
      if (!ok) return;
    }

    setUploading(true);
    try {
      await uploadPartVideo(slug, part.index, file);
      toast.success(`Đã tải lên video cho Phần ${part.index + 1}!`);
      setSelectedFile(null);
      onUploaded();
    } catch {
      toast.error("Tải lên video thất bại!");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
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
        {part.screen_count} screen · Tự tạo clip từng screen ở Google Flow/Veo rồi nối lại thành 1 file trước khi upload.
      </span>

      <VideoDropzone
        file={selectedFile}
        onFileChange={(f) => {
          setSelectedFile(f);
          if (f) handleUpload(f);
        }}
        disabled={disabled || uploading}
        hint={
          uploading
            ? "Đang tải video lên server..."
            : uploaded
              ? "Kéo thả file mới để thay thế video hiện tại"
              : "Kéo thả file video đã nối cho phần này"
        }
      />
    </div>
  );
}
