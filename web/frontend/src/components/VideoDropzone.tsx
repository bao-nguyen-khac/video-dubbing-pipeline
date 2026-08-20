// components/VideoDropzone.tsx — Khu vực kéo thả & xem trước file video trực quan
import { useState, useRef, useEffect, type DragEvent, type ChangeEvent } from "react";
import { IconClose, IconFilm, IconPlay, IconUpload, IconVideo } from "./Icon";

interface VideoDropzoneProps {
  file: File | null;
  onFileChange: (file: File | null) => void;
  disabled?: boolean;
  hint?: string;
  accept?: string;
}

interface VideoMetadata {
  duration: number;
  width: number;
  height: number;
  thumbnailUrl: string | null;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 Bytes";
  const k = 1024;
  const sizes = ["Bytes", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export default function VideoDropzone({
  file,
  onFileChange,
  disabled = false,
  hint = "Hỗ trợ file MP4, MOV, WebM (tối đa 500MB)",
  accept = "video/*",
}: VideoDropzoneProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const [metadata, setMetadata] = useState<VideoMetadata | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [videoObjectUrl, setVideoObjectUrl] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  // Tạo thumbnail và lấy duration, resolution từ File video
  useEffect(() => {
    if (!file) {
      setMetadata(null);
      setVideoObjectUrl(null);
      return;
    }

    const objUrl = URL.createObjectURL(file);
    setVideoObjectUrl(objUrl);

    const video = document.createElement("video");
    video.preload = "metadata";
    video.src = objUrl;
    video.muted = true;
    video.playsInline = true;

    video.onloadedmetadata = () => {
      const seekTime = Math.min(1.0, video.duration / 4);
      video.currentTime = seekTime;
    };

    video.onseeked = () => {
      try {
        const canvas = document.createElement("canvas");
        canvas.width = Math.min(video.videoWidth, 480);
        canvas.height = Math.round(canvas.width * (video.videoHeight / video.videoWidth));
        const ctx = canvas.getContext("2d");
        if (ctx) {
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
          const thumb = canvas.toDataURL("image/jpeg", 0.8);
          setMetadata({
            duration: video.duration,
            width: video.videoWidth,
            height: video.videoHeight,
            thumbnailUrl: thumb,
          });
        }
      } catch {
        setMetadata({
          duration: video.duration,
          width: video.videoWidth,
          height: video.videoHeight,
          thumbnailUrl: null,
        });
      }
    };

    return () => {
      video.src = "";
      URL.revokeObjectURL(objUrl);
    };
  }, [file]);

  function handleDragOver(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    if (!disabled) setIsDragOver(true);
  }

  function handleDragLeave(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragOver(false);
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragOver(false);
    if (disabled) return;

    const droppedFile = e.dataTransfer.files?.[0];
    if (droppedFile && droppedFile.type.startsWith("video/")) {
      onFileChange(droppedFile);
    }
  }

  function handleInputChange(e: ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0] ?? null;
    onFileChange(selected);
    e.target.value = "";
  }

  function handleRemove() {
    onFileChange(null);
    setMetadata(null);
  }

  return (
    <div className="video-dropzone-wrap">
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        onChange={handleInputChange}
        disabled={disabled}
        hidden
      />

      {!file ? (
        <div
          className={`video-dropzone ${isDragOver ? "video-dropzone--active" : ""} ${disabled ? "video-dropzone--disabled" : ""}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => !disabled && inputRef.current?.click()}
        >
          <div className="video-dropzone__icon">
            <IconUpload size={28} />
          </div>
          <div className="video-dropzone__title">
            <strong>Kéo thả video vào đây</strong> hoặc <span className="video-dropzone__browse">chọn file</span>
          </div>
          <div className="video-dropzone__hint">{hint}</div>
        </div>
      ) : (
        <div className="video-preview-card">
          <div className="video-preview-card__thumb-wrap">
            {metadata?.thumbnailUrl ? (
              <img src={metadata.thumbnailUrl} alt="Thumbnail preview" className="video-preview-card__thumb" />
            ) : (
              <div className="video-preview-card__thumb-placeholder">
                <IconVideo size={28} />
              </div>
            )}
            {videoObjectUrl && (
              <button
                type="button"
                className="video-preview-card__play-btn"
                onClick={() => setPreviewOpen(true)}
                title="Xem thử video"
              >
                <IconPlay size={16} />
              </button>
            )}
          </div>

          <div className="video-preview-card__info">
            <div className="video-preview-card__name" title={file.name}>
              {file.name}
            </div>
            <div className="video-preview-card__meta">
              <span className="badge badge--tag">{formatBytes(file.size)}</span>
              {metadata && (
                <>
                  <span className="badge badge--tag">
                    <IconFilm size={12} /> {formatDuration(metadata.duration)}
                  </span>
                  <span className="badge badge--tag">
                    {metadata.width}×{metadata.height}
                    {metadata.width < metadata.height ? " (9:16 dọc)" : " (16:9 ngang)"}
                  </span>
                </>
              )}
            </div>
          </div>

          <div className="video-preview-card__actions">
            <button
              type="button"
              className="btn btn--subtle"
              onClick={() => inputRef.current?.click()}
              disabled={disabled}
              title="Đổi file khác"
            >
              Đổi file
            </button>
            <button
              type="button"
              className="btn btn--subtle text-danger"
              onClick={handleRemove}
              disabled={disabled}
              title="Xoá file"
            >
              <IconClose size={16} />
            </button>
          </div>
        </div>
      )}

      {/* Video Preview Modal */}
      {previewOpen && videoObjectUrl && (
        <div className="modal-overlay" onClick={() => setPreviewOpen(false)}>
          <div className="modal-content video-player-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-header__title">
                <h2>{file?.name}</h2>
              </div>
              <button
                type="button"
                className="btn btn--subtle modal-close-btn"
                onClick={() => setPreviewOpen(false)}
              >
                <IconClose size={18} />
              </button>
            </div>
            <div className="modal-body" style={{ padding: "0" }}>
              {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
              <video
                src={videoObjectUrl}
                controls
                autoPlay
                style={{ width: "100%", maxHeight: "70vh", display: "block", borderRadius: "0 0 8px 8px" }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
